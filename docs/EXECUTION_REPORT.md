# Fnix 全栈执行报告

> 生成时间：2026-07-18  
> 架构：**Rust 高性能算力 · Python 上层大脑 · Tauri UI**  
> 命令：`pnpm stack:audit` · `pnpm stack:report`

---

## 1. 执行摘要

| 层级 | 技术 | 本次执行 | 状态 |
|------|------|----------|------|
| **L4 UI** | Tauri 2 + Mantine + agent-ui + AG-UI | 已有 + 持续 | ✅ |
| **L3 大脑** | Python agentd :8000 (KTG/STP/MFP) | **新增 AG-UI SSE 路由** | ✅ |
| **L2 算力** | Rust fnix-local :8710 | **FnixAi 源码新建 + FnixAgent 二进制** | 🟡 |
| **L1 参考** | _references/ 15 仓 | 10/10 已克隆 | ✅ |

**结论**：三层架构已按规划落地。FnixAi `apps/fnix-local` 源码已完成（真 PDG 索引），本机编译因 **磁盘/页面文件不足** 暂未完成 tree-sitter 链接；FnixAgent 侧 Rust 参考二进制与 Python fallback 均可运行。

### 1.1 Desktop 产品策略：API-only（BYOK）

| 项 | 实现 |
|----|------|
| 前端 | `FNIX_API_ONLY=true` · 所有用户必须填写 API Key · 移除管理员服务端 Key UX |
| 设置 | `apiProviders.ts` 预设 OpenAI / Qwen / DeepSeek / GLM / 自定义 Base URL |
| 引导 | `FirstRunWizard` 提供商选择 + 必填 Key |
| 门禁 | `ApiKeyBanner` · TopBar Badge · Work/Code 无 Key 不可提交 |
| 后端 | `FNIX_API_ONLY=1`（默认）· `llm_policy.resolve_llm_for_request` 强制 BYOK |
| Code | `/chat/agent` 接收 `llm` 覆盖 · `@file` mention · 批量 Apply |

---

## 2. 目标架构（已冻结）

