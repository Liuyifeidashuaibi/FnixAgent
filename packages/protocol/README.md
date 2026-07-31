# @fnixagent/protocol

Fnix 跨进程契约（**单源真相**）：

| 文件 | 用途 |
|------|------|
| `openapi/fnix-local-v1.yaml` | Desktop/agentd ↔ fnix-local |
| `schemas/ag-ui-event-map.json` | Work NDJSON ↔ AG-UI |
| `schemas/work-session.json` | Harness session 持久化 |

**Rust fnix-local（FnixAi）与 Python MVP 必须实现同一 OpenAPI。**
