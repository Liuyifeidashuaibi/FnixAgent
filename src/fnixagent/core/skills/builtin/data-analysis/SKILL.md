---
name: data-analysis
description: Excel/CSV 数据查询聚合与多表关联分析，输出可复现结构化结论
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: json
tags:
  - data
  - sql
  - csv
  - excel
  - analysis
  - trae-work
---
# Data Analysis Skill

对 Excel / CSV / 表格式数据做查询、聚合、多表关联与结构化解读。优先用可复现脚本（pandas / SQL / DuckDB），避免只给口头结论。

## 何时使用

- 用户提供 CSV / Excel / 表格，要求分析趋势、分布、关联
- 需要多表 join / 聚合 / 透视
- 需要输出结构化结论 + 可复现计算步骤

不要用于：纯图表美化（用 `chart-visualization`）、海报设计（用 `canvas-design`）。

## 工作流程

1. **探查**：读样例行、列类型、缺失值、主键候选；列出数据字典。
2. **澄清问题**：指标定义、时间粒度、过滤条件、对比维度。
3. **计算**：用脚本完成；优先 DuckDB SQL 或 pandas；结果写入 `.fnix/artifacts/<slug>/`。
4. **校验**：行数守恒、空值处理说明、异常值标注。
5. **交付**：结论摘要（先结论）+ 关键表格 + 复现命令/脚本路径。

## 输出契约

```json
{
  "question": "string",
  "datasets": ["path"],
  "method": "sql|pandas",
  "key_findings": ["..."],
  "tables": [{"name": "...", "path": "..."}],
  "caveats": ["..."]
}
```

