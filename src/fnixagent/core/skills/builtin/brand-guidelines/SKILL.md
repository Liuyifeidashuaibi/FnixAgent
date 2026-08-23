---
name: brand-guidelines
description: 品牌规范 — 色板/字体/排版/Logo 用法/语气
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: md
tags:
  - brand
  - guidelines
  - identity
  - design
  - consistency
resources:
  - office/template.py
  - apps/workbench/src/utils/themes.ts
---

# Brand Guidelines Skill

品牌规范技能，目标：从已有品牌资产（logo / 色板 / 字体 / 文案样本）中提炼品牌规范文档，作为所有产物（docx / pptx / pdf / web / 海报）的一致性约束源。

## 何时使用

- 用户首次接入 Fnix，希望从已有品牌资产生成 brand guidelines
- 用户产物（pptx / docx / 海报）需要符合品牌规范
- 用户要做品牌升级 / 重塑
- 用户希望 AI 生成的所有内容保持品牌语气一致

不要用于：纯主题色板生成（用 theme-factory）、单次产物设计（用对应 skill）。

## 工作流程

1. **资产收集**：让用户上传 logo / 现有文档 / 网址 / 文案样本；从资产中提取主色 / 字体 / 措辞风格。
2. **规范提炼**：输出 brand guidelines 草稿，含：
   - 视觉：主色 / 辅色 / 字体配对 / Logo 用法（最小尺寸 / 安全边距 / 禁用案例）
   - 排版：标题层级 / 行距 / 段距 / 引用样式
   - 语气：品牌调性关键词 / 示例句 / 禁用词
3. **用户审阅**：让用户确认或修正规范；定稿后写入 `.fnix/brand/guidelines.md`。
4. **应用约束**：在后续 `docx` / `pptx` / `frontend-design` / `canvas-design` 调用时，自动加载 guidelines 作为约束。
5. **交付**：写入 `.fnix/brand/guidelines.md`（同时生成 `.fnix/brand/tokens.json` 供程序化使用），返回路径与摘要。

## 输出契约

- `output_format: md`（同时生成 `tokens.json` 程序化版本）
- 产物路径：`.fnix/brand/guidelines.md` + `.fnix/brand/tokens.json`
- guidelines.md 必含章节：
  - `# 品牌概述`（使命 / 调性关键词）
  - `# 视觉规范`（色板 / 字体 / Logo 用法）
  - `# 排版规范`（标题层级 / 行距 / 段距）
  - `# 语气规范`（调性 / 示例 / 禁用词）
  - `# 应用案例`（正确 / 错误对照）
- tokens.json schema：
  ```json
  {
    "colors": { "primary": "#...", "secondary": "#...", "accent": "#..." },
    "fonts": { "heading": str, "body": str, "mono": str },
    "voice": { "tone": [str], "examples": [str], "forbidden_words": [str] }
  }
  ```
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.office.template.TemplateManager`（加载/管理 brand guidelines）
- 工具注册：`brand-guidelines.extract` / `brand-guidelines.validate` / `brand-guidelines.apply` / `brand-guidelines.list`
- 协作：被 `docx` / `pptx` / `frontend-design` / `canvas-design` / `internal-comms` 调用为约束源
- 持久化：写入 `.fnix/brand/`（项目级品牌规范，跨产物复用）
- 模式：Work 模式（产物是规范文档，作为后续产物的约束源）

## 示例

**用户**：我们公司有 logo（`logo.png`）和官网（`example.com`），帮我生成 brand guidelines。

**Skill 执行**：
1. `brand-guidelines.extract(logo="logo.png", website="example.com", samples=[...])`
2. 从 logo 提取主色 #1A56DB；从官网提取字体（Inter / Source Han Sans）；从文案样本提取调性「专业 / 克制 / 数据驱动」
3. 输出 guidelines.md 草稿，含 5 章
4. 用户调整禁用词清单
5. 写入 `.fnix/brand/guidelines.md` + `.fnix/brand/tokens.json`
6. 后续调用 `pptx.create(...)` 自动加载此 guidelines 约束字体/色板
