# FnixAgent Workbench 前端 UX 代码审查报告

> 审查范围：`apps/workbench/src/`
> 审查时间：2026-08-21
> 审查重点：4 个已确认 Bug 根因定位 + UX 优化 + 性能优化

---

## 一、已确认 Bug

### BUG-001：Work 模式下拉菜单（Ask/Plan/Craft）选项无法通过 Playwright click 选中

| 项目         | 内容                                                                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **影响文件** | `ui/glass/tokens.css:342`、`ui/glass/GlassComposer.tsx:131-132`、`shell/desktop/WorkModePicker.tsx:76-114`、`shell/desktop/tokens.css:1553-1601` |
| **严重级别** | High — 自动化测试无法覆盖模式切换                                                                                                                |

#### 问题描述

WorkModePicker 的下拉菜单 `.wb-mode-menu` 渲染在 Composer 底栏 `.glass-comp-r` 内部。该容器设置了 `overflow: hidden`，导致向上弹出的绝对定位菜单被裁剪。Playwright 的 `click()` 在执行前会做 actionability check（可见性、是否被覆盖），裁剪后的 option button 无法通过检查，因此 `click()` 超时失败。而 `element.click()`（JS click）绕过可见性检查直接派发 DOM click 事件，可以成功。

#### 根因分析

DOM 层级关系：

```
GlassComposer (.glass-composer)
  └── .glass-comp-bar (flex row)
       └── .glass-comp-r (overflow: hidden)     ← 裁剪源
            └── modelSlot (= modelAndModeSlot)
                 └── WorkModePicker
                      └── .wb-mode-dd (position: relative)   ← 菜单的包含块
                           ├── .wb-mode-pill (trigger button)
                           └── .wb-mode-menu (position: absolute; bottom: calc(100% + 8px))  ← 被裁剪
```

关键 CSS 链：

1. **`ui/glass/tokens.css:340-343`** — `.glass-comp-r` 设置了 `overflow: hidden`：

   ```css
   .fnix-glass .glass-comp-r {
     justify-content: flex-end;
     overflow: hidden; /* ← 裁剪向上溢出的菜单 */
   }
   ```

2. **`shell/desktop/tokens.css:1553-1554`** — `.wb-mode-dd` 设置了 `position: relative`，成为菜单的包含块：

   ```css
   .wb-mode-dd {
     position: relative;
   }
   ```

3. **`shell/desktop/tokens.css:1590-1594`** — 菜单使用 `position: absolute; bottom: calc(100% + 8px)`，向上弹出超过 `.glass-comp-r` 的内容区域：

   ```css
   .wb-mode-menu {
     position: absolute;
     bottom: calc(100% + 8px);
     z-index: 40;
     ...
   }
   ```

4. **`ui/glass/GlassComposer.tsx:131-132`** — `modelSlot`（包含 WorkModePicker）被渲染在 `.glass-comp-r` 内部：
   ```tsx
   <div className="glass-comp-r">
     {modelSlot}          {/* ← WorkModePicker 在这里 */}
     {streaming ? (...) : (...)}
   </div>
   ```

根据 CSS 规范，`overflow: hidden` 会裁剪其包含块后代中的绝对定位元素。`.wb-mode-dd`（包含块）是 `.glass-comp-r`（裁剪容器）的后代，因此 `.wb-mode-menu` 被裁剪。

#### 修复建议

**方案 A（推荐，最小改动）**：将 `.glass-comp-r` 的 `overflow: hidden` 改为 `overflow: visible`，同时为 `.glass-comp-bar` 添加 `overflow: hidden` 以保持横向裁剪能力。

```diff
--- a/apps/workbench/src/ui/glass/tokens.css
+++ b/apps/workbench/src/ui/glass/tokens.css
@@ -339,8 +339,8 @@
   flex-shrink: 1;
   min-width: 0;
 }
-.fnix-glass .glass-comp-r {
+.fnix-glass .glass-comp-bar {
   justify-content: flex-end;
   overflow: hidden;
 }
+.fnix-glass .glass-comp-r {
+  justify-content: flex-end;
+}
```

**方案 B（更健壮，使用 React Portal）**：将菜单渲染到 `document.body`，通过计算 trigger 位置定位。

