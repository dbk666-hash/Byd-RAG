"""从共享切块结果建库；不会重置索引，也不重复嵌入已有的相同块。"""
import time

import chromadb

from api_client import embed_texts
from chunk import load_corpus
from config import COLLECTION_NAME, DB_PATH, PARSED

BATCH = 16


def build_index(parsed_dir=PARSED, db_path=DB_PATH):
    _, ids, meta = load_corpus(parsed_dir)
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    stored = collection.get(include=["documents"])
    existing = dict(zip(stored["ids"], stored["documents"]))
    for cid in set(existing) & set(meta):
        if existing[cid] != meta[cid][3]:
            raise ValueError(f"已有块{cid}与当前文本不同；请使用独立索引目录，不要覆盖旧库")
    pending = [cid for cid in ids if cid not in existing]
    for start in range(0, len(pending), BATCH):
        batch = pending[start:start + BATCH]
        documents = [meta[cid][3] for cid in batch]
        vectors = embed_texts(documents)
        collection.add(ids=batch, embeddings=vectors, documents=documents,
                       metadatas=[{"year": meta[cid][1], "page": meta[cid][2]} for cid in batch])
        print(f"已新增 {min(start + BATCH, len(pending))}/{len(pending)} 块")
        time.sleep(0.3)
    print(f"完成：语料{len(ids)}块，本次新增{len(pending)}块。向量库：{db_path}")
    return len(pending)


if __name__ == "__main__":
    build_index()
