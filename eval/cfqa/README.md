# CFQA官方测试集：当前比亚迪语料适配

来源：[ygan/CFQA](https://github.com/ygan/CFQA)，论文：[Addressing investor concerns](https://doi.org/10.1140/epjds/s13688-025-00601-6)。不是另一项同名的500题CFQA。

使用官方`dataset/split_by_year/split_by_year_test.json`，不混入训练集或验证集。2026-11-06读取的该文件共2084条，其中5条为比亚迪2022年问题，可对应当前本地2021–2024年报；其余2079条未作为当前比亚迪库的有答案测试题。原始文件blob为`ebb3b7ac5e18741534677bdd3dba9a5b3dcb49ce`，清单与哈希见manifest.json。

## 运行

从Byd-RAG根目录，在已配置的byd环境中执行：

```powershell
python src/evaluate.py --questions eval/cfqa/byd_year_test.jsonl --limit 5
```

该命令走当前默认混合检索、重排、邻块扩展和真实生成接口。结果保存在被Git忽略的eval/runs目录。评测脚本未更改，**不传--questions时仍读取原50题**，因此新评测请使用上面完整命令。

## 数据与评分边界

- 问题保持官方原文，source.original_id为原编号；来源只含官方测试集。
- reference_answer_original为作者原始答案，evidence_pdf_pages_original为原始出处页序；保留原值，不默认已经核验。
- 原始页序是PDF物理页顺序（从1开始），不是印刷页码；应先和本地相同版PDF对齐。
- reference_verification目前为pending_pdf_review，answerability为unverified。空出处不自动等于无答案，有答案文本也不保证单位/年份/统计口径正确。
- 运行后应人工核对原PDF/解析文本、返回证据及问题意图，再分别报告调用成功、证据支持、回答正确性；不要仅按原始答案字符串判分。
- 这只有5题，不能称为全CFQA成绩；不是口语化专用标注，也不是原50题分数的直接替换或提升证明。题目和初步答案已被阅读，不再宣称完全未见的盲测。
- 不为凑50题而从train/dev补题、重复年份，或只替换其他公司名字为比亚迪并沿用原答案。

原50题eval/questions.jsonl继续作为已有开发/回归集保存。真正扩展官方CFQA范围需要增加对应公司的原始报告、语料映射及索引，并将其作为独立实验，不能把当前库缺少其他公司文档算作模型失败。

## 许可

保留作者仓库MIT LICENSE（本目录LICENSE）。原始年报为第三方披露材料，仓库许可不代表取得原PDF的额外权利。
