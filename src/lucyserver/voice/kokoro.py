import time
from multiprocessing import Process, Queue, Value
from queue import Empty
import pyaudio
import numpy as np
import threading
import base64

from kokoro import KPipeline

class KokoroVoice:
    def __init__(self):
        self.pipeline = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M')

    def generate(self, text):
        generator = self.pipeline(text, voice='af_bella')
        for i, (gs, ps, audio) in enumerate(generator):
            audio = np.array(audio)
            for i in range(0, audio.size, 2400):
                audio_clip = audio[i:i+2400]
                if audio_clip.size < 2400:
                    audio_clip = np.pad(audio_clip, (0, 2400 - audio_clip.size), mode='constant')
                output_bytes = audio_clip.tobytes()
                output_bytes = base64.b64encode(output_bytes).decode('utf-8')
                yield {"type": "audio", "data": output_bytes}


voice = KokoroVoice()