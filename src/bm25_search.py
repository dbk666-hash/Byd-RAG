"""纯本地BM25演示：不联网，不需要API密钥或向量库。"""
from retrieval import get_retriever


def main():
    engine = get_retriever()
    while True:
        query = input("问题(输 q 退出)> ").strip()
        if query.lower() == "q":
            return
        if not query:
            continue
        matches = engine.bm25_candidates(query, 5)
        if not matches:
            print("没有找到目标年份的年报内容。")
        for cid, score in matches:
            _, year, page, text = engine.meta[cid]
            print(f"[{year}年报·第{page}页·分{score:.1f}] {text.replace(chr(10), ' ')[:150]}")


if __name__ == "__main__":
    main()