```diff
--- a/apps/workbench/src/shell/desktop/WorkModePicker.tsx
+++ b/apps/workbench/src/shell/desktop/WorkModePicker.tsx
@@ -1,5 +1,5 @@
-import { useEffect, useRef, useState } from "react";
+import { useEffect, useRef, useState, useLayoutEffect } from "react";
 import { ChevronDown } from "lucide-react";
+import { createPortal } from "react-dom";
 import type { WorkExecMode } from "./fnixRuntime";

@@ -40,6 +42,8 @@
 }: Props) {
   const [open, setOpen] = useState(false);
   const ref = useRef<HTMLDivElement>(null);
+  const [menuPos, setMenuPos] = useState<{ left: number; bottom: number } | null>(null);
   const current = MODES.find((m) => m.id === value) || MODES[2]!;

+  useLayoutEffect(() => {
+    if (!open || !ref.current) return;
+    const rect = ref.current.getBoundingClientRect();
+    setMenuPos({ left: rect.left, bottom: window.innerHeight - rect.top + 8 });
+  }, [open]);
+
   useEffect(() => {
     if (!open) return;
     const close = (e: MouseEvent) => {
       if (!ref.current?.contains(e.target as Node)) setOpen(false);
     };
     window.addEventListener("mousedown", close);
     return () => window.removeEventListener("mousedown", close);
   }, [open]);

@@ -90,7 +100,7 @@
       {open ? (
-        <div className="wb-mode-menu" role="listbox" aria-label="Ask Plan Craft">
+        createPortal(
+          <div
+            className="wb-mode-menu"
+            role="listbox"
+            aria-label="Ask Plan Craft"
+            style={menuPos ? { left: menuPos.left, bottom: menuPos.bottom } : undefined}
+          >
             {MODES.map((m) => (
               <button
                 key={m.id}
                 type="button"
                 role="option"
                 aria-selected={value === m.id}
                 className={value === m.id ? "on" : undefined}
                 onClick={() => {
                   onChange(m.id);
                   setOpen(false);
                 }}
               >
                 <span className="wb-mode-menu-t">
                   <span className={`wb-mode-dot ${m.id}`} />
                   {m.label}
                 </span>
                 <span className="wb-mode-menu-d">{m.desc}</span>
               </button>
             ))}
-        </div>
+          </div>,
+          document.body,
+        )
       ) : null}
```

> 方案 A 简单直接，适合快速修复。方案 B 更健壮，能彻底避免任何祖先 `overflow` 裁剪问题，适合长期维护。

---

### BUG-002：Step 计数器重复显示 "Step 1/25·Step 1/25"

| 项目         | 内容                                                                           |
| ------------ | ------------------------------------------------------------------------------ |
| **影响文件** | `utils/structuredBlocks.ts:194-211`、`components/chat/ProgressStrip.tsx:48-61` |
| **严重级别** | Medium — 视觉冗余但不影响功能                                                  |

#### 问题描述

ProgressStrip 渲染格式为 `Step {currentStep}/{totalSteps}·{description}`。当 `description` 字段的值恰好是 "Step 1/25" 时，最终显示为 "Step 1/25·Step 1/25"。

#### 根因分析

渲染链路：

1. **`components/chat/ProgressStrip.tsx:48-61`** — 分别渲染 step label 和 description：

   ```tsx
   const stepLabel = totalSteps
     ? `Step ${currentStep}/${totalSteps}`    // ← "Step 1/25"
     : `Step ${currentStep}`;

   <span className="cl-progress-step">{stepLabel}</span>
   <span className="cl-progress-sep">·</span>
   <span className="cl-progress-desc">{description}</span>    // ← 如果 description 也是 "Step 1/25"
   ```

2. **`utils/structuredBlocks.ts:194-211`** — `step_start` 事件的 `description` 直接从后端透传：
   ```typescript
   case "step_start": {
     const stepRaw = ...;
     const desc = String(stepRaw.description || stepRaw.name || "Step…");
     //                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
     // 如果后端发送 description: "Step 1/25"，desc 就是 "Step 1/25"
     const stepNum = Number(stepRaw.step || stepRaw.index || 0);
     const total = Number(stepRaw.total || stepRaw.totalSteps || 0);
     return {
       kind: "progress",
       currentStep: stepNum > 0 ? stepNum : 1,
       totalSteps: total > 0 ? total : undefined,
       description: desc,    // ← "Step 1/25" 传入 description
       isComplete: false,
     };
   }
   ```

后端 `step_start` 事件的 `description` 或 `name` 字段包含了 "Step 1/25" 文本（步骤编号的文字形式），前端将此值原样渲染为 description，与已计算的 `stepLabel` 重复。

#### 修复建议

在 `ndjsonEventToBlock` 中剥离 description 里与 stepLabel 重复的 "Step N/M" 前缀：

