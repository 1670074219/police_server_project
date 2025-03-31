from django.shortcuts import HttpResponse, render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import time
from ..services.ragflow_service import RagFlowService
from openai import OpenAI
import dashscope

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
        # 发送心跳保持连接
        yield 'retry: 1000\n\n'  # 重连间隔为1秒
        
        response = ragflow_service.client.chat.completions.create(
            model=ragflow_service.model_name,
            messages=[
                {"role": "user", "content": message}
            ],
            stream=True
        )
        
        for chunk in response:
            if hasattr(chunk.choices[0].delta, 'content'):
                content = chunk.choices[0].delta.content
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
        
        # 发送结束标记
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