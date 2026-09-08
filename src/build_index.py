# -*- coding: utf-8 -*-
"""build_index.py: 年报全文 -> 切块 -> 向量化 -> 存入 Chroma 向量库。
输入:  data/parsed/*.txt        (parse_pdf.py 产物)
配置:  项目根 .env 中 SILICONFLOW_API_KEY=sk-xxx
输出:  data/chroma/  (本地向量库)
"""
import os, re, time, requests, chromadb
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")                     # 从项目根读 .env

API_KEY = os.getenv("SILICONFLOW_API_KEY")
assert API_KEY, "没读到 key!请在项目根目录建 .env 并写入 SILICONFLOW_API_KEY=sk-xxx"

EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"                    # embedding 模型
CHUNK_SIZE, OVERLAP = 512, 64                  # 与 chunk.py 相同的切块参数
BATCH = 16                                     # 每批传给 API 的文本条数
DB_PATH = ROOT / "data" / "chroma"

def embed_texts(texts: list):
    """把一批文本向量化,返回向量列表(含简单重试)"""
    for attempt in range(3):
        resp = requests.post(EMBED_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": EMBED_MODEL, "input": texts}, timeout=60)
        if resp.status_code == 200:
            data = sorted(resp.json()["data"], key=lambda x: x["index"])
            return [d["embedding"] for d in data]
        print(f"  重试 {attempt+1}/3, HTTP {resp.status_code}: {resp.text[:120]}")
        time.sleep(2 + attempt * 2)
    raise RuntimeError("embedding 多次失败,请检查 key / 模型权限 / 网络")

def chunk_text(text: str):
    """固定字符窗口切块(和 chunk.py 同逻辑)"""
    chunks, last_page, i, n = [], 0, 0, len(text)
    while i < n:
        window = text[i:i + CHUNK_SIZE]
        pages = re.findall(r"PAGE (\d+)", window)
        if pages:
            last_page = int(pages[-1])
        chunks.append((last_page, window))
        i += CHUNK_SIZE - OVERLAP
    return chunks

# --- 1) 先测一个短句:验证 key、模型、网络通不通 ---
print("测试:向量化一个短句...")
v = embed_texts(["你好"])[0]
print(f"OK! 向量维度 = {len(v)} (bge-m3 应为 1024)")

# --- 2) 建/取向量库 ---
client = chromadb.PersistentClient(path=str(DB_PATH))
col = client.get_or_create_collection(
    name="byd_reports", metadata={"hnsw:space": "cosine"})

# --- 3) 逐份年报:切块 -> 分批向量化 -> 入库 ---
PARSED = ROOT / "data" / "parsed"
total = 0
for txt in sorted(PARSED.glob("*.txt")):
    m = re.search(r"(20\d\d)", txt.stem)          # 从文件名提取年份
    year = m.group(1) if m else "unknown"
    chunks = chunk_text(txt.read_text(encoding="utf-8"))

    ids = [f"{txt.stem}_{i}" for i in range(len(chunks))]        # 每条唯一 ID
    docs = [c for _, c in chunks]                                # 文本
    metas = [{"year": year, "page": p} for p, _ in chunks]       # 元数据

    for s in range(0, len(chunks), BATCH):
        e = min(s + BATCH, len(chunks))
        vecs = embed_texts(docs[s:e])
        col.add(ids=ids[s:e], embeddings=vecs,
                documents=docs[s:e], metadatas=metas[s:e])
        print(f"  {txt.stem}: 已入库 {e}/{len(chunks)} 块")
        time.sleep(0.3)                            # 防止触发限流
    total += len(chunks)

print(f"\n全部完成,共 {total} 块入库。向量库位置: {DB_PATH}")