```diff
--- a/apps/workbench/src/utils/structuredBlocks.ts
+++ b/apps/workbench/src/utils/structuredBlocks.ts
@@ -198,7 +198,16 @@
       const stepRaw = (typeof obj.step === "object" && obj.step)
         ? obj.step as Record<string, unknown>
         : (data !== obj && typeof data === "object" && data)
           ? data as Record<string, unknown>
           : {};
-      const desc = String(stepRaw.description || stepRaw.name || "Step…");
+      let desc = String(stepRaw.description || stepRaw.name || "Step…");
+      const stepNum = Number(stepRaw.step || stepRaw.index || 0);
+      const total = Number(stepRaw.total || stepRaw.totalSteps || 0);
+      // 剥离后端 description 中与 stepLabel 重复的 "Step N/M" 前缀
+      if (total > 0 && stepNum > 0) {
+        const prefixes = [`Step ${stepNum}/${total}`, `Step ${stepNum} of ${total}`, `Step ${stepNum}`];
+        for (const p of prefixes) {
+          if (desc.startsWith(p)) {
+            desc = desc.slice(p.length).replace(/^[\s:：·-]+/, "").trim();
+            break;
+          }
+        }
+      }
+      if (!desc) desc = "进行中";
       return {
         kind: "progress",
         currentStep: stepNum > 0 ? stepNum : 1,
         totalSteps: total > 0 ? total : undefined,
         description: desc,
         isComplete: false,
       };
```

> 同时建议在 `step_end` 分支（`structuredBlocks.ts:213-229`）应用相同的剥离逻辑。

---

### BUG-003：执行过程中所有操作时间显示 "0s"

| 项目         | 内容                                                                                                                       |
| ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| **影响文件** | `shell/desktop/ProcessTimeline.tsx:90`、`shell/desktop/ProcessTimeline.tsx:65-70`、`shell/desktop/ProcessTimeline.tsx:194` |
| **严重级别** | High — 用户无法感知操作耗时                                                                                                |

#### 问题描述

ProcessTimeline 中每个操作项的时间显示恒为 "0s"。无论操作是否完成，时间都显示 0 秒。

#### 根因分析

1. **`shell/desktop/ProcessTimeline.tsx:90`** — `now` 状态初始值为 `0` 而非 `Date.now()`：

   ```typescript
   const [now, setNow] = useState(0);
   //                     ^^^^^^^^ 应为 Date.now()
   ```

2. **`shell/desktop/ProcessTimeline.tsx:98-102`** — 定时器仅在 `streaming === true` 时启动，且首次 tick 在 1 秒后：

   ```typescript
   useEffect(() => {
     if (!streaming) return;
     const timer = window.setInterval(() => setNow(Date.now()), 1000);
     return () => window.clearInterval(timer);
   }, [streaming]);
   ```

3. **`shell/desktop/ProcessTimeline.tsx:65-66`** — `formatElapsed` 对负值取 `Math.max(0, ...)` 归零：

   ```typescript
   function formatElapsed(startedAt: number, endedAt: number): string {
     const seconds = Math.max(0, Math.floor((endedAt - startedAt) / 1000));
     //                          ^^^^^^^^^^ 当 endedAt=0, startedAt=1.7e12 时，结果为负，归零
   ```

4. **`shell/desktop/ProcessTimeline.tsx:194`** — 运行中项使用 `now` 作为结束时间：
   ```tsx
   <time>{formatElapsed(item.startedAt, item.endedAt || now)}</time>
   //                                       ^^^^^^^^^^^^^^^^
   // item.endedAt 为 undefined 时回退到 now=0
   ```

**完整数据流**：`startedAt` = `1724234845000`（真实时间戳），`endedAt` = `undefined`（运行中），`now` = `0`（初始值）→ `formatElapsed(1724234845000, 0)` → `Math.max(0, (0 - 1724234845000) / 1000)` → `Math.max(0, -1724234845)` → `0` → `"0s"`

定时器启动后需等待 1 秒才更新 `now`，期间所有运行中项显示 "0s"。如果 `streaming` prop 延迟传入或组件频繁重挂载，"0s" 会持续更久。

#### 修复建议

```diff
--- a/apps/workbench/src/shell/desktop/ProcessTimeline.tsx
+++ b/apps/workbench/src/shell/desktop/ProcessTimeline.tsx
@@ -87,7 +87,7 @@
   const [open, setOpen] = useState(true);
   const [filter, setFilter] = useState<Filter>("all");
   const [expanded, setExpanded] = useState<Record<string, boolean>>({});
-  const [now, setNow] = useState(0);
+  const [now, setNow] = useState(() => Date.now());
   const bodyRef = useRef<HTMLDivElement>(null);
```

