# Fnix Stack Audit Report

> 自动生成：2026-07-18T09:17:42.946Z
> 命令：`pnpm stack:report`

## 参考仓

| 仓 | Tier | 状态 | 吸收 | Fnix 落点 |
|----|------|------|------|-----------|
| openharness | A | ✓ | Harness 布局/skills/session/gateway | src/fnixagent/harness/ |
| ag-ui | A | ✓ | AG-UI 事件 schema + HttpAgent | packages/ag-ui-mapper + agent-ui |
| copilotkit | A | ✓ | Tool 卡片 / Generative UI | packages/agent-ui |
| goose | A | ✓ | MCP 配置形态 | SettingsPanel Harness |
| openhands-sdk | A | ✓ | 本地 workspace 执行 | core/tools/workspace.py |
| aider | A | ✓ | RepoMap 符号排名 | core/code/indexer.py |
| mcp-servers | A | ✓ | MCP 标准 server | ~/.fnix/mcp.json |
| pi-mono | A | ✓ | 多平台 agent 模式 | 长期参考 |
| grok-build | B | ✓ | Agent loop / tools | core/tools/ |
| markitdown | B | ✓ | 文档→MD | Work 文档工具 |

## FnixAi 姊妹仓

路径: `E:\FNIX\FnixAi\fnix-se` · 存在: 是

| 模块 | P | 状态 | 用途 |
|------|---|------|------|
| fnix-pdg | P0 | ✓ | /v1/index PDG 图 |
| fnix-ast | P0 | ✓ | 符号解析 |
| fnix-vector | P0 | ✓ | /v1/context vector_hits |
| fnix-tools | P0 | ✓ | /v1/run PTY+blocklist |
| fnix-tools-read | P0 | ✓ | /v1/read 安全路径 |
| fnix-sandbox | P1 | ✓ | 沙箱/PTY |
| cli-index | P0 | ✓ | index 管线 |
| agent-hooks | P0 | ✓ | context 排名 |
| fnix-local-app | P0 | ✓ | OpenAPI sidecar 壳 |
| apps-server | P2 | ✓ | ❌ 非 sidecar 契约 |
| fnix-ui | P2 | ✓ | ❌ 保留 FnixAi GPU UI |
| fnix-agent-loop | P2 | ✓ | ❌ Python 大脑已有 |

**apps/fnix-local**: 已存在

## Sidecar

- OpenAPI: ✓
- Python MVP: ✓
- Rust crate: ✓
- Rust binary: ✓
- Contract tests: ✓

## UI 栈

- agent-ui: ✓
- ag-ui-mapper: ✓

## 行动项

1. 保持 `_references/` 只读 — 不 import 进产品
2. FnixAi 新建 `apps/fnix-local` 接入 fnix-pdg/fnix-tools
3. AG-UI 适配器连接 FastAPI NDJSON → 前端
4. OpenHarness session/skills 模式持续吸收

详见 [TOP_TIER_INTEGRATION.md](./TOP_TIER_INTEGRATION.md)
