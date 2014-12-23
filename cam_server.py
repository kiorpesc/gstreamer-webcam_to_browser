import tornado
import tornado.websocket
import tornado.httpserver
import threading
import time
import base64
import sys, os
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, Gtk
import json

sockets = []

frame_grabber = None

def send_all(msg):
    #print(type(msg))
    for ws in sockets:
        ws.write_message(msg, True)

class WSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        global sockets
        sockets.append(self)
        print 'new connection'
        self.write_message("Hello World")

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
        #print("Pulling new sample")
        sample = self.videosink.emit("pull-sample")
        if sample is not None:
            #print(sample)
            #print("getting buffer from sample")
            self.current_buffer = sample.get_buffer()
            #print("getting data from buffer")
            current_data = self.current_buffer.extract_dup(0, self.current_buffer.get_size())
            #print("sending data over all sockets")
            send_all(current_data)
        return False

    def get_buffer(self):
        return self.current_buffer

    def gst_thread(self):
        print("Initializing GST Elements")
        Gst.init(None)
        self.pipeline = Gst.Pipeline.new("framegrabber")
        self.videosrc = Gst.ElementFactory.make("v4l2src", "vid-src")
        self.videosrc.set_property("device", "/dev/video0")
        self.videoenc = Gst.ElementFactory.make("jpegenc", "vid-enc")
        self.videosink = Gst.ElementFactory.make("appsink", "vid-sink")
        self.videosink.set_property("max-buffers", 3)
        self.videosink.set_property("emit-signals", True)
        self.videosink.set_property("sync", False)
        self.videosink.connect("new-sample", self.pull_frame)

        print("Adding Elements to Pipeline")
        self.pipeline.add(self.videosrc)
        self.pipeline.add(self.videoenc)
        self.pipeline.add(self.videosink)

        print("Linking GST Elements")
        self.videosrc.link(self.videoenc)
        self.videoenc.link(self.videosink)

        print("Setting Pipeline State")
        self.pipeline.set_state(Gst.State.PAUSED)
        self.pipeline.set_state(Gst.State.PLAYING)

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
