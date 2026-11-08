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


def resolve_report_years(query):
    """只有一个题面年份时，才用它推导上一年。"""
    years = extract_years(query)
    if len(years) == 1 and re.search(r"去年|上(?:一)?年", query):
        years.append(str(int(years[0]) - 1))
    return years


def rrf_fuse(vec_ids, bm_ids, top_k):
    scores = defaultdict(float)
    for ids in (vec_ids, bm_ids):
        for rank, cid in enumerate(ids):
            scores[cid] += 1 / (config.K_RRF + rank + 1)
    return sorted(scores.items(), key=lambda row: row[1], reverse=True)[:top_k]


def _query_vector(collection, embedding, candidate_n, years):
    return collection.query(
        query_embeddings=[embedding], n_results=candidate_n,
        where={"year": {"$in": years}} if years else None,
    )


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
        return _query_vector(self.col, api_client.embed_one(query), candidate_n, resolve_report_years(query))

    def vector_candidates(self, query, candidate_n):
        years = resolve_report_years(query)
        if not 2 <= len(years) <= candidate_n:
            return self.vector_results(query, candidate_n)["ids"][0]

        collection = self.col
        embedding = api_client.embed_one(query)
        ids = list(_query_vector(collection, embedding, candidate_n, years)["ids"][0])
        covered = {self.meta[cid][1] for cid in ids}
        for year in years:
            if year not in covered:
                ids.extend(_query_vector(collection, embedding, candidate_n, [year])["ids"][0])
        return self._cover_years(ids, years, candidate_n)

    def _cover_years(self, ids, years, limit):
        """给各年最靠前的候选留位，其余名额按原排名填满。"""
        if not 2 <= len(years) <= limit or len(ids) <= limit:
            return ids[:limit]
        first_by_year = {}
        for cid in ids:
            first_by_year.setdefault(self.meta[cid][1], cid)
        selected = set(first_by_year.values())
        for cid in ids:
            if len(selected) >= limit:
                break
            selected.add(cid)
        return [cid for cid in ids if cid in selected]

    def bm25_candidates(self, query, candidate_n):
        years = resolve_report_years(query)
        cross_year = len(years) > 1
        scores = self.bm25.get_scores(jieba.lcut(query))
        ranked = sorted(range(len(self.corpus)), key=lambda i: scores[i], reverse=True)
        matches = {}
        for index in ranked:
            cid = self.id_list[index]
            if years and self.meta[cid][1] not in years:
                continue
            score = float(scores[index])
            if cross_year and score == 0:
                continue
            matches[cid] = score
            if not cross_year and len(matches) >= candidate_n:
                break
        ids = self._cover_years(list(matches), years, candidate_n)
        return [(cid, matches[cid]) for cid in ids]

    def retrieve(self, query, top_k=config.TOP_K, candidate_n=config.CANDIDATE_N,
                 use_rerank=False, *, candidate_rrf=config.CANDIDATE_RRF):
        """返回 [(cid, year, page, text), ...]。"""
        years = resolve_report_years(query)
        vec_ids = self.vector_candidates(query, candidate_n)
        bm_ids = [cid for cid, _ in self.bm25_candidates(query, candidate_n)]
        limit = candidate_rrf if use_rerank else top_k
        fused = [cid for cid, _ in rrf_fuse(vec_ids, bm_ids, len(vec_ids) + len(bm_ids))]
        ids = self._cover_years(fused, years, limit)
        if not use_rerank or not ids:
            return [self.meta[cid] for cid in ids]

        documents = [self.meta[cid][3] for cid in ids]
        rerank_n = max(top_k, len(ids)) if 2 <= len(years) <= top_k else top_k
        indices = api_client.rerank(query, documents, rerank_n)
        ranked_ids = [ids[index] for index in indices]
        return [self.meta[cid] for cid in self._cover_years(ranked_ids, years, top_k)]


@lru_cache(maxsize=1)
def get_retriever():
    return Retriever()


def retrieve(query, top_k=config.TOP_K, candidate_n=config.CANDIDATE_N,
             use_rerank=False, *, candidate_rrf=config.CANDIDATE_RRF):
    return get_retriever().retrieve(
        query, top_k, candidate_n, use_rerank, candidate_rrf=candidate_rrf,
    )
