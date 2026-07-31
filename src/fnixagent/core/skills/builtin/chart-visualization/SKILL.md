---
name: chart-visualization
description: 按数据特征选图并生成趋势/对比/分布/拓扑等可视化结果
version: 1.0.0
license: Apache-2.0
level: REASONING
output_format: png
tags:
  - chart
  - visualization
  - data
  - trae-work
---
# Chart Visualization Skill

根据数据特征选择合适图表类型，生成清晰的可视化（图片或可交互 HTML）。强调「选对图」而不是堆砌装饰。

## 何时使用

- 用户要看趋势、对比、分布、占比、关系/拓扑、地理分布
- 已有分析结果需要可视化交付
- 需要双轴、多系列、桑基、网络关系等较复杂图

不要用于：海报/封面艺术表达（用 `canvas-design`）、纯数值表交付（用 `xlsx` / `data-analysis`）。

## 选图规则（简表）

| 数据关系 | 优先图表 |
|---|---|
| 时间趋势 | 折线 / 面积 |
| 类别对比 | 柱状 / 条形 |
| 占比构成 | 堆叠柱 / 树图（慎用饼图） |
| 分布 | 直方图 / 箱线 |
| 相关 | 散点 |
| 流向 | 桑基 |
| 拓扑/依赖 | 网络关系图 |
| 地理 | 区域/轨迹图 |

## 工作流程

1. **理解意图**：指标、维度、对比对象、受众。
2. **选图**：按上表；说明为何不选其他图。
3. **编码**：颜色区分系列；轴标签完整；避免 3D/彩虹色盘。
4. **生成**：Python（matplotlib/plotly）或 HTML（ECharts）；输出到 `.fnix/artifacts/<slug>/`。
5. **自检**：色盲友好、图例可读、标题说明「什么+时间范围」。

## 输出契约

返回图片/HTML 路径 + 图表类型 + 所用字段映射。

