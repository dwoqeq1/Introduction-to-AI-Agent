from openai import OpenAI

# 1. 初始化客户端（通义千问）
client = OpenAI(
    api_key="sk-iEAmwx1cPwsGCqYCqFvVP-5xEQHDYhv8N1dq0WI4KL0fwg",          # ← 这里替换
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 2. 构造消息列表
messages = [
    {"role": "system", "content": "你是一个资深的Python后端工程师，回答要简练、直击痛点。"},
    {"role": "user", "content": "FastAPI和Flask有什么区别？"}
]

# 3. 发起请求（非流式）
response = client.chat.completions.create(
    model="qwen-plus",     # 模型名字，通义千问plus版
    messages=messages,
    temperature=0.7,
    top_p=0.8,
    max_tokens=500
)

# 4. 打印结果
print("大模型回复：", response.choices[0].message.content)
print("消耗Token：", response.usage.total_tokens)