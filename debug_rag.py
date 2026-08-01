# debug_rag.py
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# ！！！请务必把下面这行换成你自己的真实 API Key！！！
API_KEY = "4KL0fwg"

# 1. 初始化 embedding 配置（必须和 build_index.py 完全一致）
embedding_fn = OpenAIEmbeddingFunction(
    api_key=API_KEY,
    model_name="text-embedding-v3",
    api_base="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 2. 连接到现有的向量库
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_collection(
    name="knowledge",
    embedding_function=embedding_fn
)

# 3. 查看库里到底有多少条数据
print(f"【检查结果】知识库中的文档块总数：{collection.count()}")

if collection.count() > 0:
    # 取前两条看看内容
    sample = collection.get(limit=2)
    print("【检查结果】存储的样例内容：", sample['documents'])
    
    # 4. 模拟查询，验证检索逻辑是否正常
    test_results = collection.query(query_texts=["价格"], n_results=2)
    print("【检查结果】查询‘价格’返回的结果：", test_results['documents'])
else:
    print("【检查结果】❌ 知识库是空的！这说明 build_index.py 没有成功把数据存进去。")