from tempfile import NamedTemporaryFile
from gtts import gTTS
import hashlib
import numpy as np
from googletrans import Translator
from typing import Any, List, Dict, Optional
import pathlib
from pydub import AudioSegment
from pydexcom import Dexcom, GlucoseReading
import os
import locale
import json
import time
from datetime import timedelta, datetime
import soundfile as sf
import numpy as np
import io
import alsaaudio
import wave

DEXCOM: Dexcom = None
TRANSLATOR = Translator()
LOW_ALERT = 'low_alert'
CRITICAL_LOW_ALERT = 'critical_low_alert'
HIGH_ALERT = 'high_alert'
NO_DATA = 'no_data'
ALERTMSGS : Dict[str,str] = {}
LOCALE = []
LANG_TO_LOCALE = {}
LOCALE_TO_LANG = {}
LANGS = []
LOW_THRESHOLD: float = 4.5
CRITICAL_LOW_THRESHOLD: float = 4.0
HIGH_THRESHOLD: float = 14.0
BASE_LANG = "en"
MP3DICT = {}
POLL_INTERVAL_S = 320

def load_config_init() :

    global DEXCOM
    global ALERTMSGS
    global LOCALE
    global LOW_THRESHOLD
    global HIGH_THRESHOLD
    global CRITICAL_LOW_THRESHOLD
    global LANGS
    global LANG_TO_LOCALE
    global LOCALE_TO_LANG
    global BASE_LANG
    global POLL_INTERVAL_S

    with open('config.json', 'r') as jf:
        conf = json.load(jf)
    
    conf_alertmsgs = conf['alertmsgs']

    for alert in [LOW_ALERT, CRITICAL_LOW_ALERT, HIGH_ALERT, NO_DATA] :
        ALERTMSGS[alert] = conf_alertmsgs[alert]
    
    DEXCOM = Dexcom(conf['username'], conf['password'], ous=conf['ous'])
    LOCALE = conf['locale']
    LANGS = [l.split("_")[0] for l in LOCALE]
    LANG_TO_LOCALE = {l.split("_")[0]:l for l in LOCALE}
    LOCALE_TO_LANG = {l:l.split("_")[0] for l in LOCALE}
    LOW_THRESHOLD = conf['low_threshold']
    HIGH_THRESHOLD = conf['high_threshold']
    CRITICAL_LOW_THRESHOLD = conf['critical_low_threshold']
    BASE_LANG = conf['base_lang']
    POLL_INTERVAL_S = conf['poll_interval_s']

def prep_voice_num(num: float, loc: str) :
    locale.setlocale(locale.LC_NUMERIC, loc)
    n_str = locale.str(num)
    fname = hashlib.md5(n_str.encode()).hexdigest()
    l = LOCALE_TO_LANG[loc]
    dir = f'offline_{l}/'
    file_path = f'{dir}{fname}.wav'
    MP3DICT[l][num] = file_path
    if not os.path.exists(file_path):
        gTTS(n_str, lang=l).write_to_fp(voice := NamedTemporaryFile())
        voice.seek(0)
        AudioSegment.from_mp3(voice.name).export(file_path, format='wav')      
        voice.close()

def prep_voice_num_range(nums: List[float]) -> None:

    for loc in LOCALE :
        l = loc.split('_')[0]
        MP3DICT.setdefault(l, {})
        for n in nums :
            prep_voice_num(n,loc)


def prep_single_voice_msg(fname, msg, lang) -> None:
    dir = f'offline_{lang}/'
    file_path = f'{dir}{fname}.wav'
    MP3DICT[lang][fname] = file_path
    txt = msg if lang == BASE_LANG else TRANSLATOR.translate(msg, src=BASE_LANG, dest=lang).text
    if not os.path.exists(file_path):
        gTTS(txt, lang=lang).write_to_fp(voice := NamedTemporaryFile())
        voice.seek(0)
        AudioSegment.from_mp3(voice.name).export(file_path, format='wav')
        voice.close()
    return

def prep_voice_messages(texts: Dict[str,str]) -> None:

    for l in LANGS:
        MP3DICT.setdefault(l, {})
        for fname,msg in texts.items() :
            prep_single_voice_msg(fname, msg, l)

def prep_all():

    for l in LANGS:
        pathlib.Path(f'offline_{l}').mkdir(parents=True, exist_ok=True) 
    
    readings = np.arange(2.0, 23.0, 0.1).round(1)
    prep_voice_num_range(readings)
    prep_voice_messages(ALERTMSGS)

