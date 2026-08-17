---
name: frontend-skill
description: 克制高级感前端界面：落地页/SaaS/原型，强调信息层级与排版
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: html
tags:
  - frontend
  - landing
  - saas
  - typography
  - trae-work
---
# Frontend Skill（克制高级感界面）

构建结构清晰、风格克制的落地页 / SaaS / Demo 界面。强调信息层级、排版与留白，拒绝卡片堆叠与「AI slop」。

> 与 `frontend-design` 的分工：`frontend-design` 追求鲜明艺术风格；本 skill 追求 Linear 式克制、高端、功能优先。

## 何时使用

- 落地页、SaaS 首页、产品营销页、原型 Demo
- 需要清晰信息层级与专业排版，而非强烈装饰风格
- 用户提到「克制 / 高级感 / 像 Linear / 干净」

不要用于：有 Figma 稿需还原（用 `figma`）、要强烈艺术主题（用 `frontend-design`）。

## 硬规则

1. **一张构图**：首屏一个主视觉叙事，不要仪表盘式多模块堆砌。
2. **少卡片**：默认无卡片；交互容器才用边框/底色。
3. **图像主导**：真图或产品截图作主锚点；纯装饰渐变不算主视觉。
4. **排版**：表达性字体，避免 Inter/Roboto/Arial；严格字号阶梯。
5. **动效**：2–3 处有意运动即可，禁止噪声动画。
6. **反模式**：紫白渐变、奶油底+衬线+陶土色、报纸密栏、glow、大圆角 pill 堆。

## 工作流程

1. 定义视觉基调（1 句）+ 内容大纲（hero / 一节一件事）。
2. 定 tokens（色/字/间距），再写代码。
3. 用 `webapp-testing` 做视口与 a11y 抽检。
4. 交付到 `.fnix/artifacts/<slug>/`。

