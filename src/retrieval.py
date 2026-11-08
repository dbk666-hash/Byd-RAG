"""检索状态按需加载；纯BM25不需要密钥或打开向量库。"""
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import re

import chromadb
import jieba
from rank_bm25 import BM25Okapi

import api_client
import config
from chunk import load_corpus


def extract_years(query):
    return list(dict.fromkeys(re.findall(r"20\d\d", query)))


def rrf_fuse(vec_ids, bm_ids, top_k):
    scores = defaultdict(float)
    for ids in (vec_ids, bm_ids):
        for rank, cid in enumerate(ids):
            scores[cid] += 1 / (config.K_RRF + rank + 1)
    return sorted(scores.items(), key=lambda row: row[1], reverse=True)[:top_k]


class Retriever:
    """同一份语料、块ID和元数据供向量、BM25及上下文扩展复用。"""

    def __init__(self, parsed_dir=None, db_path=None, collection=None):
        self.parsed_dir = parsed_dir or config.PARSED
        self.corpus, self.id_list, self.meta = load_corpus(self.parsed_dir)
        self.db_path = Path(db_path or config.DB_PATH)
        self._collection = collection
        self._client = None
        self._bm25 = None

    @property
    def col(self):
        if self._collection is None:
            if not (self.db_path / "chroma.sqlite3").is_file():
                raise FileNotFoundError("向量库不存在，请先运行 src/build_index.py")
            self._client = chromadb.PersistentClient(path=str(self.db_path))
            self._collection = self._client.get_collection(config.COLLECTION_NAME)
        return self._collection

    @property
    def bm25(self):
        if self._bm25 is None:
            self._bm25 = BM25Okapi([jieba.lcut(text) for text in self.corpus])
        return self._bm25

    def vector_results(self, query, candidate_n):
        years = extract_years(query)
        result = self.col.query(
            query_embeddings=[api_client.embed_one(query)], n_results=candidate_n,
            where={"year": {"$in": years}} if years else None,
        )
        return result

    def vector_candidates(self, query, candidate_n):
        return self.vector_results(query, candidate_n)["ids"][0]

    def bm25_candidates(self, query, candidate_n):
        years = extract_years(query)
        scores = self.bm25.get_scores(jieba.lcut(query))
        ranked = sorted(range(len(self.corpus)), key=lambda i: scores[i], reverse=True)
        matches = []
        for index in ranked:
            cid = self.id_list[index]
            if years and self.meta[cid][1] not in years:
                continue
            matches.append((cid, float(scores[index])))
            if len(matches) >= candidate_n:
                break
        return matches

    def retrieve(self, query, top_k=5, candidate_n=10, use_rerank=False):
        """返回 [(cid, year, page, text), ...]；保留原检索默认参数。"""
        vec_ids = self.vector_candidates(query, candidate_n)
        bm_ids = [cid for cid, score in self.bm25_candidates(query, candidate_n)]
        if not use_rerank:
            return [self.meta[cid] for cid, score in rrf_fuse(vec_ids, bm_ids, top_k)]
        ids = list(dict.fromkeys(vec_ids + bm_ids))
        if not ids:
            return []
        documents = [self.meta[cid][3] for cid in ids]
        indices = api_client.rerank(query, documents, top_k)
        return [self.meta[ids[index]] for index in indices]


@lru_cache(maxsize=1)
def get_retriever():
    return Retriever()


def retrieve(query, top_k=5, candidate_n=10, use_rerank=False):
    return get_retriever().retrieve(query, top_k, candidate_n, use_rerank)
