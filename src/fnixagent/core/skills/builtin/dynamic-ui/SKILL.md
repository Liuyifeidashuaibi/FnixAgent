---
name: dynamic-ui
description: 在对话流内联渲染紧凑可视化 — 图表、架构图、对比矩阵、交互 demo。仅当可视化比 Markdown 更清晰时使用；不用于网站、应用、长报告、看板或幻灯片。
version: 1.0.0
license: Apache-2.0
level: reasoning
output_format: html
tags:
  - widget
  - visualization
  - chart
  - diagram
  - inline
  - trae-work
triggers:
  - 可视化
  - 图表
  - 对比
  - 比较
  - 流程图
  - 架构图
  - 示意图
  - 决策
  - 选型
  - chart
  - diagram
  - visualize
  - comparison
  - flowchart
resources:
  - src/fnixagent/core/tools/workspace.py#show_widget
  - apps/workbench/src/components/chat/WidgetBlock.tsx
---

# dynamic-ui — 对话内联可视化

## 适用范围

当紧凑的内联可视化能让「关系 / 数量级 / 选项取舍 / 单个局部交互」更清晰时使用：数据图表、架构图、流程图、对比决策矩阵、机制示意图、微交互 demo。

**禁止**用于：独立网站/应用、长报告、看板、幻灯片、一句话事实、单步命令、Markdown 表格就能扫读的内容、没有视觉焦点的内容、纯装饰。

## 工具契约

必须调用 `show_widget` 工具渲染，参数：
- `widget_code`（必填）：完整 SVG/HTML 字符串（含 `<style>`），**不要** `<!DOCTYPE>` / `<html>` / `<head>` / `<body>` 包裹
- `widget_type`：`chart` / `table` / `flow` / `decision` / `mechanism` / `custom`
- `mode`：保持默认 `inline`，不要传 `panel`

决定渲染 widget 时，静默完成布局与代码推理，直接调用工具。不要在回复正文里流式输出规划笔记、草稿代码、片段或「正在组装代码」之类的过渡句。widget 代码只出现在工具调用内。

## 运行时硬约束（Fnix 沙箱）

渲染环境是 iframe sandbox（`allow-scripts`，无 same-origin），CSP 为 `default-src 'none'; script-src 'unsafe-inline'; connect-src 'none'`：

1. **禁止外部资源**：不能加载任何 CDN 脚本/样式/字体/图片 URL。Chart.js、ECharts 等外部库全部不可用。图表必须用**纯 SVG + CSS + 原生 JS** 手绘。图片仅允许 `data:` / `blob:`。
2. **禁止内联事件属性**：`onclick=` / `onload=` 等 `on*=` 属性会被前端清洗剥离。交互一律在末尾单个 `<script>` 块内用 `addEventListener` 或事件委托绑定。
3. **禁止网络请求**：`fetch` / XHR / WebSocket 全部被 CSP 拦截。数据直接内嵌在代码里。
4. 输出顺序：`<style>` → 内容 HTML/SVG → `<script>`（仅在需要交互时）。
5. 根元素加 `data-dynamic-ui-widget` 属性；所有 DOM 查询限定在根元素内（`root.querySelector`），禁止 `document.currentScript`、兄弟遍历、全局选择器、`position: fixed`。
6. **按钮回灌对话**：需要模型继续推理的后续问题，调用 `window.sendPrompt('具体问题文本')`（宿主已注入该桥接函数）。仅用于需要 AI 回答的追问，不用于本地 UI 行为（本地行为用 addEventListener 自己处理）。给回灌按钮加 class `fnix-prompt-btn` 以获得统一样式。

## 主题与配色

宿主 iframe 已注入以下 CSS 变量（自动适配明暗主题），**必须**引用变量而非硬编码颜色：

- 主色 `var(--brand)`（青灰）、`var(--brand-soft)`（主色浅底）
- 表面 `var(--surface)` / `var(--surface-muted)`
- 文本 `var(--text-primary)` / `var(--text-secondary)` / `var(--text-muted)`
- 边框 `var(--border)`；语义色 `var(--success)` / `var(--danger)` / `var(--warning)`
- 圆角 `var(--radius)`；字体 `var(--font-sans)` / `var(--font-mono)`

规则：
- 卡片/面板/表格底色用 `--surface`，嵌套区域用 `--surface-muted`；**永不**用品牌色/语义色做大面积卡片填充，焦点用边框或标记表达
- 语义色（绿/红/黄）仅当数据本身是状态/风险变量时使用；普通图表/流程图先用中性色 + `--brand`
- 扁平设计：无渐变、无噪点纹理、无装饰特效
- 正文 ≥14px，说明文字 12px，禁止更小；禁止嵌套滚动

