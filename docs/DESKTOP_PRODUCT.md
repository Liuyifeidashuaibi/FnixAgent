# 产品前端主线：Desktop（AI 工作台）

本仓 **产品 UI 以 Tauri 2 Desktop 为主**（`apps/desktop-tauri`），Electron（`apps/desktop`）保留作过渡对照。

对标 **TRAE Work / 腾讯 WorkBuddy** 一类 **AI 原生工作台**，不是 Cursor 那种「纯写代码 IDE」。

| 对标 | 本产品对应 |
|---|---|
| **Harness Agent / ohmo** | 本地 workspace + Work/Code 双模式 + `~/.fnix` |
| **TRAE Work · Work 模式** | 提任务 → Agent 拆解执行 → 验收文档/表格/PPT/PDF 等产物 |
| **TRAE Code** | 本地编程 Agent：读改跑、Diff 验收 |
| Code / IDE 能力 | Work \| Code 并列，共用 workspace |

```
ActivityBar │ Sidebar │ Work / Composer / Editor │ Agent 侧栏
```

| 应用 | 定位 |
|---|---|
| `apps/desktop-tauri` | **主产品**（Tauri 2 壳 + 共享 renderer） |
| `apps/desktop` | Electron 过渡版（逐步退役） |
| `apps/admin` | 可选运维后台 |
| `apps/web` | **冻结** |

## 产品身份（与 GitHub README 一致）

- **智能办公 Agent**：学习 / 教育 / 办公
- 后端：`office/`（Word/Excel/PPT/PDF…）+ `business/`（检索、工作流等）+ 自进化内核
- Desktop：本地工作区 + **Work 模式任务** + Composer；编码/Diff 是加分项

## 落地架构（当前实现目标）

```
Desktop WorkPanel
  → POST /api/v1/work/stream
      { user_input, workspace?, llm?, session_id?, work_mode?: ask|plan|craft }
  → GraphComponents（默认启动）
      KTG 路径检索 → STP 技能排序 → AgenticLoop 执行
      → MFP ②固化 / ③元反思 / ④爬山
  → NDJSON: evolution / thought / action / observation / text / artifact / done
```

**护城河（必做，不是可选）**：KTG + STP + MFP。说明见 [`EVOLUTION_CORE.md`](./EVOLUTION_CORE.md)。

| 层 | 职责 |
|---|---|
| Settings（localStorage） | BYOK：provider / model / apiKey → 随请求 `llm` 下发 |
| `/work/stream` | **主路径**：办公任务 + 自进化内核 |
| `/chat/stream` | Ask/Edit；复用同一套办公工具装配 |
| `/chat/evolve` | LangGraph 全图入口（对照/深度进化） |
| `/chat/agent` | Code/Diff 附属 |

## 成熟度优先级

1. ~~Work 主路径（协议对齐 + 流式 + 产物）~~ ✅
2. ~~Settings → 请求级 LLM~~ ✅
3. ~~Stop / 任务历史~~ ✅
4. ~~Office 工具真实注册~~ ✅
5. ~~KTG / STP / MFP 进主路径~~ ✅（`work_pipeline` 9 步）
6. ~~三层记忆 / 推理选择 / 安全 / TraceId / KTG 持久化~~ ✅
7. Code/Diff/Git 不抢叙事
8. 打包与首次引导；生产级 Docker/gVisor/Jaeger 按部署环境启用

Desktop 默认打开 **Work Mode**。内核说明见 [`EVOLUTION_CORE.md`](./EVOLUTION_CORE.md)。

## 本地跑（Standalone · 测试版）

**一条命令（Tauri · 推荐）：**

```bash
pnpm dev:all          # 或 dev:all:tauri
```

Electron 过渡：

```bash
pnpm dev:all:electron
# 或 pnpm dev:electron
```

或分终端：

```bash
# API
set FNIXAGENT_PROFILE=standalone
set PYTHONPATH=src
python -m fnixagent.main serve

# Desktop
pnpm --filter @fnixagent/desktop-tauri dev
```

后端默认 `http://127.0.0.1:8000`。完整说明见 [`docs/QUICKSTART.md`](./QUICKSTART.md)。

买服务器 / 域名后：改 `FNIXAGENT_PROFILE=cloud`，见 [`docs/DEPLOY.md`](./DEPLOY.md)。

## 架构约束

1. 渲染进程不直连 Node FS / 子进程 → `window.electron.fs` / `shell.exec`
2. **产品叙事以 Work 为准**；Agent 写代码默认 preview，Accept 才写盘
3. 客户端 API Key 仅用于 Desktop BYOK，服务端 `.env` 为回退
4. 不做 Web 主线排期
