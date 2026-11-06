"""串联检索、上下文和生成，CLI与测试共用这一条流程。"""
import api_client
import config
from context import build_prompt, expand_context, format_context
from retrieval import get_retriever

NO_EVIDENCE = "未检索到相关证据，当前资料无法支持回答。"


def answer_question(query, *, retriever=None, candidate_n=config.CANDIDATE_N,
                    top_k=config.TOP_K, use_rerank=True,
                    max_chars=config.MAX_CONTEXT_CHARS, radius=config.CONTEXT_RADIUS):
    engine = retriever if retriever is not None else get_retriever()
    retrieved = engine.retrieve(query, top_k=top_k, candidate_n=candidate_n, use_rerank=use_rerank)
    if not retrieved:
        return {"query": query, "answer": NO_EVIDENCE, "retrieved_records": [],
                "evidence_records": [], "context": "", "prompt": None}
    records = expand_context(retrieved, engine.meta, max_chars, radius)
    context = format_context(records)
    prompt = build_prompt(query, context)
    return {"query": query, "answer": api_client.chat_reply(prompt),
            "retrieved_records": retrieved, "evidence_records": records,
            "context": context, "prompt": prompt}
