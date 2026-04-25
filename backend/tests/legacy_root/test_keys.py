import os
from openai import OpenAI

keys = {
    "VISION_PRIMARY": "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",
    "PARSER_NODE": "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",
    "REWARD_SCORING": "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"
}

def list_models_for_key(k_name, key_val):
    print(f"\n--- Testing Key: {k_name} ---")
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key_val
    )
    try:
        models = client.models.list()
        m_list = [m.id for m in models.data]
        if "meta/llama-3.2-90b-vision-instruct" in m_list:
            print("[✓] meta/llama-3.2-90b-vision-instruct available")
        else:
            print("[x] meta/llama-3.2-90b-vision-instruct NOT available")
            
        if "meta/llama-3.1-8b-instruct" in m_list:
            print("[✓] meta/llama-3.1-8b-instruct available")
        else:
            print("[x] meta/llama-3.1-8b-instruct NOT available")

        nem_parse = [m for m in m_list if "parse" in m.lower()]
        nem_reward = [m for m in m_list if "reward" in m.lower()]
        print(f"Parser matches: {nem_parse}")
        print(f"Reward matches: {nem_reward}")
    except Exception as e:
        print(f"Error checking {k_name}: {e}")

for k, v in keys.items():
    list_models_for_key(k, v)
