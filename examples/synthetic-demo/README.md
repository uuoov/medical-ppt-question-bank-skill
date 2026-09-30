# Synthetic question-bank demo

人工编写的格式演示，包含三页虚构来源和三道题；不对应真实药品、企业、培训课件或患者。剂量、适应症和研究结果均为虚构。

- [来源与页码](./source-pages.md)
- [完整题库 CSV](./question-bank.csv)：题干、全部选项、答案、解析、页码和依据

| 题号 | 题型 | 考点 | 答案 | 来源页 |
| --- | --- | --- | --- | --- |
| 1 | 单选题 | 适应症 | A（Condition X） | 1 |
| 2 | 多选题 | 给药方案 | AB（100 mg 每日一次；口服） | 2 |
| 3 | 判断题 | Study Alpha 应答率 | A（正确） | 3 |

在仓库根目录运行：

```bash
python skills/medical-ppt-question-bank/scripts/validate_question_bank_csv.py examples/synthetic-demo/question-bank.csv --single 1 --multiple 1 --true-false 1 --expected-total 3
```

脚本检查结构与题量，不能证明事实正确。事实验收应逐题对照 `source-pages.md`，核对答案与选项的映射及引用页码。
