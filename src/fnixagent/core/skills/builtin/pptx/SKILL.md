---
name: pptx
description: PPT 创建/布局/主题/演讲备注，对应 PPTExpert
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: pptx
tags:
  - pptx
  - powerpoint
  - slides
  - office
  - work
resources:
  - office/powerpoint.py
  - office/chart.py
  - office/image.py
---

# PPTX Skill

本机 PPT 制作技能，基于 `PPTExpert` (python-pptx) 与 `ChartExpert`。所有产物落 `.fnix/artifacts/`，遵循 Work 模式「先交产物再写盘」契约。

## 何时使用

- 用户要创建演示文稿（路演 / 内部汇报 / 培训课件）
- 需要套用主题、统一配色、批量改字体
- 需要在 PPT 中插入图表（柱/折线/饼/散点）或图片
- 需要生成演讲者备注（speaker notes）
- 需要把 Markdown 大纲一键转成 PPT

不要用于：纯文档交付（用 docx）、数据表格（用 xlsx）、纯视觉海报（用 canvas-design）。

## 工作流程

1. **意图识别**：区分 create / restyle / chart / notes / export；提取主题、目标页数、受众。
2. **大纲 → 页面映射**：把用户给的大纲拆成 slide 列表，每页确定 layout（title / content / two_content / image / chart / section）。
3. **执行**：调用 `PPTExpert.create` / `add_slide` / `apply_theme` / `set_layout`；图表用 `ChartExpert.render` 后插入；图片用 `ImageExpert.prepare`。
4. **演讲备注**：根据每页要点自动生成 80–150 字的 speaker notes，用户可后续编辑。
5. **交付**：写入 `.fnix/artifacts/<slug>.pptx`，返回路径与 `{ "slides": int, "charts": int, "images": int, "theme": str }`。

## 输出契约

- `output_format: pptx`
- 产物路径：`.fnix/artifacts/<task_slug>.pptx`
- 元数据：`{ "slides": int, "charts": int, "images": int, "has_notes": bool }`
- 备注模式：每页 speaker notes 必填（即使为简短摘要），便于用户后续演讲
- 失败时不写盘，返回 `ExpertResult(success=False, error=<原因>)`

## Fnix 集成点

- 底层实现：`fnixagent.office.powerpoint.PPTExpert`
- 工具注册：`pptx.create` / `pptx.add_slide` / `pptx.apply_theme` / `pptx.set_layout` / `pptx.add_chart` / `pptx.add_image` / `pptx.set_notes` / `pptx.export_images`
- 主题：与 `theme-factory` skill 协作，把 10 个预设主题之一应用为 PPT 主题
- 图表：`office/chart.py` 的 `ChartExpert` 生成图片后插入幻灯片
- 模板：`office/template.py` 加载组织 PPT 模板套用封面/封底

## 示例

**用户**：把 `pitch_outline.md` 转成 12 页路演 PPT，主题用「科技蓝」，每页加演讲备注。

**Skill 执行**：
1. 解析 `pitch_outline.md` 拆 12 个 slide
2. `pptx.create(theme="tech_blue", title="路演", subtitle="...")`
3. 逐页 `pptx.add_slide(layout="content", title=..., bullets=[...])`
4. `pptx.set_notes(slide_index=i, notes=...)` 自动生成备注
5. 返回 `.fnix/artifacts/pitch_deck.pptx`
