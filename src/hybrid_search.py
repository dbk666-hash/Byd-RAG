# -*- coding: utf-8 -*-
"""hybrid_search.py: V1 混合检索 —— 向量 + BM25 用 RRF 融合,自动按年份过滤。"""
import os, re, requests, chromadb, jieba
from pathlib import Path
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
API_KEY = os.getenv("SILICONFLOW_API_KEY")
assert API_KEY, "没读到 key"

EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"
PARSED = ROOT / "data" / "parsed"
CHUNK_SIZE, OVERLAP = 512, 64
K_RRF = 60     # RRF 分母常数(通用值 60)
N = 10         # 每个引擎先取 top10,再融合
TOP_K = 5      # 融合后输出 top5

def chunk_text(text: str):
    """512/64 固定窗口切块 —— 顺序与 build_index 完全一致,块 id 才能对齐"""
    chunks, last_page, i, n = [], 0, 0, len(text)
    while i < n:
        window = text[i:i + CHUNK_SIZE]
        pages = re.findall(r"PAGE (\d+)", window)  #findall返回一个列表
        if pages:
            last_page = int(pages[-1])
        chunks.append((last_page, window))
        i += CHUNK_SIZE - OVERLAP
    return chunks

def embed_one(text: str):
    resp = requests.post(EMBED_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]



# ---- 1) 建语料 + BM25 索引 ----
corpus, id_list, meta = [], [], {}    # meta[cid] = (year, page, text)
for txt in sorted(PARSED.glob("*.txt")):
    year = re.search(r"(20\d\d)", txt.stem).group(1)
    for i, (page, text) in enumerate(chunk_text(txt.read_text(encoding="utf-8"))):
        cid = f"{txt.stem}_{i}"       # 与入库 id 一致
        corpus.append(text)
        id_list.append(cid)
        meta[cid] = (year, page, text)
bm25 = BM25Okapi([jieba.lcut(d) for d in corpus])
print(f"语料 {len(corpus)} 块,BM25 就绪。\n")

client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
col = client.get_collection("byd_reports")


def retrieve(query: str, top_k: int = 8):
    """输入问题,返回 [(year, page, text), ...] 共 top_k 块"""
    # 1) 问题向量化
    qv = embed_one(query)                                   # 空1: 用 embed_one(query) 即可(hybrid 里已有这个函数)

    # 2) 向量侧:在 chroma 里检索 top N
    res = col.query(query_embeddings=[qv], n_results=N)
    vec_ids = res["ids"][0]                              # 空2: 从 res 里取 id 列表(回顾:返回有几层壳?)

    # 3) BM25 侧 top N(这里先不做年份过滤,保持简单)
    scores = bm25.get_scores(jieba.lcut(query))
    order = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
    bm_ids = [id_list[idx] for idx in order[:N]]

    # 4) RRF 融合
    rrf = defaultdict(float)
    for r, cid in enumerate(vec_ids):
        rrf[cid] += 1.0 / (K_RRF + r + 1)
    for r, cid in enumerate(bm_ids):
        rrf[cid] += 1.0 / (K_RRF + r + 1)
    top = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    # 5) 返回这些块的 (年份, 页码, 文本),供 prompt 使用
    return [meta[cid] for cid, _ in top]




while True:
    q = input("问题(输 q 退出)> ").strip()
    if q.lower() == "q":
        break
    if not q:
        continue

    # 年份过滤:提取问题里所有 20xx
    years = list(dict.fromkeys(re.findall(r"20\d\d", q)))   # 去重保序
    print(f"\n[年份] {'不过滤(全查)' if not years else '只查 ' + ','.join(years)}")

    # --- A) 向量侧 top N(支持 where 按年份过滤) ---
    where = {"year": {"$in": years}} if years else None
    res = col.query(query_embeddings=[embed_one(q)], n_results=N, where=where)
    vec_ids = res["ids"][0]
    print("[向量] top", len(vec_ids), ":", vec_ids[:5], "...")

    # --- B) BM25 侧 top N(同样排除非目标年份的块) ---
    scores = bm25.get_scores(jieba.lcut(q))
    order = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
    bm_ids = []
    for idx in order:
        cid = id_list[idx]
        if years and meta[cid][0] not in years:
            continue                        # 年份不对,跳过
        bm_ids.append(cid)
        if len(bm_ids) >= N:
            break
    print("[BM25] top", len(bm_ids), ":", bm_ids[:5], "...")

    # --- C) RRF 融合:只看排名位置,不看分数大小 ---
    rrf = defaultdict(float)
    for r, cid in enumerate(vec_ids):
        rrf[cid] += 1.0 / (K_RRF + r + 1)
    for r, cid in enumerate(bm_ids):
        rrf[cid] += 1.0 / (K_RRF + r + 1)

    vec_set, bm_set = set(vec_ids), set(bm_ids)
    ranked = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:TOP_K]
    kw = "毛利率"  # 手动指定要盯的词
    print(f"\n=== 融合后 top{TOP_K}(透视 {kw}) ===")
    for cid, score in ranked:
        year, page, text = meta[cid]
        pos = text.find(kw)  # 首次出现位置(-1 = 没有)
        cnt = text.count(kw)  # 一共出现几次
        tag = ("V+B" if cid in vec_set and cid in bm_set
               else "V" if cid in vec_set else "B")
        print(f"[{tag}] {year}年报·第{page}页·融合分{score:.4f} "
              f"| 「{kw}」出现 {cnt} 次,首次位置 {pos}")
        print(f"    开头120字: {text[:120].replace(chr(10), ' ')}")
        if pos >= 0:
            print(f"    ★该词上下文: {text[max(0, pos - 40):pos + 80].replace(chr(10), ' ')}")
