import os
import hashlib
import json
import asyncio
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
import logging

logger = logging.getLogger(__name__)

class TTSManager:
    def __init__(self):
        self.tts_cache_dir = 'tts_temp'
        self.ensure_cache_dir()
        
    def ensure_cache_dir(self):
        if not os.path.exists(self.tts_cache_dir):
            os.makedirs(self.tts_cache_dir)
            
    def get_cache_path(self, text):
        # 使用文本的hash作为文件名
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return os.path.join(self.tts_cache_dir, f'{text_hash}.wav')
    
    def check_cache(self, text):
        cache_path = self.get_cache_path(text)
        return os.path.exists(cache_path), cache_path
    
    async def synthesize_speech(self, text, chunk_callback=None):
        # 检查缓存
        exists, cache_path = self.check_cache(text)
        if exists:
            logger.info(f'使用缓存的语音文件: {cache_path}')
            return cache_path
            
        # 创建回调处理器
        class TTSCallback:
            def __init__(self):
                self.audio_data = []
                self.is_complete = False
                self.error = None

            def on_open(self):
                logger.info('语音合成开始')

            def on_close(self):
                logger.info('语音合成结束')
                self.is_complete = True

            def on_error(self, message):
                logger.error(f'语音合成错误: {message}')
                self.error = message

            def on_event(self, message):
                logger.info(f'语音合成事件: {message}')

            def on_data(self, data):
                logger.info(f'收到音频数据: {len(data)} 字节')
                self.audio_data.append(data)
                if chunk_callback:
                    asyncio.create_task(chunk_callback(data))

            def on_complete(self):
                logger.info('语音合成完成')
                self.is_complete = True

        callback = TTSCallback()
        synthesizer = SpeechSynthesizer(
            model="cosyvoice-v1",
            voice="longshuo",
            format=AudioFormat.PCM_16000HZ_MONO_16BIT,
            callback=callback
        )

        # 开始合成
        synthesizer.streaming_call(text)
        synthesizer.streaming_complete()

        # 等待合成完成
        while not callback.is_complete:
            await asyncio.sleep(0.1)

        if callback.error:
            raise Exception(f'语音合成错误: {callback.error}')

        # 保存为WAV文件
        import wave
        with wave.open(cache_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            for chunk in callback.audio_data:
                wav_file.writeframes(chunk)

        logger.info(f'语音文件已保存: {cache_path}')
        return cache_path 