## 内容规则

每个 widget 只有**一个**视觉焦点（推荐项、关键路径、瓶颈、最大值、阶段边界、风险标记），用位置、标签或单个强调色标出，不依赖颜色单独传达。

复杂度预算：
- 1 个焦点、2-5 个主节点、2-4 个选项/KPI/系列、1 个交互概念
- 横向一排最多 4 个盒子；5+ 项要分组、换行或拆分
- 节点标签 2-5 词；卡片标题 6-10 词；连接线标签 1-3 词，显而易见的省略
- 超预算时：视觉上做汇总，细节放回复正文

数据诚实：估算值标注"估算"；数值旁标单位；来源模糊时不要显示过度精确的数字。禁止渲染地图，用按地区的柱状/表格/矩阵替代。

分离原则：解释性文字放回复正文；视觉证据放 widget。图表 widget 只放图表 + 可选短标题 + 坐标轴/图例/标签，不在 widget 内写结论、分析、建议。

## SVG 几何规则

- viewBox 优先 `0 0 720 H`，`width="100%"`，安全边距 ≥40 单位
- 出图前先做坐标规划：画布、行列、节点包围盒、连接线轨道、标签槽位；任何文本放不下就先精简内容，禁止靠缩小字号、裁剪溢出、背景矩形遮挡解决
- 同行节点间距 ≥32（流程步骤 ≥60）；同列 ≥28（中间有连接线标签时 ≥56）
- 连接线 `fill="none"`，默认中性色（`--text-muted` / `--border`），主路径用 `--brand`；箭头用标准 marker（`viewBox="0 0 8 8"` `refX="7"` `refY="4"` `orient="auto"` + `marker-end`），禁止手绘装饰性箭头
- 连接线不得穿过无关节点或文本；标签放圆角胶囊里，离线条 ≥8 单位
- 起止节点用胶囊形；决策节点用圆角路径而非尖角菱形

## 场景速查

| 用户意图 | widget_type | 首选形式 |
|---|---|---|
| 数值趋势/占比/分布 | chart | 纯 SVG 折线/柱状/环形 |
| 模块关系/依赖/流程/状态机 | flow | SVG 节点+连接线 |
| 选型对比/风险矩阵 | decision | 对比卡片组 / 决策表 |
| 原理/机制/因果链 | mechanism | 分步示意图 |
| 参数切换/状态演示 | custom | HTML + addEventListener 微交互 |

## 交互示例骨架

```html
<style>
  [data-dynamic-ui-widget] { font-family: var(--font-sans); color: var(--text-primary); }
  .du-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; }
  .du-tab { padding: 4px 12px; border: 1px solid var(--border); border-radius: 999px; background: var(--surface); cursor: pointer; font-size: 12px; }
  .du-tab.active { border-color: var(--brand); color: var(--brand); background: var(--brand-soft); }
  .fnix-prompt-btn { padding: 4px 12px; border: 1px solid var(--brand); border-radius: var(--radius); background: var(--brand-soft); color: var(--brand); cursor: pointer; font-size: 12px; }
</style>
<div data-dynamic-ui-widget data-template="micro-interaction">
  <div class="du-card">
    <div class="du-tabs"><button class="du-tab active" data-k="a">方案 A</button><button class="du-tab" data-k="b">方案 B</button></div>
    <div class="du-body" data-panel="a">…方案 A 内容…</div>
    <div class="du-body" data-panel="b" hidden>…方案 B 内容…</div>
    <button class="fnix-prompt-btn" data-prompt="详细展开方案 A 的实施步骤">让 AI 展开方案 A</button>
  </div>
</div>
<script>
  (function () {
    var root = document.querySelector('[data-dynamic-ui-widget]');
    if (!root || root.dataset.mounted) return;
    root.dataset.mounted = 'true';
    root.addEventListener('click', function (e) {
      var tab = e.target.closest('.du-tab');
      if (tab) {
        root.querySelectorAll('.du-tab').forEach(function (t) { t.classList.toggle('active', t === tab); });
        root.querySelectorAll('.du-body').forEach(function (p) { p.hidden = p.dataset.panel !== tab.dataset.k; });
        return;
      }
      var pb = e.target.closest('.fnix-prompt-btn');
      if (pb && window.sendPrompt) window.sendPrompt(pb.dataset.prompt || pb.textContent);
    });
  })();
</script>
```
