# -*- coding: utf-8 -*-
"""search.py: 检索演示 —— 输入问题,从年报库里找出最相关的几块。
运行后输入问题,输 q 退出。
"""
import os, requests, chromadb
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
API_KEY = os.getenv("SILICONFLOW_API_KEY")
assert API_KEY, "没读到 key"

EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
TOP_K = 5                     # 每次返回最相关的 5 块

def embed_one(text: str):
    """把单个文本(你的问题)变成向量"""
    resp = requests.post(EMBED_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
col = client.get_collection("byd_reports")     # 打开之前建的库

print("知识库已就绪(2848 块)。输入你的问题试试,输 q 退出。\n")
while True:
    q = input("问题> ").strip()
    if q.lower() in ("q", "quit", "退出"):
        break
    if not q:
        continue

    qv = embed_one(q)                          # ① 问题也变成向量
    res = col.query(query_embeddings=[qv], n_results=TOP_K)   # ② 在库里找最近的 K 块

    print(f"\n命中 {len(res['documents'][0])} 条:\n")
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        print(f"【{meta['year']}年报 · 第{meta['page']}页 · 距离 {dist:.4f}】")
        snippet = doc.replace("\n", " ")[:180]  # 折叠换行,只显示开头
        print(f"  {snippet}\n")