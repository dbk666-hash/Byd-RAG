# 比亚迪年报智能问答（RAG）

基于比亚迪 2021–2024 年年报的命令行问答项目。常规问题通过向量与 BM25 混合检索取证，带明确年份的总资产查询直接从对应资产负债表取证。回答附带年报原文引用。

当前为命令行程序。财务表格、单位、统计口径和模型计算仍有局限，不把“能生成回答”当作“回答已经验证正确”。

## 当前流程

```text
离线：PDF → 带PAGE标记的文本 → 512字符/64重叠切块 → bge-m3 → Chroma
在线：问题 → 识别查询类型
     ├─ 总资产（含明确年份）→ 按口径定位资产总计原文行
     └─ 常规问题 → 解析年份并过滤 → 向量Top20 + BM25 Top20
                  → RRF融合Top20 → BGE重排Top5（--no-rerank 时直接取RRF Top5）
                  → 邻块扩展（radius=2，正文预算8000字符）→ 表格单位标注
     → 编号引用
     ├─ 两年在职员工人数差 → 程序计算
     └─ 其余问法 → 组装提示词 → Qwen/Qwen3.5-4B生成（关闭思考）
```

年份过滤在两条检索路径截取候选之前生效。题面只有一个明确年份时，“去年”“上一年”“上年”以该年份为锚点。跨年问题在候选和重排结果中为各年保留证据位。缺少某一年的证据时，程序指出缺失年份。

证据组装按原文位置标注已识别的财务主表、应收账款账龄表和所得税费用表，注明金额单位及来源PDF页码。识别到附注表的年份列时，也会保留列顺序。表内单位优先，继承报表默认单位的前提是能够确认表格范围。

## 项目结构

```text
src/
  config.py          路径、切块/检索参数、厂商与模型配置
  api_client.py      向量化、批量向量化、重排、生成的HTTP调用
  chunk.py           唯一切块实现、加载语料、预览切块
  retrieval.py       BM25/向量检索、年份过滤、RRF、重排结果映射
  context.py         邻块扩展、表格单位标注、证据编号、提示词
  extract_unit.py    表格边界、金额单位和来源页识别
  total_assets.py    按年份和报表口径定位资产总计原文行
  employee_count.py  核对期末在职员工合计并计算两年人数差
  pipeline.py        完整问答流程，供CLI、评测和测试共用
  hybrid_search.py   当前问答入口
  parse_pdf.py       PDF解析
  build_index.py     建库；跳过已存在且文本相同的块
  search.py          纯向量检索演示
  bm25_search.py     纯本地BM25演示
  diagnose.py        向量召回诊断、关键词原文定位
  check_pdf.py       PDF文本质量检查
  evaluate.py        按题集逐题执行并保存结果
tests/
  test_core.py       隔离语料和假接口的离线验证
eval/
  questions.jsonl    按任务意图区分的50题草稿
  README.md          运行与评分说明
data/
  raw/              本地PDF，不提交Git
  parsed/           带页码标记的年报文本
  chroma/           本地向量库，不提交Git
```

旧的 `ask.py`、`ask_v2.py` 重复问答流程已合并到当前入口；历史实现可从Git记录查看。临时切片打印脚本 `test01.py` 已移除。`search.py`、`bm25_search.py` 保留用于学习与对照，但不再复制切块或接口代码。

## 安装与配置

本次验证环境为Python 3.12。依赖列在 `requirements.txt`，无需LangChain。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

编辑 `.env`，默认只需提供 `SILICONFLOW_API_KEY`。Qwen、bge-m3和BGE重排均使用该密钥，不要求额外提供GLM密钥。

如果切换生成厂商，设置 `RAG_CHAT_PROVIDER=deepseek` 并提供 `DeepSeek_API_KEY`，或设置 `RAG_CHAT_PROVIDER=glm` 并提供 `GLM_API_KEY`。向量和重排仍需SiliconFlow密钥。实际模型权限、可用性及计费以账户为准。

默认 `RAG_TRUST_ENV=false`，跳过Requests自动读取的代理设置；这不保证绕过系统TUN。需要遵循系统代理时改为 `true`。

## 数据与建库

仓库已有解析文本时可直接建库；若从PDF开始，把报告放入 `data/raw/`，文件名包含年份，例如 `BYD_2024.pdf`：