> 使用 `useState(() => Date.now())` 惰性初始化，避免每次渲染都调用 `Date.now()`。同时建议将定时器间隔从 1000ms 缩短到 500ms 以提升时间显示的流畅度。

---

### BUG-004：任务完成后 step 计数器仍显示 "Step 1/25" 而非最终步数

| 项目         | 内容                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| **影响文件** | `shell/desktop/useChatFlow.ts:254-271`、`shell/desktop/fnixRuntime.ts:1069-1076` |
| **严重级别** | Medium — 完成态信息不准确                                                        |

#### 问题描述

任务执行完成后，进度条仍显示 "Step 1/25" 而非 "Step 25/25" 或实际完成的步数。

#### 根因分析

1. **`shell/desktop/fnixRuntime.ts:1069-1076`** — `done` 事件仅调用 `onDone` 回调，不 emit progress block：

   ```typescript
   if (t === 'done') {
     sawDone = true;
     if (obj.error) {
       opts.handlers.onError?.(String(obj.error));
     }
     opts.handlers.onDone?.(obj);
     return; // ← 不调用 emitStructuredBlock，不更新进度
   }
   ```

2. **`shell/desktop/useChatFlow.ts:254-271`** — `finalize()` 仅标记 `isComplete: true`，不更新 `currentStep`：
   ```typescript
   const finalize = () => {
     cancelRaf();
     flushStreamBuf();
     const aid = streamAssistantIdRef.current;
     if (aid) {
       commitMessages(
         messagesRef.current.map((m) => {
           if (m.id !== aid || !m.blocks || m.blocks.length === 0) return m;
           const finalizedBlocks = m.blocks.map((b) =>
             b.kind === 'thinking' || b.kind === 'progress'
               ? {
                   ...b,
                   isStreaming: false,
                   isComplete: b.kind === 'progress' ? true : b.isComplete,
                 }
               : //                                                       ^^^^^^^^^^^^^^^^
                 // 只设置 isComplete，未更新 currentStep
                 b,
           );
           return { ...m, blocks: finalizedBlocks };
         }),
       );
     }
   };
   ```

如果后端只 emit 了一个 `step_start`（step=1, total=25），之后直接发送 `done` 事件，最后一个 progress block 的 `currentStep` 停留在 1，`finalize()` 不修正它。

#### 修复建议

在 `finalize()` 中，将 progress block 的 `currentStep` 更新为 `totalSteps`（如果存在）：

```diff
--- a/apps/workbench/src/shell/desktop/useChatFlow.ts
+++ b/apps/workbench/src/shell/desktop/useChatFlow.ts
@@ -259,12 +259,17 @@
         messagesRef.current.map((m) => {
           if (m.id !== aid || !m.blocks || m.blocks.length === 0) return m;
           const finalizedBlocks = m.blocks.map((b) => {
-            if (b.kind === "thinking" || b.kind === "progress") {
-              return {
-                ...b,
-                isStreaming: false,
-                isComplete: b.kind === "progress" ? true : b.isComplete,
-              };
+            if (b.kind === "thinking") {
+              return { ...b, isStreaming: false, isComplete: b.isComplete };
+            }
+            if (b.kind === "progress") {
+              return {
+                ...b,
+                isStreaming: false,
+                isComplete: true,
+                // 完成时将 currentStep 推进到 totalSteps，避免显示 "Step 1/25"
+                currentStep: b.totalSteps ?? b.currentStep,
+              };
             }
             return b;
           });
           return { ...m, blocks: finalizedBlocks };
         }),
       );
```

> 如果后端在 `done` 事件中携带了实际完成的步数，建议在 `fnixRuntime.ts:1069-1076` 的 `done` 分支中额外 emit 一个 progress block：
>
> ```typescript
> if (t === 'done') {
>   sawDone = true;
>   // 补发最终 progress block
>   emitStructuredBlock(opts.handlers, {
>     type: 'step_end',
>     step: { step: obj.total_steps ?? obj.total, total: obj.total_steps ?? obj.total, description: '完成' },
>   });
>   ...
> }
> ```

---

## 二、UX 优化点

### UX-001：WorkModePicker 下拉菜单无键盘导航

| 项目     | 内容                                      |
| -------- | ----------------------------------------- |
| **文件** | `shell/desktop/WorkModePicker.tsx:76-114` |
| **类别** | 可访问性                                  |

**问题**：下拉菜单打开后，不支持方向键上下移动焦点、Enter 选择、Escape 关闭。仅依赖鼠标点击。

**影响**：键盘用户和屏幕阅读器用户无法使用模式切换功能。

**修复建议**：在 `.wb-mode-menu` 容器上添加 `onKeyDown` 处理：

