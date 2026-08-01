# day6_plan_execute.py
import json
import asyncio
from openai import AsyncOpenAI

# ===== 配置区 =====
API_KEY = "4KL0fwg"   # 替换！
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# =================

client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)


# ==========================================
# 1. 定义“可用工具”（和之前一样，但为了演示，我们只保留两个）
# ==========================================
async def get_current_weather(location: str):
    """查天气"""
    weather_db = {
        "北京": "25°C 晴朗",
        "上海": "28°C 多云",
        "深圳": "30°C 阵雨",
    }
    return weather_db.get(location, f"{location} 天气数据未覆盖")


async def calculate(expression: str):
    """数学计算"""
    try:
        allowed = "0123456789+-*/(). "
        cleaned = ''.join(c for c in expression if c in allowed)
        result = eval(cleaned)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算错误：{str(e)}"


# 工具注册表
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
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名"},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学运算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式"},
                },
                "required": ["expression"],
            },
        },
    },
]


# ==========================================
# 2. 核心：规划器（Planer）
# ==========================================
async def plan(user_query: str) -> list:
    """
    让大模型把用户问题拆解成 3~5 步计划
    返回一个列表，每一步是一个字符串描述
    """
    system_prompt = """你是一个任务规划专家。请把用户的目标拆解为 3~5 个具体的、可执行的步骤。
    每一步必须用 '步骤X: ' 开头，并且只描述要做什么，不需要输出结果。
    步骤之间要有逻辑顺序，后一步依赖前一步的结果。
    只输出步骤列表，不要有其他废话。"""

    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户目标：{user_query}"}
        ],
        temperature=0.3,
    )

    plan_text = response.choices[0].message.content
    print(f"📋 规划器生成的原始计划：\n{plan_text}")

    # 解析步骤（假设每行以 "步骤X:" 开头）
    steps = []
    for line in plan_text.strip().split("\n"):
        line = line.strip()
        if line and ("步骤" in line or "Step" in line):
            # 去掉序号前缀，只保留描述
            step_desc = line.split(":", 1)[-1].strip() if ":" in line else line
            steps.append(step_desc)
    
    # 如果解析失败，用整段文字作为唯一步骤
    if not steps:
        steps = [plan_text]
    
    print(f"✅ 解析后的步骤列表（共 {len(steps)} 步）：")
    for i, s in enumerate(steps, 1):
        print(f"  步骤{i}: {s}")
    
    return steps


# ==========================================
# 3. 核心：执行器（Executor）
# ==========================================
async def execute_step(step_desc: str, context: dict) -> str:
    """
    执行单一步骤：大模型根据步骤描述，决定调用哪个工具并返回结果
    context 里存放之前步骤的结果，供后续步骤参考
    """
    # 把历史上下文拼成提示
    context_str = "\n".join([f"之前步骤结果：{v}" for v in context.values()])
    system_prompt = f"""你是一个任务执行专家。当前已有的上下文信息：
{context_str}

请根据当前步骤的描述，调用合适的工具来完成它。如果不需要工具，直接给出答案。
当前步骤：{step_desc}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请执行步骤：{step_desc}"}
    ]

    # 调用大模型，带上工具
    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=TOOLS_SCHEMA,
        tool_choice="auto",
    )

    assistant_msg = response.choices[0].message

    # 如果大模型决定调用工具
    if assistant_msg.tool_calls:
        results = []
        for tool_call in assistant_msg.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)
            print(f"   🔧 调用工具：{func_name}，参数：{func_args}")

            tool_func = TOOLS_MAP.get(func_name)
            if tool_func:
                result = await tool_func(**func_args)
            else:
                result = f"错误：未找到工具 {func_name}"
            results.append(result)
        
        # 把工具结果组合成一个字符串
        step_result = "\n".join(results)
        print(f"   📤 步骤结果：{step_result}")
        return step_result

    # 如果大模型直接回答（不需要工具）
    answer = assistant_msg.content
    print(f"   💬 直接回答：{answer}")
    return answer


# ==========================================
# 4. 核心：Plan-and-Execute 总控制器
# ==========================================
async def plan_and_execute(user_query: str):
    print(f"\n🎯 用户目标：{user_query}")
    
    # 阶段1：规划
    steps = await plan(user_query)
    
    # 阶段2：执行（顺序执行，每步结果存入 context）
    context = {}
    for i, step in enumerate(steps, 1):
        print(f"\n🔄 执行步骤 {i}/{len(steps)}：{step}")
        result = await execute_step(step, context)
        context[f"步骤{i}"] = result
    
    # 阶段3：汇总
    print("\n" + "="*60)
    print("📊 汇总所有步骤结果：")
    for key, val in context.items():
        print(f"  {key}: {val}")
    
    # 让大模型生成最终总结
    summary_prompt = f"""用户最初的目标是：{user_query}
    
以下是执行每个步骤得到的结果：
{json.dumps(context, ensure_ascii=False, indent=2)}

请根据这些结果，给用户一个完整、自然的最终回答。"""
    
    final_response = await client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.5,
    )
    
    final_answer = final_response.choices[0].message.content
    print(f"\n🤖 最终回答：\n{final_answer}")
    return final_answer


# ==========================================
# 5. 测试入口
# ==========================================
if __name__ == "__main__":
    print("🚀 启动 Plan-and-Execute 演示...\n")
    
    # 一个需要多步推理的复杂任务
    asyncio.run(plan_and_execute(
        "我想去上海玩，查一下上海天气，然后帮我算算如果待3天，每天打车花费50元，总共需要多少交通费？"
    ))