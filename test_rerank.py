# test_rerank.py
from sentence_transformers import CrossEncoder
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# 1. 加载精排模型（BAAI/bge-reranker-base 是开源且支持中文的王者）
print("⏳ 正在加载精排模型（首次运行需下载约 1GB 文件，请稍候）...")
reranker = CrossEncoder('BAAI/bge-reranker-base', max_length=512)
print("✅ 精排模型加载完毕！")

# 2. 配置（和之前一样）
API_KEY = "v8N1dq0WI4KL0fwg"  # 替换成你的

embedding_fn = OpenAIEmbeddingFunction(
    api_key=API_KEY,
    model_name="text-embedding-v3",
    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_collection(
    name="knowledge",
    embedding_function=embedding_fn
)

# 3. 模拟用户提问（故意问得模糊一点，测试精排效果）
query = "企业版有什么特殊权益？"

# 4. 向量库先粗召回（取 top 5）
results = collection.query(query_texts=[query], n_results=5)
if not results['documents'] or not results['documents'][0]:
    print("未检索到资料")
    exit()

candidates = results['documents'][0]
print(f"\n【粗召回阶段】共召回 {len(candidates)} 个候选块：")
for i, doc in enumerate(candidates):
    print(f"  第{i+1}名: {doc[:30]}...")

# 5. ★★★ 核心操作：精排（Rerank）★★★
# 构造 (query, passage) 对
pairs = [[query, doc] for doc in candidates]
# 计算相关性分数（分数越高越相关）
scores = reranker.predict(pairs)

# 6. 按分数从高到低排序
sorted_pairs = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)

print("\n【精排（Rerank）后结果】分数越接近 1 代表越相关：")
for i, (doc, score) in enumerate(sorted_pairs):
    print(f"  第{i+1}名 (分数: {score:.4f}): {doc[:40]}...")