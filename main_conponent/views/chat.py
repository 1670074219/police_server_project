from django.shortcuts import render
import os
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from dashscope.audio.asr import TranslationRecognizerChat, TranslationRecognizerCallback
from dashscope.audio.asr import TranscriptionResult, TranslationResult
import dashscope
import logging
import wave
from pydub import AudioSegment
import io
import time
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
import pyaudio
import json
from ..services.asr_service import ASRCallback

# 设置 FFmpeg 路径
ffmpeg_path = r"D:\Desktop\ffmpeg-master-latest-win64-gpl\bin"
os.environ["PATH"] += os.pathsep + ffmpeg_path

# 设置 pydub 的路径
AudioSegment.converter = os.path.join(ffmpeg_path, "ffmpeg.exe")
AudioSegment.ffmpeg = os.path.join(ffmpeg_path, "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(ffmpeg_path, "ffprobe.exe")

# 设置日志
logger = logging.getLogger(__name__)

# 设置API key
dashscope.api_key = "sk-d7b419aabe41461a99febae96b60b030"

def chat_page(request):
    return render(request, 'chat.html')

@csrf_exempt
def process_voice(request):
    if request.method == 'POST':
        wav_path = None
        try:
            # 确保voice_temp目录存在
            voice_temp_dir = 'voice_temp'
            if not os.path.exists(voice_temp_dir):
                os.makedirs(voice_temp_dir)
            
            # 检查是否有文件上传
            if 'audio' not in request.FILES:
                return JsonResponse({'error': '没有收到音频文件'}, status=400)
            
            # 读取上传的音频文件
            audio_file = request.FILES['audio']
            audio_data = audio_file.read()
            
            try:
                # 使用pydub加载webm音频并转换
                audio = AudioSegment.from_file(io.BytesIO(audio_data), format='webm')
                logger.info(f'原始音频: 通道数={audio.channels}, 采样率={audio.frame_rate}, 时长={len(audio)/1000}秒')
                
                # 转换为单声道和16kHz采样率
                if audio.channels != 1:
                    audio = audio.set_channels(1)
                if audio.frame_rate != 16000:
                    audio = audio.set_frame_rate(16000)
                    logger.info('已转换采样率到16kHz')
                
                # 保存为WAV格式
                wav_path = os.path.join(voice_temp_dir, 'temp_audio.wav')
                audio.export(wav_path, format='wav', parameters=["-acodec", "pcm_s16le"])
                logger.info(f'已保存为WAV格式: {wav_path}')
                
                # 读取WAV文件并发送数据
                with wave.open(wav_path, 'rb') as wf:
                    logger.info(f'WAV文件信息: 通道数={wf.getnchannels()}, 采样率={wf.getframerate()}, 帧数={wf.getnframes()}')
                    
                    # 创建回调对象
                    callback = ASRCallback()
                    
                    # 初始化识别器
                    translator = TranslationRecognizerChat(
                        model="gummy-chat-v1",
                        format="pcm",
                        sample_rate=16000,
                        transcription_enabled=True,
                        translation_enabled=False,
                        callback=callback
                    )
                    
                    # 开始识别
                    translator.start()
                    logger.info('开始发送音频数据')
                    
                    # 读取音频数据并发送
                    chunk_size = 3200  # 200ms的数据
                    total_chunks = 0
                    while True:
                        data = wf.readframes(chunk_size)
                        if not data:
                            break
                        translator.send_audio_frame(data)
                        total_chunks += 1
                        # 每发送一块数据后稍微等待一下
                        time.sleep(0.01)
                    
                    logger.info(f'发送完成，共发送 {total_chunks} 个数据块')
                    
                    # 停止识别并等待结果
                    translator.stop()
                    
                    # 等待结果（最多等待30秒）
                    wait_time = 0
                    max_wait_time = 30  # 增加等待时间到30秒
                    
                    while wait_time < max_wait_time:
                        if callback.is_finished:  # 移除 and callback.is_sentence_end 条件
                            # 给一点额外时间等待最后的结果
                            time.sleep(0.5)
                            break
                        time.sleep(0.1)
                        wait_time += 0.1
                    
                    if wait_time >= max_wait_time:
                        logger.warning('等待超时')
                    
                    # 检查是否有错误
                    if callback.error:
                        return JsonResponse({'error': f'语音识别错误: {callback.error}'}, status=500)
                    
                    # 获取最终识别结果
                    if callback.final_text:
                        logger.info(f'识别成功: {callback.final_text}')
                        return JsonResponse({'text': callback.final_text})
                    elif callback.all_text:  # 如果有任何中间结果，使用最后一个
                        final_text = callback.all_text[-1]
                        logger.info(f'使用最后的中间结果: {final_text}')
                        return JsonResponse({'text': final_text})
                    else:
                        logger.error('没有得到识别结果')
                        return JsonResponse({'error': '语音识别结果为空'}, status=500)
                    
            except Exception as api_error:
                logger.error(f"API调用错误: {str(api_error)}")
                return JsonResponse({'error': f'API调用错误: {str(api_error)}'}, status=500)
            finally:
                # 清理临时文件
                try:
                    if wav_path and os.path.exists(wav_path):
                        os.remove(wav_path)
                except Exception as e:
                    logger.error(f"删除临时文件失败: {str(e)}")
                
        except Exception as e:
            logger.error(f"处理语音请求时发生错误: {str(e)}")
            return JsonResponse({'error': f'服务器错误: {str(e)}'}, status=500)
    
    return JsonResponse({'error': '不支持的请求方法'}, status=400)

class TTSCallback:
    def __init__(self):
        self.audio_data = []
        self.is_complete = False
        self.error = None

    def on_open(self) -> None:
        logger.info('语音合成开始')

    def on_close(self) -> None:
        logger.info('语音合成结束')
        self.is_complete = True

    def on_error(self, message: str):
        logger.error(f'语音合成错误: {message}')
        self.error = message

    def on_event(self, message):
        logger.info(f'语音合成事件: {message}')

    def on_data(self, data: bytes) -> None:
        logger.info(f'收到音频数据: {len(data)} 字节')
        self.audio_data.append(data)

    def on_complete(self):
        logger.info('语音合成完成')
        self.is_complete = True

@csrf_exempt
def text_to_speech(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            text = data.get('text')
            if not text:
                return JsonResponse({'error': '没有收到文本'}, status=400)

            callback = TTSCallback()
            synthesizer = SpeechSynthesizer(
                model="cosyvoice-v1",      # 使用正确的模型
                voice="longshuo",      # 使用正确的声音
                format=AudioFormat.PCM_16000HZ_MONO_16BIT,  # 使用16kHz采样率
                callback=callback
            )

            # 发送文本进行合成
            synthesizer.streaming_call(text)
            synthesizer.streaming_complete()

            # 等待合成完成
            wait_time = 0
            while not callback.is_complete and wait_time < 30:
                time.sleep(0.1)
                wait_time += 0.1

            if callback.error:
                return JsonResponse({'error': f'语音合成错误: {callback.error}'}, status=500)

            if not callback.audio_data:
                return JsonResponse({'error': '没有得到音频数据'}, status=500)

            # 将PCM数据转换为WAV格式
            import wave
            import io

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16位采样
                wav_file.setframerate(16000)  # 采样率
                for chunk in callback.audio_data:
                    wav_file.writeframes(chunk)

            # 返回WAV数据
            wav_buffer.seek(0)
            response = StreamingHttpResponse(wav_buffer, content_type='audio/wav')
            response['Content-Disposition'] = 'attachment; filename="speech.wav"'
            return response

        except Exception as e:
            logger.error(f"语音合成错误: {str(e)}")
            return JsonResponse({'error': f'服务器错误: {str(e)}'}, status=500)

    return JsonResponse({'error': '不支持的请求方法'}, status=400)