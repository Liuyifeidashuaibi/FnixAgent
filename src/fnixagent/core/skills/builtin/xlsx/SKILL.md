---
name: xlsx
description: Excel 公式/图表/格式/数据透视，对应 ExcelExpert
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: xlsx
tags:
  - xlsx
  - excel
  - spreadsheet
  - formula
  - chart
resources:
  - office/excel.py
  - office/chart.py
  - office/evaluator.py
---

# XLSX Skill

本机 Excel 处理技能，基于 `ExcelExpert` (openpyxl) 与 `ChartExpert`。所有产物落 `.fnix/artifacts/`，遵循 Work 模式「先交产物再写盘」契约。

## 何时使用

- 用户要创建/编辑 Excel 工作簿（财务模型 / 数据汇总 / 排班表 / 报价单）
- 需要写公式（SUM / VLOOKUP / IF / 数组公式 / 命名区域）
- 需要插入图表（柱/折线/饼/散点/组合图）
- 需要做条件格式 / 数据验证 / 数据透视表
- 需要把 CSV / JSON 批量转成带格式的 xlsx
- 需要对已有 xlsx 做公式审计 / 错误溯源

不要用于：纯文字报告（用 docx）、纯展示（用 pptx）、复杂统计建模（建议用 Python 脚本 + 评测器）。

## 工作流程

1. **意图识别**：区分 create / edit / formula / chart / pivot / format / audit；提取数据源、目标结构、公式需求。
2. **结构设计**：先输出 sheet/tab 列表（含列名、数据类型、公式列），让用户确认；用户确认后落盘。
3. **执行**：调用 `ExcelExpert.create` / `edit` / `set_formula` / `add_chart` / `add_pivot` / `set_conditional_format` / `set_data_validation`。
4. **公式审计**：调用 `ExcelExpert.audit_formulas` 检查循环引用 / #REF! / #DIV/0!；若有错误进入 fix 循环。
5. **交付**：写入 `.fnix/artifacts/<slug>.xlsx`，返回路径与 `{ "sheets": int, "formulas": int, "charts": int, "data_range": str }`。

## 输出契约

- `output_format: xlsx`
- 产物路径：`.fnix/artifacts/<task_slug>.xlsx`
- 元数据：`{ "sheets": int, "formulas": int, "charts": int, "has_pivot": bool }`
- 公式规范：所有公式以 `=` 开头，使用英文逗号分隔参数；命名区域用 `manager_name`
- 错误处理：单元格出现 `#REF!` / `#DIV/0!` / `#NAME?` 视为失败，必须修复后交付
- 失败时不写盘，返回 `ExpertResult(success=False, error=<原因>)`

## Fnix 集成点

- 底层实现：`fnixagent.office.excel.ExcelExpert` + `fnixagent.office.chart.ChartExpert`
- 工具注册：`xlsx.create` / `xlsx.edit` / `xlsx.set_formula` / `xlsx.add_chart` / `xlsx.add_pivot` / `xlsx.set_conditional_format` / `xlsx.set_data_validation` / `xlsx.audit` / `xlsx.csv_to_xlsx`
- 模板：`office/template.py` 加载组织 Excel 模板套用表头/字体规范
- 评测：`office/evaluator.py` 对接 SpreadsheetBench 风格 Soft/Hard 指标
- 转换：`office/converter.py` 的 `ExcelConverter` 做 xlsx ↔ csv 互转

## 示例

**用户**：把 `sales_q3.csv` 转成 Excel，按区域做数据透视表，加柱状图，并写「总计」公式。

**Skill 执行**：
1. `xlsx.csv_to_xlsx(source="sales_q3.csv", output=".fnix/artifacts/sales_q3.xlsx")`
2. `xlsx.add_pivot(sheet="Sheet1", rows=["区域"], values=["销售额"])`
3. `xlsx.add_chart(sheet="Sheet1", type="bar", data_range="A1:B10", anchor="D2")`
4. `xlsx.set_formula(cell="C11", formula="=SUM(C2:C10)")`
5. `xlsx.audit()` 校验无 #REF! 错误
6. 返回 `.fnix/artifacts/sales_q3.xlsx` 与元数据
