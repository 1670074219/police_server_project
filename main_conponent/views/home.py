from django.shortcuts import HttpResponse, render
from django.http import JsonResponse, StreamingHttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import time
import asyncio
import os
import re
import threading

# from test import assistant
from ..services.tts_service import TTSManager
from ..services.ragflow_service import RagFlowService
from openai import OpenAI
import dashscope
from dashscope.audio.tts_v2 import *
from ragflow_sdk import RAGFlow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# init config
RAGFLOW_API_KEY = "ragflow-BhYTBmYWUyMGVmOTExZjBiMDIzNmE4Yj"  
RAGFLOW_BASE_URL = "http://219.216.99.136:6523"  
RAGFLOW_CHAT_ID = "2150c87c0fca11f0bcd96a8b746c55e2"
RAGFLOW_MODEL = "deepseek-r1:14b@Ollama"

ragflow_service = RagFlowService(
    api_key=RAGFLOW_API_KEY,
    base_url=RAGFLOW_BASE_URL,
    model_name=RAGFLOW_MODEL,
    chat_id=RAGFLOW_CHAT_ID
)

model = "cosyvoice-v1"
voice = "longxiaochun"
dashscope.api_key = "sk-d7b419aabe41461a99febae96b60b030"

tts_manager = TTSManager()

def home_page(request):
    return render(request, 'home.html')

# set model
@csrf_exempt
def set_model(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        ragflow_chat_id = data.get('ragflow_chat_id', '')
        ragflow_model = data.get('ragflow_model', '')
        ragflow_service.chat_id = ragflow_chat_id
        ragflow_service.model_name = ragflow_model
        ragflow_service.base_url = f"{RAGFLOW_BASE_URL}/api/v1/chats_openai/{ragflow_chat_id}"
        ragflow_service.client = OpenAI(
            api_key=RAGFLOW_API_KEY,
            base_url=ragflow_service.base_url
        )
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': '只接受POST请求'}, status=405)

def clean_text(text):
    """清理文本，移除不可见字符和特殊字符"""
    # 移除知识库引用格式 ##数字$$
    text = re.sub(r'##\d+\$\$', '', text)
    # 保留中文、英文、数字、基本标点
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？,.!?、:：""'' ]', '', text)
    # 移除多余的空白字符
    text = ' '.join(text.split())
    return text

# 判断句子是否有效（不仅仅是数字或标点）
def is_valid_sentence(text):
    # 移除数字和标点后检查是否还有内容
    stripped = re.sub(r'[\d\s,.。，!！?？:：;；]', '', text)
    return len(stripped) > 0

def process_speech(sentence, idx):
    try:
        audio_path = asyncio.run(tts_manager.synthesize_speech(sentence))
        file_name = os.path.basename(audio_path)
        return (idx, file_name)
    except Exception as e:
        logger.error(f"语音合成错误: {str(e)}")
        return (idx, None)

class Callback(ResultCallback):
    def __init__(self):
        self.audio_chunks = []
        self.current_index = 0
        self.is_completed = False
        self.is_error = False
        self.error_message = None
        
    def on_open(self):
        logger.info("TTS连接已打开")
        
    def on_complete(self):
        logger.info("TTS合成任务已完成")
        self.is_completed = True
        
    def on_error(self, message: str):
        logger.error(f"TTS合成错误: {message}")
        self.is_error = True
        self.error_message = message
        
    def on_close(self):
        logger.info("TTS连接已关闭")
        
    def on_event(self, message):
        pass
        #logger.info(f"TTS事件: {message}")
        
    def on_data(self, data: bytes) -> None:
        try:
            import base64
            encoded_data = base64.b64encode(data).decode('utf-8')
            
            # 生成唯一的chunk ID
            chunk_id = self.current_index
            self.current_index += 1
            
            # logger.info(f"收到音频数据: {len(data)}字节, chunk_id: {chunk_id}")
            
            # 创建音频数据JSON
            audio_json = json.dumps({
                'audio_data': encoded_data,
                'chunk_id': chunk_id,
                'sample_rate': 16000,
                'format': 'pcm'
            })
            
            # 添加到音频块列表
            self.audio_chunks.append(f"data: {audio_json}\n\n")   
        except Exception as e:
            logger.error(f"处理音频数据时出错: {str(e)}")

