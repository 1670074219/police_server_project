# coding=utf-8
#
# Installation instructions for pyaudio:
# APPLE Mac OS X
#   brew install portaudio
#   pip install pyaudio
# Debian/Ubuntu
#   sudo apt-get install python-pyaudio python3-pyaudio
#   or
#   pip install pyaudio
# CentOS
#   sudo yum install -y portaudio portaudio-devel && pip install pyaudio
# Microsoft Windows
#   python -m pip install pyaudio

import time
import wave
import pyaudio
import dashscope
from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
from dashscope.audio.tts_v2 import *
from datetime import datetime
import os

def get_timestamp():
    now = datetime.now()
    formatted_timestamp = now.strftime("[%Y-%m-%d %H:%M:%S.%f]")
    return formatted_timestamp

# 若没有将API Key配置到环境变量中，需将your-api-key替换为自己的API Key
# dashscope.api_key = "your-api-key"

model = "cosyvoice-v1"
voice = "longxiaochun"
dashscope.api_key = "sk-d7b419aabe41461a99febae96b60b030"

class Callback(ResultCallback):
    def __init__(self):
        self.output_dir = "tts_output"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self.audio_data = bytearray()
        self.file_count = 0
        
    def on_open(self):
        print("开始语音合成...")
        self.audio_data = bytearray()
        
    def on_complete(self):
        print(get_timestamp() + " 语音合成任务完成")
        # 保存为WAV文件
        filename = os.path.join(self.output_dir, f"output_{self.file_count}.wav")
        self.save_to_wav(filename)
        self.file_count += 1
        print(f"音频已保存到: {filename}")

    def on_error(self, message: str):
        print(f"语音合成任务失败: {message}")

    def on_close(self):
        print(get_timestamp() + " 连接已关闭")

    def on_event(self, message):
        pass

    def on_data(self, data: bytes) -> None:
        print(get_timestamp() + " 收到音频数据长度: " + str(len(data)))
        self.audio_data.extend(data)
        
    def save_to_wav(self, filename):
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(1)  # 单声道
            wf.setsampwidth(2)  # 16位采样
            wf.setframerate(22050)  # 采样率
            wf.writeframes(self.audio_data)

callback = Callback()

# test_text = [
#     "流式文本语音合成SDK，",
#     "可以将输入的文本",
#     "合成为语音二进制数据，",
#     "相比于非流式语音合成，",
#     "流式合成的优势在于实时性",
#     "更强。用户在输入文本的同时",
#     "可以听到接近同步的语音输出，",
#     "极大地提升了交互体验，",
#     "减少了用户等待时间。",
#     "适用于调用大规模",
#     "语言模型（LLM），以",
#     "流式输入文本的方式",
#     "进行语音合成的场景。",
# ]

synthesizer = SpeechSynthesizer(
    model=model,
    voice=voice,
    format=AudioFormat.PCM_22050HZ_MONO_16BIT,  
    callback=callback,
)


# for text in test_text:
#     synthesizer.streaming_call(text)
#     time.sleep(0.1)
# synthesizer.streaming_complete()

# print('[Metric] requestId: {}, first package delay ms: {}'.format(
#     synthesizer.get_last_request_id(),
#     synthesizer.get_first_package_delay()))