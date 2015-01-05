import tornado
import tornado.websocket
import tornado.httpserver
import threading
import time
import sys, os

# Gstreamer 0.10 imports
import pygst
pygst.require("0.10")
import gst
import pygtk
import gtk

import json

sockets = []

frame_grabber = None

def send_all(msg):
    for ws in sockets:
        ws.write_message(msg, True)

class WSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        global sockets
        sockets.append(self)
        print 'new connection'

    def on_message(self, message):
        print 'message received %s' % message

    def on_close(self):
        global sockets
        sockets.remove(self)
        print 'connection closed'

    def check_origin(self, origin):
        return True

class MainPipeline():
    def __init__(self):
        self.pipeline = None
        self.videosrc = None
        self.videoenc = None
        self.videosink = None
        self.current_buffer = None

    def pull_frame(self, sink):
        # second param appears to be the sink itself
        sample = self.videosink.emit("pull-sample")
        if sample is not None:
            self.current_buffer = sample.get_buffer()
            current_data = self.current_buffer.extract_dup(0, self.current_buffer.get_size())
            send_all(current_data)
        return False

    def gst_thread(self):
        print("Initializing GST Elements")
        #Gst.init(None)

        self.pipeline = gst.Pipeline("framegrabber")

        # instantiate the camera source
        self.videosrc = gst.element_factory_make("v4l2src", "vid-src")
        self.videosrc.set_property("device", "/dev/video0")

        # instantiate the jpeg encoder
        self.videoenc = gst.element_factory_make("jpegenc", "vid-enc")

        # instantiate the appsink - allows access to raw frame data
        self.videosink = gst.element_factory_make("appsink", "vid-sink")
        self.videosink.set_property("max-buffers", 3)
        self.videosink.set_property("drop", True)
        self.videosink.set_property("emit-signals", True)
        self.videosink.set_property("sync", False)
        self.videosink.connect("new-sample", self.pull_frame)

        # add all the new elements to the pipeline
        print("Adding Elements to Pipeline")
        self.pipeline.add(self.videosrc)
        self.pipeline.add(self.videoenc)
        self.pipeline.add(self.videosink)

        # link the elements in order, adding a filter to ensure correct size and framerate
        print("Linking GST Elements")
        self.videosrc.link_filtered(self.videoenc,
            gst.caps_from_string('video/x-raw,width=640,height=480,format=YUY2,framerate=30/1'))
        self.videoenc.link(self.videosink)

        # start the video
        print("Setting Pipeline State")
        self.pipeline.set_state(gst.STATE_PAUSED)
        self.pipeline.set_state(gst.STATE_PLAYING)

def start_server(app):
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8888)
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":

    application = tornado.web.Application([
        (r'/ws', WSHandler),
    ])

    print("Starting GST thread...")

    pipeline = MainPipeline()
    gst_thread = threading.Thread(target=pipeline.gst_thread)
    gst_thread.start()

    time.sleep(1)

    print("starting frame grabber thread")

    print("Starting server thread")
    server_thread = threading.Thread(target=start_server, args=[application])
    server_thread.start()

    try:
        gst_thread.join()
        server_thread.join()
    except:
        print("exiting")
        exit(0)