```tsx
const [activeIndex, setActiveIndex] = useState(0);

// 在菜单容器上：
<div
  className="wb-mode-menu"
  role="listbox"
  aria-label="Ask Plan Craft"
  aria-activedescendant={`mode-opt-${activeIndex}`}
  onKeyDown={(e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, MODES.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      onChange(MODES[activeIndex].id);
      setOpen(false);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }}
>
  {MODES.map((m, i) => (
    <button
      key={m.id}
      id={`mode-opt-${i}`}
      // ...
      className={`${value === m.id ? "on" : ""} ${i === activeIndex ? "active" : ""}`}
    >
```

---

### UX-002：ProcessTimeline `<time>` 元素缺少 `dateTime` 属性

| 项目     | 内容                                    |
| -------- | --------------------------------------- |
| **文件** | `shell/desktop/ProcessTimeline.tsx:194` |
| **类别** | 可访问性                                |

**问题**：`<time>{formatElapsed(item.startedAt, item.endedAt || now)}</time>` 只显示了人类可读的 "3s" 文本，但缺少 `dateTime` 属性，屏幕阅读器和搜索引擎无法解析机器可读的时间。

**修复建议**：

```diff
-<time>{formatElapsed(item.startedAt, item.endedAt || now)}</time>
+<time dateTime={`PT${Math.max(0, Math.floor(((item.endedAt || now) - item.startedAt) / 1000))}S`}>
+  {formatElapsed(item.startedAt, item.endedAt || now)}
+</time>
```

---

### UX-003：错误 block 未提取 `detail` 和 `suggestion` 字段

| 项目     | 内容                                |
| -------- | ----------------------------------- |
| **文件** | `utils/structuredBlocks.ts:270-285` |
| **类别** | 错误提示                            |

**问题**：`ErrorBlock` 接口定义了 `detail`、`suggestion`、`toolName`、`severity`、`retryCount`、`maxRetries` 等字段（`structuredBlocks.ts:91-107`），但 `ndjsonEventToBlock` 的 `error` 分支只提取了 `message` 和 `severity`，忽略了其他字段。用户看到的错误信息只有标题，缺少诊断详情和修复建议。

```typescript
case "error": {
  const msg = typeof data === "string" ? data : String(((data as Record<string, unknown>)?.message ?? data) ?? "");
  // 只提取了 message，未提取 detail / suggestion / toolName / retryCount
  let severity: "transient" | "persistent" | "fatal" = "transient";
  // ...
  return {
    kind: "error",
    title: msg.slice(0, 200),
    severity,
    // 缺少: detail, suggestion, toolName, retryCount, maxRetries
  };
}
```

**修复建议**：

```diff
 case "error": {
-  const msg = typeof data === "string" ? data : String(((data as Record<string, unknown>)?.message ?? data) ?? "");
+  const d = (typeof data === "object" && data) ? data as Record<string, unknown> : {};
+  const msg = typeof data === "string" ? data : String(d.message ?? data ?? "");
   const lower = msg.toLowerCase();
   let severity: "transient" | "persistent" | "fatal" = "transient";
   if (/api key|unauthorized|401|invalid.*key|fatal|cannot continue/i.test(lower)) {
     severity = "fatal";
   } else if (/timeout|eaddrinuse|port.*occupied|already in use|persistent/i.test(lower)) {
     severity = "persistent";
   }
   return {
     kind: "error",
     title: msg.slice(0, 200),
+    detail: d.detail ? String(d.detail) : undefined,
+    suggestion: d.suggestion ? String(d.suggestion) : undefined,
+    toolName: d.tool_name ? String(d.tool_name) : d.tool ? String(d.tool) : undefined,
+    retryCount: typeof d.retry_count === "number" ? d.retry_count : undefined,
+    maxRetries: typeof d.max_retries === "number" ? d.max_retries : undefined,
     severity,
   };
 }
```

---

### UX-004：Composer 发送按钮无 loading/success 反馈

| 项目     | 内容                                 |
| -------- | ------------------------------------ |
| **文件** | `ui/glass/GlassComposer.tsx:143-152` |
| **类别** | 交互反馈                             |

**问题**：发送按钮点击后立即切换到 Stop 按钮，但没有过渡动画或短暂的成功反馈。用户点击发送后，如果后端响应慢，textarea 仍保留用户输入文本直到第一条流式数据到达，用户不确定是否发送成功。

**修复建议**：在 `onSend` 后添加 200ms 的发送中视觉反馈（如按钮闪绿色 + textarea 内容清空时添加淡出动画），或至少在 `streaming` 切换瞬间添加 `transition: all 0.15s ease`。

---

