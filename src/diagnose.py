# -*- coding: utf-8 -*-
"""diagnose.py: 给检索"看病"。
三个功能:
  1) 识别问题里的年份,提示要不要按年份过滤
  2) 打印检索命中的 top5 原文(你能肉眼看召回质量)
  3) 关键词反查:看某个词在原文里"应该出现在哪些页",和检索结果对比出"漏检"
"""
import os, re, requests, chromadb
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
API_KEY = os.getenv("SILICONFLOW_API_KEY")
assert API_KEY

EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
TOP_K = 5
PARSED = ROOT / "data" / "parsed"

def embed_one(text: str):
    resp = requests.post(EMBED_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

def kw_locate(kw: str):
    """扫描全部年报,报告每个词出现在哪些年份的哪些页"""
    print(f"\n=== 关键词「{kw}」在原文中出现的位置 ===")
    for txt in sorted(PARSED.glob("*.txt")):
        year = re.search(r"(20\d\d)", txt.stem).group(1)
        hits, cur_page, page_text = [], 0, ""
        for line in txt.read_text(encoding="utf-8").splitlines():
            m = re.match(r"=====PAGE (\d+)=====", line)
            if m:
                if kw in page_text:
                    hits.append(cur_page)
                cur_page, page_text = int(m.group(1)), ""
            else:
                page_text += line
        if kw in page_text:
            hits.append(cur_page)                 # 别忘了最后一页
        print(f"  {year}年报: 出现「{kw}」的页 = {hits[:25]}")

client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
col = client.get_collection("byd_reports")

q = input("要诊断的问题> ").strip()

# --- 1) 年份提示 ---
m_year = re.search(r"(20\d\d)", q)
if m_year:
    print(f"\n⚠️ 问题含年份 {m_year.group(1)} —— 当前没有按年份过滤,别的年份的块也会混进来")

# --- 2) 打印检索命中的 top5 ---
qv = embed_one(q)
res = col.query(query_embeddings=[qv], n_results=TOP_K)
print(f"\n=== 检索命中的 {TOP_K} 块 ===")
for i, (doc, meta, dist) in enumerate(zip(res["documents"][0], res["metadatas"][0], res["distances"][0])):
    snip = doc.replace("\n", " ")[:160]
    print(f"[{i+1}] {meta['year']}年报·第{meta['page']}页·距离{dist:.4f}: {snip}")

# --- 3) 关键词反查 ---
kw = input("\n输入一个'应该出现但可能没被召回'的关键词(如:毛利率),回车跳过> ").strip()
if kw:
    kw_locate(kw)