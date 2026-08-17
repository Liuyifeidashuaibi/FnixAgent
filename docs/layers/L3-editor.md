# L3 — 编辑器内核报告

## 1. 目标与边界

Code 模式可控写盘：Monaco Diff · `@file` · Accept/Reject · 多文件队列。

| 做 | 不做 |
|----|------|
| 提及解析注入 prompt | 完整 LSP / 调试器 |
| Diff Accept 错误重试 | 云端协同编辑 |
| Ctrl+L 聚焦 Composer | Electron 专用路径 |

## 2. 实现清单

| 项 | 路径 | 状态 |
|----|------|------|
| `@file` 解析 + 读盘注入 | `apps/desktop/src/renderer/fileMentions.ts` | ✅ |
| Composer 接入 listWorkspaceFiles（修缺失 import） | `ComposerPanel.tsx` | ✅ |
| Ask/Agent 发送前 expand mentions | `ComposerPanel.tsx` | ✅ |
| Diff 写盘失败 Alert + 重试；busy 态 | `DiffView.tsx` / Composer | ✅ |
| 多文件待审队列切换 | `ComposerPanel.tsx` Modal | ✅ |
| FNIX_FOCUS_COMPOSER 聚焦 textarea | `ComposerPanel.tsx` | ✅ |
| 自动化 | `scripts/test-file-mentions.mjs` | ✅ |

## 3. 验收命令与证据

```bash
node scripts/test-file-mentions.mjs
# → [ok] fileMentions L3 checks passed
```

手测：Code → `@path` 选文件 → Agent 出 Diff → Accept 写盘 / Reject 不写；多文件可切换队列。

## 4. 下一层入口

→ **L4 AI Harness**：WorkPanel AG-UI SSE、SOUL/memories/skills 注入、CLI/MCP 对齐。