### UX-005：ProcessTimeline 展开行缺少进入动画

| 项目     | 内容                                    |
| -------- | --------------------------------------- |
| **文件** | `shell/desktop/ProcessTimeline.tsx:220` |
| **类别** | 交互反馈                                |

**问题**：点击"查看输出"展开 `item.detail` 时，`<pre>` 直接出现，无高度过渡或淡入动画，视觉跳跃明显。

**修复建议**：使用 CSS `max-height` 过渡或 `React` 的 `CSSTransition` 实现展开动画：

```css
.fnix-agent-event-detail {
  max-height: 0;
  overflow: hidden;
  transition:
    max-height 0.2s ease,
    opacity 0.2s ease;
  opacity: 0;
}
.fnix-agent-event.expanded .fnix-agent-event-detail {
  max-height: 400px;
  opacity: 1;
}
```

---

### UX-006：MessageList "Show earlier messages" 按钮使用英文

| 项目     | 内容                                |
| -------- | ----------------------------------- |
| **文件** | `shell/desktop/MessageList.tsx:127` |
| **类别** | 布局/排版                           |

**问题**：按钮文本 `"Show earlier messages ({hidden} hidden)"` 为英文，与界面其他部分的中文不一致。

**修复建议**：

```diff
-<button type="button" className="fnix-expand-msg" onClick={() => setShowAll(true)}>
-  Show earlier messages ({hidden} hidden)
-</button>
+<button type="button" className="fnix-expand-msg" onClick={() => setShowAll(true)}>
+  展开更早的 {hidden} 条消息
+</button>
```

---

### UX-007：Composer textarea 高度计算在每次 `value` 变化时同步执行

| 项目     | 内容                               |
| -------- | ---------------------------------- |
| **文件** | `ui/glass/GlassComposer.tsx:55-67` |
| **类别** | 性能/交互流畅度                    |

**问题**：`useEffect` 依赖 `[value, compact]`，SSE 流式输出时 `value` 每帧变化，textarea 高度重计算频繁。虽然单次计算成本低，但在长文本场景下 `scrollHeight` 的同步读取可能引起布局抖动（layout thrashing）。

**修复建议**：使用 `ResizeObserver` 或 RAF 节流：

```typescript
const rafRef = useRef<number>(0);
useEffect(() => {
  if (rafRef.current) cancelAnimationFrame(rafRef.current);
  rafRef.current = requestAnimationFrame(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    const max = 200;
    const min = compact ? 44 : 28;
    el.style.height = `${Math.min(max, Math.max(min, el.scrollHeight))}px`;
  });
  return () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
  };
}, [value, compact]);
```

---

## 三、性能优化点

### PERF-001：ProcessTimeline 每次渲染都计算 `Math.min/max(...spread)`

| 项目     | 内容                                        |
| -------- | ------------------------------------------- |
| **文件** | `shell/desktop/ProcessTimeline.tsx:118-119` |
| **类别** | 不必要的 re-render / 计算                   |

**问题**：

```typescript
const start = Math.min(...visibleItems.map((item) => item.startedAt));
const end = Math.max(...visibleItems.map((item) => item.endedAt || now || item.startedAt));
```

每次渲染（包括 `now` 每秒更新时）都遍历整个 `visibleItems` 数组两次。当操作项超过 100 条时，spread 操作可能触发调用栈溢出（`Math.max(...arr)` 在数组 > ~100k 时栈溢出）。

**修复建议**：用 `useMemo` 缓存，并改用 `reduce` 避免 spread：

```typescript
const { start, end } = useMemo(() => {
  if (visibleItems.length === 0) return { start: 0, end: 0 };
  let min = visibleItems[0].startedAt;
  let max = visibleItems[0].endedAt || now || visibleItems[0].startedAt;
  for (let i = 1; i < visibleItems.length; i++) {
    const item = visibleItems[i];
    if (item.startedAt < min) min = item.startedAt;
    const itemEnd = item.endedAt || now || item.startedAt;
    if (itemEnd > max) max = itemEnd;
  }
  return { start: min, end: max };
}, [visibleItems, now]);
```

---

### PERF-002：MessageList 无虚拟化，48 条消息全量渲染

| 项目     | 内容                                                                     |
| -------- | ------------------------------------------------------------------------ |
| **文件** | `shell/desktop/MessageList.tsx:132-154`、`shell/desktop/windowing.ts:12` |
| **类别** | 大列表无虚拟化                                                           |

