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

# from test import assistant
from ..services.asr_service import ASRCallback
from ragflow_sdk import RAGFlow

# 设置日志
logger = logging.getLogger(__name__)

# 设置API key
dashscope.api_key = "sk-d7b419aabe41461a99febae96b60b030"

# RAGFlow配置
RAGFLOW_API_KEY = "ragflow-BhYTBmYWUyMGVmOTExZjBiMDIzNmE4Yj"  
RAGFLOW_BASE_URL = "http://219.216.99.136:6523"  
RAGFLOW_DATASET = "demo"  # 默认数据集名称
RAGFLOW_DATASET_ID = "82165e840ef711f0b6896a8b746c55e2"  # 数据集ID

def chat_page(request):
    return render(request, 'chat.html')

def document_management(request):
    return render(request, 'document_management.html')

@csrf_exempt
def list_documents(request):
    """获取文档列表"""
    try:
        # 获取请求参数
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        keywords = request.GET.get('keywords', None)
        
        # 创建RAGFlow客户端
        rag_object = RAGFlow(api_key=RAGFLOW_API_KEY, base_url=RAGFLOW_BASE_URL)
        
        # 获取数据集
        dataset_list = rag_object.list_datasets(id=RAGFLOW_DATASET_ID)
        if not dataset_list:
            return JsonResponse({
                'success': False,
                'error': '未找到数据集'
            }, status=404)
        
        dataset = dataset_list[0]
        
        # 获取文档列表
        documents = dataset.list_documents(
            keywords=keywords,
            page=page,
            page_size=page_size,
            orderby="update_time",
            desc=True
        )
        
        # 计算总页数（这里假设RAGFlow SDK不直接提供总记录数）
        # 如果返回的文档数小于page_size，说明是最后一页
        is_last_page = len(documents) < page_size
        # 如果是第一页且为空，总页数为1
        if page == 1 and len(documents) == 0:
            total_pages = 1
        # 如果是最后一页，计算总页数
        elif is_last_page:
            total_pages = page
        # 否则至少还有下一页
        else:
            total_pages = page + 1
        
        # 转换文档对象为可序列化的字典
        serialized_docs = []
        for doc in documents:
            serialized_docs.append({
                'id': doc.id,
                'name': doc.name or "未命名文档",
                'size': doc.size,
                'token_count': doc.token_count,
                'chunk_count': doc.chunk_count,
                'progress': doc.progress,
                'progress_msg': doc.progress_msg,
                'process_begin_at': doc.process_begin_at,
                'process_duration': getattr(doc, 'process_duation', 0),  # 注意这里可能有拼写错误
                'run': doc.run,
                'status': doc.status
            })
        
        return JsonResponse({
            'success': True,
            'documents': serialized_docs,
            'total_pages': total_pages,
            'current_page': page,
            'page_size': page_size
        })
        
    except Exception as e:
        logger.exception(f"获取文档列表出错: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"服务器错误: {str(e)}"
        }, status=500)

