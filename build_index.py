# build_index.py (智能分块版)
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ========== 1. 配置（请替换为你的真实 Key）==========
API_KEY = "sk-ws-H.EIRLREX.eYMk.MEUCIES6DugE0RxhZtd5Ja3YYN19jyIrXyC"   # 这里填你自己的完整 Key
# =================================================

# 2. 初始化 Embedding 函数（必须和 main.py 保持一致）
embedding_fn = OpenAIEmbeddingFunction(
    api_key=API_KEY,
    model_name="text-embedding-v3",
    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 3. 连接向量库（每次重建，防止旧数据干扰）
chroma_client = chromadb.PersistentClient(path="./chroma_db")
try:
    chroma_client.delete_collection("knowledge")  # 删掉旧集合
except:
    pass
collection = chroma_client.create_collection(
    name="knowledge",
    embedding_function=embedding_fn
)

# 4. 读取你的文档
with open("knowledge/example.txt", "r", encoding="utf-8") as f:
    text = f.read()

# 5. ★★★ 核心升级：递归分块（自动适应中文）★★★
splitter = RecursiveCharacterTextSplitter(
    chunk_size=200,        # 每块约 200 个字符（适合中文语义）
    chunk_overlap=30,      # 重叠 30 个字符，防止关键信息被切断
    separators=["\n\n", "\n", "。", "，", " ", ""]  # 优先按段落、句子切
)
chunks = splitter.split_text(text)

print(f"原文档长度：{len(text)} 字符，被切分为 {len(chunks)} 个语义块。")

# 6. 生成 ID 和元数据
ids = [f"chunk_{i}" for i in range(len(chunks))]
metadatas = [{"source": "example.txt", "index": i} for i in range(len(chunks))]

# 7. 存入向量库
collection.add(
    documents=chunks,
    ids=ids,
    metadatas=metadatas
)

print("✅ 智能分块数据入库成功！")
print("前 3 块预览：")
for i in range(min(3, len(chunks))):
    print(f"块{i+1}: {chunks[i][:50]}...")