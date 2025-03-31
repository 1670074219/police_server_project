import logging
import time
from openai import OpenAI

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RagFlowService:
    def __init__(self, api_key, base_url, model_name, chat_id):
        self.api_key = api_key
        self.base_url = f"{base_url}/api/v1/chats_openai/{chat_id}"
        self.model_name = model_name
        self.chat_id = chat_id
        
        # 初始化 OpenAI 客户端，添加超时和重试设置
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=120.0,  # 增加超时时间到120秒
            max_retries=5,  # 增加重试次数
            default_headers={
                "Content-Type": "application/json",
                "Connection": "keep-alive"
            }
        )
    
    def generate_response(self, prompt, system_prompt=None):
        """
        向RagFlow发送请求并获取回复
        """
        # 记录开始时间
        start_time = time.time()
        
        # 检查客户端是否已初始化
        if not self.client:
            return "请先选择一个助手模型"
        
        # 构建消息列表
        messages = []
        
        # 添加系统提示（如果有）
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 添加用户消息
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"发送请求到RagFlow: {self.base_url}")
            logger.info(f"使用模型: {self.model_name}")
            logger.info(f"请求内容: {messages}")
            
            # 发送请求
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=False  # 不使用流式响应
            )
            
            # 检查completion是否为None
            if not completion:
                logger.error("RagFlow返回了空的completion对象")
                return "模型未返回响应"
                
            logger.info(f"RagFlow返回的completion对象: {completion}")
            
            # 记录响应时间
            elapsed_time = time.time() - start_time
            logger.info(f"RagFlow响应时间: {elapsed_time:.2f}秒")
            
            # 获取响应内容
            response = completion.choices[0].message.content
            logger.info(f"RagFlow响应内容: {response[:100]}...")
            
            return response
            
        except Exception as e:
            error_msg = f"RagFlow请求失败: {str(e)}"
            logger.exception(error_msg)
            return error_msg 