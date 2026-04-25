from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

def list_models():
    print(">>> 正在查询可用模型列表...")
    try:
        models = client.models.list()
        for m in models.data:
            print(f"- {m.id}")
    except Exception as e:
        print(f"!!! 查询失败: {str(e)}")

if __name__ == "__main__":
    list_models()
