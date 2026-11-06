"""问答启动入口：python src/hybrid_search.py，或加 --query 做一次问答。"""
import argparse

# 保留练习中常用的导入入口；实现在独立模块，不再在导入时建库。
from api_client import chat_reply, embed_one
from chunk import chunk_text
import context as evidence_context
from context import build_prompt, format_context
from pipeline import answer_question
from retrieval import get_retriever, retrieve, rrf_fuse


def expand_context(results, max_chars, radius=2):
    return evidence_context.expand_context(results, get_retriever().meta, max_chars, radius)


def main():
    parser = argparse.ArgumentParser(description="比亚迪年报RAG问答")
    parser.add_argument("--query", help="只回答一个问题；不指定则交互输入")
    parser.add_argument("--no-rerank", action="store_true", help="改走RRF融合，默认使用重排")
    args = parser.parse_args()
    while True:
        query = args.query if args.query is not None else input("问题(输 q 退出)> ").strip()
        if query.lower() == "q":
            return
        if not query:
            if args.query is not None:
                parser.error("问题不能为空")
            continue
        result = answer_question(query, use_rerank=not args.no_rerank)
        print(result["answer"])
        if result["context"]:
            print("\n—— 引用证据 ——")
            print(result["context"])
        if args.query is not None:
            return


if __name__ == "__main__":
    main()
