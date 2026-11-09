# 比亚迪年报智能问答（RAG）

基于比亚迪 2021–2024 年报的命令行问答项目。支持财务金额与单位核对、合并与母公司口径区分、跨年比较，回答附带年报证据。

## 快速演示

| 问题 | 实际回答 | 年报出处 |
| --- | --- | --- |
| 比亚迪 2022 年所得税费用合计多少？ | **3,366,625 千元** | 2022 年报 PDF 第 221 页，单位说明见第 143 页 |
| 2022 年比亚迪账上的资产一共有多少？ | **合并总资产 493,860,646 千元** | 2022 年报 PDF 第 127 页，合并资产负债表 |
| 2022 年比亚迪在职员工比去年多了多少？ | **增加 281,874 人**（570,060 − 288,186） | 2022、2021 年报各自的 PDF 第 57 页 |

## 核心流程

按年份用 BM25 和向量检索召回证据，经 RRF 融合和重排后，补上已识别表格的单位和来源页，再生成带引用的回答。明确年份的总资产查询按报表口径直接取证，两年在职员工人数差由程序根据证据计算。

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

省略 `--query` 进入交互问答。已有匹配的索引时可直接提问。

## 测试与评测

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

在 50 道比亚迪年报开发题的固定证据回归中，补充表格和附注单位后，核心答案正确率从 70% 提升到 80%，金额、单位和报表口径正确率从 45% 提升到 85%（20 道金额题）。结果用于比较当时的单位标注版本。评测用法见 [eval/README.md](eval/README.md)。

这是一个 AI 辅助开发的学习项目。模型给出的金额和引用可回到年报原文核对。
