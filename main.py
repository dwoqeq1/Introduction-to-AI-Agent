# main.py (RAG 完整版，已修正安全与重复问题)
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from openai import AsyncOpenAI
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# ---------- 初始化 FastAPI ----------
app = FastAPI(title="RAG Agent 接口")

# ---------- 初始化大模型客户端（只保留一个） ----------
client = AsyncOpenAI(
    api_key="fwg",   # ← 务必更换为新的 Key
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# ---------- 初始化 Embedding 客户端（用于向量检索） ----------
embedding_client = AsyncOpenAI(
    api_key="sk-ws-H.EIRLREX.eYMk.MEUCIES6DugE0RxhZtd5Ja3YYN19jyIrXyC9DQIT9mFOpRbLAiEAmwx1cPwsGCqYCqFvVP-5xEQHDYhv8N1dq0WI4KL0fwg",   # 同一个 Key 即可
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# ---------- 初始化 Chroma 向量库 ----------
# 使用 OpenAIEmbeddingFunction 兼容阿里云 embedding
embedding_fn = OpenAIEmbeddingFunction(
    api_key="sk-ws-H.EIRLREX.eYMk.MEUCIES6DugE0RxhZtd5Ja3YYN19jyIrXyC9DQIT9mFOpRbLAiEAmwx1cPwsGCqYCqFvVP-5xEQHDYhv8N1dq0WI4KL0fwg",
    model_name="text-embedding-v3",
    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(
    name="knowledge",
    embedding_function=embedding_fn
)

# ---------- 请求模型 ----------
class ChatRequest(BaseModel):
    user_message: str
    history: list = []      # 历史对话
    top_k: int = 3          # 检索返回的文档块数量

# ---------- 检索函数 ----------
async def retrieve_docs(query: str, history: list, top_k: int = 3):
    # ★ 将历史对话拼接到查询中，解决“那它呢”这类指代问题
    if history:
        recent_history = history[-4:]  # 取最近 4 条（2问2答）
        context_str = " ".join([item["content"] for item in recent_history])
        enhanced_query = f"{context_str} {query}"
    else:
        enhanced_query = query
    
    try:
        results = collection.query(
            query_texts=[enhanced_query],
            n_results=top_k
        )
        if results['documents'] and results['documents'][0]:
            return results['documents'][0]
        return []
    except Exception as e:
        print(f"检索失败: {e}")
        return []
    try:
        results = collection.query(
            query_texts=[query],
            n_results=top_k
        )
        if results['documents'] and results['documents'][0]:
            return results['documents'][0]   # 返回文档列表
        return []
    except Exception as e:
        print(f"检索失败: {e}")
        return []

# ---------- 流式生成器（含 RAG） ----------
async def generate_stream(user_msg: str, history: list, top_k: int):
    # 1. 检索相关文档
    retrieved_docs = await retrieve_docs(user_msg, history, top_k)
    print("检索到的资料：", retrieved_docs)
	
    # 2. 构建系统 prompt
    if retrieved_docs:
        context = "\n\n".join(retrieved_docs)
        system_prompt = f"""你是一个基于知识库的问答助手。请根据以下参考资料回答用户问题，如果参考资料中没有相关信息，则诚实地说“根据现有知识，我无法回答该问题”。
        === 参考资料 ===
        {context}
        === 参考结束 ===
        """
    else:
        system_prompt = "你是一个乐于助人的AI助手，请基于你的通用知识回答问题。"

    # 3. 组装 messages
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    print("\n=== 发送给大模型的完整 messages ===")
    import json
    print(json.dumps(messages, ensure_ascii=False, indent=2))
    print("====================================\n")
    # 4. 调用大模型（流式）
    stream = await client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        stream=True,
        temperature=0.3   # 低温度提高事实性
    )

    # 5. 按 SSE 输出
    async for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
    yield f"data: [DONE]\n\n"

# ---------- 路由 ----------
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(
        generate_stream(req.user_message, req.history, req.top_k),
        media_type="text/event-stream"
    )

# ---------- 测试页面（增加 top_k 参数） ----------
@app.get("/")
async def get_test_page():
    html_content = """
    <html>
        <body>
            <h2>RAG 智能问答测试</h2>
            <input type="text" id="msg" placeholder="输入问题..." style="width:300px;">
            <button onclick="sendMsg()">发送</button>
            <p style="font-size:0.9em;color:#666;">（知识库：示例产品手册）</p>
            <h3>AI 回复：</h3>
            <div id="response" style="white-space: pre-wrap; border: 1px solid #ccc; padding: 10px; min-height: 100px;"></div>
            <script>
                async function sendMsg() {
                    const msg = document.getElementById('msg').value;
                    const resDiv = document.getElementById('response');
                    resDiv.innerHTML = '';
                    
                    const response = await fetch('/api/chat/stream', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            user_message: msg,
                            top_k: 3
                        })
                    });
                    
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    
                    while(true) {
                        const {done, value} = await reader.read();
                        if(done) break;
                        
                        const text = decoder.decode(value);
                        const lines = text.split('\\n\\n');
                        for(let line of lines) {
                            if(line.startsWith('data: ')) {
                                const data = line.substring(6);
                                if(data === '[DONE]') break;
                                try {
                                    const json = JSON.parse(data);
                                    resDiv.innerHTML += json.content;
                                } catch(e) {}
                            }
                        }
                    }
                }
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)