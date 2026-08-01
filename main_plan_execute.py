# main_plan_execute.py
# Plan-and-Execute 流式 API（带进度可视化）

import json
import asyncio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

# ========== 配置区 ==========
API_KEY = "4KL0fwg"   # 替换！
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# ============================

app = FastAPI(title="Plan-and-Execute Agent")
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

# ---------- 定义工具（同之前） ----------
async def get_current_weather(location: str):
    weather_db = {
        "北京": "25°C 晴朗",
        "上海": "28°C 多云",
        "深圳": "30°C 阵雨",
    }
    return weather_db.get(location, f"{location} 天气数据未覆盖")

async def calculate(expression: str):
    try:
        allowed = "0123456789+-*/(). "
        cleaned = ''.join(c for c in expression if c in allowed)
        result = eval(cleaned)
        return f"{expression} = {result}"
    except Exception as e:
        return f"计算错误：{str(e)}"

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

# ---------- 规划器 ----------
async def plan(user_query: str) -> list:
    system_prompt = """你是一个任务规划专家。请把用户目标拆解为3~5个具体步骤。
每一步必须用"步骤X: "开头，只描述要做什么。只输出步骤列表。"""
    response = await client.chat.completions.create(
        model="qwen-plus",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户目标：{user_query}"}
        ],
        temperature=0.3,
    )
    plan_text = response.choices[0].message.content
    # 解析步骤
    steps = []
    for line in plan_text.strip().split("\n"):
        line = line.strip()
        if line and ("步骤" in line or "Step" in line):
            parts = line.split(":", 1)
            step_desc = parts[1].strip() if len(parts) > 1 else line
            steps.append(step_desc)
    return steps if steps else [plan_text]

# ---------- 执行器 ----------
async def execute_step(step_desc: str, context: dict):
    context_str = "\n".join([f"之前结果：{v}" for v in context.values()])
    system_prompt = f"""已有上下文：{context_str}
根据当前步骤调用合适工具。当前步骤：{step_desc}"""
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
        for tc in assistant_msg.tool_calls:
            func_name = tc.function.name
            func_args = json.loads(tc.function.arguments)
            tool_func = TOOLS_MAP.get(func_name)
            result = await tool_func(**func_args) if tool_func else f"未找到工具 {func_name}"
            results.append(result)
        return "\n".join(results)
    return assistant_msg.content or "执行完成（无输出）"

# ---------- 流式核心（SSE） ----------
async def plan_execute_stream(user_query: str):
    # 1. 规划阶段
    steps = await plan(user_query)
    yield f"data: {json.dumps({'type': 'plan', 'steps': steps}, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0.1)  # 让前端感知更新

    # 2. 执行阶段
    context = {}
    for i, step in enumerate(steps, 1):
        # 发送开始执行事件
        yield f"data: {json.dumps({'type': 'step_start', 'step_index': i, 'step_desc': step}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)

        result = await execute_step(step, context)
        context[f"步骤{i}"] = result
        
        # 发送步骤结果
        yield f"data: {json.dumps({'type': 'step_result', 'step_index': i, 'result': result}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)

    # 3. 汇总阶段（发送最终答案）
    summary_prompt = f"""用户目标：{user_query}
各步骤结果：{json.dumps(context, ensure_ascii=False, indent=2)}
请生成最终回答。"""
    final_resp = await client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": summary_prompt}],
        temperature=0.5,
    )
    final_answer = final_resp.choices[0].message.content
    yield f"data: {json.dumps({'type': 'final', 'content': final_answer}, ensure_ascii=False)}\n\n"
    yield f"data: [DONE]\n\n"

# ---------- API 路由 ----------
class ChatRequest(BaseModel):
    user_message: str

@app.post("/api/plan-execute/stream")
async def stream_plan_execute(req: ChatRequest):
    return StreamingResponse(
        plan_execute_stream(req.user_message),
        media_type="text/event-stream"
    )

