# L4 — AI Harness 调度层报告

## 1. 目标与边界

Work/Code 会话、工具编排、skills/memory、CLI、AG-UI 同源。

| 做 | 不做 |
|----|------|
| Desktop Work → AG-UI SSE | 第二套 Dashboard 产品 |
| SOUL/memories/skills 注入测 | Hermes 消息网关 |
| 修复 WorkPanel 模板字符串致命 bug | 企业 JWT 主路径 |

## 2. 实现清单

| 项 | 路径 | 状态 |
|----|------|------|
| WorkPanel 改接 `/api/v1/ag-ui/work/stream` | `WorkPanel.tsx` | ✅ |
| SSE→NDJSON 桥 | `agUiStream.ts` | ✅ |
| 修复 `\${}` / `\\n` 写盘/流解析 bug | `WorkPanel.tsx` | ✅ |
| AG-UI 徽章 | `AgUiRunBar.tsx` | ✅ |
| SOUL/memory/skills 单测 | `tests/unit/test_harness_memory.py` | ✅ |
| 流水线已注入 local_context（含 SOUL） | `work_pipeline.py` | ✅（既有） |
| MCP Settings ↔ `~/.fnix/mcp.json` | `SettingsPanel` / harness API | ✅（既有） |

## 3. 验收命令与证据

```bash
PYTHONPATH=src pytest tests/unit/test_harness_memory.py tests/unit/test_ag_ui_mapper.py -q
# → 6 passed

node scripts/test-ag-ui-stream.mjs
# → [ok] ag-ui stream bridge checks passed

# 可选全栈
pnpm smoke:hermes
curl -s http://127.0.0.1:8000/api/v1/ag-ui/health
fnixagent doctor
```

## 4. 下一层入口

→ **L5 上层产品**：引导/工作台打磨、e2e 无登录、§11 场景对齐。
