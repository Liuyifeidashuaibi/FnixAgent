---
name: canvas-design
description: PNG/PDF 视觉设计 — 海报/名片/封面/信息图
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: png
tags:
  - canvas
  - design
  - visual
  - poster
  - creative
resources:
  - office/image.py
  - office/chart.py
---

# Canvas Design Skill

视觉设计技能，目标：产出 PNG / PDF 格式的视觉作品（海报 / 名片 / 封面 / 信息图 / 社交媒体图）。强调「设计意图驱动」而非「布局堆叠」，所有元素必须服务于一个明确的视觉焦点。

## 何时使用

- 用户要做海报（活动 / 营销 / 招聘）
- 用户要做名片 / 邀请函 / 证书
- 用户要做封面（报告 / 书籍 / 专辑）
- 用户要做信息图（数据可视化 + 视觉叙事）
- 用户要做社交媒体配图（公众号头图 / Twitter card / 小红书）

不要用于：复杂交互 UI（用 frontend-design）、office 文档（用 docx/pdf skill）、纯数据图表（用 xlsx chart）。

## 工作流程

1. **意图识别**：从用户输入提取作品类型 / 尺寸 / 主题 / 调性 / 必含元素（文字 / logo / 日期 / 二维码）。
2. **设计构思**：输出 1–2 句「视觉焦点」描述 + 色板（≤3 主色） + 字体配对（≤2 字体）；让用户确认。
3. **布局草稿**：用 SVG / HTML 预览草稿（线框 + 文字位置），让用户确认布局。
4. **渲染**：调用 `office/image.py` 渲染为 PNG（300dpi）或 PDF（矢量）；图片素材用 `ImageExpert.prepare` 处理。
5. **质量自检**：检查分辨率 / 色彩空间（sRGB） / 印刷安全边距 / 文字可读性；失败进入 fix 循环。
6. **交付**：写入 `.fnix/artifacts/<slug>.png`（或 `.pdf`），返回路径与 `{ "size": str, "dpi": int, "colors": [...] }`。

## 输出契约

- `output_format: png`（默认；印刷场景输出 `pdf`）
- 产物路径：`.fnix/artifacts/<task_slug>.png` 或 `.pdf`
- 元数据：`{ "size_px": [w, h], "dpi": int, "color_mode": "sRGB", "palette": [...] }`
- 设计约束：
  - 主色 ≤3（避免色板混乱）
  - 字体 ≤2（标题 + 正文）
  - 焦点元素 ≤1（视觉中心明确）
  - 印刷场景必留 3mm 出血 + 5mm 安全边距
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.office.image.ImageExpert` + `fnixagent.office.chart.ChartExpert`
- 工具注册：`canvas-design.poster` / `canvas-design.card` / `canvas-design.cover` / `canvas-design.infographic` / `canvas-design.social`
- 主题：与 `theme-factory` skill 协作套用预设色板
- 品牌约束：与 `brand-guidelines` skill 协作确保符合品牌规范
- 链式协作：完成后可调 `pdf` skill 转 PDF；或嵌入 `docx` / `pptx` skill 产物
- 模式：Work 模式 — 产物落 `.fnix/artifacts/`；不修改用户源码

## 示例

**用户**：做一张 A4 活动海报，主题「AI Salon」，时间 2026-08-15，地点上海，配图用科技感几何元素。

**Skill 执行**：
1. `canvas-design.poster(type="event", size="A4", theme="tech_geometry")`
2. 设计焦点：「AI Salon」标题居中放大；色板 = 深蓝 #0B1F3F + 金 #E5B567 + 白；字体 = Montserrat + 思源黑体
3. 输出 SVG 草稿让用户确认布局
4. 渲染为 PNG（300dpi, 2480×3508）
5. 自检：分辨率达标 / 安全区无关键元素裁切
6. 返回 `.fnix/artifacts/ai_salon_poster.png`
