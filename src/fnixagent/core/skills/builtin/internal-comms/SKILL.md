---
name: internal-comms
description: 状态报告/新闻稿/FAQ/邮件模板，对应 TemplateManager
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: md
tags:
  - comms
  - report
  - press-release
  - faq
  - email
  - office
  - work
resources:
  - office/template.py
  - office/markdown.py
---

# Internal Comms Skill

组织内部沟通文档生成技能，基于 `TemplateManager` 套用预设模板，快速产出周报 / 项目状态 / 新闻稿 / FAQ / 邮件。强调「填空式」写作，避免每次从零开始。

## 何时使用

- 用户要写周报 / 月报 / 项目状态报告 / 立项简报
- 用户要写对内/对外新闻稿（融资 / 产品发布 / 人事任命）
- 用户要写 FAQ（产品 / HR / IT 支持）
- 用户要写正式邮件（邀请 / 致歉 / 通知 / 跟进）

不要用于：长文白皮书（用 doc-coauthoring）、营销文案（用 frontend-design 配合落地页）、合同法务（建议人工审核）。

## 工作流程

1. **意图识别**：从用户输入判定 doc_type（status_report / press_release / faq / email / announcement）；提取受众、语气、关键事实。
2. **模板选择**：调用 `TemplateManager.list_templates(category=doc_type)` 让用户选模板，或自动选默认模板。
3. **填空**：按模板字段让用户提供关键信息（缺失字段用 `[待补充：…]` 占位，绝不编造事实）。
4. **生成**：渲染模板，调用 `MarkdownRenderer` 输出 Markdown；若需 docx/pdf 再链式调用对应 skill。
5. **交付**：写入 `.fnix/artifacts/<slug>.md`，返回路径与 `{ "template": str, "fields_filled": int, "fields_pending": int }`。

## 输出契约

- `output_format: md`（可链式转换 docx/pdf/html）
- 产物路径：`.fnix/artifacts/<task_slug>.md`
- 元数据：`{ "template": str, "fields_filled": int, "fields_pending": int, "word_count": int }`
- 事实守则：未提供的事实字段必须以 `[待补充：…]` 标注，禁止编造数字 / 人名 / 日期
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.office.template.TemplateManager`
- 工具注册：`internal-comms.status_report` / `internal-comms.press_release` / `internal-comms.faq` / `internal-comms.email` / `internal-comms.announcement` / `internal-comms.list_templates`
- 模板：`office/template.py` 的 `TemplateManager` 注册组织模板（YAML 配置）
- 渲染：`office/markdown.py` 的 `MarkdownRenderer` 把模板字段渲染为 Markdown
- 链式协作：完成后可调 `docx` / `pdf` / `pptx` skill 转换为最终格式

## 示例

**用户**：写一份本周项目状态报告，项目「北极星」，本周完成 P0/P1，下周计划做 P2。

**Skill 执行**：
1. `internal-comms.status_report(project="北极星", week="2026-W29")`
2. 从模板库选 `status_report_default.md.tpl`
3. 用户提供：本周完成 = [P0, P1]，下周计划 = [P2]
4. 渲染模板，未提供字段（如「风险」「资源需求」）以 `[待补充：…]` 占位
5. 返回 `.fnix/artifacts/northstar_status_w29.md`，元数据 `{ "fields_filled": 4, "fields_pending": 2 }`
