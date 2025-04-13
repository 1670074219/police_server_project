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
from ..services.tts_service import TTSManager
from ..services.ragflow_service import RagFlowService
from openai import OpenAI
from ..services.tts_service2 import synthesizer
import dashscope
from dashscope.audio.tts_v2 import *

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

def generate_response(message):
    """生成流式响应"""

    current_sentence = ""
    sentence_index = 0  
    speech_tasks = []  

    yield 'retry: 1000\n\n'
    
    response = ragflow_service.client.chat.completions.create(
        model=ragflow_service.model_name,
        messages=[
            {"role": "user", "content": message}
        ],
        stream=True,
        timeout=120
    )


    for chunk in response:
        content = chunk.choices[0].delta.content

        if not content:
            continue

        synthesizer.streaming_call(content)
        time.sleep(0.1)


        for char in content:
            current_sentence += char
            
            yield f"data: {json.dumps({'content': char})}\n\n"
            
    
            # if char in ['。', '！', '？', '.', '!', '?']:
            #     cleaned_sentence = clean_text(current_sentence)
            #     if cleaned_sentence.strip() and is_valid_sentence(cleaned_sentence):
            #         current_index = sentence_index  
            #         sentence_index += 1  

            #         task = threading.Thread(
            #             target=lambda: speech_tasks.append((current_index, cleaned_sentence, process_speech(cleaned_sentence, current_index)))
            #         )
            #         task.daemon = True
            #         task.start()
                
            #     current_sentence = ""

        # completed_tasks = []
        # for i, (idx, sentence, result) in enumerate(speech_tasks):
        #     if result is not None:  
        #         task_idx, file_name = result
        #         if file_name: 
        #             yield f"data: {json.dumps({'audio_path': file_name, 'text': sentence, 'sentence_index': task_idx})}\n\n"
        #         completed_tasks.append(i)

        # for i in sorted(completed_tasks, reverse=True):
        #     speech_tasks.pop(i)
    synthesizer.streaming_complete()
                
    # if current_sentence:
    #     cleaned_sentence = clean_text(current_sentence)
    #     if cleaned_sentence.strip() and is_valid_sentence(cleaned_sentence):
    #         current_index = sentence_index
    #         audio_path = asyncio.run(tts_manager.synthesize_speech(cleaned_sentence))
    #         file_name = os.path.basename(audio_path)
    #         yield f"data: {json.dumps({'audio_path': file_name, 'text': cleaned_sentence, 'sentence_index': current_index})}\n\n"
    
    # 等待所有语音合成任务完成
    # while speech_tasks:
    #     completed_tasks = []
    #     for i, (idx, sentence, result) in enumerate(speech_tasks):
    #         if result is not None:  # 任务已完成
    #             task_idx, file_name = result
    #             if file_name:  # 成功
    #                 yield f"data: {json.dumps({'audio_path': file_name, 'text': sentence, 'sentence_index': task_idx})}\n\n"
    #             completed_tasks.append(i)
        
    #     # 移除已完成的任务
    #     for i in sorted(completed_tasks, reverse=True):
    #         speech_tasks.pop(i)
        
    #     if speech_tasks:  # 如果还有未完成的任务，等待一下
    #         time.sleep(0.1)
    
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