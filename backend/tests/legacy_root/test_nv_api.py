from openai import OpenAI
import sys

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

def test_api():
    print(">>> 正在启动诊断任务...")
    try:
        # 测试较小的模型以确保速度和兼容性
        completion = client.chat.completions.create(
            model="meta/llama-3.1-8b-instruct",
            messages=[{"role":"user","content":"Hello, respond with 'ON' if you are active."}],
            max_tokens=10
        )
        print(f">>> API 通讯结果: {completion.choices[0].message.content}")
    except Exception as e:
        print(f"!!! 侦测到致命错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    test_api()
