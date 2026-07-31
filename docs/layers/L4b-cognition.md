# L4b — 调度 / 工具 / 记忆 / 可视化（完善）

## 目标

打通 Harness 四核心产品面：调度引擎可观测、工具轨迹统一、记忆可读写回显、认知轨道 UI。

## 实现清单

| 项 | 路径 | 状态 |
|----|------|------|
| 记忆 CRUD + 注入摘要 | `harness/memory.py` | ✅ |
| API `GET/PUT /harness/memory` · `/memory/injection` | `api/routers/harness.py` | ✅ |
| Work mission 附带 `memory_injection` | `work_pipeline.py` | ✅ |
| `ToolCallTrace` + stream 解析 | `workTypes.ts` / `workStreamHandlers.ts` | ✅ |
| 认知面板 | `CognitionPanel.tsx` | ✅ |
| LivingWorkbench 右侧 aside | `LivingWorkbench.tsx` | ✅ |
| Work 工具卡片 = AgentToolCallCard | `WorkPanel.tsx` / `ToolCallCard.tsx` | ✅ |

## 验收

```bash
PYTHONPATH=src pytest tests/unit/test_harness_memory_crud.py tests/unit/test_harness_memory.py -q
```

UI：打开 Desktop → 顶栏脑图标 → 认知轨道（调度 / 工具 / 记忆）。
