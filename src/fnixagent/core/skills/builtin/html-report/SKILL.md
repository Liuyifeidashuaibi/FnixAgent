---
name: html-report
description: 生成自包含 HTML 交付物（幻灯片除外）— 研究报告、白皮书、PRD、方案书、竞品分析、简历、数据看板等。产物是零外部依赖的 HTML 文件，写入 .fnix/artifacts/。
version: 1.0.0
license: Apache-2.0
level: reasoning
output_format: html
tags:
  - report
  - html
  - deliverable
  - prd
  - whitepaper
  - trae-work
triggers:
  - 报告
  - 研究报告
  - 白皮书
  - PRD
  - 需求文档
  - 方案
  - 竞品分析
  - 可行性
  - 简历
  - 看板
  - report
  - whitepaper
  - dashboard
---

# html-report — 自包含 HTML 报告

用户要求产出结构化书面交付物且**未明确指定** .docx/.pdf 时，默认走本技能：产出一个精心设计、自包含的 HTML 文件。

## 工作流

### Step 1: 规划（写代码前必须完成）

内部确定以下所有决策（简单报告在推理中完成即可；5 章以上的长报告先写 `plan.md` 到产物目录）：

- **元信息**：类型（报告/白皮书/PRD/方案）、主题一句话、读者、语言（与用户提问语言一致）
- **设计系统**：全部样式走 CSS 变量，禁止散落硬编码色值
  - `--bg` 背景 / `--bg2` 表面 / `--ink` 正文 / `--muted` 次要文本 / `--rule` 边框 / `--accent` 强调 / `--accent2` 次强调
  - 对比度 ≥ 4.5:1（WCAG AA）；层级用字号+字重+留白表达，不堆字体族
- **排版**：正文 15-17px，行高 1.6-1.8；最大宽度 860-1080px；确定标题风格与章节间距
- **结构**：章节列表（H2 章 / H3 节 / H4 小节）
- **视觉件**：每个图表/示意图先定「表达什么」再选工具（见 Step 3）
- **核心论点**：2-4 条

### Step 2: 写内容

- 全文与用户语言一致；论点有数据/例证支撑；每段推进论证，不注水
- 重点强调二选一并全文统一：`<strong>` 加粗（正式/学术）或 `<mark class="key">` 强调色（现代/视觉），后者配 CSS `mark.key { background: none; color: var(--accent); font-weight: 600; }`
- 有检索来源时用上标编号引用 `<sup><a href="#cite-1">[1]</a></sup>`，页脚放来源列表（标题+链接+访问日期）

### Step 3: 视觉件

| 需求 | 工具 |
|---|---|
| 数据图表（柱/线/饼/散点） | **内联 SVG 手绘**（首选，零依赖）；数据复杂时 ECharts CDN + `<noscript>` 降级 |
| 流程/架构/时序图 | 内联 SVG（遵循 dynamic-ui 技能的 SVG 几何规则） |
| 迷你趋势/地图 | 内联 SVG |

- 自包含优先：能内联的全部内联；外链仅限 CDN 的 ECharts 且必须有无 JS 时的可读降级
- 图表配色引用设计系统变量；每图一个焦点；估算值明确标注

### Step 4: 落盘与验收

1. 用 `write_file` 写入 `.fnix/artifacts/<报告名>/index.html`（单文件自包含）
2. 附属资源（如拆分的 CSS）同目录；禁止散落到工作区根目录
3. 写完自检：打开无需网络即可读；目录锚点跳转正常；深浅背景下文字可读
4. 回复中列出产物路径与打开方式（双击 index.html）

## 禁止

- 幻灯片（走 html-deck 技能）
- 用户明确要 .docx → 走 docx 技能；明确要 .pdf → 走 pdf 技能
- 空洞的「行动清单」「30 天计划」式填充内容
- 未经验证的精确数字；无来源的关键论断
