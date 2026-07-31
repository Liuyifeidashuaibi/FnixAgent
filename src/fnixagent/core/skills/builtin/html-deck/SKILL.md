---
name: html-deck
description: 从零创建自包含 HTML 幻灯片 — 从主题/大纲/文档/Markdown 生成可在任何浏览器打开的演示文稿。用户要「演示/幻灯片/路演/汇报」且不涉及已有 .pptx 文件时使用；产物永远是 HTML，写入 .fnix/artifacts/。
version: 1.0.0
license: MIT
level: reasoning
output_format: html
tags:
  - slides
  - presentation
  - deck
  - html
  - trae-work
triggers:
  - 幻灯片
  - 演示文稿
  - 演示
  - 路演
  - 汇报
  - 提案
  - 宣讲
  - deck
  - slides
  - presentation
  - keynote
  - pitch
---

# html-deck — 自包含 HTML 幻灯片

用户要新建演示文稿（无既有 .pptx）时使用。产物是单个自包含 HTML 文件，双击即放映。用户明确要 .pptx 时改走 pptx 技能。

## 工作流

### Step 1: 叙事规划（写代码前必须完成）

先确定演示类型（融资路演 / 季度复盘 / 项目启动 / 产品发布 / 课程讲义 / 毕业答辩 / 个人作品集…），据此定叙事骨架。规划一张逐页表（8 页以上的长 deck 建议先落 `plan.md`，最终交付不包含它）：

```
| # | 标题 | 角色 | 内容摘要 | 版式 | 动画 |
|---|------|------|----------|------|------|
| 1 | 封面 | Cover | 主标题+副标题 | cover | 淡入 |
| 2 | 目录 | TOC | 3-5 个议题 | toc | 列表逐项 |
| 3 | 问题 | Section | 章节分隔页 | divider | 上升入场 |
| … | | Body | 每页一个论点 | bullets/chart/comparison | |
| N | 谢谢 | Closing | 联系方式/CTA | thanks | 淡入 |
```

叙事规则：
- 每页**一个**论点；要点每页 ≤4 条，每条 ≤2 行
- 结构遵循「封面 → 目录 → 章节分隔 → 内容 → 总结/CTA」
- 数据页图表优先于文字表格；对比页用左右分栏卡片

### Step 2: 设计系统

单一 `<style>` 块内定义全套 CSS 变量并全文引用（禁止散落硬编码色值）：
- `--bg` / `--bg2` / `--ink` / `--muted` / `--accent` / `--accent2` / `--rule`
- 深浅主题二选一并全 deck 统一；对比度 ≥ 4.5:1
- 标题字号阶梯：封面 ≥56px、页标题 36-44px、正文 20-24px（幻灯片正文比网页大）
- 每页固定 16:9 画布（`aspect-ratio: 16/9`），内容安全边距 ≥6%

### Step 3: 骨架与交互

自包含实现（零外部依赖，禁止 CDN）：

```html
<div class="deck">
  <section class="slide" data-idx="1">…</section>
  <section class="slide" data-idx="2">…</section>
</div>
<script>
  // 键盘 ←/→/Space 翻页、页码指示器、URL hash 同步（#3 直达第 3 页）
  // 入场动画用 CSS class + IntersectionObserver 或翻页时切 class
</script>
```

- 翻页：方向键 / 空格 / 点击左右缘；页脚显示 `当前页/总页数`
- 动画克制：每页 1 种入场效果（fade-up / rise-in / 列表逐项），禁止花哨堆叠
- 图表用内联 SVG 手绘（遵循 dynamic-ui 技能的 SVG 几何规则）；一页一图一个焦点

### Step 4: 落盘与验收

1. `write_file` 写入 `.fnix/artifacts/<deck名>/index.html`
2. 自检：断网可放映；键盘可翻页；每页文字不溢出画布；深浅色下可读
3. 回复列出产物路径 + 「双击打开，←/→ 翻页」

## 禁止

- 外部 CDN / 字体 / 图片 URL（自包含）
- 单页塞多个论点或超过 4 条要点
- 用户明确要 .pptx 时用本技能
- 输出 `<write_file>` XML 假装写文件（必须走 tools API）
