from django.shortcuts import HttpResponse, render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
import time
from ..services.ragflow_service import RagFlowService
from openai import OpenAI

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

@csrf_exempt
def chat_with_model(request):
    if request.method == 'POST':
        start_time = time.time()
        try:
            # 记录请求体
            body = request.body.decode('utf-8')
            logger.info(f"收到POST请求: {body}")
            
            data = json.loads(body)
            user_message = data.get('message', '')
            logger.info(f"用户消息: {user_message}")
            
            # 获取模型回复
            logger.info("正在请求RagFlow模型回复...")
            response = ragflow_service.generate_response(user_message)
            
            # 记录响应时间
            elapsed_time = time.time() - start_time
            logger.info(f"总处理时间: {elapsed_time:.2f}秒")
            logger.info(f"模型回复: {response[:100]}...")
            
            return JsonResponse({
                'status': 'success',
                'response': response,
                'elapsed_time': f"{elapsed_time:.2f}"
            })
        except json.JSONDecodeError as json_error:
            error_msg = f"JSON解析错误: {str(json_error)}"
            logger.error(error_msg)
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=400)
        except Exception as e:
            elapsed_time = time.time() - start_time
            error_msg = f"处理请求时出错: {str(e)}"
            logger.error(f"{error_msg}，总耗时: {elapsed_time:.2f}秒")
            return JsonResponse({
                'status': 'error',
                'message': error_msg
            }, status=500)
    
    return JsonResponse({'status': 'error', 'message': '只接受POST请求'}, status=405)