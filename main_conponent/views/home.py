from django.shortcuts import HttpResponse, render
from django.http import JsonResponse, StreamingHttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import time
from ..services.ragflow_service import RagFlowService
from openai import OpenAI
import dashscope
from ..services.tts_service import TTSManager
import asyncio
from asgiref.sync import sync_to_async
import os

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化RagFlow服务
# 这些配置应该从环境变量或配置文件中读取
RAGFLOW_API_KEY = "ragflow-Q4NDg1OWU2MDQ4YTExZjBhYjQwMDI0Mm"  # 替换为实际的API密钥
RAGFLOW_BASE_URL = "http://192.168.101.206:80"  # 替换为实际的RagFlow地址
RAGFLOW_CHAT_ID = "0cca3740057e11f0b0320242ac120004"
RAGFLOW_MODEL = "qwq-32b@Tongyi-Qianwen"

ragflow_service = RagFlowService(
    api_key=RAGFLOW_API_KEY,
    base_url=RAGFLOW_BASE_URL,
    model_name=RAGFLOW_MODEL,
    chat_id=RAGFLOW_CHAT_ID
)

tts_manager = TTSManager()

def home_page(request):
    # 简化视图，不再使用数据库
    return render(request, 'home.html')

# 设置模型
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

def generate_response(message):
    """生成流式响应"""
    try:
        yield 'retry: 1000\n\n'
        
        try:
            response = ragflow_service.client.chat.completions.create(
                model=ragflow_service.model_name,
                messages=[
                    {"role": "system", "content": "你是一个有用的助手。"},
                    {"role": "user", "content": message}
                ],
                stream=True,
                timeout=120
            )
        except Exception as e:
            logger.error(f"RagFlow服务连接错误: {str(e)}")
            yield f"data: {json.dumps({'error': '服务连接超时，请重试'})}\n\n"
            return

        current_sentence = ""
        
        def clean_text(text):
            """清理文本，移除不可见字符和特殊字符"""
            import re
            # 保留中文、英文、数字、基本标点
            text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9，。！？,.!?、:：""'' ]', '', text)
            # 移除多余的空白字符
            text = ' '.join(text.split())
            return text
        
        try:
            for chunk in response:
                if hasattr(chunk.choices[0].delta, 'content'):
                    content = chunk.choices[0].delta.content
                    if content:
                        # 处理新文本
                        for char in content:
                            current_sentence += char
                            # 发送字符到前端
                            yield f"data: {json.dumps({'content': char})}\n\n"
                            
                            # 检查是否句子结束
                            if char in ['。', '！', '？', '.', '!', '?']:
                                try:
                                    # 清理并检查句子
                                    cleaned_sentence = clean_text(current_sentence)
                                    if cleaned_sentence.strip():
                                        # 异步生成语音
                                        audio_path = asyncio.run(tts_manager.synthesize_speech(cleaned_sentence))
                                        file_name = os.path.basename(audio_path)
                                        # 发送语音文件路径
                                        yield f"data: {json.dumps({'audio_path': file_name, 'text': cleaned_sentence})}\n\n"
                                    # 清空当前句子
                                    current_sentence = ""
                                except Exception as e:
                                    logger.error(f"语音合成错误: {str(e)}")
                                    yield f"data: {json.dumps({'error': f'语音合成错误: {str(e)}'})}\n\n"
        except Exception as e:
            logger.error(f"流式响应错误: {str(e)}")
            yield f"data: {json.dumps({'error': '响应处理错误，请重试'})}\n\n"
            return
        
        # 处理最后一个不完整的句子
        if current_sentence:
            try:
                # 清理并检查最后的句子
                cleaned_sentence = clean_text(current_sentence)
                if cleaned_sentence.strip():
                    audio_path = asyncio.run(tts_manager.synthesize_speech(cleaned_sentence))
                    file_name = os.path.basename(audio_path)
                    yield f"data: {json.dumps({'audio_path': file_name, 'text': cleaned_sentence})}\n\n"
            except Exception as e:
                logger.error(f"语音合成错误: {str(e)}")
                yield f"data: {json.dumps({'error': f'语音合成错误: {str(e)}'})}\n\n"
        
        yield "data: [DONE]\n\n"
                    
    except Exception as e:
        logger.error(f"生成响应错误: {str(e)}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@csrf_exempt
def chat_with_model(request):
    if request.method == 'POST':
        try:
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
            return response
            
        except Exception as e:
            logger.error(f"处理请求错误: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)
            
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