# Fnix v1.0 Mega Plan — 完成度对照表

> 更新时间：2026-07-18  
> **主计划文档**：[`HARNESS_PLAN_v1.0.md`](./HARNESS_PLAN_v1.0.md) · 桌面副本：`pnpm sync:plan-desktop`  
> 自动验收：`pnpm check:plan`

## 终态目标

```
clone → BYOK → pnpm dev:all → Work | Code 双模式 → 重启任务仍在 → GitHub 可交付
```

---

## ✅ 已完成（代码 + 自动测试）

| # | 计划项 | 证据 |
|---|--------|------|
| 1 | Harness 门面 `~/.fnix` / session / skills | `src/fnixagent/harness/` |
| 2 | fnix-local Python MVP `:8710` | `src/fnixagent/local/` + OpenAPI |
| 3 | 三进程 dev:all | `scripts/dev-all.mjs` → Tauri |
| 4 | Work/Code session 持久化 | `harness/session.py` + `GET /work/sessions` |
| 5 | MCP 配置 API | `harness.py` + Settings Harness 页 |
| 6 | 协议包 + AG-UI 映射 | `packages/protocol` `packages/ag-ui-mapper` |
| 7 | Tauri 2 Desktop 壳 | `apps/desktop-tauri` 共享 renderer |
| 8 | Rust spawn agentd + sidecar | `runtime.rs` lifecycle |
| 9 | OS Keychain JWT | `secure.rs` + platform 桥 |
| 10 | PTY 本地终端 | `pty.rs` + `LocalPtyTerminal.tsx` |
| 11 | Python bundle 打包资源 | `bundle-python-runtime.mjs` |
| 12 | Workspace PDG 索引 | `harnessApi.indexHarnessWorkspace` 打开文件夹触发 |
| 13 | Code 会话侧栏 | `LivingWorkbench` + `ComposerPanel sessionId` |
| 14 | E2E API + Standalone 自启动 | `e2e:api` `e2e:standalone` |
| 15 | Beta 验收脚本 | `verify:beta` |
| 16 | GitHub Release 工作流 | `.github/workflows/release.yml` |
| 17 | 集成测试 session 持久化 | `tests/integration/test_standalone_harness.py` |
| 18 | Electron 退役标记 | `apps/desktop/DEPRECATED.md` |
| 19 | dev:all 默认 Tauri | `dev-all.mjs` 转发 |
| 20 | dev:all:electron 过渡脚本 | `scripts/dev-all-electron.mjs` |
| 21 | AG-UI + AgUiRunBar + mapper | `AgUiRunBar.tsx` `workStreamHandlers.ts` |
| 22 | Code Diff Accept + apply API | `ComposerPanel` + `/chat/agent/apply` |
| 23 | 首次引导向导 | `FirstRunWizard.tsx` |
| 24 | ToolCallCard（CopilotKit 风格） | `ToolCallCard.tsx` |
| 25 | 参考仓克隆 8+7 + 重试 | `clone-references.mjs` `refs:verify` |
| 26 | 完整 E2E harness 流 | `e2e:full.mjs` |
| 27 | Fnix 品牌登录页 | `LoginPage.tsx` |
| 28 | `@fnixagent/agent-ui` 成熟 UI 层 | `packages/agent-ui` + ComposerPanel 重构 |
| 29 | Rust fnix-local 参考实现 | `apps/fnix-local` + `build-fnix-local.mjs` |
| 30 | OpenAPI 契约测试 | `tests/contract/test_fnix_local_openapi.py` |
| 31 | Playwright UI E2E | `playwright.config.ts` + `e2e/ui/login.spec.ts` |
| 32 | FirstRunWizard openFolder 修复 | `FirstRunWizard.tsx` |
| 33 | local_bridge read_file | `local_bridge.py` |

---

## ○ 需人工点验（有 BYOK / UI）

| # | 计划项 | 怎么验 |
|---|--------|--------|
| A | Work 模式完成一次任务 | `pnpm dev:all` → 登录 → 打开文件夹 → Work 输入任务 |
| B | Code 模式完成一次会话 | Code Tab → Composer → 看 Diff Accept |
| C | 重启后任务列表仍在 | 关 Desktop → 重开 → 侧边栏 / `GET /work/sessions` |
| D | Tauri PTY Tab | 终端 →「本地 Shell」输入命令 |
| E | Keychain 存 Token | Tauri 登录 → 不应只在 localStorage |

---

## ⏳ 外部依赖 / 未阻塞开发

| # | 计划项 | 状态 |
|---|--------|------|
| 1 | Rust fnix-local 二进制 | 本仓 `apps/fnix-local` ✅；FnixAi 高性能版待迁移 |
| 2 | GitHub Release 安装包 | 工作流就绪；需 `git tag v1.0.0-beta.1 && git push` |
| 3 | Demo GIF | 未录 |
| 4 | Windows 本地 `tauri build` | 需 MSVC；CI 用 msvc 目标 |
| 5 | Electron 代码删除 | 标记 DEPRECATED；renderer 仍共享 |
| 6 | Playwright 浏览器 UI E2E | ✅ 登录页 smoke；可扩展 Work/Code 场景 |

---

## 验收命令

```bash
pnpm check:plan          # Mega Plan 自动项
pnpm verify:beta         # pytest + typecheck + cargo + e2e:standalone
pnpm dev:all             # Tauri 三进程
pnpm dev:all:electron    # Electron 过渡
pnpm e2e:ui             # Playwright 浏览器 UI
```

---

## 架构（冻结）

```
Desktop (Tauri 2) → agentd:8000 → fnix-local:8710
                 ↘ ~/.fnix + {workspace}/.fnix
```
