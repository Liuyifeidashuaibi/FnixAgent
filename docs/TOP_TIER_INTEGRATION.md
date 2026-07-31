# Fnix 顶级集成方案 — 强壮代码从哪来、怎么用

> 更新时间：2026-07-18  
> 工具：`pnpm stack:audit` · `pnpm stack:sync` · `pnpm stack:sidecar` · `pnpm stack:report`

---

## 1. 设计原则（冻结）

| 原则 | 说明 |
|------|------|
| **契约驱动** | `packages/protocol/openapi/fnix-local-v1.yaml` 是唯一 sidecar 真相 |
| **只读借鉴** | `_references/` 与 FnixAi 姊妹仓 **禁止** 直接 import 进产品 |
| **分层复用** | UI 层 npm · 大脑 Python · 算力 Rust sidecar · 各自独立演进 |
| **降级可用** | Rust 离线 → Python MVP → Workspace 工具，用户始终能干活 |

---

## 2. 网络成熟项目矩阵（可下载 · 已克隆）

运行 `pnpm refs:clone` 后，15 个参考仓在 `_references/`。

### Tier A — Harness / Agent 核心（必用）

| 项目 | GitHub | 吸收什么 | Fnix 落点 |
|------|--------|----------|-----------|
| **OpenHarness** | [HKUDS/OpenHarness](https://github.com/HKUDS/OpenHarness) | `~/.ohmo` 布局、skills、session、gateway、MCP | `harness/*` |
| **AG-UI** | [ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui) | 事件 schema、HttpAgent、SSE | `ag-ui-mapper` + `@ag-ui/client` |
| **CopilotKit** | [CopilotKit/CopilotKit](https://github.com/CopilotKit/CopilotKit) | Tool 卡片 UX、Generative UI 模式 | `@fnixagent/agent-ui` |
| **goose** | [aaif-goose/goose](https://github.com/aaif-goose/goose) | MCP 配置、Desktop 扩展形态 | Settings Harness 页 |
| **OpenHands SDK** | [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk) | 本地 workspace 执行、沙箱 | `core/tools/workspace.py` |
| **aider** | [Aider-AI/aider](https://github.com/Aider-AI/aider) | RepoMap / 符号排名算法 | `core/code/indexer.py` |
| **MCP servers** | [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) | 标准 MCP 形态 | `~/.fnix/mcp.json` |

### Tier B — Office / 工具链（Work 模式）

| 项目 | 吸收什么 | Fnix 落点 |
|------|----------|-----------|
| **markitdown** | 文档→Markdown | Work 文档工具 |
| **grok-build** | Agent loop / grep 工具 | 工具注册模式 |
| **Office MCP / Bench** | 办公场景评测 | Work pipeline 场景 |

### Tier C — 前端/Desktop 壳（可选）

| 项目 | 吸收什么 | 说明 |
|------|----------|------|
| **Terax**（参考） | Tauri PTY 轻量壳 | 已实现 `pty.rs` |
| **pi-mono** | 多平台 agent 模式 | 长期参考 |

---

## 3. FnixAi 姊妹仓 — 可复用清单

**Canonical 路径**：`E:\FNIX\FnixAi\fnix-se`（不在 FnixAgent git 内）

### ✅ 应接入 fnix-local sidecar（最高 ROI）

| FnixAi 模块 | 路径 | 替换 FnixAgent 什么 |
|-------------|------|---------------------|
| **fnix-pdg** | `crates/fnix-pdg/` | 正则扫描 → 真 tree-sitter PDG |
| **fnix-ast** | `crates/fnix-ast/` | 符号解析 |
| **fnix-vector** | `crates/fnix-vector/` | `/v1/context` vector_hits |
| **fnix-tools** | `crates/fnix-tools/read_file.rs`, `run_command.rs` | 安全读文件 + PTY 命令 |
| **fnix-sandbox** | `crates/fnix-sandbox/` | 超时、blocklist |
| **CLI index** | `apps/cli/src/main.rs` (`fnix index`) | `/v1/index` 逻辑 |
| **agent_hooks** | `apps/cli/src/agent_hooks.rs` | `/v1/context` 排名 |

### ❌ 保留在 FnixAi，不迁入 FnixAgent

| 模块 | 原因 |
|------|------|
| `fnix-ui` GPU Cognitive Surface | AgentOS 主产品，与 Tauri Desktop 定位不同 |
| `fnix-agent/loop_engine.rs` | FnixAgent 已有 Python KTG/STP/MFP 大脑 |
| `apps/server` (:8080) | API 形状不同，非 sidecar 契约 |
| `fnix-evolution` / DAG | L3 调度，非 v1.0 sidecar 范围 |

### 🔨 待 FnixAi 新建

```
E:\FNIX\FnixAi\fnix-se\apps\fnix-local\   ← 实现 OpenAPI :8710
  依赖: fnix-pdg + fnix-vector + fnix-tools + fnix-sandbox
  输出: fnix-local-{win,mac,linux}.zip → FnixAgent fetch-fnix-local.mjs
```

---

## 4. 顶级目标架构

```text
┌──────────────────────────────────────────────────────────────────┐
│ L4 产品 UI (FnixAgent)                                           │
│  Tauri 2 + Mantine + @fnixagent/agent-ui + @ag-ui/client         │
│  CopilotKit 模式（自研 agent-ui，v1.1 可接 CopilotRuntime）       │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP :8000
┌────────────────────────────▼─────────────────────────────────────┐
│ L3 Python 大脑 (FnixAgent agentd)                                │
│  Harness ~/.fnix · Work KTG/STP/MFP · Code Agent · MCP           │
│  local_bridge.py ──────────────────────────────┐                 │
└────────────────────────────────────────────────│─────────────────┘
                                                 │ OpenAPI :8710
┌────────────────────────────────────────────────▼─────────────────┐
│ L2 本地算力 Sidecar（优先级）                                     │
│  ① FnixAi apps/fnix-local (fnix-pdg + vector + tools)  ← 目标  │
│  ② FnixAgent apps/fnix-local (Axum 参考实现)           ← 当前  │
│  ③ Python fnixagent.local                              ← 降级   │
└──────────────────────────────────────────────────────────────────┘
                             ▲
┌────────────────────────────┴─────────────────────────────────────┐
│ L1 参考库 (_references/ 只读)                                     │
│  OpenHarness · AG-UI · CopilotKit · aider · OpenHands · goose    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. 实施路线图

### Phase 1 — 现在可用（已完成）

- [x] `_references/` 15 仓克隆 + 验证
- [x] `@fnixagent/agent-ui` + AG-UI mapper
- [x] `apps/fnix-local` Rust 参考 sidecar
- [x] OpenAPI 契约测试
- [x] `pnpm stack:*` 集成工具

### Phase 2 — FnixAi sidecar（1–2 周）

1. FnixAi 新建 `apps/fnix-local`，复用 `fnix-pdg` 索引
2. 输出格式适配 `pdg_summary.json` + OpenAPI
3. CI Release → `FNIX_LOCAL_RELEASE_URL`
4. FnixAgent `fetch-fnix-local.mjs` 自动拉取

### Phase 3 — UI 顶级化（1 周）

1. `FnixAgUiRuntime` — FastAPI NDJSON → AG-UI SSE 适配器
2. Work/Code 统一 `AgentChatPanel`
3. CopilotKit `useRenderTool` 渐进替换 ToolCallCard

### Phase 4 — Harness 吸收 OpenHarness（持续）

1. session compaction 模式（参考 ohmo）
2. skills 热加载 workflow
3. MCP registry 对齐 goose 形态

---

## 6. 命令速查

```bash
pnpm refs:clone          # 克隆 15 个参考仓
pnpm refs:verify         # 验证参考仓健康
pnpm stack:audit         # 审计：参考仓 + FnixAi + sidecar + 契约
pnpm stack:sync          # 同步：clone + verify + 姊妹仓检查
pnpm stack:sidecar       # 编译 sidecar（FnixAi 优先，本仓 fallback）
pnpm stack:report        # 生成 docs/STACK_AUDIT.md
pnpm build:fnix-local    # 仅本仓 Rust sidecar
pnpm check:plan          # Mega Plan 验收
```

---

## 7. 许可证合规

| 来源 | License | 用法 |
|------|---------|------|
| OpenHarness, AG-UI, CopilotKit | MIT | 架构/UX 借鉴，不复制大段代码 |
| goose, aider, OpenHands | Apache-2.0 | 算法/模式移植需注明 |
| FnixAi fnix-se | 姊妹仓私有 | 二进制/link 复用，不 merge 代码树 |