# ---------- 可视化测试页面 ----------
@app.get("/")
async def get_test_page():
    html = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; background: #f5f7fa; }
            .card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
            .plan-item { background: #e8f4fd; padding: 8px 12px; margin: 5px 0; border-radius: 5px; border-left: 4px solid #2196F3; }
            .step-log { background: #f0f0f0; padding: 8px 12px; margin: 5px 0; border-radius: 5px; font-family: monospace; }
            .step-done { background: #e8f5e9; border-left: 4px solid #4CAF50; }
            .step-running { background: #fff3e0; border-left: 4px solid #FF9800; }
            #response { white-space: pre-wrap; line-height: 1.6; }
            button { background: #2196F3; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
            input { width: 70%; padding: 10px; border: 1px solid #ccc; border-radius: 5px; }
            .status { color: #666; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <h2>🧠 Plan-and-Execute Agent</h2>
        <p class="status">输入复杂任务，AI 会先规划再执行，每一步都可见</p>
        <div class="card">
            <input type="text" id="msg" placeholder="例如：查一下上海天气，并计算3天打车费共多少钱" style="width:70%;">
            <button onclick="sendMsg()">运行 Agent</button>
        </div>
        <div id="planArea" class="card" style="display:none;">
            <h4>📋 规划步骤</h4>
            <div id="planList"></div>
        </div>
        <div id="logArea" class="card" style="display:none;">
            <h4>🔄 执行日志</h4>
            <div id="logList"></div>
        </div>
        <div id="resultArea" class="card" style="display:none;">
            <h4>🤖 最终回答</h4>
            <div id="response"></div>
        </div>

        <script>
        async function sendMsg() {
            const msg = document.getElementById('msg').value;
            if (!msg) return;

            // 重置界面
            document.getElementById('planArea').style.display = 'none';
            document.getElementById('logArea').style.display = 'none';
            document.getElementById('resultArea').style.display = 'none';
            document.getElementById('planList').innerHTML = '';
            document.getElementById('logList').innerHTML = '';
            document.getElementById('response').innerHTML = '';

            const response = await fetch('/api/plan-execute/stream', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({user_message: msg})
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while(true) {
                const {done, value} = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, {stream: true});
                const lines = buffer.split('\\n\\n');
                buffer = lines.pop();

                for (let line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = line.substring(6);
                    if (data === '[DONE]') continue;

                    try {
                        const json = JSON.parse(data);
                        handleEvent(json);
                    } catch(e) {}
                }
            }
        }

        function handleEvent(json) {
            if (json.type === 'plan') {
                // 显示规划
                document.getElementById('planArea').style.display = 'block';
                const list = document.getElementById('planList');
                json.steps.forEach((step, idx) => {
                    const div = document.createElement('div');
                    div.className = 'plan-item';
                    div.textContent = `步骤${idx+1}: ${step}`;
                    div.id = `plan_${idx+1}`;
                    list.appendChild(div);
                });
            } else if (json.type === 'step_start') {
                // 高亮当前执行的步骤
                document.getElementById('logArea').style.display = 'block';
                const el = document.getElementById(`plan_${json.step_index}`);
                if (el) el.style.background = '#fff3e0';
                // 加日志
                const log = document.getElementById('logList');
                const div = document.createElement('div');
                div.className = 'step-log step-running';
                div.textContent = `⏳ 执行步骤 ${json.step_index}: ${json.step_desc}`;
                log.appendChild(div);
            } else if (json.type === 'step_result') {
                // 显示步骤结果
                const logItems = document.getElementById('logList').children;
                if (logItems.length > 0) {
                    const last = logItems[logItems.length - 1];
                    last.className = 'step-log step-done';
                    last.textContent = `✅ 步骤 ${json.step_index} 结果: ${json.result}`;
                }
                const el = document.getElementById(`plan_${json.step_index}`);
                if (el) el.style.background = '#e8f5e9';
            } else if (json.type === 'final') {
                document.getElementById('resultArea').style.display = 'block';
                document.getElementById('response').innerHTML = json.content;
            }
        }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)