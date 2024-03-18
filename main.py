import cv2, queue, threading, time
from PIL import Image
from io import BytesIO
from flask import Flask, Response, app
from ntcore import NetworkTableInstance

app = Flask(__name__)

STREAM1 = "http://localhost:9000/"
STREAM2 = "http://localhost:9001/"

selected_stream = NetworkTableInstance.getDefault().getTable("MJPEGSwitcher").getStringTopic("SelectedDriverCam").subscribe(STREAM1)

# Non-brittle bufferless VideoCapture
class VideoCapture:
    def __init__(self, name):
        self.q = queue.Queue()

        self._name = name
        self.cap = cv2.VideoCapture(name)
        
        self.stop_lock = threading.Lock()
        self.stopped_lock = threading.Lock()
        self.stopped_lock.acquire()

        t = threading.Thread(target=self._reader)
        t.daemon = True
        t.start()

    # read frames as soon as they are available, keeping only most recent one
    def _reader(self):
        while not self.stop_lock.locked():
            ret, frame = self.cap.read()
            if not ret:
                break
            if not self.q.empty():
                try:
                    self.q.get_nowait()   # discard previous (unprocessed) frame
                except queue.Empty:
                    pass
            self.q.put(frame)
        self.cap.release()
        self.stopped_lock.release()

    def stop(self):
        self.stop_lock.acquire()
        self.stopped_lock.acquire()

    def read(self):
        try:
            return (True, self.q.get(timeout=1))
        except queue.Empty:
            return (False, None)

    def name(self):
        return self._name

def cam_iter():
    cap = VideoCapture(STREAM1)
    exported = BytesIO()
    last_selected = selected_stream.get()
    while True:
        cur_selected = selected_stream.get()
        print(cur_selected)
        if last_selected != cur_selected:
            cap.stop()
            cap = VideoCapture(cur_selected)
            last_selected = cur_selected
        ret, img_arr = cap.read()
        while not ret:
            time.sleep(0.5)
            cap.stop()
            cap = VideoCapture(STREAM1)
            ret, img_arr = cap.read()
        img = Image.fromarray(img_arr)
        exported.seek(0)
        img.save(exported, format="jpeg")
        cnt = img.tell()
        exported.seek(0)
        yield (b"--ffmpegasdfkl\r\nContent-Type: image/jpeg\r\n\r\n" + exported.read() + b"\r\n")

@app.route("/")
def cam_feed():
    return Response(cam_iter(), mimetype="multipart/x-mixed-replace; boundary=ffmpegasdfkl")

if __name__ == "__main__":
    nt_inst = NetworkTableInstance.getDefault()
    nt_inst.startClient4("MJPEG Switcher")
    nt_inst.setServer("localhost")
    nt_inst.startDSClient()
    app.run()
