# 智警实战综合训练平台 (CAPTP) 增强版配置文件

# 核心 API 配置
NVIDIA_API_KEY = "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"

# 专项模型 API Keys
KEYS = {
    "VISION_PRIMARY": "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",
    "PARSER_NODE": "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",
    "REWARD_SCORING": "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"
}

# 模型路由配置
MODELS = {
    "VISION": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "VISION_FALLBACK": "microsoft/phi-3.5-vision-instruct",
    "TACTICAL": "qwen/qwen2.5-7b-instruct",
    "TACTICAL_FALLBACK": "qwen/qwen2-7b-instruct",
    "PARSER": "nvidia/nemotron-parse", # 映射到 nemotron-parse 逻辑
    "REWARD": "nvidia/llama-3.1-nemotron-70b-reward"
}

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
