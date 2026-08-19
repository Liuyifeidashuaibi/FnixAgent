# Brand Typography / 品牌字体

> 一种字体 + 系统字体回退。简洁、克制、专业。

---

## 主字体 / Primary: Inter

**为什么选 Inter:**

- ✅ 开源(OFL 许可,可商用)
- ✅ 现代开发者首选字体(Tailwind / Vercel / GitHub 等)
- ✅ 中文用 `Inter + 系统中文` 回退
- ✅ 完整字重:Thin / Light / Regular / Medium / SemiBold / Bold / ExtraBold / Black

**使用方式**:

```html
<!-- Web (Google Fonts) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

```css
/* CSS */
:root {
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont,
               'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei',
               'Helvetica Neue', sans-serif;
}
```

```typescript
// Tailwind config
export default {
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont',
               'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
      },
    },
  },
}
```

---

## 等宽字体 / Monospace: JetBrains Mono

**为什么选 JetBrains Mono:**

- ✅ 开源(OFL)
- ✅ 开发者首选
- ✅ 完整的代码提示 ligature(支持 `->` `=>` `!=` 等)
- ✅ 中文回退用系统等宽

```css
:root {
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace,
               'SF Mono', Menlo, Consolas, monospace;
}
```

---

## 字号规范 / Type Scale

使用 **1.25 完美四度音阶**(Major Third):

| Token | Size | Line Height | 用途 |
| --- | --- | --- | --- |
| `text-xs` | 12 px | 16 px (1.33) | 辅助标签 |
| `text-sm` | 14 px | 20 px (1.43) | 次要文字 |
| `text-base` | 16 px | 24 px (1.50) | 正文 |
| `text-lg` | 20 px | 28 px (1.40) | 小标题 |
| `text-xl` | 25 px | 32 px (1.28) | 中标题 |
| `text-2xl` | 31 px | 38 px (1.23) | 大标题 |
| `text-3xl` | 39 px | 46 px (1.18) | 卡片标题 |
| `text-4xl` | 49 px | 56 px (1.14) | 页面标题 |
| `text-5xl` | 61 px | 68 px (1.11) | Hero |
| `text-6xl` | 76 px | 84 px (1.10) | Landing |

---

## 字重 / Weights

| Token | Weight | 用途 |
| --- | --- | --- |
| `font-normal` | 400 | 正文 |
| `font-medium` | 500 | 强调文字 |
| `font-semibold` | 600 | 小标题、按钮 |
| `font-bold` | 700 | 大标题 |

**禁止使用**:
- ❌ `font-light` (300) — 屏幕易糊
- ❌ `font-extralight` (200) — 同上
- ❌ `font-black` (900) — 太重,仅限 Logo 装饰

---

## 中英混排 / Mixed CJK + Latin

**规则**:

1. 中英文之间加 1 个半角空格(可选,正式文档建议加)
2. 中文标点 vs 英文标点:文档中**统一中文标点**,代码中**统一英文标点**
3. 中文行宽 ≤ 42 字 / 行,英文行宽 ≤ 75 字 / 行
4. 不在中文字符间插入 `letter-spacing`(会让中文破碎)

---

## 代码字体 / Code Style

```python
# 函数名 snake_case
def calculate_task_priority(goal: str) -> float:
    ...

# 类名 PascalCase
class MemoryStore:
    ...

# 常量 UPPER_SNAKE_CASE
MAX_CONTEXT_TOKENS = 8192
```

```typescript
// 变量 camelCase
const taskGraph = new TaskGraph()

// 类型/类 PascalCase
interface AgentConfig { ... }
class MemoryStore { ... }

// 常量 UPPER_SNAKE_CASE
const MAX_RETRY_COUNT = 3
```

---

## 标点 / Punctuation

| 场景 | 标点 |
| --- | --- |
| 中文文档 | `，。；：「」『』（）《》` |
| 英文文档 | `, . ; : " " ' ' ( )` |
| 代码 | 全英文标点 |

---

## 不要做的事 / Don't

| ❌ 行为 | 后果 |
| --- | --- |
| 引入第 4 种字体 | 视觉混乱 |
| 用 `font-weight: bold` 字面标签 | 不一致 |
| 在不同 platform 用不同字体 | 跨设备不一致 |
| 在中文间 letter-spacing | 阅读破碎 |
| Logo 用普通字体拼"FnixAgent" | 必须是 Logo SVG |

---

## 参考 / References

- [Inter](https://rsms.me/inter/)
- [JetBrains Mono](https://www.jetbrains.com/lp/mono/)
- [Type Scale Calculator](https://type-scale.com/)
- [WCAG Text Spacing](https://www.w3.org/WAI/WCAG21/Understanding/text-spacing.html)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.