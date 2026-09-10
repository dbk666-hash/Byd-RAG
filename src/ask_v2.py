# -*- coding: utf-8 -*-
"""ask_v2.py: V1 完整闭环 —— 混合检索(RRF)+ 年份过滤 + 大模型生成带引用答案。
用法: 输入问题,输 q 退出。对比 ask.py(V0 纯向量)看效果差异。
"""
import os, re, requests, chromadb, jieba
from pathlib import Path
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SF_API_KEY = os.getenv("SILICONFLOW_API_KEY")
DS_API_KEY = os.getenv("DeepSeek_API_KEY")
assert SF_API_KEY, "没读到 Siliconflow key"
assert DS_API_KEY, "没读到 DeepSeek key"

# ---- embedding 固定走 SiliconFlow ----
EMBED_URL = "https://api.siliconflow.cn/v1/embeddings"
EMBED_MODEL = "BAAI/bge-m3"

# ---- chat:默认 SiliconFlow。若你已切 DeepSeek 官方,把这三行换成:
# CHAT_URL="https://api.deepseek.com/chat/completions"
# CHAT_MODEL="deepseek-v4-pro"    # 或页面上的其他模型名
# (chat 请求头里 Bearer 用 DEEPSEEK_API_KEY)
CHAT_URL = "https://api.deepseek.com/chat/completions"
CHAT_MODEL = "deepseek-v4-flash"

PARSED = ROOT / "data" / "parsed"
CHUNK_SIZE, OVERLAP = 512, 64
K_RRF = 60      # RRF 常数
N = 10          # 每个引擎先取 top10
FINAL_K = 8     # 融合后喂给模型的块数(比 V0 的 5 更多,给模型更多证据)
MIN_CHUNK = 80

SYSTEM_PROMPT = """你是比亚迪年报智能问答助手。只依据下面带编号的"参考内容"回答,禁止编造、禁止使用参考内容之外的知识。
参考内容每条前标了 [编号] 与来源(年份、页码)。要求:
1. 关键信息后用 [编号] 标注出处;
2. 若参考内容只覆盖部分口径,要明确说明(例如只有分行业毛利率、没有整体毛利率,就写明"只能按分行业口径回答");
3. 与问题无关的编号可忽略;
4. 资料不足以回答时,明确写"资料中未找到足够信息",不要猜测;
5. 用简洁的中文回答。"""

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

def embed_one(text: str):
    resp = requests.post(EMBED_URL,
        headers={"Authorization": f"Bearer {SF_API_KEY}"},
        json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]

def chat_reply(user_prompt: str) -> str:
    resp = requests.post(CHAT_URL,
        headers={"Authorization": f"Bearer {DS_API_KEY}"},
        json={"model": CHAT_MODEL,
              "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": user_prompt}],
              "temperature": 0.3}, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# ---- 语料 + BM25(顺序/id 与 build_index 一致) ----
corpus, id_list, meta = [], [], {}
for txt in sorted(PARSED.glob("*.txt")):
    year = re.search(r"(20\d\d)", txt.stem).group(1)
    for i, (page, text) in enumerate(chunk_text(txt.read_text(encoding="utf-8"))):
        cid = f"{txt.stem}_{i}"
        corpus.append(text)
        id_list.append(cid)
        meta[cid] = (year, page, text)
bm25 = BM25Okapi([jieba.lcut(d) for d in corpus])
print(f"语料 {len(corpus)} 块,BM25 就绪。\n")

client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
col = client.get_collection("byd_reports")

while True:
    q = input("问题(输 q 退出)> ").strip()
    if q.lower() == "q":
        break
    if not q:
        continue

    years = list(dict.fromkeys(re.findall(r"20\d\d", q)))

    # 1) 向量侧 top10(可年份过滤)
    where = {"year": {"$in": years}} if years else None
    vec_res = col.query(query_embeddings=[embed_one(q)], n_results=N, where=where)
    vec_ids = vec_res["ids"][0]

    # 2) BM25 侧 top10(同样过滤年份)
    scores = bm25.get_scores(jieba.lcut(q))
    bm_ids = []
    for idx in sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True):
        cid = id_list[idx]
        if years and meta[cid][0] not in years:
            continue
        bm_ids.append(cid)
        if len(bm_ids) >= N:
            break

    # 3) RRF 融合 -> 取 FINAL_K 块
    rrf = defaultdict(float)
    for r, cid in enumerate(vec_ids):
        rrf[cid] += 1.0 / (K_RRF + r + 1)
    for r, cid in enumerate(bm_ids):
        rrf[cid] += 1.0 / (K_RRF + r + 1)
    top_cids = [cid for cid, _ in sorted(rrf.items(),
                key=lambda kv: kv[1], reverse=True)[:FINAL_K]]

    # 4) 组装带编号和来源的上下文
    ctx_lines = []
    for i, cid in enumerate(top_cids):
        year, page, text = meta[cid]
        ctx_lines.append(f"[{i+1}] 来源:{year}年报,第{page}页\n{text}")
    prompt = f"问题:{q}\n\n参考内容:\n" + "\n\n".join(ctx_lines)

    # 5) 生成
    answer = chat_reply(prompt)
    print(f"\n【回答】\n{answer}\n")
    print("—— 依据的原文块来源 ——")
    for i, cid in enumerate(top_cids):
        year, page, _ = meta[cid]
        print(f"  [{i+1}] {year}年报 第{page}页")