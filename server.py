import subprocess
import os
import signal
import shlex
import queue
import threading
import random
import time
import binascii
import isodate
import requests
import re
import eventlet
eventlet.monkey_patch(os=False, thread=False)

from flask_socketio import emit
from mpv import MPV
from flask import Flask
from flask import Session
from flask_socketio import SocketIO
from flask_socketio import join_room
from flask import request
from flask import json
from flask import jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = binascii.hexlify(os.urandom(24))
socketio = SocketIO(app, async_mode='eventlet')

youtube_api_key = 'AIzaSyDnXC_k6YB-A8H4GC3swaqO7lzFXPQGjTQ'

is_first = True
autoplay = False

playlist = queue.Queue()
video_ids = queue.Queue()

waiting_time = 60

autoplay_history = []

time_pos = 0
duration = 0
prev_time = time.time()

if os.name == 'nt':
    player = MPV(ytdl=True, volume=50)
else:
    player = MPV('no-video', ytdl=True, volume=50)

currently_playing_youtube_id = ''

ips_with_times = {}

buff = 0

def song_ended():
    socketio.emit('songEnded', 'asd', broadcast=True)


def song_added(auto_video_json):
    socketio.emit('songAdded', json.dumps(auto_video_json), json=True, broadcast=True)

@player.property_observer('time-pos')
def print_time_pos(_name, _value):
    global time_pos
    global duration
    global prev_time
    global buff
    global is_first
    global currently_playing_youtube_id

    time_pos = player.osd.time_pos
    duration = player.osd.duration

    if (time.time() - prev_time) >= 1 and time_pos is not None and duration is not None:
        time_pos_in_sec = sum(x * int(t) for x, t in zip([3600, 60, 1], time_pos.split(":"))) 
        duration_in_sec = sum(x * int(t) for x, t in zip([3600, 60, 1], duration.split(":"))) 

        buff = time_pos_in_sec/duration_in_sec*100
        
        prev_time = time.time()

        if time_pos_in_sec == duration_in_sec - 2 and time_pos_in_sec != 0 and duration_in_sec != 0:
            video_id_to_search = currently_playing_youtube_id
            eventlet.spawn(song_ended)
            playlist.get()
            
            if playlist.qsize() > 0:
                video_id = video_ids.get()
                currently_playing_youtube_id = video_id
                player.playlist_next()
                time.sleep(5)
            else:
                is_first = True
                if autoplay:
                    auto_video_json = get_next_related_video_dict(video_id_to_search)
                    playlist.put(auto_video_json)
                    video_id = auto_video_json.get('youtubeId')
                    autoplay_history.append(video_id)
                    player.playlist_append('http://www.youtube.com/watch?v={}'.format(video_id))
                    video_ids.put(video_id)
                    eventlet.spawn(song_added, auto_video_json)
                    video_id = video_ids.get()
                    player.play('http://www.youtube.com/watch?v={}'.format(video_id))
                    currently_playing_youtube_id = video_id
                    is_first = False


@app.route('/playlist', methods=['GET'])
def get_playlist():
    return jsonify(list(playlist.queue))


def increase_time():
    global ips_with_times
    while True:
        for key, value in ips_with_times.items():
            ips_with_times[key] +=1
            socketio.emit('remainingTimeChanged', waiting_time - ips_with_times[key], room=key)
        time.sleep(1)


def volume_changed():
    


@socketio.on('joined')
def joined():
    if request.remote_addr not in ips_with_times:
        ips_with_times[request.remote_addr] = 61
    join_room(request.remote_addr)


@app.route('/volume', methods=['PUT'])
def set_volume():
    putted_dict = request.json
    value = putted_dict.get('value', player.osd.volume)
    print(value)
    if 0 < value < 100: 
        try:
            player._set_property('volume', value)
            socketio.emit('volumeChanged', value, broadcast=True)
        except:
            return jsonify({"message": "Mpv is not playing anything"}), 503
    return "OK"


@app.route('/volume', methods=['GET'])
def get_volume():
    try:
        volume = player._get_property('ao-volume')
        return jsonify({"volume": volume})
    except:
        return jsonify({"message": "Mpv is not playing anything"}), 503


@app.route('/autoplay', methods=['GET'])
def get_autoplay():
    return jsonify({'value': autoplay})


@app.route('/autoplay', methods=['PUT'])
def set_autoplay():
    global autoplay
    global autoplay_history
    putted_dict = request.json
    autoplay_history.clear()
    autoplay = putted_dict.get('value')
    socketio.emit('autoplayChanged', autoplay, broadcast=True)
    return 'Ok'


@app.route('/waiting-time', methods=['GET'])
def get_waiting_time():
    return jsonify({'value': waiting_time})


@app.route('/waiting-time', methods=['PUT'])
def set_waiting_time():
    global waiting_time
    putted_dict = request.json
    waiting_time = int(putted_dict.get('value'))
    socketio.emit('waitingTimeChanged', waiting_time, broadcast=True)
    return 'Ok'


