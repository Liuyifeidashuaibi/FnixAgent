# Fnix 本地 Harness 架构

> **产品形态**：本地 Harness Agent — 同一工作台，**Work**（办公任务）与 **Code**（本地编程）共用 workspace。  
> **主计划**：[`HARNESS_PLAN_v1.0.md`](./HARNESS_PLAN_v1.0.md)

---

## 1. 三进程架构（v1.0 ✅）

```
Desktop (Tauri 2)
    ↕ HTTP (window.electron 桥)
fnix-agentd (Python, 127.0.0.1:8000)
    ↕ HTTP (FNIX_LOCAL_URL)
fnix-local (Python MVP → 未来 Rust)
```

| 进程 | 默认端口 | 职责 |
|------|----------|------|
| Desktop (Tauri) | — | Work/Code UI、IPC、PTY、Keychain |
| fnix-agentd | 8000 | KTG/STP/MFP、Work/Code 大脑 |
| fnix-local | 8710 | 索引、PDG digest、沙箱命令 |

**启动**：

```bash
pnpm dev:all          # Tauri 三进程（推荐）
pnpm dev:all:tauri    # 同上
pnpm dev:all:electron # Electron 过渡
```

Standalone 仅 Desktop：`pnpm dev`（Tauri 自动 spawn 后端）

**降级**：fnix-local 离线时 Work/Code 仍可用 Python workspace 工具。

**Sidecar 生命周期**：Tauri `runtime.rs` 管理 spawn/stop；`dev:all:tauri` 外部三进程时设 `FNIX_LOCAL_MANAGED=false`。

---

## 2. 目录约定

### 用户级 `~/.fnix/`（或 `FNIX_HOME`）

| 路径 | 用途 |
|------|------|
| `config.toml` | provider / model / MCP（后续） |
| `mcp.json` | MCP server 配置 |
| `sessions/*.json` | Work + Code 任务持久化 |
| `logs/` | 本地日志 |

### 项目级 `{workspace}/.fnix/`

| 路径 | 用途 |
|------|------|
| `skills/*.md` | 项目技能（注入 STP / prompt） |
| `artifacts/` | 推荐产物输出目录 |
| `topology/` | KTG 项目缓存 |
| `index/` | fnix-local 索引（PDG） |
| `rules.md` | 项目规则（AGENTS.md 兼容） |

打开文件夹时 Desktop 调用 `POST /api/v1/harness/workspace/ensure` 并 `POST /api/v1/harness/index`。

---

## 3. Python 模块

```
src/fnixagent/harness/
├── paths.py          # ~/.fnix 与 .fnix 路径
├── workspace.py      # 布局初始化
├── session.py        # Work/Code session JSON
├── skills_loader.py  # .fnix/skills 加载
├── gateway.py        # 启动初始化 + 状态
├── local_bridge.py   # fnix-local HTTP 桥
├── local_context.py  # Code 模式 PDG prompt
└── config.py         # config.toml
```

**主路径**：`services/work_pipeline.run_work_stream` 读写 session、加载 skills。

---

## 4. API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/harness/status` | Harness + sidecar 状态 |
| POST | `/api/v1/harness/workspace/ensure` | 初始化项目 .fnix |
| POST | `/api/v1/harness/index` | 触发 PDG 索引 |
| GET | `/api/v1/harness/skills?workspace=` | 列出技能 |
| POST | `/api/v1/harness/skills/reload` | 热加载技能 |
| GET/PUT | `/api/v1/harness/mcp` | MCP 配置 |
| GET | `/api/v1/work/sessions` | 任务列表（work/code） |
| GET | `/api/v1/work/sessions/{id}` | 单个任务 |
| POST | `/api/v1/work/stream` | Work 流式执行 |
| POST | `/api/v1/chat/agent` | Code 流式 Agent |

契约：`packages/protocol/openapi/fnix-local-v1.yaml`

---

## 5. Desktop 集成

| 模块 | 职责 |
|------|------|
| `LivingWorkbench` | 选文件夹 → ensure + index；Work/Code 切换 |
| `WorkPanel` | Work 流式 + AG-UI 步骤条 |
| `ComposerPanel` | Code 会话 + session_id |
| `SettingsPanel` | Harness / MCP / BYOK |
| `TerminalPanel` | 本地 PTY（Tauri）+ AgentOS |
| `harnessApi.ts` | Harness / sessions 客户端 |
| `apps/desktop-tauri` | Tauri 桥 `platform.ts` |

---

## 6. Work vs Code

| 模式 | API | Harness 共用 |
|------|-----|--------------|
| **Work** | `/work/stream` | workspace、skills、session、artifacts |
| **Code** | `/chat/agent` | workspace、PDG 上下文、session mode=code |

---

## 7. 与 OpenHarness 的关系

- **借鉴**：workspace 布局、skills 文件化、本地 gateway 概念  
- **保留 Fnix 独有**：KTG / STP / MFP、Office 工具链、TraceId  
- **不 fork** OpenHarness 整仓

---

## 8. 验收

**自动**：

```bash
pnpm check:plan
pnpm verify:beta
```

**手动**（需 BYOK）：

1. `pnpm dev:all` → 登录 → 打开文件夹  
2. `{folder}/.fnix/` 已创建  
3. Work 任务流式完成  
4. Code Composer 会话 + Diff  
5. 重启后 `GET /work/sessions` 有历史  

---

## 9. 下一步（v1.1）

- FnixAi Release → Rust `fnix-local` 二进制（`pnpm fetch:fnix-local`）  
- GitHub Release tag + Demo GIF  
- 可选：PyInstaller 内嵌 agentd、Playwright UI E2E  
