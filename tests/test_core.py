"""离线验证：临时语料、假集合和假HTTP响应，不打开用户原索引。"""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import api_client
import build_index
import config
from chunk import chunk_text, load_corpus
from context import build_prompt, expand_context, format_context
from pipeline import answer_question
from retrieval import Retriever, rrf_fuse


class Response:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise api_client.requests.HTTPError(str(self.status_code))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parsed = Path(self.temp.name) / "parsed"
        self.parsed.mkdir()
        (self.parsed / "BYD_2023.txt").write_text("=====PAGE 8=====\n营业收入 2023 年。", encoding="utf-8")
        (self.parsed / "BYD_2024.txt").write_text("=====PAGE 9=====\n营业收入 2024 年。", encoding="utf-8")

    def engine(self):
        collection = Mock()
        def query(**kwargs):
            years = kwargs["where"]["year"]["$in"] if kwargs["where"] else ["2024", "2023"]
            return {"ids": [[f"BYD_{year}_0" for year in years if year in {"2023", "2024"}]]}
        collection.query.side_effect = query
        return Retriever(parsed_dir=self.parsed, collection=collection)


class CoreTests(Fixture):
    def test_shared_chunk_ids_and_page_windows(self):
        corpus, ids, meta = load_corpus(self.parsed)
        self.assertEqual(ids, ["BYD_2023_0", "BYD_2024_0"])
        self.assertEqual(meta[ids[1]], (ids[1], "2024", 9, corpus[1]))
        text = "=====PAGE 1=====\n" + "a"*500 + "=====PAGE 2=====\n" + "b"*500
        chunks = chunk_text(text)
        self.assertEqual(chunks[1][1], text[448:960])
        self.assertEqual(chunks[1][0], 2)

    def test_imports_do_not_call_network_db_or_input(self):
        script = '''
import importlib, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
with patch("requests.Session.post", side_effect=AssertionError("network on import")), patch("chromadb.PersistentClient", side_effect=AssertionError("db on import")), patch("builtins.input", side_effect=AssertionError("input on import")):
    for name in ("config", "api_client", "chunk", "retrieval", "context", "pipeline", "hybrid_search", "search", "bm25_search", "diagnose", "parse_pdf", "build_index", "check_pdf", "evaluate"):
        importlib.import_module(name)
print("safe imports")
'''
        result = subprocess.run([sys.executable, "-c", script, str(SRC)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "safe imports")

    def test_bm25_is_local_and_filters_before_topk(self):
        with patch("api_client.embed_one", side_effect=AssertionError("network")), patch("chromadb.PersistentClient", side_effect=AssertionError("db")):
            engine = Retriever(parsed_dir=self.parsed)
            matches = engine.bm25_candidates("2023年营业收入", 1)
            self.assertEqual([cid for cid, score in matches], ["BYD_2023_0"])
            self.assertEqual(engine.bm25_candidates("2099年营业收入", 5), [])

    def test_year_filter_and_rerank_original_index_mapping(self):
        engine = self.engine()
        with patch("api_client.embed_one", return_value=[0.1]), patch("api_client.rerank", return_value=[1, 0]) as rerank:
            rows = engine.retrieve("2024和2023年营业收入", top_k=2, candidate_n=10, use_rerank=True)
        self.assertEqual([row[0] for row in rows], ["BYD_2023_0", "BYD_2024_0"])
        self.assertEqual(engine.col.query.call_args.kwargs["where"], {"year": {"$in": ["2024", "2023"]}})
        self.assertEqual(rerank.call_args.args[1], [engine.meta["BYD_2024_0"][3], engine.meta["BYD_2023_0"][3]])

    def test_empty_retrieval_never_calls_generation_or_rerank(self):
        with patch("api_client.embed_one", return_value=[0.1]), patch("api_client.rerank") as rerank, patch("api_client.chat_reply") as chat:
            result = answer_question("2099年营业收入", retriever=self.engine())
        self.assertEqual(result["evidence_records"], [])
        self.assertIsNone(result["prompt"])
        rerank.assert_not_called()
        chat.assert_not_called()

    def test_rrf_fusion_preserves_ties_and_combines_both_lanes(self):
        ranking = rrf_fuse(["a", "b"], ["b", "c"], 3)
        self.assertEqual([cid for cid, score in ranking], ["b", "a", "c"])
        self.assertAlmostEqual(ranking[0][1], 1/62+1/61)

    def test_context_budget_and_source_order(self):
        meta = {f"BYD_2024_{i}": (f"BYD_2024_{i}", "2024", 1, "aa") for i in range(5)}
        rows = expand_context([meta["BYD_2024_2"]], meta, 6, radius=1)
        self.assertEqual([r[0] for r in rows], ["BYD_2024_1", "BYD_2024_2", "BYD_2024_3"])
        self.assertEqual(sum(len(r[3]) for r in rows), 6)
        self.assertIn("[证据1]", format_context(rows))

    def test_pipeline_uses_same_context_for_prompt_and_returned_evidence(self):
        engine = self.engine()
        with patch("api_client.embed_one", return_value=[0.1]), patch("api_client.rerank", return_value=[0]), patch("api_client.chat_reply", return_value="回答[证据1]") as chat:
            result = answer_question("2024年营业收入", retriever=engine)
        self.assertEqual(chat.call_args.args[0], build_prompt(result["query"], result["context"]))
        self.assertEqual(result["answer"], "回答[证据1]")
        self.assertTrue(all(row[1] == "2024" for row in result["evidence_records"]))

    def test_pipeline_labels_cross_table_evidence_by_fragment(self):
        report = (
            "=====PAGE 8=====\n表外说明\n二、财务报表\n"
            "财务附注中报表的单位：千元\n"
            "1、合并现金流量表\n职工现金 111\n"
            "2、公司现金流量表\n单位：元\n职工现金 222\n"
            "三、基本情况\n表后说明"
        )
        (self.parsed / "BYD_2023.txt").write_text(report, encoding="utf-8")
        engine = self.engine()
        record = engine.meta["BYD_2023_0"]
        with patch.object(engine, "retrieve", return_value=[record]), patch(
            "api_client.chat_reply", return_value="回答[证据1]"
        ) as chat:
            result = answer_question("2023年职工现金", retriever=engine)

        context = result["context"]
        self.assertEqual(context.count("[证据1]"), 1)
        self.assertIn("合并现金流量表｜单位：千元｜单位来源：PDF 第 8 页】\n1、合并现金流量表\n职工现金 111", context)
        self.assertIn("公司现金流量表｜单位：元｜单位来源：PDF 第 8 页】\n2、公司现金流量表\n单位：元\n职工现金 222", context)
        self.assertLess(context.index("表外说明"), context.index("【表格片段｜"))
        self.assertGreater(context.index("表后说明"), context.rindex("【表格片段结束】"))
        self.assertIn(context, chat.call_args.args[0])
        stale = ("BYD_2023_0", "2023", 8, "旧索引正文")
        self.assertTrue(format_context([stale], parsed_dir=self.parsed).endswith("正文：旧索引正文"))

    def test_note_amount_tables_inherit_report_unit_only_within_table(self):
        report = (
            "=====PAGE 1=====\n二、财务报表\n1、合并资产负债表\n资产 100\n"
            "三、基本情况\n编制本财务报表，除有特别说明外，均以人民币千元为单位表示。\n"
            "=====PAGE 2=====\n七、合并财务报表主要项目注释\n3.\n应收账款\n"
            "应收账款的账龄分析如下：\n2022 年\n2021 年\n38,828,494\n36,251,280\n"
            "上述应收账款含补贴款。\n比例(%)\n2.54\n"
            "61、所得税费用\n2022 年\n2021 年\n3,366,625\n550,737\n单位：元\n"
            "所得税费用与利润总额的关系列示如下：\n2022 年\n2021 年\n"
            "按本集团实际税率计算的所得税费用\n3,366,625\n550,737\n注1：税率说明\n"
            "62、每股收益\n元/股\n5.71\n八、合并范围的变动\n"
        )
        (self.parsed / "BYD_2022.txt").write_text(report, encoding="utf-8")
        records = [(f"BYD_2022_{i}", "2022", page, body)
                   for i, (page, body) in enumerate(chunk_text(report))]
        context = format_context(records, parsed_dir=self.parsed)

        self.assertIn("应收账款账龄分析｜单位：千元｜单位来源：PDF 第 1 页｜年份列顺序：2022 年、2021 年", context)
        self.assertIn("所得税费用｜单位：元｜单位来源：PDF 第 2 页", context)
        self.assertIn("所得税费用与利润总额的关系｜单位：千元", context)
        self.assertRegex(context, r"36,251,280\n\n【表格片段结束】\n上述应收账款")
        self.assertNotIn("每股收益｜单位：千元", context)
        self.assertEqual(context.count("5.71"), 1)

    def test_batch_embedding_response_index_order(self):
        response = Response({"data": [{"index": 1, "embedding": [1]}, {"index": 0, "embedding": [0]}]})
        with patch.dict("os.environ", {"SILICONFLOW_API_KEY": "test-key"}, clear=True), patch.object(api_client.sf_session, "post", return_value=response):
            self.assertEqual(api_client.embed_texts(["a", "b"]), [[0], [1]])

    def test_chat_uses_only_selected_provider_key_and_payload(self):
        for provider, url, model, key_name in ((name, *values) for name, values in config.CHAT_PROVIDERS.items()):
            with self.subTest(provider=provider), patch.multiple(config, CHAT_PROVIDER=provider, CHAT_URL=url, CHAT_MODEL=model, CHAT_KEY_ENV=key_name), patch.dict("os.environ", {key_name: "test-key"}, clear=True), patch.object(api_client.sf_session, "post", return_value=Response({"choices": [{"message": {"content": "ok"}}]})) as post:
                self.assertEqual(api_client.chat_reply("prompt"), "ok")
                self.assertEqual(post.call_args.args[0], url)
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["model"], model)
                if provider == "siliconflow":
                    self.assertFalse(payload["enable_thinking"])
                else:
                    self.assertEqual(payload["thinking"], {"type": "disabled"})

    def test_parse_writes_only_to_configured_temp_output(self):
        import parse_pdf
        page = Mock()
        page.get_text.return_value = "年报内容"
        doc = Mock()
        doc.__iter__ = Mock(return_value=iter([page]))
        output = Path(self.temp.name)/"parsed-output"
        output.mkdir()
        with patch("parse_pdf.pymupdf.open", return_value=doc), patch.object(parse_pdf, "OUT", output):
            parse_pdf.parse_one(Path("BYD_2024.pdf"))
        self.assertEqual((output/"BYD_2024.txt").read_text(encoding="utf-8"), "=====PAGE 1=====\n\n年报内容")
        doc.close.assert_called_once()

    def test_embedding_connection_retry_and_chat_429_policy(self):
        with patch.dict("os.environ", {"SILICONFLOW_API_KEY": "test-key"}, clear=True), patch.object(api_client.sf_session, "post", side_effect=[api_client.requests.ConnectionError(), Response({"data": [{"embedding": [1]}]})]), patch("api_client.time.sleep") as sleep:
            self.assertEqual(api_client.embed_one("问题"), [1])
            sleep.assert_called_once_with(1)
        body = {"choices": [{"message": {"content": "答案"}}]}
        with patch.dict("os.environ", {config.CHAT_KEY_ENV: "test-key"}, clear=True), patch.object(api_client.sf_session, "post", side_effect=[Response({}, 429), Response(body)]) as post, patch("api_client.time.sleep") as sleep:
            self.assertEqual(api_client.chat_reply("问题"), "答案")
            sleep.assert_called_once_with(5)
            self.assertEqual(post.call_args.kwargs["json"]["messages"], [{"role": "user", "content": "问题"}])

    def test_rebuild_skips_existing_and_rejects_changed_documents(self):
        corpus, ids, meta = load_corpus(self.parsed)
        collection = Mock()
        collection.get.return_value = {"ids": ids, "documents": corpus}
        client = Mock()
        client.get_or_create_collection.return_value = collection
        with patch("build_index.chromadb.PersistentClient", return_value=client), patch("build_index.embed_texts") as embed:
            self.assertEqual(build_index.build_index(self.parsed, Path(self.temp.name)/"db"), 0)
            embed.assert_not_called()
            collection.add.assert_not_called()
            collection.get.return_value = {"ids": [ids[0]], "documents": ["changed"]}
            with self.assertRaisesRegex(ValueError, "已有块"):
                build_index.build_index(self.parsed, Path(self.temp.name)/"db")
            embed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