@app.route('/next-song', methods=['GET'])
def next_song():
    global is_first
    global currently_playing_youtube_id
    global video_ids
    global playlist

    video_ids.queue.clear()
    playlist.queue.clear()
    player.playlist_clear()
    
    auto_video_json = get_next_related_video_dict(currently_playing_youtube_id)
    playlist.put(auto_video_json)
    video_id = auto_video_json.get('youtubeId')
    autoplay_history.append(video_id)
    player.playlist_append('http://www.youtube.com/watch?v={}'.format(video_id))
    video_ids.put(video_id)
    socketio.emit('nextSongAdded', json.dumps(auto_video_json), json=True, broadcast=True)
    video_id = video_ids.get()
    player.play('http://www.youtube.com/watch?v={}'.format(video_id))
    currently_playing_youtube_id = video_id
    is_first = False

    print('asd')

    return 'Ok'


def get_next_related_video_dict(video_id):

    duration_sec = 601

    while duration_sec > 600 or duration_sec < 1: 
        response_get = requests.get('https://www.googleapis.com/youtube/v3/search?part=snippet&relatedToVideoId={}&type=video&key={}'.format(video_id, youtube_api_key))

        items_len = len(response_get.json().get('items'))
        random_index = random.randint(0, items_len-1)
        item = response_get.json().get('items')[random_index]
    
        response_get_duration = requests.get('https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={}&key={}'.format(item.get('id').get('videoId'), youtube_api_key))
     
        duration_str = response_get_duration.json().get('items')[0].get('contentDetails').get('duration')
        duration_timedelta = isodate.parse_duration(duration_str)

        duration_sec = (int(duration_timedelta.total_seconds()))

        snippet = item.get('snippet')

        if 'live' in snippet.get('title').lower() or item.get('id').get('videoId') in autoplay_history:
            duration_sec = 601

        auto_video_dict = {'duration': duration_sec, 'youtubeId': item.get('id').get('videoId'), 'title': snippet.get('title'), 'imageUrl': snippet.get('thumbnails').get('default').get('url')}
    
    return auto_video_dict


@app.route('/song', methods=['POST'])
def post_song():
    global currently_playing_youtube_id
    global is_first
    global ips_with_times

    posted_dict = request.json
    print(posted_dict.get('youtubeId'))
    print('current: {}'.format(currently_playing_youtube_id))
    print('video ids: {}'.format(list(video_ids.queue)))
    if posted_dict.get('youtubeId') in list(video_ids.queue) or \
         currently_playing_youtube_id == posted_dict.get('youtubeId'):
        return 'Video is already added', 409
    
    if ips_with_times.get(request.remote_addr, waiting_time + 1) < waiting_time:
        return 'asd', 429
    
    playlist.put(posted_dict)
    video_id = posted_dict.get('youtubeId')
    player.playlist_append('http://www.youtube.com/watch?v={}'.format(video_id))
    video_ids.put(video_id)
    socketio.emit('songAdded', json.dumps(posted_dict), json=True, broadcast=True)
    if is_first or playlist.qsize() == 0:
        video_id = video_ids.get()
        player.play('http://www.youtube.com/watch?v={}'.format(video_id))
        is_first = False
        currently_playing_youtube_id = video_id

    ips_with_times[request.remote_addr] = 0

    return 'Ok'


@app.route('/song', methods=['DELETE'])
def delete_song():
    eventlet.spawn(test)
    global currently_playing_youtube_id
    global is_first
    posted_dict = request.json
    youtube_id = posted_dict.get('youtubeId')

    video_ids_list = list(video_ids.queue)

    if youtube_id not in video_ids_list and \
         currently_playing_youtube_id != posted_dict.get('youtubeId'):
        return 'Video is already deleted', 409

    index = player.playlist_filenames.index('http://www.youtube.com/watch?v={}'.format(youtube_id))

    player.playlist_remove(index)

    playlist_list = list(playlist.queue)
    playlist_list = [item for item in playlist_list if youtube_id != item.get('youtubeId')]

    playlist.queue.clear()
    [playlist.put(item) for item in playlist_list]

    print(video_ids_list)
    if youtube_id in video_ids_list:
        video_ids_list.remove(youtube_id)
        video_ids.queue.clear()
        [video_ids.put(item) for item in video_ids_list]

    print(list(video_ids.queue))
    print(player.playlist_filenames)

    if playlist.qsize() < 1:
        is_first = True
        currently_playing_youtube_id = ''
        
    socketio.emit('songDeleted', youtube_id, broadcast=True)
    return 'Ok'


def test():
    while True:
        socketio.emit('timePosChanged', int(buff), broadcast=True)
        eventlet.sleep(1)

if __name__ == "__main__":
    try:
        eventlet.spawn(increase_time)
        eventlet.spawn(test)
        socketio.run(app, '0.0.0.0')
    except:
        pass
