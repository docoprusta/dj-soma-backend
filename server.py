import subprocess
import os
import signal
import shlex
import queue
import threading
import time
import binascii

from flask_socketio import emit
from mpv import MPV
from flask import Flask
from flask import Session
from flask_socketio import SocketIO
from flask_socketio import join_room
from flask import request
from flask import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = binascii.hexlify(os.urandom(24))
socketio = SocketIO(app, async_mode='threading')

is_first = True

playlist = queue.Queue()
video_ids = queue.Queue()

time_pos = 0
duration = 0
prev_time = time.time()

if os.name == 'nt':
    player = MPV(ytdl=True)
else:
    player = MPV('no-video', ytdl=True)

currently_playing_youtube_id = ''

ips_with_times = {}

@player.property_observer('time-pos')
def print_time_pos(_name, _value):
    global time_pos
    global duration
    global prev_time
    global is_first
    global currently_playing_youtube_id

    time_pos = player.osd.time_pos
    duration = player.osd.duration

    if (time.time() - prev_time) >= 1 and time_pos is not None and duration is not None:
        time_pos_in_sec = sum(x * int(t) for x, t in zip([3600, 60, 1], time_pos.split(":"))) 
        duration_in_sec = sum(x * int(t) for x, t in zip([3600, 60, 1], duration.split(":"))) 
        socketio.emit('timePosChanged', time_pos_in_sec/duration_in_sec*100, broadcast=True)
        prev_time = time.time()

        if time_pos_in_sec == duration_in_sec - 2 and time_pos_in_sec != 0 and duration_in_sec != 0:
            currently_playing_youtube_id = ''
            socketio.emit('songEnded', 'asd', broadcast=True)
            playlist.get()
            if playlist.qsize() > 0:
                video_id = video_ids.get()
                player.playlist_next()
                time.sleep(5)
            else:
                is_first = True


@app.route('/playlist', methods=['GET'])
def get_playlist():
    return json.dumps(list(playlist.queue))


def increase_time():
    global ips_with_times
    while True:
        for key, value in ips_with_times.items():
            ips_with_times[key] +=1
            socketio.emit('remainingTimeChanged', 60 - ips_with_times[key], room=key)
        time.sleep(1)


@socketio.on('joined')
def joined():
    print(request.remote_addr not in ips_with_times)
    if request.remote_addr not in ips_with_times:
        ips_with_times[request.remote_addr] = 61
    print('joined ' + request.remote_addr)
    join_room(request.remote_addr)


@app.route('/volume', methods=['PUT'])
def set_volume():
    putted_dict = request.json
    value = putted_dict.get('value', player.osd.volume)
    if 0 < value < 100: 
        player._set_property('ao-volume', value)
    return "OK"

@app.route('/song', methods=['POST'])
def post_song():
    global currently_playing_youtube_id
    global is_first
    global ips_with_times

    posted_dict = request.json
    if posted_dict.get('youtubeId') in list(video_ids.queue) or \
         currently_playing_youtube_id == posted_dict.get('youtubeId'):
        return 'Video is already added', 409
    
    if ips_with_times.get(request.remote_addr, 61) < 60:
        return 'asd', 429
    
    playlist.put(posted_dict)
    video_id = posted_dict.get('youtubeId')
    player.playlist_append('http://www.youtube.com/watch?v={}'.format(video_id))
    video_ids.put(video_id)
    socketio.emit('songAdded', json.dumps(posted_dict), json=True, broadcast=True)
    if is_first or playlist.qsize() == 0:
        video_id = video_ids.get()
        currently_playing_youtube_id = video_id
        player.play('http://www.youtube.com/watch?v={}'.format(video_id))
        is_first = False

    ips_with_times[request.remote_addr] = 0

    return 'Ok'


if __name__ == "__main__":
    try:
        threading.Thread(target=increase_time).start()
        socketio.run(app, '0.0.0.0')
    except:
        pass