```text
┌─────────────────────────────────────────────────────────┐
│  Tauri Desktop (UI)                                      │
│  LivingWorkbench · WorkPanel · ComposerPanel · agent-ui  │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP :8000
┌───────────────────────────▼─────────────────────────────┐
│  Python agentd (大脑)                                    │
│  /work/stream · /chat/agent · /harness/*                 │
│  /ag-ui/work/stream  ← 新增 AG-UI SSE                   │
│  work_pipeline (KTG/STP/MFP 9步)                         │
└───────────────────────────┬─────────────────────────────┘
                            │ local_bridge.py · OpenAPI
┌───────────────────────────▼─────────────────────────────┐
│  Rust fnix-local (高性能)                                │
│  ① FnixAi apps/fnix-local (fnix-pdg) ← 源码已建         │
│  ② FnixAgent apps/fnix-local         ← 二进制可用       │
│  ③ Python fnixagent.local              ← 降级           │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 本次新增/修改清单

### FnixAi（姊妹仓 `E:\FNIX\FnixAi\fnix-se`）

| 文件 | 说明 |
|------|------|
| `apps/fnix-local/Cargo.toml` | 新 sidecar crate（fnix-ast + fnix-pdg） |
| `apps/fnix-local/src/main.rs` | OpenAPI 5 路由 + blocklist |
| `apps/fnix-local/src/index.rs` | 真 PDG 索引（tree-sitter） |
| `Cargo.toml` | workspace 加入 `apps/fnix-local` |

### FnixAgent（本仓）

| 文件 | 说明 |
|------|------|
| `src/fnixagent/core/ag_ui/mapper.py` | NDJSON → AG-UI SSE 事件 |
| `src/fnixagent/api/routers/ag_ui.py` | `POST /api/v1/ag-ui/work/stream` |
| `src/fnixagent/main.py` | 注册 ag_ui 路由 |
| `tests/unit/test_ag_ui_mapper.py` | AG-UI 映射单测 |
| `scripts/fnix-stack.mjs` | 集成审计/同步/编译工具 |
| `docs/TOP_TIER_INTEGRATION.md` | 顶级集成方案 |
| `docs/STACK_AUDIT.md` | 自动审计报告 |

---

## 4. 网络成熟项目吸收矩阵

| 项目 | 吸收内容 | Fnix 落点 | 状态 |
|------|----------|-----------|------|
| OpenHarness | Harness 布局/skills/session | `harness/*` | ✅ 已吸收 |
| AG-UI | 事件协议 | `ag-ui-mapper` + **Python SSE** | ✅ 本次完成 |
| CopilotKit | Tool UX | `@fnixagent/agent-ui` | ✅ |
| aider | RepoMap | `core/code/indexer.py` | ✅ |
| OpenHands | workspace 执行 | `core/tools/workspace.py` | ✅ |
| goose | MCP 形态 | Settings Harness | ✅ |

---

## 5. FnixAi 可复用模块审计

| 模块 | 路径 | 用途 | 状态 |
|------|------|------|------|
| fnix-pdg | `crates/fnix-pdg` | PDG 图索引 | ✅ 已接入 fnix-local |
| fnix-ast | `crates/fnix-ast` | tree-sitter 解析 | ✅ 已接入 fnix-local |
| fnix-vector | `crates/fnix-vector` | 语义检索 | ⏳ v1.1 接入 context |
| fnix-tools | `crates/fnix-tools` | PTY run_command | ⏳ 轻量 run 已实现 |
| **apps/fnix-local** | `apps/fnix-local` | OpenAPI sidecar | ✅ **源码新建** |
| fnix-ui | GPU UI | — | ❌ 保留 FnixAi |
| apps/server | :8080 工程 API | — | ❌ 非 sidecar 契约 |

---

## 6. API 端点一览

### Python 大脑 (:8000)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/work/stream` | Work NDJSON（原有） |
| POST | `/api/v1/ag-ui/work/stream` | **Work AG-UI SSE（新增）** |
| GET | `/api/v1/ag-ui/health` | AG-UI 层健康 |
| POST | `/api/v1/chat/agent` | Code Agent |
| POST | `/api/v1/harness/index` | 触发 sidecar 索引 |

### Rust 算力 (:8710)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | runtime=rust, engine=fnix-pdg |
| POST | `/v1/index` | PDG 索引 |
| GET | `/v1/context` | digest + vector_hits |
| POST | `/v1/run` | 沙箱命令 |
| GET | `/v1/read` | 安全读文件 |

---

## 7. 验收结果

```bash
# 已通过
pytest tests/unit/test_ag_ui_mapper.py          # 4 passed
pytest tests/contract/test_fnix_local_openapi.py # 4 passed
pnpm stack:audit                                 # 参考仓 10/10, sidecar 全绿
node scripts/build-fnix-local.mjs              # FnixAgent 二进制 OK

# FnixAi 编译
cargo build -p fnix-local @ fnix-se            # ❌ 磁盘空间不足 (tree-sitter C 编译)
```

### 解除 FnixAi 编译阻塞

```powershell
# 清理 temp + 增大页面文件，或指定 target 到大盘
$env:CARGO_TARGET_DIR="E:\FNIX\FnixAi\fnix-se\target"
cd E:\FNIX\FnixAi\fnix-se
cargo build --release -p fnix-local
node E:\FNIX\FnixAgent\scripts\build-fnix-local.mjs
```

---

## 8. 推荐使用方式

```bash
# 开发三进程
pnpm dev:all

# 集成审计
pnpm stack:audit
pnpm stack:report

# 编译 sidecar（FnixAi 优先 → 本仓 fallback）
pnpm stack:sidecar

# Work 流 — 两种消费方式
# ① 原有 NDJSON（Desktop WorkPanel）
POST /api/v1/work/stream

# ② AG-UI SSE（CopilotKit / @ag-ui/client）
POST /api/v1/ag-ui/work/stream
Accept: text/event-stream
```

---

## 9. 下一步（按 ROI）

| # | 任务 | 负责层 |
|---|------|--------|
| 1 | 释放磁盘 → 编译 FnixAi fnix-local | Rust |
| 2 | `fnix-vector` 接入 `/v1/context` | Rust |
| 3 | Desktop WorkPanel 接 `@ag-ui/client` HttpAgent | Tauri UI |
| 4 | CopilotKit Runtime 适配 Code 模式 | UI + Python |
| 5 | push `v1.0.0-beta.1` tag | 发布 |

---

## 10. 文件索引

| 文档 | 路径 |
|------|------|
| 主计划 | `docs/HARNESS_PLAN_v1.0.md` |
| 顶级集成方案 | `docs/TOP_TIER_INTEGRATION.md` |
| 自动审计 | `docs/STACK_AUDIT.md` |
| 架构细节 | `docs/ARCHITECTURE_LOCAL_HARNESS.md` |
| OpenAPI 契约 | `packages/protocol/openapi/fnix-local-v1.yaml` |
| 集成工具 | `scripts/fnix-stack.mjs` |

---

**执行完成。** 三层分工已落实：Rust 负责 PDG/索引/命令，Python 负责 Agent 大脑与 AG-UI 桥接，Tauri 负责产品 UI。
