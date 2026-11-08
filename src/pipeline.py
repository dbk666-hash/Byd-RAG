"""串联检索、上下文和生成，CLI与测试共用这一条流程。"""
import api_client
import config
from context import build_prompt, expand_context, format_context
from retrieval import get_retriever
from total_assets import lookup_total_assets

NO_EVIDENCE = "未检索到相关证据，当前资料无法支持回答。"


def answer_question(query, *, retriever=None, candidate_n=config.CANDIDATE_N,
                    top_k=config.TOP_K, use_rerank=True,
                    max_chars=config.MAX_CONTEXT_CHARS, radius=config.CONTEXT_RADIUS):
    engine = retriever if retriever is not None else get_retriever()
    assets = lookup_total_assets(query, engine)
    if assets is None:
        retrieved = engine.retrieve(query, top_k=top_k, candidate_n=candidate_n, use_rerank=use_rerank)
        records = expand_context(retrieved, engine.meta, max_chars, radius) if retrieved else []
        context = format_context(records, parsed_dir=getattr(engine, "parsed_dir", None))
    else:
        retrieved, context = assets
        records = retrieved
    if not retrieved:
        return {"query": query, "answer": NO_EVIDENCE, "retrieved_records": [],
                "evidence_records": [], "context": "", "prompt": None}
    prompt = build_prompt(query, context)
    return {"query": query, "answer": api_client.chat_reply(prompt),
            "retrieved_records": retrieved, "evidence_records": records,
            "context": context, "prompt": prompt}
