# day6_plan_execute_with_reflection.py
import json
import asyncio
from openai import AsyncOpenAI

# ===== 配置区 =====
API_KEY = "sEQHDYhv8N1dq0WI4KL0fwg"   # 替换！
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# =================

client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

# ==========================================
# 1. 工具定义（模拟脆弱性，用于演示反思）
# ==========================================
async def get_current_weather(location: str):
    """查天气（故意只支持三个城市，触发反思）"""
    weather_db = {
        "北京": "25°C 晴朗",
        "上海": "28°C 多云",
        "深圳": "30°C 阵雨",
    }
    # 如果查不到，返回错误信息，触发反思
    if location not in weather_db:
        return f"ERROR: 未找到 '{location}' 的天气数据。"
    return weather_db[location]

async def calculate(expression: str):
    """数学计算（模拟）"""
    try:
        allowed = "0123456789+-*/(). "
        cleaned = ''.join(c for c in expression if c in allowed)
        result = eval(cleaned)
        return f"{expression} = {result}"
    except Exception as e:
        return f"ERROR: 计算错误 - {str(e)}"

TOOLS_MAP = {
    "get_current_weather": get_current_weather,
    "calculate": calculate,
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "获取指定城市的天气",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学运算",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        },
    },
]

# ==========================================
# 2. 规划器（Planer）- 同前
# ==========================================
async def plan(user_query: str) -> list:
    system_prompt = "你是一个任务规划专家。把目标拆解为3~5个具体步骤，每步以'步骤X:'开头。"
    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户目标：{user_query}"}
        ],
        temperature=0.3,
    )
    plan_text = response.choices[0].message.content
    steps = []
    for line in plan_text.strip().split("\n"):
        line = line.strip()
        if line and ("步骤" in line or "Step" in line):
            step_desc = line.split(":", 1)[-1].strip() if ":" in line else line
            steps.append(step_desc)
    if not steps:
        steps = [plan_text]
    
    print(f"📋 规划完成，共 {len(steps)} 步")
    for i, s in enumerate(steps, 1):
        print(f"  步骤{i}: {s}")
    return steps

# ==========================================
# 3. 执行器（Executor）- 执行单个动作
# ==========================================
async def execute_action(step_desc: str, context: str) -> str:
    """执行一步，返回工具执行结果"""
    system_prompt = f"当前上下文：{context}\n请根据步骤描述调用工具。步骤：{step_desc}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"执行：{step_desc}"}
    ]
    
    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=TOOLS_SCHEMA,
        tool_choice="auto",
    )
    assistant_msg = response.choices[0].message

    if assistant_msg.tool_calls:
        results = []
        for tool_call in assistant_msg.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            print(f"   🔧 调用工具：{func_name}，参数：{func_args}")
            tool_func = TOOLS_MAP.get(func_name)
            result = await tool_func(**func_args) if tool_func else f"未知工具 {func_name}"
            results.append(result)
        return "\n".join(results)
    
    return assistant_msg.content or "执行完成，无具体输出。"

# ==========================================
# 4. ★★★ 核心升级：反思器（Reflector） ★★★
# ==========================================
async def reflect(step_desc: str, raw_result: str) -> dict:
    """
    检查执行结果是否成功。
    返回：{"status": "PASS" / "FAIL", "suggestion": "修正建议"}
    """
    check_prompt = f"""你是一个严格的质量检查员。
目标步骤：{step_desc}
执行结果：{raw_result}

请判断该结果是否成功实现了目标。
- 如果结果中明显包含错误信息（如 ERROR, 失败, 无法, 未找到），或者结果为空，请回复 FAIL。
- 如果结果合理、有效，请回复 PASS。

如果判定为 FAIL，请用一句简短的话给出修正建议（例如：“重新查询广州的天气”或“检查表达式格式”）。

输出格式（严格按此 JSON）：
{{"status": "PASS" 或 "FAIL", "suggestion": "修正建议"}}"""

    try:
        resp = await client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": check_prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = resp.choices[0].message.content
        # 提取 JSON（防止模型加废话）
        start = content.find('{')
        end = content.rfind('}') + 1
        json_str = content[start:end] if start != -1 else content
        result = json.loads(json_str)
        return result
    except Exception as e:
        # 如果解析失败，默认 PASS，避免死循环
        print(f"   ⚠️ 反思器解析异常，默认通过：{e}")
        return {"status": "PASS", "suggestion": ""}

# ==========================================
# 5. 带反思的执行流程（带重试）
# ==========================================
async def execute_step_with_reflection(step_desc: str, context: dict, max_retries: int = 2):
    """执行步骤，如果失败则根据反思建议重试"""
    context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
    
    for attempt in range(1, max_retries + 1):
        print(f"   🏃 尝试第 {attempt} 次执行...")
        
        # 执行动作
        raw_result = await execute_action(step_desc, context_str)
        print(f"   📤 原始结果：{raw_result[:100]}...")
        
        # 调用反思器
        reflection = await reflect(step_desc, raw_result)
        
        if reflection.get("status") == "PASS":
            print(f"   ✅ 反思通过！")
            return raw_result
        else:
            suggestion = reflection.get("suggestion", "请重试")
            print(f"   ❌ 反思失败，建议：{suggestion}")
            
            if attempt < max_retries:
                # 将修正建议注入到上下文中，供下一次重试使用
                context["_retry_hint"] = suggestion
                context_str = context_str + f"\n上次失败原因及修正建议：{suggestion}"
                print(f"   🔄 准备根据建议重试...")
            else:
                print(f"   🚫 达到最大重试次数，返回当前结果（含错误）")
                return raw_result
    
    return "执行失败（多次重试无效）"

# ==========================================
# 6. Plan-and-Execute 总控（带反思）
# ==========================================
async def plan_and_execute(user_query: str):
    print(f"\n🎯 用户目标：{user_query}")
    
    # 阶段1：规划
    steps = await plan(user_query)
    
    # 阶段2：带反思的执行
    context = {}
    for i, step in enumerate(steps, 1):
        print(f"\n🔄 执行步骤 {i}/{len(steps)}：{step}")
        result = await execute_step_with_reflection(step, context)
        context[f"步骤{i}"] = result
    
    # 阶段3：汇总
    print("\n" + "="*60)
    summary_prompt = f"""用户目标：{user_query}
执行结果摘要：{json.dumps(context, ensure_ascii=False, indent=2)}
请生成自然的最终回答。"""
    final = await client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.5,
    )
    print(f"\n🤖 最终回答：\n{final.choices[0].message.content}")

# ==========================================
# 7. 测试入口（专为触发反思设计）
# ==========================================
if __name__ == "__main__":
    print("🚀 启动 带反思的 Plan-and-Execute...\n")
    # 故意问一个“广州”天气，我们的天气库没有广州，会触发反思重试
    asyncio.run(plan_and_execute("查一下广州天气，再算算 10*5 等于多少？"))