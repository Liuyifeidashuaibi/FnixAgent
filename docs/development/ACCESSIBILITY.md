# 可访问性 / Accessibility

> FnixAgent 承诺遵守 WCAG 2.1 AA 标准。本文件定义具体规范和实现要求。

---

## 一、目标 / Goals

- **WCAG 2.1 AA 合规**(目标 AAA,最低 AA)
- **键盘可达 100%**:所有功能纯键盘可用
- **屏幕阅读器友好**:VoiceOver / NVDA / JAWS / Orca 全兼容
- **高对比度模式**:支持系统级高对比度
- **动效可关闭**:遵循 `prefers-reduced-motion`
- **国际化**:右到左 (RTL) / 中文 / 阿拉伯数字

---

## 二、实现规范 / Implementation

### 2.1 语义化 HTML

```tsx
// ❌ div soup
<div onClick={handleClick}>提交</div>

// ✅ button
<button onClick={handleClick} aria-label="提交表单">提交</button>

// ✅ heading 层级
<h1>主标题</h1>
<h2>二级标题</h2>
// 不要跳级
```

### 2.2 ARIA 属性

#### 必备 ARIA

```tsx
// 标签
<label htmlFor="api-key">API Key</label>
<input id="api-key" type="password" aria-describedby="hint-key" />
<span id="hint-key">从  LLM 控制台获取</span>

// 加载状态
<button aria-busy={loading} disabled={loading}>
  {loading ? <Spinner aria-label="加载中" /> : '提交'}
</button>

// 实时区域
<div aria-live="polite" aria-atomic="true">
  {statusMessage}
</div>

// 模态对话框
<div role="dialog" aria-modal="true" aria-labelledby="dialog-title">
  <h2 id="dialog-title">确认删除?</h2>
</div>
```

#### Skill 列表

```tsx
// 列表使用 ul/li,不要 div
<ul role="list">
  {skills.map(skill => (
    <li key={skill.id}>
      <button aria-describedby={`skill-${skill.id}-desc`}>
        {skill.name}
      </button>
      <span id={`skill-${skill.id}-desc`}>{skill.description}</span>
    </li>
  ))}
</ul>
```

### 2.3 键盘导航

#### Tab 顺序

```tsx
// ❌ 随机
<button>后</button>
<button>前</button>

// ✅ DOM 顺序即视觉顺序
<button>前</button>
<button>后</button>
```

#### 自定义快捷键

```tsx
// 全局快捷键必须 Ctrl/Cmd
useHotkeys('mod+k', openCommandPalette)
useHotkeys('mod+/', openHelp)
useHotkeys('mod+shift+p', openPlanPanel)

// 单字母快捷键要 Alt 前缀
useHotkeys('alt+n', newConversation)
```

#### 焦点管理

```tsx
function Modal({ onClose }) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(=> {
    // 进入时聚焦关闭按钮
    closeRef.current?.focus()
    // 关闭时返回触发元素
    return => triggerRef.current?.focus()
  }, [])

  return (
    <dialog open>
      <button ref={closeRef} onClick={onClose} aria-label="关闭">×</button>
      {/* 内容 */}
    </dialog>
  )
}
```

#### Skip Links

```tsx
<a href="#main" className="skip-link">
  跳到主内容
</a>
<main id="main" tabIndex={-1}>
  {/* ... */}
</main>
```

### 2.4 颜色与对比度

#### 最小对比度

| 元素 | 比率 |
|------|------|
| 正文 | 4.5:1 |
| 大文本 (≥18px / ≥14px bold) | 3:1 |
| UI 组件 / 图形 | 3:1 |

#### 不依赖颜色

```tsx
// ❌ 只靠颜色
<span style={{ color: 'red' }}>错误</span>

// ✅ 颜色 + 图标 + 文字
<span style={{ color: 'red' }}>
  <ErrorIcon aria-hidden="true" /> 错误:网络断开
</span>
```

#### 高对比度模式

```css
@media (prefers-contrast: more) {
  :root {
    --fg: #000;
    --bg: #fff;
    --border: #000;
  }
}
```

### 2.5 动效

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

```tsx
// 用 CSS 变量而非动画属性硬编码
const duration = useReducedMotion? '0ms' : '200ms'
```

### 2.6 表单

```tsx
<form>
  {/* 每个输入有 label */}
  <label htmlFor="model-select">选择模型</label>
  <select id="model-select">
    <option value="gpt-4o">GPT-4o</option>
  </select>

  {/* 必填字段有 aria-required */}
  <input
    type="text"
    required
    aria-required="true"
    aria-invalid={!!error}
    aria-errormessage={error ? 'err-msg' : undefined}
  />
  {error && <span id="err-msg" role="alert">{error}</span>}
</form>
```

---

## 三、测试 / Testing

### 3.1 自动化

```bash
# 安装 axe-core
pnpm add -D @axe-core/playwright

# 跑无障碍扫描
pnpm test:a11y
```

```typescript
// tests/a11y.spec.ts
import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test('home page has no a11y violations', async ({ page }) => {
  await page.goto('/')
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(results.violations).toEqual([])
})
```

### 3.2 手动测试

每次发版前:

- [ ] **键盘测试**:拔掉鼠标,只用键盘走完核心流程
- [ ] **VoiceOver** (macOS) / **NVDA** (Windows):开启屏幕阅读器跑核心流程
- [ ] **200% 缩放**:浏览器放大到 200%,所有内容可读
- [ ] **高对比度**:Windows 高对比度模式 + macOS 增加对比度
- [ ] **关闭 JavaScript**:渐进增强测试

### 3.3 颜色对比度审计

```bash
# 提取 CSS 中所有颜色
pnpm a11y:colors

# 用 Pa11y / Lighthouse 审计
pnpm a11y:audit
```

---

## 四、辅助技术兼容性矩阵 / Compatibility Matrix

| 辅助技术 | 平台 | 测试状态 |
| --- | --- | --- |
| VoiceOver | macOS / iOS | ✓ |
| NVDA | Windows | ✓ |
| JAWS | Windows | ✓ |
| Orca | Linux GNOME | ✓ |
| TalkBack | Android | N/A (桌面端) |
| 旁白 | iOS | N/A (桌面端) |
| Windows 高对比度 | Windows | ✓ |
| 系统级缩小动画 | All | ✓ |

---

## 五、文档无障碍 / Docs A11y

`docs/` 下的所有 Markdown 必须:

- 使用标题层级 (`#` `##` `###`)
- 图片有 alt 文本(`![替代文字](url)`)
- 表格有 header row
- 代码块指定语言
- 链接文本有意义(避免"点击这里")

---

## 六、Issue 模板 / Issue Template

`.github/ISSUE_TEMPLATE/a11y.md`:

```markdown
---
name: 可访问性问题
about: 报告可访问性 / 辅助技术问题
---

## 环境
- OS:
- 浏览器 / Tauri 版本:
- 辅助技术:
- 严重程度:

## 复现步骤
1.
2.
3.

## 期望行为

## 实际行为

## WCAG 标准
影响哪条: [ ] Perceivable [ ] Operable [ ] Understandable [ ] Robust

## 截图 / 录屏
```

---

## 七、/ References

- [WCAG 2.1](https://www.w3.org/TR/WCAG21/)
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
- [Inclusive Components](https://inclusive-components.design/)
- [A11y Project Checklist](https://www.a11yproject.com/checklist/)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.