**问题**：`MESSAGE_WINDOW = 48`，窗口内所有消息通过 `.map()` 全量渲染为 `MessageBubble`。每个 `MessageBubble` 可能包含 Markdown 渲染、代码高亮（highlight.js）、diff block 等重量级组件。当单条消息内容很长（接近 `CONTENT_SOFT_LIMIT = 12000` 字符）时，48 条消息的渲染总成本很高。

当前 `MessageBubble` 已用 `memo` 包裹且有自定义比较函数（`MessageBubble.tsx:594-611`），这有效阻止了非流式消息的重渲染。但首次挂载和窗口切换时仍需全量渲染。

**修复建议**：

1. **短期**：降低 `MESSAGE_WINDOW` 到 24-30，大多数会话不需要同时显示 48 条。
2. **中期**：引入 `react-window` 或 `@tanstack/react-virtual` 对消息列表做虚拟化，只渲染视口内的消息。
3. **已有的好实践**：`softTruncate`（`windowing.ts:27-35`）对长文本做软截断，`MessageBubble` 的 `memo` 比较函数设计完善，这些应该保留。

---

### PERF-003：SSE 流式数据每帧触发 `commitMessages` 全量映射

| 项目     | 内容                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------------------ |
| **文件** | `shell/desktop/useChatFlow.ts:254-271`（`finalize`）、`shell/desktop/useChatFlow.ts:200-273`（`createStreamLocalState`） |
| **类别** | SSE 流式数据处理效率                                                                                                     |

**问题**：`createStreamLocalState` 使用 RAF 缓冲流式数据，这是正确的设计。但 `flushStreamBuf` 和 `appendStructuredBlock` 都调用 `commitMessages`，后者通过 `setMessages(messagesRef.current.map(...))` 对整个消息数组做映射。如果会话有 100+ 条消息，每次 RAF flush（约 16ms）都要遍历整个数组。

**根因**：`messagesRef.current.map((m) => ...)` 每次创建新数组，即使只有最后一条消息在变化。

**修复建议**：只更新变化的消息，避免全量映射：

```typescript
// 替换 commitMessages 的调用方式
const updateLastMessage = (updater: (m: ChatMsg) => ChatMsg) => {
  const msgs = messagesRef.current;
  if (msgs.length === 0) return;
  const last = msgs[msgs.length - 1];
  const updated = updater(last);
  if (updated === last) return; // 无变化
  setMessages([...msgs.slice(0, -1), updated]);
};
```

> 当前实现已使用 RAF 节流，影响可控。但如果在低端设备上出现卡顿，这个优化能显著减少 GC 压力。

---

### PERF-004：`appendBlock` 每次创建新数组（文本/思考合并）

| 项目     | 内容                                |
| -------- | ----------------------------------- |
| **文件** | `utils/structuredBlocks.ts:329-373` |
| **类别** | 状态管理 / GC 压力                  |

**问题**：`appendBlock` 在合并 text/thinking block 时使用 `[...blocks.slice(0, -1), { ...last, ... }]`，每次都创建新数组和新对象。在 SSE 高频流式场景下（每帧可能有多个 text chunk），这会产生大量短生命周期对象，增加 GC 压力。

**当前缓解**：RAF 缓冲合并了同一帧内的多个 chunk，降低了调用频率。

**修复建议**（可选，当前性能可接受时不必修改）：使用 mutable 更新 + 浅比较跳过：

```typescript
// 在 createStreamLocalState 的 RAF 回调中批量合并 text chunks
// 而不是逐个调用 appendBlock
```

---

### PERF-005：`filteredItems.slice(-24)` 每次渲染创建新数组

| 项目     | 内容                                    |
| -------- | --------------------------------------- |
| **文件** | `shell/desktop/ProcessTimeline.tsx:120` |
| **类别** | 不必要的 re-render                      |

**问题**：

```typescript
const rows = filteredItems.slice(-24);
```

每次渲染（包括 `now` 每秒更新时）都创建新数组，虽然成本低，但可以轻松用 `useMemo` 避免。

**修复建议**：

```typescript
const rows = useMemo(() => filteredItems.slice(-24), [filteredItems]);
const hiddenRows = filteredItems.length - rows.length;
```

---

### PERF-006：`MessageBubble` memo 比较函数遗漏 `onCopy` 回调

| 项目     | 内容                                      |
| -------- | ----------------------------------------- |
| **文件** | `shell/desktop/MessageBubble.tsx:594-611` |
| **类别** | 状态管理                                  |

**问题**：memo 比较函数检查了 `onOpenDiff`、`onRegenerate`、`onPin`、`onSendPrompt`，但遗漏了 `onCopy` 回调。如果 `onCopy` 的引用变化（父级 `useCallback` 依赖变化时），`MessageBubble` 不会重渲染，可能导致复制功能使用旧回调。

