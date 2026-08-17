---
name: theme-factory
description: 10 预设主题 + 自定义 — 色板/字体/间距/圆角 design tokens
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: json
tags:
  - theme
  - design-tokens
  - palette
  - typography
  - design
resources:
  - apps/workbench/src/utils/themes.ts
---

# Theme Factory Skill

主题工厂技能，目标：提供 10 个经过精心调配的预设主题，并支持基于品牌色自定义生成新主题。输出标准 design tokens（色板 / 字体 / 间距 / 圆角 / 阴影），可被 `frontend-design` / `artifacts-builder` / `pptx` / `canvas-design` 等 skill 复用。

## 何时使用

- 用户在用 `frontend-design` / `artifacts-builder` / `pptx` / `canvas-design` 前需要选主题
- 用户要做品牌主题定制（基于品牌色生成完整 tokens）
- 用户要做暗色/亮色模式切换
- 用户要做主题预览（让用户从 10 个预设中选）

不要用于：直接构建 UI（用 frontend-design）、做单张海报（用 canvas-design）。

## 工作流程

1. **意图识别**：区分 list / preview / generate / customize；提取品牌色（可选）、调性（professional / playful / minimal / bold）。
2. **预设选择**：若用户无品牌色，输出 10 个预设主题预览（thumbnail + 描述）；让用户挑选。
3. **自定义生成**：若用户提供品牌色，按「色相旋转 + 亮度梯度」生成完整 11 阶色板（50/100/200/.../900/950）；自动选配字体（衬线/无衬线/等宽）与圆角风格。
4. **导出 tokens**：输出标准 design tokens JSON（CSS variables / Tailwind config / shadcn theme 三种格式）。
5. **交付**：写入 `.fnix/artifacts/<slug>_theme.json`（或 `.css` / `.ts`），返回路径与主题摘要。

## 输出契约

- `output_format: json`（可导出为 `.css` / `.ts` / `.tsx`）
- 产物路径：`.fnix/artifacts/<task_slug>_theme.json`（+ 同名 `.css` / `.ts` 可选）
- tokens schema：
  ```json
  {
    "name": str,
    "mode": "light" | "dark" | "both",
    "colors": {
      "primary": { "50": "#...", ..., "950": "#..." },
      "neutral": { ... },
      "accent": { ... }
    },
    "typography": { "heading": str, "body": str, "mono": str },
    "spacing": { "unit": "4px", "scale": [0,1,2,3,4,6,8,12,16] },
    "radius": { "sm": "2px", "md": "6px", "lg": "12px" },
    "shadow": { "sm": "...", "md": "...", "lg": "..." }
  }
  ```
- 预设主题：nordic / sunset / forest / ocean / mono / candy / slate / amber / royal / neon
- 自定义约束：色板必须满足 WCAG AA 对比度（≥4.5:1 文字 / ≥3:1 大字）
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`apps/workbench/src/utils/themes.ts`（前端主题工具，后端通过工具调用复用色板配置）
- 工具注册：`theme-factory.list` / `theme-factory.preview` / `theme-factory.generate` / `theme-factory.customize` / `theme-factory.export`
- 协作：被 `frontend-design` / `artifacts-builder` / `pptx` / `canvas-design` / `brand-guidelines` 调用
- 持久化：用户选定的主题写入 `.fnix/artifacts/<slug>_theme.json`，可被多个 skill 复用
- 模式：Work 模式（产物是 tokens，不直接写代码）

## 示例

**用户**：基于品牌色 `#FF5722` 生成一个主题，要有暗色模式。

**Skill 执行**：
1. `theme-factory.generate(brand_color="#FF5722", mode="both", tone="professional")`
2. 生成 11 阶 primary 色板（基于 HSL 旋转 + 亮度梯度）
3. 自动配字体：heading = Inter / body = Inter / mono = JetBrains Mono
4. 输出 light + dark 两套 tokens
5. 验证 WCAG AA 对比度
6. 返回 `.fnix/artifacts/brand_orange_theme.json`（+ `.css` 文件）
