"""纯向量检索演示；复用检索器与接口配置，不生成答案。"""
from retrieval import get_retriever


def main():
    engine = get_retriever()
    while True:
        query = input("问题(输 q 退出)> ").strip()
        if query.lower() in {"q", "quit", "退出"}:
            return
        if not query:
            continue
        result = engine.vector_results(query, 5)
        for doc, meta, distance in zip(result["documents"][0], result["metadatas"][0], result["distances"][0]):
            print(f"【{meta['year']}年报·第{meta['page']}页·距离{distance:.4f}】")
            print(doc.replace("\n", " ")[:180], "\n")


if __name__ == "__main__":
    main()
