# L2 — 底层引擎报告

## 1. 目标与边界

使 KTG/STP/MFP、fnix-local/PDG、LLM BYOK **可观测、可测、可降级**。

| 边界 | 说明 |
|------|------|
| 做 | 健康快照、sidecar 离线降级字段、BYOK 链回归测 |
| 不做 | 重写整个 LangGraph；改企业 cloud JWT |

### 引擎调用链

```text
Desktop/CLI llm override
    → llm_policy.resolve_llm_for_request (FNIX_API_ONLY)
    → Work/Code pipeline / chat
    → LLMAdapter._auto_detect (~/.fnix secrets + config)
    →  LLM-compatible provider

Work/Code context
    → local_bridge / local_context
    → fnix-local :8710 (PDG)  ──offline──▶ python-workspace-tools
    → KTG/STP/MFP (graph_components)
```

## 2. 实现清单

| 项 | 路径 | 状态 |
|----|------|------|
| 引擎健康快照 | `src/fnixagent/services/engine_status.py` | ✅ |
| `/work/status` 合并降级字段 | `api/routers/work.py` | ✅ |
| harness status degraded | `harness/gateway.py` | ✅ |
| 单元测：engine + offline | `tests/unit/test_engine_status.py` | ✅ |
| 单元测：BYOK harness 链 | `tests/unit/test_byok_harness_chain.py` | ✅ |

## 3. 验收命令与证据

```bash
PYTHONPATH=src pytest tests/unit/test_engine_status.py \
  tests/unit/test_byok_harness_chain.py \
  tests/unit/test_llm_policy_api_only.py -q
# → 9 passed (2026-07-18)
```

可选（需服务已起）：

```bash
curl -s http://127.0.0.1:8000/api/v1/work/status
curl -s http://127.0.0.1:8000/api/v1/harness/status
```

期望字段：`api_only`、`degraded`、`degradation.fallback`、`sidecar`。

## 4. 下一层入口

→ **L3 编辑器内核**：`@file`、多文件 Diff 队列、Accept 错误提示、Studio 焦点环。
