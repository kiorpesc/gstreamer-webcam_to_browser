gstreamer-webcam_to_browser
===========================

Realtime webcam stream to a browser window using Python, Tornado, WebSockets, and Gstreamer

Dependencies:
=============

- Python
- Tornado (pip install tornado)
- GStreamer 1.0+
- GStreamer Python bindings

To run, simply enter:

    python cam_server.py

in your Linux terminal.

Right now, it is not possible to stop the server without sending a SIGTERM.  I am attempting to fix this.
