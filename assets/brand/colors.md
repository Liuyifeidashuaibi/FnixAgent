# Brand Colors / 品牌色

> FnixAgent 官方品牌色 — 源自 Logo 真实采样。
> 严格使用以下色值,**不要**自行添加新的主色。

---

## 核心色 / Core Palette

### 立方体灰阶(Cube Grays)

Logo 是**等距投影立方体**配 **AI 神经节点**,主色为冷灰阶:

| Token | Hex | RGB | 用途 |
| --- | --- | --- | --- |
| `--brand-cube-top` | `#E8E8E8` | 232, 232, 232 | 立方体顶面(高光) |
| `--brand-cube-mid` | `#A0A0A0` | 160, 160, 160 | 立方体顶面渐变收尾 |
| `--brand-cube-left` | `#7A7A7A` | 122, 122, 122 | 左面亮区 |
| `--brand-cube-left-shadow` | `#3D3D3D` | 61, 61, 61 | 左面暗区 |
| `--brand-cube-right` | `#5C5C5C` | 92, 92, 92 | 右面亮区 |
| `--brand-cube-right-shadow` | `#1F1F1F` | 31, 31, 31 | 右面暗区 |
| `--brand-stroke` | `#0A0A0A` | 10, 10, 10 | 立方体描边 |

### 神经节点(Node)

| Token | Hex | RGB | 用途 |
| --- | --- | --- | --- |
| `--brand-node` | `#FFFFFF` | 255, 255, 255 | 节点核心 |
| `--brand-node-glow` | `rgba(255,255,255,0.6)` | — | 节点光晕外层 |

---

## 中性色 / Neutrals

UI 文字、背景、边框:

| Token | Hex | 用途 |
| --- | --- | --- |
| `--neutral-0` | `#FFFFFF` | 纯白 |
| `--neutral-50` | `#FAFAFA` | 极浅背景 |
| `--neutral-100` | `#F5F5F5` | 浅背景 |
| `--neutral-200` | `#E5E5E5` | 卡片分隔 |
| `--neutral-400` | `#A3A3A3` | 次要文字 |
| `--neutral-600` | `#525252` | 辅助文字 |
| `--neutral-800` | `#262626` | 正文 |
| `--neutral-900` | `#171717` | 标题 |
| `--neutral-950` | `#0A0A0A` | 深背景 |

---

## 语义色 / Semantic

**克制使用** — 仅用于状态指示,不参与品牌主色:

| Token | Hex | 用途 |
| --- | --- | --- |
| `--color-success` | `#10B981` | 成功 |
| `--color-warning` | `#F59E0B` | 警告 |
| `--color-danger` | `#EF4444` | 错误 |
| `--color-info` | `#3B82F6` | 信息 |

---

## 暗色模式 / Dark Mode

品牌色保持不变(灰阶),背景翻转为:

| Token | 暗色值 |
| --- | --- |
| `--bg-primary` | `#0A0A0A` |
| `--bg-secondary` | `#171717` |
| `--bg-tertiary` | `#262626` |
| `--fg-primary` | `#FAFAFA` |
| `--fg-secondary` | `#A3A3A3` |
| `--border-default` | `#262626` |

---

## 对比度 / Contrast

| 组合 | 比率 | WCAG |
| --- | --- | --- |
| 顶面 `#E8E8E8` 上黑文字 | 14.7:1 | AAA |
| 右面 `#1F1F1F` 上白文字 | 17.4:1 | AAA |
| 暗背景 `#0A0A0A` 上白文字 | 19.9:1 | AAA |
| 浅背景 `#FFFFFF` 上深文字 | 17.5:1 | AAA |

全部满足 WCAG 2.1 AA,大部分满足 AAA。

---

## 不要使用的颜色 / Forbidden

| ❌ 颜色 | 为什么 |
| --- | --- |
| `#FF6B35` / `#FF5A1F` 橙色 | 占位时期的临时色,已被真实 Logo 取代 |
| `#3B82F6` 蓝色作为主色 | 仅作 info 用,不作品牌色 |
| 纯 `#000000` 黑 | 用 `#0A0A0A` 更柔和 |
| 渐变色作为主色 | Logo 内有,但 UI 中禁止滥用 |

---

## 在代码中使用

```css
/* CSS Variables */
:root {
  --brand-cube-top: #E8E8E8;
  --brand-cube-mid: #A0A0A0;
  --brand-cube-left: #7A7A7A;
  --brand-cube-left-shadow: #3D3D3D;
  --brand-cube-right: #5C5C5C;
  --brand-cube-right-shadow: #1F1F1F;
  --brand-stroke: #0A0A0A;
  --brand-node: #FFFFFF;
}
```

```typescript
// Tailwind config
export default {
  theme: {
    extend: {
      colors: {
        brand: {
          'cube-top': '#E8E8E8',
          'cube-mid': '#A0A0A0',
          'cube-left': '#7A7A7A',
          'cube-left-shadow': '#3D3D3D',
          'cube-right': '#5C5C5C',
          'cube-right-shadow': '#1F1F1F',
          'stroke': '#0A0A0A',
          'node': '#FFFFFF',
        },
      },
    },
  },
}
```

---

© 2024-2026 FnixAgent. All Rights Reserved.