@csrf_exempt
def delete_document(request):
    """删除文档"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '只接受POST请求'}, status=405)
    
    try:
        # 解析请求体
        data = json.loads(request.body)
        document_id = data.get('document_id')
        
        if not document_id:
            return JsonResponse({'success': False, 'error': '缺少文档ID'}, status=400)
        
        # 创建RAGFlow客户端
        rag_object = RAGFlow(api_key=RAGFLOW_API_KEY, base_url=RAGFLOW_BASE_URL)
        
        # 获取数据集
        dataset_list = rag_object.list_datasets(id=RAGFLOW_DATASET_ID)
        if not dataset_list:
            return JsonResponse({
                'success': False,
                'error': '未找到数据集'
            }, status=404)
        
        dataset = dataset_list[0]
        
        # 删除文档
        dataset.delete_documents(ids=[document_id])
        
        return JsonResponse({
            'success': True,
            'message': '文档删除成功'
        })
        
    except Exception as e:
        logger.exception(f"删除文档出错: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"服务器错误: {str(e)}"
        }, status=500)

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

@csrf_exempt
def upload_documents(request):
    """
    处理文档上传和解析，API信息和URL直接在后端代码中设置
    """
    if request.method != 'POST':
        return JsonResponse({'error': '只接受POST请求'}, status=405)
    
    try:
        # 确保上传目录存在
        upload_dir = 'upload_temp'
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        # 检查是否有文件上传
        if not request.FILES.getlist('documents'):
            return JsonResponse({'error': '没有收到文档文件'}, status=400)
        
        # 使用后端预设的RAGFlow配置
        api_key = RAGFLOW_API_KEY
        base_url = RAGFLOW_BASE_URL
        dataset_name = RAGFLOW_DATASET
        
        # 创建RAGFlow客户端
        logger.info(f"创建RAGFlow客户端: base_url={base_url}")
        rag_object = RAGFlow(api_key=api_key, base_url=base_url)
        
        # 创建数据集对象
        logger.info(f"使用数据集: {dataset_name}")
        dataset_list = rag_object.list_datasets(id=RAGFLOW_DATASET_ID)
        dataset = dataset_list[0]
        
        # 准备上传文档
        logger.info("准备上传文档...")
        documents = []
        for file in request.FILES.getlist('documents'):
            # 读取文件内容
            file_content = file.read()
            
            # 添加到文档列表
            documents.append({
                'display_name': file.name,
                'blob': file_content
            })
            
            logger.info(f"添加文件: {file.name}, 大小: {len(file_content)} 字节")
        
        # 上传文档
        logger.info(f"上传 {len(documents)} 个文档...")
        dataset.upload_documents(documents)
        
        # 返回上传成功结果，不管解析是否成功
        upload_result = {
            'success': True, 
            'message': '文档已成功上传',
            'documents_count': len(documents)
        }
        
        # 尝试解析文档，但不影响上传结果
        try:
            # 获取上传的文档ID
            logger.info("获取文档列表...")
            document_list = dataset.list_documents(keywords=None)
            
            if document_list:
                # 收集文档ID
                doc_ids = []
                for document in document_list:
                    doc_ids.append(document.id)
                
                if doc_ids:
                    # 异步解析文档
                    logger.info(f"开始异步解析 {len(doc_ids)} 个文档...")
                    try:
                        dataset.async_parse_documents(doc_ids)
                        logger.info("文档解析任务已提交")
                        upload_result['message'] = '文档已成功上传并开始解析'
                        upload_result['documents_processed'] = len(doc_ids)
                    except Exception as parse_error:
                        logger.warning(f"解析文档时出错，但不影响上传: {str(parse_error)}")
                        upload_result['message'] = '文档已成功上传，解析将在后台自动进行'
            else:
                logger.warning("找不到文档列表，无法解析文档")
        except Exception as list_error:
            logger.warning(f"获取文档列表或解析文档时出错，但不影响上传: {str(list_error)}")
        
        # 返回成功结果
        return JsonResponse(upload_result)
        
    except Exception as e:
        logger.exception(f"文档上传处理出错: {str(e)}")
        return JsonResponse({'error': f"服务器错误: {str(e)}"}, status=500)
    
def newchat(request):
    """创建新的聊天会话"""
    try:
        # 创建RAGFlow客户端
        rag_object = RAGFlow(api_key=RAGFLOW_API_KEY, base_url=RAGFLOW_BASE_URL)
        
        # 获取聊天助手
        assistant_list = rag_object.list_chats(name='小智')
        
        if not assistant_list:
            return JsonResponse({
                'success': False,
                'error': '找不到指定的聊天助手'
            }, status=404)
        
        assistant = assistant_list[0]
        
        # 列出所有名为server的会话
        logger.info(f"正在查找名为'server'的会话")
        sessions = assistant.list_sessions(name='server')
        
        # 如果有旧会话，删除它们
        if sessions:
            session_ids = [session.id for session in sessions]
            logger.info(f"找到 {len(session_ids)} 个会话，准备删除")
            assistant.delete_sessions(ids=session_ids)
            logger.info(f"已删除旧会话")
        else:
            logger.info(f"未找到旧会话")
        
        # 创建新会话
        session = assistant.create_session(name='server')
        logger.info(f"已创建新会话，ID: {session.id}")
        
        return JsonResponse({
            'success': True,
            'message': '新对话已创建',
            'session_id': session.id
        })
        
    except Exception as e:
        logger.exception(f"创建新对话时出错: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f"服务器错误: {str(e)}"
        }, status=500)