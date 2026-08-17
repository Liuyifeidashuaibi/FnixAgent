# Fnix 参考代码索引

> 只读借鉴，**禁止** import 进 `src/fnixagent`。克隆：`pnpm refs:clone` · 验证：`pnpm refs:verify`

**克隆状态**：Tier A **8/8** + Tier B Office/工具链（见 `_references/CLONE.md`）+ **Hermes Agent**（见 `_references/HERMES.md`）。

## Hermes Agent（产品对标 · 2026-07）

| 组件 | 参考路径 |
|------|----------|
| 主仓 + CLI | `_references/hermes-agent/hermes_cli/` |
| Web Dashboard | `_references/hermes-agent/web/` + `hermes_cli/web_server.py` |
| Desktop (Electron) | `_references/hermes-agent/apps/desktop/` |
| 安装脚本 | `_references/hermes-agent/scripts/install.ps1` |
| 文档站 | `_references/hermes-agent/website/` |

对照文档：`docs/HERMES_ALIGNMENT.md` · `_references/HERMES.md`

## ChatGPT / Codex Desktop（UI 对标 · 2026-07）

> 官方 Desktop App **不开源**；开源的是 Codex App Server + 社区桌面壳。清单见 `docs/references/chatgpt-desktop-oss.md`。

| 组件 | 本地路径 | License |
|------|----------|---------|
| Codex App Server（协议/文档） | `_references/chatgpt-desktop-oss/openai-codex/codex-rs/app-server/` | Apache-2.0 |
| Sense-1 Workspace（Electron + React19 + TW4） | `_references/chatgpt-desktop-oss/sense-1-workspace/` | Apache-2.0 |
| Codexia（Tauri v2 GUI） | `_references/chatgpt-desktop-oss/codexia/` | AGPL-3.0 |

## 姊妹仓（不克隆到此目录）

| 路径 | 用途 |
|------|------|
| `E:\FNIX\FnixAi\fnix-se\apps\server\src\main.rs` | Rust sidecar HTTP `/api/index` |
| `E:\FNIX\FnixAi\fnix-se\crates\fnix-pdg` | PDG 图 |
| `E:\FNIX\FnixAi\fnix-se\crates\fnix-sandbox` | 沙箱/PTY |

---

## 问题 → 参考文件

### Harness / 产品

| 问题 | Fnix 文件 | 参考 |
|------|-----------|------|
| workspace 布局 | `harness/workspace.py` | `openharness/` README → ohmo / `~/.ohmo` |
| gateway | `harness/gateway.py` | `openharness/` 包结构 |
| skills | `harness/skills_loader.py` | OpenHarness skill workflows |
| session | `harness/session.py` | ohmo session / compaction |

### Sidecar / 索引

| 问题 | Fnix 文件 | 参考 |
|------|-----------|------|
| HTTP index API | `local/sidecar_app.py` | FnixAi `apps/server` + OpenAPI |
| RepoMap | `core/code/indexer.py` | `aider/aider/repomap.py` |
| MCP 配置 | `harness/config.py` | `goose/documentation/docs/getting-started/using-extensions.md` |

### Agent UI

| 问题 | Fnix 文件 | 参考 |
|------|-----------|------|
| 流式事件 | `workStreamHandlers.ts` | `ag-ui/sdks/typescript` |
| NDJSON→AG-UI | `packages/ag-ui-mapper` + `AgUiRunBar.tsx` | ag-ui 事件 schema |
| Tool 卡片 UI | `ToolCallCard.tsx` | `copilotkit/skills/react-core/references/rendering-tool-calls.md` |

### Workspace 执行

| 问题 | Fnix 文件 | 参考 |
|------|-----------|------|
| 本地命令/文件 | `core/tools/workspace.py` | `openhands-sdk/openhands/sdk/workspace/local.py` |
| MCP servers | `core/mcp/` | `mcp-servers/src/` |
| Grok 工具 loop | `fnix-adapt/grep.rs` | `grok-build/crates/` |
| 文档→MD | `fnix-adapt/markitdown.rs` | `markitdown/packages/markitdown` |

---

## License

| 仓 | License | 用法 |
|----|---------|------|
| OpenHarness | MIT | 借鉴架构 |
| goose | Apache-2.0 | MCP/Desktop 模式 |
| ag-ui | MIT | 事件 schema |
| CopilotKit | MIT | Tool 卡片 UX 参考 |
| aider | Apache-2.0 | repomap 算法 |
| grok-build | Apache-2.0 | Agent loop / tools |
