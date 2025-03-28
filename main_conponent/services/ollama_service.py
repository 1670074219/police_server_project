import requests
import logging
import time
import json

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaService:
    def __init__(self, model_name="llama2"):
        self.model_name = model_name
        self.base_url = "http://localhost:11434/api"
    
    def generate_response(self, prompt, system_prompt=None):
        """
        向Ollama发送请求并获取回复
        """
        url = f"{self.base_url}/generate"
        
        payload = {
            "model": self.model_name,
            "prompt": prompt,
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        # 记录开始时间
        start_time = time.time()
        
        try:
            logger.info(f"发送请求到Ollama: {url}")
            logger.info(f"请求内容: {payload}")
            
            # 发送请求
            response = requests.post(url, json=payload, timeout=60)
            
            # 记录响应时间
            elapsed_time = time.time() - start_time
            logger.info(f"Ollama响应时间: {elapsed_time:.2f}秒")
            logger.info(f"Ollama响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                # 处理流式响应
                full_response = ""
                for line in response.text.strip().split('\n'):
                    try:
                        if line.strip():
                            result = json.loads(line)
                            if "response" in result:
                                full_response += result["response"]
                    except json.JSONDecodeError as e:
                        logger.warning(f"解析响应行时出错: {e}, 行内容: {line}")
                        continue
                
                if full_response:
                    return full_response
                else:
                    logger.error("没有找到有效的响应内容")
                    return "未能获取到有效的回复内容"
            else:
                error_msg = f"请求失败，状态码: {response.status_code}, 响应内容: {response.text}"
                logger.error(error_msg)
                return error_msg
        except requests.exceptions.ConnectionError:
            error_msg = "无法连接到Ollama服务，请确保Ollama正在运行"
            logger.error(error_msg)
            return error_msg
        except requests.exceptions.Timeout:
            error_msg = "请求超时，Ollama服务响应时间过长"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"发生错误: {str(e)}"
            logger.exception(error_msg)
            return error_msg 