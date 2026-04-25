import os
import json
from openai import OpenAI

keys = {
    "VISION_PRIMARY": "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",
    "PARSER_NODE": "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",
    "REWARD_SCORING": "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"
}

out = {}

def get_list(k_name, key_val):
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key_val
    )
    try:
        models = client.models.list()
        m_list = [m.id for m in models.data]
        res = {
            "has_vision": "meta/llama-3.2-90b-vision-instruct" in m_list,
            "has_tactical": "meta/llama-3.1-8b-instruct" in m_list,
            "has_tactical_70b": "nvidia/llama-3.1-nemotron-70b-instruct" in m_list,
            "parse": [m for m in m_list if "parse" in m.lower()],
            "reward": [m for m in m_list if "reward" in m.lower()]
        }
        out[k_name] = res
    except Exception as e:
        out[k_name] = str(e)

for k, v in keys.items():
    get_list(k, v)

with open('out.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2)
