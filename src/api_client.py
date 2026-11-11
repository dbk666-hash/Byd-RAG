"""统一管理外部接口；向量、重排共用 SiliconFlow，生成可切换厂商。"""
import os
import time

import requests

import config

sf_session = requests.Session()
sf_session.trust_env = config.TRUST_ENV


def _headers(key_name):
    key = os.getenv(key_name)
    if not key:
        raise ValueError(f"缺少 {key_name}，请在项目根目录 .env 中配置")
    return {"Authorization": f"Bearer {key}"}


def embed_one(text):
    """问题向量化；保留原来的最多3次连接/超时重试。"""
    for attempt in range(3):
        try:
            response = sf_session.post(
                config.EMBED_URL, headers=_headers("SILICONFLOW_API_KEY"),
                json={"model": config.EMBED_MODEL, "input": [text]}, timeout=30,
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == 2:
                raise
            seconds = 2 ** attempt
            print(f"向量请求连接失败，{seconds}秒后重试")
            time.sleep(seconds)


def embed_texts(texts):
    """建库批量向量化；按响应 index 恢复输入顺序。"""
    for attempt in range(3):
        response = sf_session.post(
            config.EMBED_URL, headers=_headers("SILICONFLOW_API_KEY"),
            json={"model": config.EMBED_MODEL, "input": texts}, timeout=60,
        )
        if response.status_code == 200:
            data = sorted(response.json()["data"], key=lambda row: row["index"])
            if len(data) != len(texts) or [r["index"] for r in data] != list(range(len(texts))):
                raise ValueError("向量响应数量或 index 与输入不一致，停止建库")
            return [row["embedding"] for row in data]
        print(f"批量向量化重试 {attempt + 1}/3，HTTP {response.status_code}")
        time.sleep(2 + attempt * 2)
    response.raise_for_status()
    raise RuntimeError("批量向量化未返回有效结果")


def rerank(query, documents, top_k=5):
    """返回相对于 documents 的原始下标，不返回正文或全库块编号。"""
    response = sf_session.post(
        config.RERANK_URL, headers=_headers("SILICONFLOW_API_KEY"),
        json={"model": config.RERANK_MODEL, "query": query,
              "documents": documents, "top_n": top_k}, timeout=60,
    )
    response.raise_for_status()
    results = response.json()["results"]
    if config.DEBUG_RERANK:
        print("Rerank (index, relevance_score):",
              [(row["index"], row["relevance_score"]) for row in results])
    min_score = config.RERANK_MIN_SCORE
    return [row["index"] for row in results
            if min_score is None or row["relevance_score"] >= min_score]


def chat_reply(prompt):
    """生成答案；保留原来的429等待重试，不在重构中改变采样参数。"""
    payload = {"model": config.CHAT_MODEL,
               "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
    if config.CHAT_PROVIDER == "siliconflow":
        payload["enable_thinking"] = False
    else:
        payload["thinking"] = {"type": "disabled"}
    for attempt in range(3):
        response = sf_session.post(
            config.CHAT_URL, headers=_headers(config.CHAT_KEY_ENV), json=payload, timeout=120,
        )
        if response.status_code == 429 and attempt < 2:
            seconds = 5 * (2 ** attempt)
            print(f"模型繁忙，{seconds}秒后重试")
            time.sleep(seconds)
            continue
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
