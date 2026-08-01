# day5_multi_tools.py (修好缩进 + 删除重复函数)

import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from openai import AsyncOpenAI

# ================= 配置区（请你修改这里！）=================
# 1. 你的发件邮箱和授权码（用于真实发邮件）
SENDER_EMAIL = "110@qq.com"   # 改成你的QQ邮箱
AUTH_CODE   = "qaq"       # 改成你的授权码（不是密码）

# 2. 你的阿里云百炼 API Key
API_KEY = "sk-ws-H.EIRLREX.eYMk.MEUCIES6DugE0RxhZtd5Ja3YYN19jyIrXyC9DQIT9mFOpRbLAiEAmwx1cPwsGCqYCqFvVP-5xEQHDYhv8N1dq0WI4KL0fwg"   # 请换成你自己的真实完整Key
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# ==========================================================

# 初始化大模型客户端
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)


# ==========================================
# 1. 定义三个“本地工具”的具体实现
# ==========================================

# 工具1：查天气（模拟）
async def get_current_weather(location: str, unit: str = "celsius"):
    weather_db = {
        "北京": {"celsius": "25°C", "condition": "晴朗"},
        "上海": {"celsius": "28°C", "condition": "多云"},
        "深圳": {"celsius": "30°C", "condition": "阵雨"},
    }
    info = weather_db.get(location, {"celsius": "未知", "condition": "数据未覆盖"})
    return f"{location}天气：{info['condition']}，温度 {info.get(unit, info['celsius'])}"


# 工具2：发送真实邮件（缩进已修正）
async def send_email(recipient: str, subject: str, body: str):
    try:
        # 构造邮件
        message = MIMEText(body, 'plain', 'utf-8')
        message['From'] = Header(SENDER_EMAIL)
        message['To'] = Header(recipient)
        message['Subject'] = Header(subject, 'utf-8')

        # 连接 QQ 邮箱 SMTP 服务器（SSL）
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SENDER_EMAIL, AUTH_CODE)
        server.sendmail(SENDER_EMAIL, [recipient], message.as_string())
        server.quit()

        return f"✅ 邮件已成功发送至 {recipient}，主题：{subject}"
    except Exception as e:
        # 注意这里 except 与 try 对齐，没有多余缩进
        return f"❌ 邮件发送失败，错误信息：{str(e)}"


# 工具3：数学计算（模拟）
async def calculate(expression: str):
    try:
        allowed = "0123456789+-*/(). "
        cleaned = ''.join(c for c in expression if c in allowed)
        result = eval(cleaned)
        return f"计算结果：{expression} = {result}"
    except Exception as e:
        return f"计算错误：{str(e)}"


# ==========================================
# 2. 工具注册表（路由）
# ==========================================
TOOLS_MAP = {
    "get_current_weather": get_current_weather,
    "send_email": send_email,
    "calculate": calculate,
}

# ==========================================
# 3. 工具描述（JSON Schema，供大模型理解）
# ==========================================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "获取指定城市的当前天气情况",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称，如：北京、上海"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "温度单位，默认为 celsius"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "向指定邮箱发送一封邮件",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "description": "收件人邮箱地址"},
                    "subject": {"type": "string", "description": "邮件主题"},
                    "body": {"type": "string", "description": "邮件正文内容"},
                },
                "required": ["recipient", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行基础数学运算（加减乘除）",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如：'3 + 5 * 2'"},
                },
                "required": ["expression"],
            },
        },
    },
]


# ==========================================
# 4. 核心 Agent 引擎（无需修改）
# ==========================================
async def run_agent(user_query: str):
    print(f"\n👤 用户问：{user_query}")
    messages = [{"role": "user", "content": user_query}]

    # 第一轮：大模型决定是否调用工具
    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=TOOLS_SCHEMA,
        tool_choice="auto",
    )
    assistant_msg = response.choices[0].message

    if not assistant_msg.tool_calls:
        print(f"🤖 直接回答：{assistant_msg.content}")
        return assistant_msg.content

    # 第二轮：执行工具调用
    messages.append(assistant_msg)
    for tool_call in assistant_msg.tool_calls:
        func_name = tool_call.function.name
        func_args = json.loads(tool_call.function.arguments)
        print(f"🧠 调用工具：{func_name}，参数：{func_args}")

        tool_func = TOOLS_MAP.get(func_name)
        if tool_func:
            result = await tool_func(**func_args)
        else:
            result = f"错误：未找到工具 {func_name}"
        print(f"🔧 工具返回：{result}")

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        })

    # 第三轮：生成最终回答
    final_response = await client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
    )
    final_answer = final_response.choices[0].message.content
    print(f"🤖 最终回答：{final_answer}")
    return final_answer


# ==========================================
# 5. 测试入口
# ==========================================
if __name__ == "__main__":
    print("🚀 启动 多工具 Agent 演示...\n")
    asyncio.run(run_agent("上海今天天气如何？"))
    print("\n" + "="*60 + "\n")
    asyncio.run(run_agent("帮我算一下 (100 + 200) * 3 等于多少？"))
    print("\n" + "="*60 + "\n")
    asyncio.run(run_agent("给 QAQ@3.com 发一封邮件，主题是‘周报’，正文写‘本周项目进展顺利’"))