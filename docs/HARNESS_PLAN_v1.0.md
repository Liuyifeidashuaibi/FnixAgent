# Fnix 本地 Harness 完整改造计划（v1.0）

> **主文档** — 整合原始改造计划、Mega Plan 终局版与后续设计（Tauri 2 / Beta 发布）  
> **桌面副本**：运行 `pnpm sync:plan-desktop` → `~/Desktop/Fnix-Harness-Plan-v1.0/`  
> **执行对照**：[`PLAN_STATUS.md`](./PLAN_STATUS.md) · **自动验收**：`pnpm check:plan`

---

## 0. 产品定义

**Fnix = 本地 Harness 产品壳（Tauri 2）+ Python 自进化大脑（KTG/STP/MFP）+ 本地算力 sidecar（fnix-local）**

| 对标 | Fnix 对应 | 独有 |
|------|-----------|------|
| OpenHarness / ohmo | agentd + `~/.fnix` | KTG/STP/MFP |
| Trae Work | Work 模式 + 本地文件夹 | Office 工具链 |
| Trae Code | Code 模式 + fnix-local | PDG digest |
| CopilotKit | AG-UI 事件映射 | 进化状态可视化 |

**用户故事（v1.0 验收）**：

```text
git clone → cp .env.example .env → 填 API Key
→ pnpm dev:all
→ 登录 → 打开文件夹 → Work | Code
→ KTG/STP/MFP 流式 → 产物落盘
→ 重启后 GET /work/sessions 仍有历史
```

---

## 1. 目标架构（冻结 · 2026-07 更新）

```
Desktop (Tauri 2)  ←→  fnix-agentd (Python :8000)  ←→  fnix-local (:8710)
                              ↘ ~/.fnix
                               ↘ {workspace}/.fnix
```

**铁律**：

1. Desktop 只连 agentd（8000），不直连 LLM  
2. agentd 通过 `harness/local_bridge.py` 连 sidecar（8710）  
3. sidecar HTTP 契约：`packages/protocol/openapi/fnix-local-v1.yaml`  
4. KTG/STP/MFP 永远在 Work 主路径  

---

## 2. 目录约定

### `~/.fnix/`

| 路径 | 用途 |
|------|------|
| `config.toml` | provider / model |
| `sessions/*.json` | Work + Code 任务持久化 |
| `mcp.json` | MCP server 列表 |
| `logs/` | 本地日志 |

### `{workspace}/.fnix/`

| 路径 | 用途 |
|------|------|
| `skills/*.md` | 项目技能 → STP |
| `artifacts/` | Work 产物 |
| `index/` | fnix-local PDG |
| `topology/` | KTG 项目缓存 |
| `rules.md` | 项目规则 |

---

## 3. Phase 执行对照（原计划 → 现状）

### Phase 0：基线冻结 — ✅ 完成

| 任务 | 状态 |
|------|------|
| Standalone profile | ✅ |
| `pnpm dev:all` 三进程 | ✅（Tauri） |
| QUICKSTART | ✅ |
| 后端离线引导 | ✅ `BackendOffline` |

### Phase 1：Harness 门面 — ✅ 完成

| # | 任务 | 状态 | 位置 |
|---|------|------|------|
| 1.1 | Workspace 管理器 | ✅ | `harness/workspace.py` |
| 1.2 | 用户级配置 | ✅ | `harness/config.py` |
| 1.3 | Session 持久化 | ✅ | `harness/session.py` + API |
| 1.4 | Skills 加载器 | ✅ | `harness/skills_loader.py` |
| 1.5 | Gateway | ✅ | `harness/gateway.py` |
| 1.6 | work_pipeline 挂钩 | ✅ | `services/work_pipeline.py` |
| 1.7 | Desktop 任务列表 | ✅ | `LivingWorkbench` + server sessions |
| 1.8 | 架构文档 | ✅ | `ARCHITECTURE_LOCAL_HARNESS.md` |

### Phase 2：fnix-local Sidecar — 🟡 大部分完成

| # | 任务 | 状态 | 说明 |
|---|------|------|------|
| 2.1 | Rust `apps/fnix-local` | ✅ | 本仓参考实现 + 姊妹仓优先 |
| 2.2 | 5 个 RPC / OpenAPI | ✅ | Python MVP + Rust 对齐契约 |
| 2.3 | CI Release 二进制 | 🟡 | `build-fnix-local.mjs` + CI `FNIX_BUILD_LOCAL=1` |
| 2.4 | `local_bridge.py` | ✅ | index + context + read_file |
| 2.5 | 壳层管理 sidecar | ✅ | **Tauri `runtime.rs`**（原 Electron Main） |
| 2.6 | Code PDG 注入 | ✅ | `chat_agent` + `local_context_prompt` |
| 2.7 | sidecar 离线降级 | ✅ | Python fallback |

