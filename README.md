# 比亚迪年报智能问答（RAG）

基于比亚迪 2021–2024 年报的命令行问答项目。支持财务金额与单位核对、合并与母公司口径区分、跨年比较，回答附带年报证据。

## 快速演示

| 问题 | 实际回答 | 年报出处 |
| --- | --- | --- |
| 比亚迪 2022 年所得税费用合计多少？ | **3,366,625 千元** | 2022 年报 PDF 第 221 页，单位说明见第 143 页 |
| 2022 年比亚迪账上的资产一共有多少？ | **合并总资产 493,860,646 千元** | 2022 年报 PDF 第 127 页，合并资产负债表 |
| 2022 年比亚迪在职员工比去年多了多少？ | **增加 281,874 人**（570,060 − 288,186） | 2022、2021 年报各自的 PDF 第 57 页 |

## 核心流程

年报按 PDF 页拆分，每页以 512 字符、64 字符重叠切块。BM25 和向量检索使用同一批块，每块对应一个 PDF 页码。按年份召回证据，经 RRF 融合和重排后，补上已识别表格的单位和来源页，再生成带引用的回答。明确年份的总资产查询按报表口径直接取证，两年在职员工人数差由程序根据证据计算。

## 本地运行

在仓库根目录用 Python 3.12 执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

在 `.env` 填写 `SILICONFLOW_API_KEY`。仓库已包含解析好的年报文本，可以直接建索引和提问：

```powershell
.\.venv\Scripts\python.exe src/build_index.py
.\.venv\Scripts\python.exe src/hybrid_search.py --query "比亚迪2022年所得税费用合计多少？"
```

省略 `--query` 进入交互问答。按页版本首次运行需要建新索引，默认使用 `data/chroma-page-v1/` 和 `byd_reports_page_v1` 集合。已有匹配的按页索引时可直接提问。旧版索引和历史评测结果使用原切块编号。

### 可选：离线体验 BM25

安装依赖后即可运行，无需 API 密钥或向量索引。输入问题后会显示命中的年报片段及页码。

```powershell
.\.venv\Scripts\python.exe src/bm25_search.py
```

## 测试与评测

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- **当前按页版本。** 在 CFQA 改编的 50 道开发题上，关闭阈值与使用 Rerank 阈值 0.8 均答对 38 题，标注证据页 Recall@5 从 53% 降至 50%。另测 4 道应拒答题，生成前直接拒答从 1 题增至 3 题。[阈值对照报告](eval/rerank-threshold-08.md)
- **旧切块版本。** 固定证据的表格与附注单位实验中，核心答案正确率从 70% 提升到 80%，20 道金额题的金额、单位与口径正确率从 45% 提升到 85%。

评测命令、题集和评分口径见 [评测说明](eval/README.md)。

这是一个 AI 辅助开发的学习项目。模型给出的金额和引用可回到年报原文核对。