**修复建议**：

```diff
 export const MessageBubble = memo(MessageBubbleInner, (a, b) => {
   return (
     a.message.id === b.message.id &&
     a.message.content === b.message.content &&
     a.message.blocks === b.message.blocks &&
     a.isLastAssistant === b.isLastAssistant &&
     a.streaming === b.streaming &&
     a.status === b.status &&
     a.copiedId === b.copiedId &&
     a.vote === b.vote &&
     a.fileChanges === b.fileChanges &&
     a.onOpenDiff === b.onOpenDiff &&
     a.onRegenerate === b.onRegenerate &&
     a.onPin === b.onPin &&
-    a.onSendPrompt === b.onSendPrompt
+    a.onSendPrompt === b.onSendPrompt &&
+    a.onCopy === b.onCopy &&
+    a.onVote === b.onVote
   );
 });
```

> 注意：`onCopy` 和 `onVote` 在 `MessageList.tsx:92-118` 中使用 `useCallback` 包裹，引用通常稳定。但 `onVote` 依赖 `[messages]`，当消息列表变化时引用会更新，此时 memo 应感知到变化。

---

## 四、问题汇总

| 编号     | 类型        | 文件                                        | 严重级别 | 状态       |
| -------- | ----------- | ------------------------------------------- | -------- | ---------- |
| BUG-001  | Bug         | `ui/glass/tokens.css:342`                   | High     | 已定位根因 |
| BUG-002  | Bug         | `utils/structuredBlocks.ts:201`             | Medium   | 已定位根因 |
| BUG-003  | Bug         | `shell/desktop/ProcessTimeline.tsx:90`      | High     | 已定位根因 |
| BUG-004  | Bug         | `shell/desktop/useChatFlow.ts:262-264`      | Medium   | 已定位根因 |
| UX-001   | 可访问性    | `shell/desktop/WorkModePicker.tsx`          | Medium   | 建议修复   |
| UX-002   | 可访问性    | `shell/desktop/ProcessTimeline.tsx:194`     | Low      | 建议修复   |
| UX-003   | 错误提示    | `utils/structuredBlocks.ts:270-285`         | Medium   | 建议修复   |
| UX-004   | 交互反馈    | `ui/glass/GlassComposer.tsx:143-152`        | Low      | 建议优化   |
| UX-005   | 交互反馈    | `shell/desktop/ProcessTimeline.tsx:220`     | Low      | 建议优化   |
| UX-006   | 布局/排版   | `shell/desktop/MessageList.tsx:127`         | Low      | 建议修复   |
| UX-007   | 性能/流畅度 | `ui/glass/GlassComposer.tsx:55-67`          | Low      | 建议优化   |
| PERF-001 | 性能        | `shell/desktop/ProcessTimeline.tsx:118-119` | Medium   | 建议修复   |
| PERF-002 | 性能        | `shell/desktop/MessageList.tsx:132`         | Medium   | 建议优化   |
| PERF-003 | 性能        | `shell/desktop/useChatFlow.ts`              | Low      | 建议优化   |
| PERF-004 | 性能        | `utils/structuredBlocks.ts:329-373`         | Low      | 当前可接受 |
| PERF-005 | 性能        | `shell/desktop/ProcessTimeline.tsx:120`     | Low      | 建议修复   |
| PERF-006 | 状态管理    | `shell/desktop/MessageBubble.tsx:594-611`   | Low      | 建议修复   |

---

## 五、已有的良好实践（值得保留）

审查过程中发现以下设计值得肯定：

1. **RAF 流式缓冲**（`useChatFlow.ts:200-273`）：使用 `requestAnimationFrame` 合并同一帧内的多个 SSE chunk，避免高频 `setState`。
2. **MessageBubble memo 比较函数**（`MessageBubble.tsx:594-611`）：自定义浅比较覆盖了大部分关键 prop，有效阻止非流式消息的重渲染。
3. **消息窗口化**（`windowing.ts`）：`MESSAGE_WINDOW = 48` + `softTruncate` 限制首屏渲染量，对长会话有基本保护。
4. **凭据脱敏**（`structuredBlocks.ts:160-165`）：`redactSensitiveText` 在工具参数进入 UI 前过滤 API key、Bearer token 等敏感信息。
5. **ProgressStrip 完成态设计**（`ProgressStrip.tsx:54-58`）：使用 `Check` 图标替代 spinner + 降低不透明度，完成态视觉清晰。
6. **ProcessTimeline 筛选器**（`ProcessTimeline.tsx:160-177`）：提供 all/files/commands/issues 四维筛选，对复杂执行过程有良好的信息分层。