### Phase 3：AG-UI + Work UI — ✅ 完成

| # | 任务 | 状态 |
|---|------|------|
| 3.1 | `packages/ag-ui-mapper` | ✅ |
| 3.2 | WorkPanel 进化/步骤条 | ✅ `AgUiRunBar` |
| 3.3 | Artifact 卡片 | ✅ |
| 3.4 | CopilotKit 全量 | ⏸ v1.1 可选 |
| 3.5 | `@fnixagent/agent-ui` 成熟 UI 层 | ✅ Mantine + AG-UI npm |

### Phase 4：MCP Harness 化 — ✅ 完成

| # | 任务 | 状态 |
|---|------|------|
| 4.1 | `~/.fnix/mcp.json` | ✅ |
| 4.2 | registry 接 harness | ✅ |
| 4.3 | Settings MCP UI | ✅ Harness 页 |
| 4.4 | Office 优先于 MCP | ✅ STP |

### Phase 5：打包与 GitHub 发布 — 🟡 部分完成

| # | 任务 | 状态 |
|---|------|------|
| 5.1 | Desktop + sidecar 捆绑 | 🟡 Tauri bundle Python；Rust 二进制待 Release |
| 5.2 | 内嵌 Python agentd | ⏸ v1.1（当前要求本机 Python） |
| 5.3 | 首次引导 | ✅ `FirstRunWizard` + openFolder 修复 |
| 5.4 | GitHub Release + GIF | 🟡 `release.yml` ✅；tag + GIF 待做 |
| 5.5 | smoke CI | ✅ `check:plan` + `verify:beta` + Playwright UI |

### Phase 6：云可选 — ⏸ 非 v1.0

---

## 4. Mega Plan 六步（终局版）对照

| 步 | 内容 | 状态 |
|----|------|------|
| 1 | 协议冻结 `packages/protocol` | ✅ |
| 2 | FnixAi Rust fnix-local | 🟡 本仓 `apps/fnix-local` 可用；FnixAi 姊妹仓待迁移 |
| 3 | Harness 补全（Code session/MCP/status） | ✅ |
| 4 | AG-UI + Work UI | ✅ |
| 5 | Desktop 产品化（Tauri/PTY/Keychain） | ✅ |
| 6 | 测试 + Release | 🟡 自动测试 ✅；Release tag 待 push |

---

## 5. 模块地图

```text
src/fnixagent/harness/     # 门面
src/fnixagent/local/       # Python sidecar MVP
src/fnixagent/services/work_pipeline.py
packages/protocol/         # OpenAPI + schemas
packages/ag-ui-mapper/     # NDJSON → AG-UI
packages/agent-ui/         # Mantine 成熟 Agent UI
apps/fnix-local/           # Rust sidecar（OpenAPI 参考实现）
apps/desktop-tauri/        # Tauri 2 壳（主产品）
apps/desktop/src/renderer/ # 共享 UI
scripts/dev-all.mjs        # → Tauri 三进程
scripts/check-plan.mjs     # 计划验收
```

---

## 6. 参考项目（只读 `_references/`）

| 参考 | 吸收 |
|------|------|
| OpenHarness | workspace、skills、gateway 概念 |
| goose | MCP 配置形态 |
| ag-ui | 事件 schema |
| Terax | Tauri PTY / 轻量壳 |
| IfAI | Harness 工具注册 |

`pnpm refs:clone` — 不 fork、不合并进主产品。

---

## 7. 验收命令

```bash
pnpm sync:plan-desktop   # 同步本计划到桌面
pnpm check:plan            # Mega Plan 自动项
pnpm verify:beta           # 完整 Beta
pnpm dev:all               # Tauri 三进程
pnpm e2e:standalone        # API 自启动 E2E
```

---

## 8. 相关文档

- [`PLAN_STATUS.md`](./PLAN_STATUS.md) — 逐项完成度  
- [`ARCHITECTURE_LOCAL_HARNESS.md`](./ARCHITECTURE_LOCAL_HARNESS.md) — 架构细节  
- [`DESKTOP_TAURI.md`](./DESKTOP_TAURI.md) — Tauri 实现  
- [`BETA_RELEASE.md`](./BETA_RELEASE.md) — 发布流程  
- [`EVOLUTION_CORE.md`](./EVOLUTION_CORE.md) — KTG/STP/MFP  

---

## 9. 剩余工作（诚实清单）

**代码可继续做**：Playwright 扩展场景、Electron 代码删除  
**需你操作**：BYOK 点验 Work/Code、push `v1.0.0-beta.1` tag、录 Demo GIF  
**可选升级**：FnixAi 姊妹仓 `apps/fnix-local` 高性能 PDG（本仓已有 Rust MVP）
