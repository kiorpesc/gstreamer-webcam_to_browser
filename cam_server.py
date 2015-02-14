import tornado
import tornado.websocket
import tornado.httpserver
import threading
import time
import base64
import sys, os
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
import json
import signal

cam_sockets = []
key_sockets = []

frame_grabber = None

#import Adafruit_BBIO.GPIO as GPIO
#import Adafruit_BBIO.PWM as PWM

DEAD_ZONE = 10
FORWARD_SPEED = 75.0
TURN_SPEED = 50.0
FORWARD = 1
BACKWARD = -1
LEFT = 0
RIGHT = 1

"""
Output pins for the motor driver board:
"""
motor_pwms = ["P9_14", "P9_21"]
motor_ins = [["P9_11", "P9_12"], ["P9_25", "P9_26"]]
STBY = "P9_27"

def init_motors():
    """
    Initialize the pins needed for the motor driver.
    """
    """global motor_ins
    global motor_pwms
    # initialize GPIO pins
    GPIO.setup(STBY, GPIO.OUT)
    GPIO.output(STBY, GPIO.HIGH)
    for motor in motor_ins:
        for pin in motor:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
    # initialize PWM pins
    # first need bogus start due to unknown bug in library
    PWM.start("P9_14", 0.0)
    PWM.stop("P9_14")
    # now start the desired PWMs
    for pwm_pin in motor_pwms:
        PWM.start(pwm_pin, 0.0)"""

def set_motor(motor, direction, value):
    """
    Set an individual motor's direction and speed
    """
    """if direction == BACKWARD: # For now, assume CW is forwards
        # forwards: in1 LOW, in2 HIGH
        GPIO.output(motor_ins[motor][0], GPIO.LOW)
        GPIO.output(motor_ins[motor][1], GPIO.HIGH)
    elif direction == FORWARD:
        GPIO.output(motor_ins[motor][0], GPIO.HIGH)
        GPIO.output(motor_ins[motor][1], GPIO.LOW)
    else:
        # there has been an error, stop motors
        GPIO.output(STBY, GPIO.LOW)
    PWM.set_duty_cycle(motor_pwms[motor], value)"""


def parse_command_vector(s):
    """left_speed = 0.0
    left_dir = FORWARD
    right_speed = 0.0
    right_dir = FORWARD
    if s[1] == 1:
        print('UP')
        left_speed = FORWARD_SPEED
        right_speed = FORWARD_SPEED
    if s[2] == 1:
        print('DOWN')
        left_speed = FORWARD_SPEED
        right_speed = FORWARD_SPEED
        left_dir = BACKWARD
        right_dir = BACKWARD
    if s[3] == 1:
        print('LEFT')
        left_speed = FORWARD_SPEED
        right_speed = FORWARD_SPEED
        left_dir = BACKWARD
        right_dir = FORWARD
    if s[4] == 1:
        print('RIGHT')
        left_dir = FORWARD
        left_speed = FORWARD_SPEED
        right_speed = FORWARD_SPEED
        right_dir = BACKWARD

    set_motor(LEFT, left_dir, left_speed)
    set_motor(RIGHT, right_dir, right_speed)"""



def send_all(msg):
    for ws in cam_sockets:
        ws.write_message(msg, True)

class CamWSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        global cam_sockets
        cam_sockets.append(self)
        print('new camera connection')

    def on_message(self, message):
        print (message)

    def on_close(self):
        global cam_sockets
        cam_sockets.remove(self)
        print('camera connection closed')

    def check_origin(self, origin):
        return True

class KeyWSHandler(tornado.websocket.WebSocketHandler):
    def open(self):
        global key_sockets
        key_sockets.append(self)
        print('new command connection')

    def on_message(self, message):
        print (message)
        parse_command_vector(json.loads(message))

    def on_close(self):
        global key_sockets
        key_sockets.remove(self)
        print('command connection closed')

    def check_origin(self, origin):
        return True

class HTTPServer(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class MainPipeline():
    def __init__(self):
        self.pipeline = None
        self.videosrc = None
        self.videoparse = None
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
        Gst.init(None)

        self.pipeline = Gst.Pipeline.new("framegrabber")

        # instantiate the camera source
        self.videosrc = Gst.ElementFactory.make("v4l2src", "vid-src")
        self.videosrc.set_property("device", "/dev/video0")

        # instantiate the jpeg parser to ensure whole frames
        self.videoparse = Gst.ElementFactory.make("jpegparse", "vid-parse")

        # instantiate the appsink - allows access to raw frame data
        self.videosink = Gst.ElementFactory.make("appsink", "vid-sink")
        self.videosink.set_property("max-buffers", 3)
        self.videosink.set_property("drop", True)
        self.videosink.set_property("emit-signals", True)
        self.videosink.set_property("sync", False)
        self.videosink.connect("new-sample", self.pull_frame)

        # add all the new elements to the pipeline
        print("Adding Elements to Pipeline")
        self.pipeline.add(self.videosrc)
        self.pipeline.add(self.videoparse)
        self.pipeline.add(self.videosink)

        # link the elements in order, adding a filter to ensure correct size and framerate
        print("Linking GST Elements")
        self.videosrc.link_filtered(self.videoparse,
            Gst.caps_from_string('image/jpeg,width=640,height=480,framerate=30/1'))
        self.videoparse.link(self.videosink)

        # start the video
        print("Setting Pipeline State")
        self.pipeline.set_state(Gst.State.PAUSED)
        self.pipeline.set_state(Gst.State.PLAYING)

def start_server(cam_app, key_app):
    cam_server = tornado.httpserver.HTTPServer(cam_app)
    key_server = tornado.httpserver.HTTPServer(key_app)
    cam_server.listen(8888)
    key_server.listen(8889)
    tornado.ioloop.IOLoop.instance().start()

def signal_handler(signum, frame):
    print("Interrupt caught")
    tornado.ioloop.IOLoop.instance().stop()
    server_thread.stop()

if __name__ == "__main__":

    init_motors()

    cam_app = tornado.web.Application([
        (r'/ws', CamWSHandler),
        (r'/', HTTPServer),
    ])

    key_app = tornado.web.Application([
        (r'/ws', KeyWSHandler)
    ])


    print("Starting GST thread...")

    pipeline = MainPipeline()
    gst_thread = threading.Thread(target=pipeline.gst_thread)
    gst_thread.start()

    time.sleep(1)

    print("starting frame grabber thread")

    print("Starting server thread")
    server_thread = threading.Thread(target=start_server, args=[cam_app, key_app])
    server_thread.start()

    # or you can use a custom handler,
    # in which case recv will fail with EINTR
    print("registering sigint")
    signal.signal(signal.SIGINT, signal_handler)

    try:
        print("gst_thread_join")
        gst_thread.join()
        print("Pausing so that thread doesn't exit")
        while(1):
            time.sleep(1)

    except:
        print("exiting")
        exit(0)
