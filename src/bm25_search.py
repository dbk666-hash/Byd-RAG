# -*- coding: utf-8 -*-
"""bm25_search.py: 用 BM25(关键词打分)检索年报块。
和向量检索对比: 它抓"字面词",向量抓"语义"。输入问题,打印 BM25 命中的 top5。
不联网、不花 key —— 纯本地计算。
"""
import re
import jieba
from pathlib import Path
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "parsed"
CHUNK_SIZE, OVERLAP = 512, 64
TOP_K = 5

def chunk_text(text: str):
    chunks, last_page, i, n = [], 0, 0, len(text)
    while i < n:
        window = text[i:i + CHUNK_SIZE]
        pages = re.findall(r"PAGE (\d+)", window)
        if pages:
            last_page = int(pages[-1])
        chunks.append((last_page, window))
        i += CHUNK_SIZE - OVERLAP
    return chunks

# ① 把所有年报切成块,ID 编号规则与 build_index 完全一致(为以后融合对齐)
corpus, meta = [], []          # meta: 与块平行的 (年份, 页码)
for txt in sorted(PARSED.glob("*.txt")):
    year = re.search(r"(20\d\d)", txt.stem).group(1)
    for i, (page, text) in enumerate(chunk_text(txt.read_text(encoding="utf-8"))):
        corpus.append(text)
        meta.append((year, page))
print(f"共 {len(corpus)} 块,开始构建 BM25 索引...")

# ② 分词后构建 BM25 索引
tokenized_corpus = [jieba.lcut(doc) for doc in corpus]
bm25 = BM25Okapi(tokenized_corpus)
print("BM25 索引就绪(纯本地,秒级检索)。\n")

while True:
    q = input("问题(输 q 退出)> ").strip()
    if q.lower() == "q":
        break
    if not q:
        continue
    scores = bm25.get_scores(jieba.lcut(q))          # 对每个词打分,汇总到每块
    top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K]
    print(f"\n=== BM25 命中的 {TOP_K} 块 ===")
    for idx in top:
        y, p = meta[idx]
        snip = corpus[idx].replace("\n", " ")[:150]
        print(f"[{y}年报·第{p}页·分{scores[idx]:.1f}]: {snip}")