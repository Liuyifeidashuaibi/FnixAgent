---
name: frontend-design
description: 前端设计系统 — 消除 AI slop UI，产出 production-grade 代码
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: html
tags:
  - frontend
  - design-system
  - code
  - ui
  - anti-slop
resources:
  - core/code/agent.py
  - core/code/tools.py
---

# Frontend Design Skill

前端设计系统技能，目标：消除 AI 生成 UI 的「slop」通病（千篇一律的渐变、emoji、卡片堆叠、low-contrast 文字）。产出 production-grade 代码，要求有明确的设计语言、排版系统、色板、组件约束。

## 何时使用

- 用户要构建 web 组件 / 页面 / 落地页 / 仪表盘 / React 组件 / HTML/CSS 布局
- 用户要美化现有 UI（升级设计质量、消除 AI slop）
- 用户要做设计系统（design tokens / typography / color palette）
- 用户要构建可交互 demo / 原型

不要用于：office 文档交付（用 docx/pdf）、纯视觉海报（用 canvas-design）。

## 工作流程

1. **意图识别**：区分 build / restyle / design-system / prototype；提取目标平台（web/desktop/mobile）、技术栈、设计语言参考。
2. **设计语言定义**：先输出 design tokens（color / spacing / typography / radius / shadow），让用户确认或挑选预设主题；禁止随意使用色值。
3. **组件实现**：按 tokens 实现组件，遵循「单一职责、可组合、无 magic number」原则；优先用 Tailwind utility + shadcn/ui，避免自创 CSS 类。
4. **质量自检**：调用 `webapp-testing` skill 做 Playwright 验证（视觉/交互/响应式）；用 `core/code/agent.py` 的「look → fix」循环修复 slop。
5. **交付**：写入 `.fnix/artifacts/<slug>/index.html`（或 React 组件），返回路径与设计 tokens 摘要。

## 输出契约

- `output_format: html`（或 `tsx` / `jsx`，按用户技术栈）
- 产物路径：`.fnix/artifacts/<task_slug>/index.html` 或 `.tsx` 文件
- 元数据：`{ "tokens": {...}, "components": int, "responsive": bool, "a11y_score": float }`
- Anti-slop 检查项：
  - 无低对比度文字（WCAG AA 起步）
  - 无 emoji 当 icon（除非用户明确要求）
  - 无滥用渐变（≤2 处渐变/页）
  - 无卡片堆叠无层次（必须有 clear visual hierarchy）
  - 无自创 magic CSS 类（必须用 design tokens）
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.core.code.agent.CodeAgent` + `fnixagent.core.code.tools`
- 工具注册：`frontend-design.build` / `frontend-design.restyle` / `frontend-design.design_system` / `frontend-design.prototype`
- 主题：与 `theme-factory` skill 协作，从 10 个预设主题选一个作为设计基底
- 验证：与 `webapp-testing` skill 协作，自动做 Playwright UI 验证
- 模式：Code 模式 — 写盘前先 diff 给用户审阅；产物落 `.fnix/artifacts/`

## 示例

**用户**：做一个 SaaS 产品落地页，要有 hero / features / pricing / footer，用 Tailwind + shadcn。

**Skill 执行**：
1. `frontend-design.design_system(theme="nordic")` 输出 tokens
2. `frontend-design.build(sections=["hero", "features", "pricing", "footer"], stack="tailwind+shadcn")`
3. 自检：调用 `webapp-testing` 做 3 视口（mobile/tablet/desktop）截图 + a11y 扫描
4. 发现 hero 区 contrast 不达标 → 进入 look → fix 循环
5. 返回 `.fnix/artifacts/saas_landing/index.html`
