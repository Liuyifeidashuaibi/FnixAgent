# ChatGPT / Codex Desktop — 开源材料清单

> 采集日期：2026-07-18  
> 本地克隆：`_references/chatgpt-desktop-oss/`（已被 `.gitignore` 忽略，需本机保留）  
> 用途：只读借鉴 UI/协议/桌面壳模式；**后续**再按 Fnix（React 19 + Tauri 2 + Tailwind 4 + BYOK）改造。

## 结论（先读）

| 层级 | 是否开源 | 说明 |
|------|----------|------|
| ChatGPT Desktop / Codex App（官方 Electron UI） | **否** | OpenAI 明确暂无开源计划（[openai/codex#10733](https://github.com/openai/codex/issues/10733)） |
| Codex VS Code 扩展 UI | **否**（闭源插件） | 官方未开源扩展前端 |
| Codex CLI + **App Server** | **是** Apache-2.0 | 官方开放的是 harness / JSON-RPC，不是桌面皮肤 |
| 社区桌面壳（Sense-1、Codexia 等） | **是** | 可参考交互与接线；外观≠官方 1:1 |

官网宣发页（浅色 Work / Codex 产品叙事）仍是视觉对照源：  
https://openai.com/zh-Hans-CN/index/chatgpt-for-your-most-ambitious-work/

---

## 已克隆到本机

路径根：`E:\FNIX\FnixAgent\_references\chatgpt-desktop-oss\`

### 1. `openai-codex` ← [openai/codex](https://github.com/openai/codex)

- **License**: Apache-2.0  
- **我们取的内容**: 稀疏检出 `codex-rs/app-server`、`docs`、`sdk`  
- **关键文档**: `codex-rs/app-server/README.md`  
- **协议要点**:
  - JSON-RPC 2.0（stdio / unix socket；ws 实验性）
  - 原语：`Thread` → `Turn` → `Item`
  - 握手：`initialize` → `initialized`
  - 会话：`thread/start|resume|fork`，`turn/start`，流式 `item/*` / `turn/completed`
  - Schema：`codex app-server generate-ts` / `generate-json-schema`
- **博客**: [Unlocking the Codex harness](https://openai.com/index/unlocking-the-codex-harness/)
- **对 Fnix 的价值**: 协议与事件模型参考；**不是** UI 克隆源。Fnix 已有 agentd → fnix-local，不必绑死 Codex runtime，但可对齐「thread/turn/item + approvals」心智模型。

### 2. `sense-1-workspace` ← [georgestander/sense-1-workspace](https://github.com/georgestander/sense-1-workspace)

- **License**: Apache-2.0（便于借鉴）  
- **栈**: Electron + React 19 + Tailwind 4 + TypeScript + `@openai/codex` app-server  
- **设计规范**: `DESIGN.md`（Governed Atelier：浅色白底、OKLCH token、no-line 规则）  
- **前端重点路径**:
  - `desktop/src/renderer/components/` — sidebar / composer / thread / settings / automations
  - `desktop/src/renderer/state/session/` — 流式会话状态
  - `desktop/src/main/runtime/` — 监督启动 Codex app-server
  - `desktop/src/shared/contracts/` — 前后端契约
- **对 Fnix 的价值**:
  - 与 Fnix workbench **前端栈最接近**（React 19 + TW4）
  - 可借鉴：侧栏会话、composer、审批流、workspace 绑定、start surface
  - 外壳是 Electron → 改造时映射到 **Tauri 2** IPC，不抄 main process

### 3. `codexia` ← [milisp/codexia](https://github.com/milisp/codexia)

- **License**: **AGPL-3.0**（注意：直接合入闭源/商业发行需谨慎；优先学架构，避免整段拷贝）  
- **栈**: **Tauri v2** + React + TypeScript + Zustand + shadcn + Tailwind 4  
- **结构**:
  - `src/` — UI（`views/`、`components/`、`stores/`、`services/tauri/`）
  - `src-tauri/` — 桌面后端与 Codex 接线
  - `web/` — headless Axum + `/ws` 远程控制
- **对 Fnix 的价值**:
  - **桌面壳技术路线最接近**（Tauri 2）
  - 可看：thread/turn API 封装、approval、worktree、scheduler、文件树
  - 外观偏「agent workstation」，不是 ChatGPT 官网浅色 Work/Codex 皮肤

---

## React + Tailwind Chat / Agent UI（2026-07 增补）

| 项目 | 栈 | 借鉴点 |
|------|-----|--------|
| [vercel/ai-chatbot](https://github.com/vercel/ai-chatbot)（已克隆 → `vercel-ai-chatbot/`） | Next 15 · React 19 · TW · AI SDK | 消息列、Copy/Vote、streaming shimmer、composer |
| Sense-1（上表） | React 19 · TW4 · Electron | 侧栏 Projects、composer pill、transcript |
| Codexia（上表） | Tauri 2 · React · TW4 | 桌面壳分层（勿整段 AGPL 拷贝） |

Fnix 落地：`apps/workbench/src/shell/chatgpt-desktop/`（ChatGPT 客户端模样 + BYOK）。

## 未克隆但已知的相关仓

| 项目 | 说明 | 是否优先 |
|------|------|----------|
| 官方 Codex App | Electron，闭源 | 仅官网截图对照 |
| [jeremiahodom/codex-ui](https://github.com/jeremiahodom/codex-ui) | Codexia 社区 fork，Node/SSE | 低 |
| openchatui / CortexOne 等 | 通用 Chat 壳 | 低（不像 Codex Desktop） |

如需再扩：`git clone --depth 1` 进同一目录即可。

---

## 建议的借鉴顺序（给后续改造）

1. **视觉对照**（已在做）: 官网浅色 Work / Codex 布局 → `apps/workbench/src/shell/chatgpt-desktop/`  
2. **交互骨架**: Sense-1 的 sidebar + composer + thread transcript + start surface  
3. **桌面接线模式**: Codexia 的 Tauri command / 服务层拆分（勿整仓 AGPL 拷贝）  
4. **运行时**: 继续 Fnix BYOK + agentd + fnix-local；仅在需要时可选对接 Codex app-server  
5. **产品映射**: ChatGPT Work → Fnix Work；Codex → Fnix Code；去掉登录，数据落 `~/.fnix` + `{workspace}/.fnix`

---

## 复现克隆命令

```powershell
$dir = "E:\FNIX\FnixAgent\_references\chatgpt-desktop-oss"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Set-Location $dir

git clone --depth 1 https://github.com/georgestander/sense-1-workspace.git
git clone --depth 1 https://github.com/milisp/codexia.git

git clone --depth 1 --filter=blob:none --sparse https://github.com/openai/codex.git openai-codex
Set-Location openai-codex
git sparse-checkout set codex-rs/app-server docs sdk
```

---

## License 速查

| 仓 | License | 借鉴策略 |
|----|---------|----------|
| openai/codex | Apache-2.0 | 协议/事件/文档可对照实现 |
| sense-1-workspace | Apache-2.0 | UI 模式与状态机可参考改写 |
| milisp/codexia | AGPL-3.0 | 学架构与 Tauri 分层；避免直接粘贴大段源码进 Fnix |
