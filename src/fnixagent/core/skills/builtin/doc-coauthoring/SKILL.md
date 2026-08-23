---
name: doc-coauthoring
description: 人机协作写作 — 长文大纲/草稿/润色/扩写，对应 MarkdownRenderer
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: md
tags:
  - coauthoring
  - writing
  - markdown
  - office
  - work
resources:
  - office/markdown.py
  - office/template.py
---

# Doc Co-authoring Skill

人机协作写作技能，基于 `MarkdownRenderer` 与结构化大纲驱动。强调「先大纲、再草稿、最后润色」的三段式协作，避免一次性长文导致用户失去掌控。

## 何时使用

- 用户要写长文（>2000 字）：报告 / 文章 / 招股书 / 小说章节 / 技术白皮书
- 用户已有一份草稿，希望 AI 帮助润色 / 扩写 / 缩写 / 调结构
- 用户希望与 AI 来回迭代大纲（多轮对话）
- 需要把对话内容整理成结构化文档交付

不要用于：纯排版产物（用 docx）、演示（用 pptx）、海报（用 canvas-design）。

## 工作流程

1. **意图识别**：区分 outline / draft / polish / expand / shorten / restructure；提取主题、目标字数、受众、语气。
2. **大纲阶段**：输出 2–3 级 Markdown 大纲，每节附 30 字摘要；用户确认或调整后才进入下一步。
3. **草稿阶段**：按大纲逐节生成内容，每节末尾留 `[待用户补充：…]` 占位符；节与节之间允许用户介入改写。
4. **润色阶段**：调用 `MarkdownRenderer` 检查语气一致性、术语统一、段落过渡；输出 diff 形式让用户审阅。
5. **交付**：写入 `.fnix/artifacts/<slug>.md`（若需 docx/pdf 再调对应 skill 转换）；返回路径与 `{ "words": int, "sections": int, "outline_locked": bool }`。

## 输出契约

- `output_format: md`（中间态），可链式调用 `docx` / `pdf` skill 转换为最终交付格式
- 产物路径：`.fnix/artifacts/<task_slug>.md`
- 元数据：`{ "words": int, "sections": int, "iterations": int }`
- 协作规范：每次 AI 改写都需保留前一版本（`.fnix/artifacts/<slug>.v<n>.md`），便于回滚
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.office.markdown.MarkdownRenderer`
- 工具注册：`doc-coauthoring.outline` / `doc-coauthoring.draft` / `doc-coauthoring.polish` / `doc-coauthoring.expand` / `doc-coauthoring.shorten` / `doc-coauthoring.restructure`
- 模板：`office/template.py` 加载写作风格模板（如「公司报告」「学术论文」「科普文章」）
- 链式协作：完成后可调用 `docx` skill 渲染为 Word，或 `pdf` skill 转 PDF
- 检查：`office/inspector.py` 渲染预览首页让用户审阅

## 示例

**用户**：帮我写一篇 5000 字的《AI Agent 在企业知识管理中的应用》白皮书。

**Skill 执行**：
1. `doc-coauthoring.outline(topic="...", audience="企业 IT 决策者", target_words=5000)` → 输出 5 章 12 节大纲
2. 用户调整大纲后 → `doc-coauthoring.draft(outline=<...>, sections=[1,2,3], tone="professional")`
3. 用户对 §3 不满意 → `doc-coauthoring.polish(section=3, instructions="...")`
4. 全文定稿 → `doc-coauthoring.polish(scope="all", check="consistency")`
5. 写入 `.fnix/artifacts/ai_agent_km_whitepaper.md`，并可选调用 `docx` 渲染