def concat_audio(store: np.ndarray, file_path: str) :
    data, samplerate = sf.read(file_path)
    store = np.append(store, data)
    return store, samplerate

def play(device_type, f: wave.Wave_read, till_time: datetime):
    format = None

    # 8bit is unsigned in wav files
    if f.getsampwidth() == 1:
        format = alsaaudio.PCM_FORMAT_U8
    # Otherwise we assume signed data, little endian
    elif f.getsampwidth() == 2:
        format = alsaaudio.PCM_FORMAT_S16_LE
    elif f.getsampwidth() == 3:
        format = alsaaudio.PCM_FORMAT_S24_3LE
    elif f.getsampwidth() == 4:
        format = alsaaudio.PCM_FORMAT_S32_LE
    else:
        raise ValueError('Unsupported format')
    
    periodsize = f.getframerate() // 8

    while datetime.now() < till_time :
        device = alsaaudio.PCM(channels=f.getnchannels(), rate=f.getframerate(), format=format, periodsize=periodsize, device=device_type)
        data = f.readframes(periodsize)
        while data:
            device.write(data)
            data = f.readframes(periodsize)
        time.sleep(2)
        f.rewind()
    

def get_audio_msg(reading: float, trend: str, msg: str) :
    # total_audio = AudioSegment.empty()
    total_audio = np.array([])
    for l in LANGS :
        l_dict: dict = MP3DICT[l]
        trend_name = trend.replace(' ', '_')
        if reading not in l_dict :
            prep_voice_num(reading, LANG_TO_LOCALE[l])
        if msg not in l_dict:
            prep_single_voice_msg(msg, ALERTMSGS[msg], l)
        if trend not in l_dict:
            prep_single_voice_msg(trend_name, trend, l)
        
        for n in [reading, trend_name, msg] :
            total_audio, samplerate = concat_audio(total_audio, l_dict[n])
    
    return total_audio, samplerate

# def get_audio_msg_old(reading: float, trend: str, msg: str) :
#     total_audio = AudioSegment.empty()
#     for l in LANGS :
#         l_dict: dict = MP3DICT[l]
#         trend_name = trend.replace(' ', '_')
#         if reading not in l_dict :
#             prep_voice_num(reading, LANG_TO_LOCALE[l])
#         if msg not in l_dict:
#             prep_single_voice_msg(msg, ALERTMSGS[msg], l)
#         if trend not in l_dict:
#             prep_single_voice_msg(trend_name, trend, l)
#         total_audio += AudioSegment.from_wav(l_dict[reading])
#         total_audio += AudioSegment.from_wav(l_dict[trend_name])
#         total_audio += AudioSegment.from_wav(l_dict[msg])
#     return total_audio


def get_glucose_reading() -> Optional[GlucoseReading] :
    return DEXCOM.get_current_glucose_reading()

def get_next_poll_seconds(dt : datetime) :
    delta = datetime.now() - dt
    return POLL_INTERVAL_S - delta.seconds

def loop_play_till_time(gr: GlucoseReading, alert) :
    audio, samplerate = get_audio_msg(gr.mmol_l, gr.trend_description, alert)
    next_pool_after = get_next_poll_seconds(gr.datetime)
    till_time = datetime.now() + timedelta(0, next_pool_after)
    iobytes = io.BytesIO()
    sf.write(iobytes, audio, samplerate=samplerate, format="wav")
    iobytes.seek(0)
    with wave.open(iobytes, 'rb') as f:
	    play('default', f, till_time)

def react(gr: GlucoseReading) -> int:
    if gr.mmol_l <= CRITICAL_LOW_THRESHOLD :
        loop_play_till_time(gr, CRITICAL_LOW_ALERT)
    elif gr.mmol_l <= LOW_THRESHOLD :
        loop_play_till_time(gr, LOW_ALERT)
    elif gr.mmol_l >= HIGH_THRESHOLD :
        loop_play_till_time(gr, HIGH_ALERT)
    else :
        next_pool_after = get_next_poll_seconds(gr.datetime)
        print(next_pool_after)
        time.sleep(next_pool_after)

def main():
    load_config_init()
    prep_all()
    print('started')
    while True :
        react(get_glucose_reading())


if __name__ == "__main__":
    main()

#sudo locale-gen pl_PL.UTF-8
#sudo update-locale