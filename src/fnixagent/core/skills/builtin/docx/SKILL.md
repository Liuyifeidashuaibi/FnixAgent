---
name: docx
description: Word 文档创建/编辑/修订/批注，对应 WordExpert
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: docx
tags:
  - docx
  - word
  - office
  - work
  - revision
resources:
  - office/word.py
  - office/run_editor.py
---

# DOCX Skill

本机 Word 文档处理技能，基于 `WordExpert` (python-docx) 与 `RunEditor` (run-level 精修)。所有产物落 `.fnix/artifacts/`，遵循 Work 模式「先交产物再写盘」契约。

## 何时使用

- 用户要创建/编辑 Word 文档（报告/方案/合同/说明书）
- 需要在已有 docx 上做修订（插入段落/替换文字/调样式/加批注）
- 需要生成目录、表格、页眉页脚、引用
- 需要把 Markdown 内容渲染成正式 Word 交付物
- 需要做版本比对 / 脱敏 / 合并文档

不要用于：纯排版交付（用 pdf）、表格计算（用 xlsx）、演示（用 pptx）。

## 工作流程

1. **意图识别**：区分 create / edit / annotate / compare / redact；从用户输入中提取主题、章节大纲、目标样式。
2. **大纲设计**：先输出 Markdown 大纲让用户确认（必要时）；用户确认后再进入 docx 生成阶段。
3. **执行**：调用 `WordExpert.create` / `edit` / `add_table` / `add_toc` / `add_comment` / `compare`；对 run-level 精修使用 `RunEditor.apply(ops=[EditOp(...)])`。
4. **样式检查**：用 `DocumentInspector` 渲染首页快照，检查字体/字号/段落/页眉一致性；不一致则 `FormatNormalizer.normalize(spec)`。
5. **交付**：写入 `.fnix/artifacts/<slug>.docx`，返回路径与 `{ "paragraphs": int, "tables": int, "pages_est": int }` 元数据。

## 输出契约

- `output_format: docx`
- 产物路径：`.fnix/artifacts/<task_slug>.docx`
- 元数据：`{ "paragraphs": int, "tables": int, "images": int, "has_toc": bool }`
- 修订模式：保留 track-changes 元数据，用户可在 Word 中接受/拒绝
- 失败时不写盘，返回 `ExpertResult(success=False, error=<原因>)`

## Fnix 集成点

- 底层实现：`fnixagent.office.word.WordExpert` + `fnixagent.office.run_editor.RunEditor`
- 工具注册：`docx.create` / `docx.edit` / `docx.add_table` / `docx.add_toc` / `docx.add_comment` / `docx.compare` / `docx.redact`
- 模板：`office/template.py` 加载组织 docx 模板套用页眉/页脚/字体规范
- 检查：`office/inspector.py` 的 `DocumentInspector` 做 render → look → fix 闭环
- 评测：`office/evaluator.py` 可对接 OfficeBench 风格的 Soft/Hard 指标

## 示例

**用户**：基于 `outline.md` 生成一份《2026Q3 产品规划》Word 文档，要求带目录、表格、宋体小四。

**Skill 执行**：
1. 读 `outline.md` 解析章节
2. `docx.create(title="2026Q3 产品规划", template="org_standard.docx")` 拉起骨架
3. `docx.add_toc()` 插入目录
4. 逐章 `docx.edit(insert_paragraphs=[...], style="Normal")`，对表格用 `docx.add_table(rows=5, cols=3)`
5. `FormatNormalizer.normalize(spec={"font": "宋体", "size": "12pt"})`
6. 返回 `.fnix/artifacts/2026q3_product_plan.docx`
