# Fnix v1.0 Mega Plan（本地 Harness Agent）

> **主计划**：[`HARNESS_PLAN_v1.0.md`](./HARNESS_PLAN_v1.0.md) · **完成度对照**：[`PLAN_STATUS.md`](./PLAN_STATUS.md) · 桌面副本：`pnpm sync:plan-desktop` · 自动验收：`pnpm check:plan`

## 已完成

| 模块 | 状态 |
|------|------|
| Harness 门面 | `~/.fnix`、session、skills、gateway |
| fnix-local Python MVP | `:8710` + OpenAPI 契约 |
| 三进程 dev:all | → Tauri（`dev-all-tauri.mjs`） |
| Work/Code session | server 持久化 + `mode=work\|code` |
| MCP 配置 | `~/.fnix/mcp.json` + API + Settings |
| 协议包 / AG-UI | `packages/protocol` `packages/ag-ui-mapper` |
| Tauri 2 Desktop | 共享 renderer + platform 桥 |
| Rust spawn + Keychain + PTY | `runtime.rs` `secure.rs` `pty.rs` |
| 打包 Python 资源 | `bundle-python-runtime.mjs` |
| PDG 索引 | 打开文件夹 → `POST /harness/index` |
| E2E standalone / verify:beta | `e2e:standalone` `verify:beta` |
| GitHub Release 工作流 | `release.yml` + `BETA_RELEASE.md` |
| Electron 过渡 | `DEPRECATED.md` + `dev:all:electron` |

## 未完成（非代码阻塞）

| 项 | 说明 |
|----|------|
| Rust fnix-local 二进制 | 等 FnixAi Release；Python sidecar 已可用 |
| GitHub Release 产物 | 打 tag `v1.0.0-beta.1` 触发 CI |
| Demo GIF | 需录屏 |
| UI 人工点验 | Work/Code 真实 LLM 任务、PTY Tab、Keychain |
| Electron 代码删除 | 下个小版本 |
| Playwright UI E2E | 可选；API E2E 已覆盖 |

## 架构（冻结）

```
Desktop (Tauri 2) → agentd:8000 → fnix-local:8710
                 ↘ ~/.fnix + {ws}/.fnix
```

## 验收

```bash
pnpm check:plan     # Mega Plan 自动项
pnpm verify:beta    # 完整 Beta
pnpm dev:all        # Tauri 三进程
```

```text
☑ pnpm verify:beta / check:plan（自动）
☑ pytest harness + integration
☑ e2e:standalone sidecar runtime=python
☑ session 重启持久化（集成测试）
□ UI：Work + Code 各完成一次任务（需 BYOK）
□ UI：Tauri PTY Tab
□ git tag v1.0.0-beta.1 → Release
```

## 参考

- [`PLAN_STATUS.md`](./PLAN_STATUS.md)
- [`DESKTOP_TAURI.md`](./DESKTOP_TAURI.md)
- [`BETA_RELEASE.md`](./BETA_RELEASE.md)
- [`ARCHITECTURE_LOCAL_HARNESS.md`](./ARCHITECTURE_LOCAL_HARNESS.md)
