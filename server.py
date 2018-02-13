import subprocess
import psutil
import os
import signal
import shlex
import queue
import threading
import time

from flask import Flask
from flask import request
from flask_cors import CORS
app = Flask(__name__)
CORS(app)

is_first = True
process = None


if os.name == 'posix':
    mpv_path = 'mpv'
elif os.name == 'nt':
    mpv_path = 'windows\\mpv.exe'

video_ids = queue.Queue()

def play_video():
    while True:
        try:
            os.wait()
        except:
            pass

        if not video_ids.empty() and process is not None and not psutil.pid_exists(process.pid):
            threading.Thread(target=start_process, args=[video_ids.get(timeout=1)]).start()
        time.sleep(.5)

def start_process(video_id):
    global process
    splitted_command = shlex.split('{} --no-video https://www.youtube.com/watch?v={}'.format(mpv_path, video_id))
    print(splitted_command)
    process = subprocess.Popen(splitted_command)
    # process.stdout.read()

@app.route('/')
def hello_world():
    global is_first
    video_id = request.args.get('video')
    if is_first:
        start_process(video_id)
        threading.Thread(target=play_video).start()
    else:
        video_ids.put(video_id, timeout=1)
    
    # if process is not None and not is_first and psutil.pid_exists(process.pid):
        # os.kill(process.pid, signal.SIGTERM)


    is_first = False

    return 'Hello, World!'


if __name__ == "__main__":
    app.run('0.0.0.0')
