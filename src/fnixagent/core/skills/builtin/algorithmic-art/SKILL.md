---
name: algorithmic-art
description: p5.js 生成艺术 — 几何/粒子/噪声/L-System 视觉作品
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: html
tags:
  - algorithmic-art
  - p5js
  - generative
  - creative
  - code
resources:
  - core/code/agent.py
---

# Algorithmic Art Skill

算法艺术技能，基于 p5.js 生成视觉作品。涵盖几何镶嵌 / 粒子系统 / Perlin 噪声 / L-System / 元胞自动机 / 反应扩散等算法。产物为可独立运行的 HTML（含 p5.js CDN）。

## 何时使用

- 用户要做生成艺术（壁纸 / 装饰画 / 数字藏品）
- 用户要做数据可视化艺术化（如把数据转成视觉作品）
- 用户要做创意编程练习 / 教学示例
- 用户要做交互式视觉装置原型

不要用于：纯静态海报（用 canvas-design）、UI 组件（用 frontend-design）、数据图表（用 xlsx chart）。

## 工作流程

1. **意图识别**：从用户输入提取算法类型（geometry / particles / noise / lsystem / ca / reaction-diffusion）、调性（calm / vibrant / dark / minimal）、目标尺寸。
2. **算法设计**：输出 1 段算法描述（伪代码 + 关键参数）让用户确认；解释视觉预期。
3. **实现**：用 p5.js 实现，遵循「setup() / draw() 分离、参数集中在 config 对象、无 magic number」原则。
4. **预览**：调用 `webapp-testing` skill 截图预览（如可行）；让用户调参迭代。
5. **导出**：产物为 HTML（含 p5.js CDN，离线可运行）；可选导出 PNG 序列帧（用于 GIF / 视频）。
6. **交付**：写入 `.fnix/artifacts/<slug>/index.html`，返回路径与 `{ "algorithm": str, "frames": int, "interactive": bool }`。

## 输出契约

- `output_format: html`（含 p5.js CDN，离线可运行）
- 产物路径：`.fnix/artifacts/<task_slug>/index.html`（可选 `sketch.js` 拆分）
- 元数据：`{ "algorithm": str, "frames": int, "interactive": bool, "params": {...} }`
- 代码规范：
  - p5.js 用 global mode（除非用户要 instance mode）
  - 所有参数集中在 `const CONFIG = { ... }`，禁止 magic number
  - `setup()` 一次初始化，`draw()` 每帧绘制，逻辑分离
  - 帧率控制用 `frameRate(60)` 显式声明
- 可运行性：HTML 必须能在浏览器中直接打开运行（无需 build）
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.core.code.agent.CodeAgent`（生成 p5.js 代码）
- 工具注册：`algorithmic-art.geometry` / `algorithmic-art.particles` / `algorithmic-art.noise` / `algorithmic-art.lsystem` / `algorithmic-art.ca` / `algorithmic-art.reaction_diffusion`
- 验证：与 `webapp-testing` skill 协作截图预览
- 主题：与 `theme-factory` skill 协作套用色板
- 模式：Code 模式 — 写盘前 diff 给用户审阅；产物落 `.fnix/artifacts/`

## 示例

**用户**：用 Perlin 噪声做一个流动场的艺术作品，调性「宁静」，1080×1080。

**Skill 执行**：
1. `algorithmic-art.noise(type="flow_field", tone="calm", size=[1080, 1080])`
2. 算法设计：1000 粒子，按 Perlin 噪声场流动，trail 长度 50，背景 `#0F172A`，粒子色板 `[#E2E8F0, #94A3B8, #64748B]`
3. 输出伪代码让用户确认
4. 实现 `sketch.js`：CONFIG 集中参数，setup/draw 分离
5. 调用 `webapp-testing` 截图预览（30 帧后截图）
6. 用户调粒子数 2000 → 进入 fix 循环
7. 返回 `.fnix/artifacts/perlin_flow_field/index.html`