```powershell
python src/check_pdf.py
python src/parse_pdf.py
python src/chunk.py
python src/build_index.py
```

在已配置解释器的PyCharm终端中，也可直接使用这些 `python` 命令。若使用上面新建的虚拟环境，可用 `.\.venv\Scripts\python.exe` 替换 `python`。

切块编号保持 `<文件名>_<顺序号>`。建库和在线语料使用同一实现。已有同ID但正文不同的块会拒绝继续添加；请使用独立的 `RAG_DB_PATH` 建实验库，不要混用不同切块或向量模型的旧索引。建库不会删除、清空原有集合。

## 问答与检索演示

```powershell
python src/hybrid_search.py
python src/hybrid_search.py --query "2024年比亚迪的营业收入是多少？"
python src/hybrid_search.py --no-rerank
python src/bm25_search.py
python src/search.py
```

纯BM25演示不联网、不需要密钥或向量库。导入模块不会自动运行交互循环、建BM25或打开Chroma；首次检索时才加载所需状态。

### 总资产查询

```powershell
python src/hybrid_search.py --query "2022年比亚迪账上的资产一共有多少？"
python src/hybrid_search.py --query "2022年比亚迪母公司总资产是多少？"
```

总资产查询默认取合并口径，明确问母公司时取母公司表，同时问两种口径时分别取证。证据包含对应年份、原表金额、单位和 PDF 页码。缺少指定年份或口径的证据时，程序直接说明证据不足。这个分支直接读取解析文本，生成回答仍使用配置的模型接口。

以 2022 年为例，合并总资产为 **493,860,646 千元**，原文在 PDF 第 127 页。母公司总资产为 **76,250,627 千元**，原文在第 135 页。页码为 PDF 文件内从 1 开始的页序。

### 跨年比较

```powershell
python src/hybrid_search.py --query "2022年比亚迪在职员工比去年多了多少？"
```

这里的“去年”指 2021 年。程序从两份年报中核对期末在职员工合计，用 **570,060 人**减去 **288,186 人**，得出增加 **281,874 人**。回答引用两份年报各自的 PDF 第 57 页。

## 验证与评测

```powershell
python -m unittest discover -s tests -v
# 默认回归题集
python src/evaluate.py --questions eval/questions.jsonl --limit 50
```

工作区有 CFQA 题集文件时，也可以显式指定对应路径。

```powershell
# 重新标注答案与证据的比亚迪改编题
python src/evaluate.py --questions eval/cfqa_adapted/byd50_v1/questions.jsonl --limit 50
# 原样保留的 CFQA 比亚迪题
python src/evaluate.py --questions eval/cfqa/byd_year_test.jsonl --limit 5
```

离线测试使用模拟接口，覆盖总资产的报表口径和单位，以及相对年份、重排后各年证据覆盖和缺少人数原文时的处理。评测命令使用真实检索接口，将回答、证据、提示词、耗时与错误保存到 `eval/runs/*.jsonl`。跨年题缺少所需年份的证据时，评测记录 `missing_year_evidence`。

题集有参考要点，但仍是已使用过事实的开发集，不是独立盲测。评测脚本不自动给出语义准确率；需要分别核对核心任务、单位/年份/符号、引用支撑及额外推断。详见 [eval/README.md](eval/README.md)。

## 已知局限与后续工作

- 常规检索使用固定长度切块，表头、单位和合并/母公司口径可能与数字分离。跨页块的页码可能近似，核对时应结合块 ID 和原文。
- 相对年份需要题面给出单一的年份锚点。跨年取证会检查年报覆盖，证据是否支持具体指标仍需核对。
- 模型可能把千元当元、错配表格年度列，或在操作数正确时算错；引用编号存在不等于每条引用都支持答案。
- 保留原有重试策略：问题向量化对连接/超时重试，生成对429等待重试；重排及生成的其他网络错误仍会抛出，需调用方处理。
- 当前入口支持命令行；FastAPI服务和网页尚未接入这个真实项目。

下一步用同一题集复核跨年取证，并核对财务指标的口径与引用。

## 开发说明

这是AI辅助的学习项目。核心模块按实际职责拆分，保留可追踪的检索与证据链；不以README中的示例回答替代实际评测。
