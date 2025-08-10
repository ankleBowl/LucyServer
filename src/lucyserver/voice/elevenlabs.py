import threading
from multiprocessing import Queue
import numpy as np
import time
from elevenlabs.client import ElevenLabs
import base64
import subprocess

class ElevenLabsAIVoice:
    def __init__(self, api_key, voice_id):
        self.client = ElevenLabs(api_key=api_key)

        self.model_id = "eleven_multilingual_v2"
        self.voice_id = voice_id


    # def generate(self, text):        
    #     yield {"type": "speech_sr", "sr": 48000}
    #     audio_stream = self.client.text_to_speech.stream(
    #         text=text,
    #         voice_id=self.voice_id,
    #         model_id=self.model_id,
    #     )

    #     print("ElevenLabs audio stream started.")
    #     ffmpeg_proc = subprocess.Popen(
    #         [
    #             'ffmpeg',
    #             '-hide_banner',
    #             '-loglevel', 'error',
    #             '-i', 'pipe:0',          # input from stdin
    #             '-f', 's16le',           # raw PCM 16-bit little endian
    #             '-acodec', 'pcm_s16le',  # PCM codec
    #             '-ac', '1',              # 1 channel (mono)
    #             '-ar', '48000',          # sample rate
    #             'pipe:1'                 # output to stdout
    #         ],
    #         stdin=subprocess.PIPE,
    #         stdout=subprocess.PIPE,
    #         stderr=subprocess.DEVNULL,
    #         bufsize=0
    #     )

    #     print("FFmpeg process started.")

    #     for chunk in audio_stream:
    #         if chunk is None:
    #             print("Received None chunk from ElevenLabs, ending stream.")
    #             break
    #         ffmpeg_proc.stdin.write(chunk)

    #     print("Finished sending chunks to FFmpeg.")

    #     ffmpeg_proc.stdin.close()

    #     print("Finished sending audio to FFmpeg. Reading PCM data...")

    #     while True:
    #         pcm_data = ffmpeg_proc.stdout.read(4096)
    #         if not pcm_data:
    #             break
    #         audio_data = np.frombuffer(pcm_data, dtype=np.int16)
    #         audio_data = audio_data.astype(np.float32) / 32768.0
            
    #         output_bytes = audio_data.tobytes()
    #         output_bytes = base64.b64encode(output_bytes).decode('utf-8')
    #         yield {"type": "audio", "data": output_bytes}

    #     print("Finished reading PCM data from FFmpeg.")

    #     ffmpeg_proc.wait()

    #     print("FFmpeg process ended.")

    def generate(self, text):        
        yield {"type": "speech_sr", "sr": 48000}
        audio_stream = self.client.text_to_speech.stream(
            text=text,
            voice_id=self.voice_id,
            model_id=self.model_id,
        )

        print("ElevenLabs audio stream started.")
        ffmpeg_proc = subprocess.Popen(
            [
                'ffmpeg',
                '-hide_banner',
                '-loglevel', 'error',
                '-nostdin',               # don't wait for console input
                '-i', 'pipe:0',
                '-f', 's16le',
                '-acodec', 'pcm_s16le',
                '-ac', '1',
                '-ar', '48000',
                'pipe:1'
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE
        )

        print("FFmpeg process started.")

        for chunk in audio_stream:
            if chunk is None:
                break
            ffmpeg_proc.stdin.write(chunk)

        # Signal EOF to ffmpeg
        ffmpeg_proc.stdin.close()

        # Read all PCM data after ffmpeg finishes
        pcm_data_all = ffmpeg_proc.stdout.read()
        ffmpeg_proc.wait()

        # Convert to float and yield
        audio_data = np.frombuffer(pcm_data_all, dtype=np.int16).astype(np.float32) / 32768.0
        output_bytes = base64.b64encode(audio_data.tobytes()).decode('utf-8')
        yield {"type": "audio", "data": output_bytes}

        print("FFmpeg process ended.")


voice = ElevenLabsAIVoice(api_key="", voice_id="odyUrTN5HMVKujvVAgWW")