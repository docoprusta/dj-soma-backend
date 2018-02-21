import subprocess
import psutil
import os
import signal
import shlex
import queue

import threading
import time

from flask_socketio import emit
from mpv import MPV
from flask import Flask
from flask_socketio import SocketIO
from flask import request
from flask import json
from flask_cors import CORS
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = '0271521ae2e214eb55e6d34d48f1d63754ecf00f7137777a43306fac9da070d5'
socketio = SocketIO(app, async_mode='threading')

is_first = True

playlist = queue.Queue()
video_ids = queue.Queue()

time_pos = 0
duration = 0
prev_time = time.time()

player = MPV('no-video', ytdl=True)


@player.property_observer('time-pos')
def print_time_pos(_name, _value):
    global time_pos
    global duration
    global prev_time
    time_pos = player.osd.time_pos
    duration = player.osd.duration

    if (time.time() - prev_time) >= 1 and time_pos is not None and duration is not None:
        time_pos_in_sec = sum(x * int(t) for x, t in zip([3600, 60, 1], time_pos.split(":"))) 
        duration_in_sec = sum(x * int(t) for x, t in zip([3600, 60, 1], duration.split(":"))) 
        socketio.emit('message', int((time_pos_in_sec/duration_in_sec)*100), broadcast=True)
        prev_time = time.time()

    if time_pos == duration and time_pos != 0 and duration != 0:
        playlist.get()
        video_id = video_ids.get()
        player.play('http://www.youtube.com/watch?v={}'.format(video_id))

def start_process(video_id):
    player.play('http://www.youtube.com/watch?v={}'.format(video_id))
    send_playtime_in_every_second()


@app.route('/playlist', methods=['GET'])
def get_playlist():
    return json.dumps(list(playlist.queue))


def send_playtime_in_every_second():
    print(time_pos, duration)
    while True:
        print(time_pos, duration)
        if time_pos == duration and time_pos != 0 and duration != 0:
            break
        print(is_first)
        socketio.emit('message', time_pos, broadcast=True)
        socketio.sleep(1)


@app.route('/song', methods=['POST'])
def post_song():
    
    global is_first
    posted_dict = request.json
    playlist.put(posted_dict)
    video_id = posted_dict.get('youtubeId')
    video_ids.put(video_id)
    if is_first:
        video_id = video_ids.get()
        player.play('http://www.youtube.com/watch?v={}'.format(video_id))
        is_first = False
    return 'Hello, World!'


if __name__ == "__main__":
    try:
        socketio.run(app, '0.0.0.0')
    except:
        pass