def generate_response(message):
    rag_object = RAGFlow(
        api_key="ragflow-BhYTBmYWUyMGVmOTExZjBiMDIzNmE4Yj",
        base_url="http://219.216.99.136:6523",
    )

    assistant_list = rag_object.list_chats(name="小智")
    assistant = assistant_list[0]
    session = assistant.list_sessions(name="server")[0]

    """生成流式响应"""
    yield 'retry: 1000\n\n'
    
    try:
        # response = ragflow_service.client.chat.completions.create(
        #     model=ragflow_service.model_name,
        #     messages=[{"role": "user", "content": message}],
        #     stream=True,
        #     timeout=120
        # )

        response = session.ask(message, stream=True)
        
        callback = Callback()
        synthesizer = SpeechSynthesizer(
            model=model,
            voice=voice,
            format=AudioFormat.PCM_16000HZ_MONO_16BIT,  # 改为16000Hz
            callback=callback
        )

        content = ""
        think_flag = False
        think_count = 0
        think_idx = 0
        
        for chunk in response:
            # 发送文本
            new_content = chunk.content[len(content):]
            for char in new_content:
                # 确保标签能够正确传输，不被过滤
                # 直接发送字符内容
                yield f"data: {json.dumps({'content': char})}\n\n"
                if char == ">" and think_flag == False:
                    think_count += 1
                    if think_count == 2:
                        think_idx = new_content.find('</think>')  # 在新内容中查找，而不是在content中
                        if think_idx != -1:  # 确保找到了标签
                            logger.info(f"think_idx: {think_idx}, new_content: {new_content}")
                            new_content = new_content[think_idx + 8:]  # 8是'</think>'的长度
                            logger.info(f"处理后的new_content: {new_content}")
                            think_flag = True
                        else:
                            logger.warning(f"未找到</think>标签，当前new_content: {new_content}")
            


            # 发送语音
            if think_flag:
                try:
                    synthesizer.streaming_call(new_content)
                    
                    # 给TTS服务一些时间生成音频
                    await_time = 0
                    while len(callback.audio_chunks) == 0 and await_time < 1.0 and not callback.is_error:
                        time.sleep(0.1)
                        await_time += 0.1
                    
                    # 发送可用的音频数据
                    if callback.audio_chunks:
                        logger.info(f"发送 {len(callback.audio_chunks)} 个音频块")
                        for audio_response in callback.audio_chunks:
                            yield audio_response
                        callback.audio_chunks = []
                except Exception as e:
                    logger.error(f"处理音频时出错: {str(e)}")

            content = chunk.content
        
        # 完成TTS流式合成
        try:
            logger.info("完成TTS流式合成")
            synthesizer.streaming_complete()
            
            # 等待最后的音频数据
            await_time = 0
            while not callback.is_completed and await_time < 2.0 and not callback.is_error:
                time.sleep(0.1)
                await_time += 0.1
            
            # 发送剩余的音频数据
            if callback.audio_chunks:
                logger.info(f"发送剩余的 {len(callback.audio_chunks)} 个音频块")
                for audio_response in callback.audio_chunks:
                    yield audio_response
        except Exception as e:
            logger.error(f"完成音频合成时出错: {str(e)}")
    
    except Exception as e:
        logger.error(f"生成响应时出错: {str(e)}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    finally:
        logger.info("响应生成完成，发送[DONE]标记")
        yield "data: [DONE]\n\n"

@csrf_exempt
def chat_with_model(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        message = data.get('message', '')
        
        # 返回流式响应
        response = StreamingHttpResponse(
            generate_response(message),
            content_type='text/event-stream'
        )
        # 只保留必要的响应头
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        # 移除 Connection 头部

        print("response:", response)
        return response

    return JsonResponse({'error': '不支持的请求方法'}, status=400)

def get_audio_file(request, file_path):
    try:
        # 确保文件路径不包含目录遍历
        safe_file_path = os.path.basename(file_path)
        full_path = os.path.join(tts_manager.tts_cache_dir, safe_file_path)
        
        # 验证文件是否存在
        if not os.path.exists(full_path):
            logger.error(f"音频文件不存在: {full_path}")
            return JsonResponse({'error': '音频文件不存在'}, status=404)
            
        # 验证文件是否在允许的目录中
        if not os.path.abspath(full_path).startswith(os.path.abspath(tts_manager.tts_cache_dir)):
            logger.error(f"非法的文件路径: {full_path}")
            return JsonResponse({'error': '非法的文件路径'}, status=403)
            
        return FileResponse(open(full_path, 'rb'), content_type='audio/wav')
    except Exception as e:
        logger.error(f"获取音频文件错误: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)