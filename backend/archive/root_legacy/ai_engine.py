import base64
import requests
from openai import OpenAI
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, MODELS

class CAPTPEngine:
    """智警 AI 实战引擎 - 封装 NVIDIA NIM 调用逻辑"""
    def __init__(self):
        self.client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=NVIDIA_API_KEY
        )

    def analyze_frame(self, image_bytes, prompt, mode="vision"):
        """
        全场景视觉分析：支持射击姿态、格斗评分、弹孔识别
        """
        model_name = MODELS.get(mode, MODELS["vision"])
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        try:
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }],
                max_tokens=1024,
                temperature=0.2
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"🚨 AI 引擎分析失败: {str(e)}"

    def simulate_decision(self, history):
        """
        案件决策推演：利用强推理模型进行情景生成与逻辑博弈
        """
        try:
            response = self.client.chat.completions.create(
                model=MODELS["tactical"],
                messages=history,
                max_tokens=2048,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"🚨 战术推演链路异常: {str(e)}"
