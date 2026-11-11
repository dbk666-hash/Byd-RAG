# 评测

当前评测使用 **CFQA 改编的比亚迪 50 题 v1**。在仓库根目录运行，先按 [本地运行说明](../README.md#本地运行) 配置密钥并构建按页索引。

```powershell
.\.venv\Scripts\python.exe src/evaluate.py --questions eval/cfqa_adapted/byd50_v1/questions.jsonl --limit 50
```

[题目列表](cfqa_adapted/byd50_v1/questions.md) · [参考答案](cfqa_adapted/byd50_v1/answers.md) · [标注和评分说明](cfqa_adapted/byd50_v1/README.md)。题集和评分尚未独立复核。原50题与原样5题均保留。

将上面的限制改为 5 可先验证一次调用。运行记录写入本地评测目录，语义正确性按题集评分要点核对。

- [按页切块的 Rerank 0.8 回归](rerank-threshold-08.md)对比同一题集关闭阈值和启用阈值的表现，另有 4 道拒答样例。
- [旧切块的表格标注基线](cfqa-current-baseline.md)记录 2026 年 11 月 8 日的实验。BM25 与默认重排的核心答案均为 40/50。

另保留CFQA官方按年份测试集的原样比亚迪5题：

```powershell
python src/evaluate.py --questions eval/cfqa/byd_year_test.jsonl --limit 5
```

来源、5题范围及标准答案核验边界见[CFQA说明](cfqa/README.md)。下面保留的50题用于已有开发/回归；默认脚本仍读取旧50题，新实验需显式指定--questions。

`questions.jsonl` 是现有按任务意图区分的50题草稿，保留原编号、原文锚点和参考要点。事实已参与过先前实验，不是独立留出集；部分参考判定仍需人工复核。

从项目根目录运行：

```powershell
python src/evaluate.py --limit 5
python src/evaluate.py --limit 50
```

会调用当前配置的真实接口；结果逐题写入 `eval/runs/` 的独立JSONL文件，包含问题、完整回答、证据、提示词、耗时及失败类型。已有文件不会被覆盖，运行结果默认不提交Git。

脚本不自动计算语义准确率：先核对核心任务、年份/单位/正负号、引用支持和额外推断，再做逐题评分。接口返回成功不等于答对；空检索拒答和调用失败也要分开。计算题应独立复算，JSON题应整段解析。

旧50题、500题及这批50题的分数不可直接比较；不同实验应固定同一题集、语料、候选预算和评分口径。

此入口直接复用 `pipeline.answer_question()`，替代依赖旧单文件AST布局的临时评测方式。历史原始运行与复核仍保留在原学习工作台，未改写为本次重构的新成绩。
