# -*- coding: utf-8 -*-
"""ask.py: 端到端 RAG —— 检索年报块 + 大模型生成带引用答案。
运行后输入问题,输 q 退出。
"""
import os, requests, chromadb
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SF_API_KEY = os.getenv("SILICONFLOW_API_KEY")
DS_API_KEY = os.getenv("DeepSeek_API_KEY")
assert SF_API_KEY, "没读到 Siliconflow key"
assert DS_API_KEY, "没读到 DeepSeek key"

# --- 两个接口:embedding(检索用)+ chat(生成答案用)---
EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
CHAT_URL = "https://api.deepseek.com/chat/completions"
CHAT_MODEL = "deepseek-v4-flash"   # 若报"模型不存在",去模型广场复制任意 chat 模型 id 换上

TOP_K = 5
# 给模型立规矩:这是防"瞎编"的关键
SYSTEM_PROMPT = """你是比亚迪年报智能问答助手。只依据"参考内容"回答,禁止使用参考内容之外的知识。
每条参考内容开头标了 [编号] 与来源(年份、页码)。回答要求:
1. 关键信息后用 [编号] 标注它来自哪条;
2. 如果参考内容不足以回答,明确写"资料中未找到足够信息",不要编造;
3. 用简洁的中文回答。"""

def embed_one(text: str):
    """问题 -> 向量(和 search.py 一样)"""
    resp = requests.post(EMBED_URL,
        headers={"Authorization": f"Bearer {SF_API_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

def chat_reply(user_prompt: str) -> str:
    """把组装好的提示发给大模型,返回回答文本"""
    resp = requests.post(CHAT_URL,
        headers={"Authorization": f"Bearer {DS_API_KEY}"},
        json={
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,     # 低温度 = 回答更稳定、更少发挥
        }, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
col = client.get_collection("byd_reports")

print("比亚迪年报问答助手就绪。输入问题试试,输 q 退出。\n")
while True:
    q = input("问题> ").strip()
    if q.lower() in ("q", "quit", "退出"):
        break
    if not q:
        continue

    # --- 1) 检索:问题向量在库里找最近的 TOP_K 块 ---
    qv = embed_one(q)
    res = col.query(query_embeddings=[qv], n_results=TOP_K)
    docs   = res["documents"][0]
    metas  = res["metadatas"][0]

    # --- 2) 组装上下文:给每块编号 + 标注来源(年份/页码) ---
    context_lines = []
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        context_lines.append(
            f"[{i+1}] 来源:{meta['year']}年报,第{meta['page']}页\n{doc}")

    prompt = f"问题:{q}\n\n参考内容:\n" + "\n\n".join(context_lines)

    # --- 3) 生成:让大模型只依据这些块作答 ---
    answer = chat_reply(prompt)

    print(f"\n【回答】\n{answer}\n")
    print("—— 依据的原文块 ——")
    for line in context_lines:
        head = line.split("\n", 1)[0]          # 只打印来源行,别刷屏
        print(" ", head)