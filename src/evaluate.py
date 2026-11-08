"""用真实问答流程逐题保存结果；不把接口成功误报为答案正确。"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time

import config
from pipeline import answer_question


def main():
    parser = argparse.ArgumentParser(description="运行题集并保存完整回答和证据")
    parser.add_argument("--questions", type=Path, default=config.ROOT / "eval/questions.jsonl")
    parser.add_argument("--limit", type=int, default=5, help="默认5题；运行全部50题请显式指定50")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("limit必须大于0")
    questions = [json.loads(line) for line in args.questions.read_text(encoding="utf-8").splitlines() if line.strip()][:args.limit]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = args.output or config.ROOT / "eval/runs" / f"{stamp}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    # x模式防止覆盖已有运行记录；每题立即flush，中断时已完成结果仍在。
    with output.open("x", encoding="utf-8") as stream:
        for question in questions:
            started = time.perf_counter()
            record = {"id": question["id"], "question": question["question"],
                      "model": config.CHAT_MODEL, "provider": config.CHAT_PROVIDER,
                      "settings": {"candidate_n": config.CANDIDATE_N, "top_k": config.TOP_K,
                                   "use_rerank": True, "max_chars": config.MAX_CONTEXT_CHARS,
                                   "radius": config.CONTEXT_RADIUS, "trust_env": config.TRUST_ENV}}
            try:
                record.update(answer_question(question["question"]))
                if record.get("missing_years"):
                    record["status"] = "missing_year_evidence"
                else:
                    record["status"] = "completed" if record["retrieved_records"] else "empty_retrieval"
            except Exception as exc:
                record.update(status="failed", error_type=type(exc).__name__)
                response = getattr(exc, "response", None)
                if response is not None:
                    record["http_status"] = response.status_code
            record["elapsed_seconds"] = round(time.perf_counter()-started, 3)
            stream.write(json.dumps(record, ensure_ascii=False)+"\n")
            stream.flush()
            print(record["id"], record["status"], f"{record['elapsed_seconds']:.2f}s")
    print(f"结果已保存：{output}；回答正确性需另行核验。")


if __name__ == "__main__":
    main()
