# Fnix Harness × Hermes Agent — 设计调整方案

> **目标**：开源 Desktop 产品对齐 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 的「下载 → 配置 → 干活」自托管体验，同时保留 Fnix 的 **Work/Code 双模式 + KTG/STP/MFP** 差异化。
>
> **状态**：v0.1 方案 · 2026-07-18  
> **关联**：[OPEN_SOURCE_DESIGN.md](./OPEN_SOURCE_DESIGN.md)（用户路径冻结）

---

## 1. Hermes 产品模型（我们要对标的什么）

Hermes 不是「带登录的 SaaS」，而是 **本机 Agent 运行时 + 可选 GUI**：

```text
install.sh / install.ps1 / Desktop .exe
        ↓
~/.hermes（或 %LOCALAPPDATA%\hermes）
  ├── config（provider / model / tools）
  ├── sessions / memory / skills
  └── hermes-agent（可选 git checkout）
        ↓
hermes（CLI） 或  hermes desktop（GUI）
        ↓
hermes setup → 选 provider + Key → 直接对话
```

| 维度 | Hermes 做法 | 设计含义 |
|------|-------------|----------|
| **身份** | 无云账号；自托管默认匿名 | 不阻塞首次使用 |
| **安装** | 一条命令装齐 Python/uv/依赖 | 用户不感知运行时 |
| **配置** | `hermes setup` / Settings 向导 | Key 在本机，不上传 |
| **数据** | 全在 `~/.hermes` | 可备份、可迁移 |
| **入口** | CLI 与 Desktop **共享** config/sessions | 同一 Agent，多壳 |
| **模型** | BYOK 为主；Portal OAuth 为**可选**便利 | 开源路径不依赖 Portal |
| **Doctor** | `hermes doctor` 诊断环境 | 降低 support 成本 |
| **发布** | GitHub Releases 三平台 + 文档站 | 90% 用户零编译 |

**Hermes 明确不做的事（开源版可对齐）**：不要求注册、不默认遥测、不把 LLM Key 托管在 Nous 服务器（Portal 是 opt-in）。

---

## 2. Fnix 当前状态（已实现 vs 缺口）

### 2.1 已对齐 ✅

| Hermes | Fnix | 实现 |
|--------|------|------|
| 无登录自托管 | 无 LoginPage | `App.tsx` 直连工作台 |
| BYOK | Settings / FirstRunWizard | `apiProviders.ts` + `FNIX_API_ONLY` |
| 本地数据目录 | `~/.fnix` + `{workspace}/.fnix` | harness 路由 + workspaceStore |
| Standalone 零 Docker | `FNIXAGENT_PROFILE=standalone` | profile.py |
| 本机 API 免 JWT | standalone 匿名 principal | `main.py` GatewayMiddleware |
| 一条命令 dev | `pnpm setup` / `pnpm doctor` / `pnpm dev` | scripts/*.mjs |
| Tauri Desktop | desktop-tauri | 弃用 Electron |
| 隐私本地说明 | LocalPrivacySettings | 替代账号 PrivacyCenter |

### 2.2 部分对齐 🟡

| Hermes | Fnix 现状 | 差距 |
|--------|-----------|------|
| `curl \| bash` 安装 | `install.ps1` / `install.sh` + `pnpm setup` | 未做到「非开发者零 Node」；Release 包未首发 |
| `hermes desktop` 与 CLI 同源 | Desktop 为主，CLI 弱 | 配置/session 未统一读写路径 |
| `hermes setup` 交互向导 | FirstRunWizard（3 步） | 缺 model 选择、tools/MCP 一步配齐 |
| `hermes doctor` | `pnpm doctor` | 未覆盖 sidecar/Key/WebView2 一键修复 |
| Skills / Memory 开放标准 | KTG/STP/MFP 内核 | 缺 agentskills.io 导入/export 故事 |
| 文档站 | docs/*.md | 无独立 docs 站、无 Quickstart 2 分钟路径 |

### 2.3 刻意不对齐 ❌（Fnix 边界）

| Hermes 能力 | Fnix 开源版 | 原因 |
|-------------|-------------|------|
| Telegram/Discord Gateway | 不做 | Desktop Harness 定位，非 messaging bot |
| Nous Portal OAuth | 不做 | BYOK-only 产品策略 |
| 六类 terminal backend（Modal/Daytona…） | 仅本机 + fnix-local 沙箱 | 降低复杂度 |
| Electron Desktop | Tauri 2 | 已冻结 |
| 云 VPS 常驻 Agent | 本机优先 | standalone 默认 |

---

## 3. 设计原则（冻结）

1. **Open Path = Hermes Self-Hosted Path**  
   下载 / 安装包用户：**零账号、零编译、零 Docker**。

2. **Configuration Local-First**  
   API Key、工作区、会话均在设备上；网络默认 `127.0.0.1`。

3. **One Runtime, Multiple Shells（目标态）**  
   Desktop UI 与 `fnixagent` CLI 读写同一 `~/.fnix` config（分阶段落地）。

4. **Setup Before Scale**  
   先打通 Release + FirstRun + BYOK，再补 Skills/MCP/记忆导出。

5. **Fail Open for Local, Fail Closed for Cloud**  
   `standalone` → 网关匿名；`cloud` → JWT 必须（企业/deploy 保留 auth.py）。

---

## 4. 体验流程调整（对标 Hermes Quickstart）

### 4.1 目标用户路径（5 步 · 与 Hermes 同构）

```text
Download → Install → Open → Setup（Key + Model + Folder）→ Work | Code
```

| 步骤 | Hermes | Fnix 调整 |
|------|--------|-------------|
| Install | `install.ps1` 装 uv+Python+Git | Release 内嵌 Python sidecar；开发者 `pnpm setup` |
| Open | 无登录 | ✅ 已实现 |
| Setup | `hermes setup` | **增强 FirstRunWizard**（见 §5.1） |
| Chat | TUI / Desktop 同 session | Work/Code 面板 + 会话列表 |
| Doctor | `hermes doctor` | **增强 pnpm doctor**（见 §5.2） |

### 4.2 配置模型（对齐 Hermes config 分层）

```text
~/.fnix/
  config.json          # 全局：provider, model, api_key_ref, theme
  sessions/            # Work/Code 会话索引
  mcp.json             # MCP servers（已有 harness 路由）
  skills/              # 未来：用户技能（可选）

{workspace}/.fnix/
  harness.json         # 工作区绑定、索引状态
  artifacts/           # Work 交付物
```

**Key 存储**：Settings 写入 `config.json` 或 OS Keychain（Tauri plugin），**永不**进 repo / `.env`（Desktop 用户）。

---

## 5. 分阶段调整方案

### Phase 0 — 发布就绪（P0，1–2 周）

> 让用户能像装 Hermes Desktop 一样装上 Fnix。

| # | 项 | 动作 | 验收 |
|---|-----|------|------|
| 0.1 | GitHub Release | 打 `v1.0.0-beta.1`，三平台 CI | README Download 可点 |
| 0.2 | 安装包内嵌运行时 | bundle-python + sidecar 仅写 `desktop-tauri/resources` | 干净机器双击可开 |
| 0.3 | 无登录 | ✅ 已完成 | 无 Login / OAuth UI |
| 0.4 | MSVC Release | Windows CI 用 MSVC；文档写清源码需 VS | `pnpm doctor` 通过 |
| 0.5 | Release Notes | 5 步 Quickstart + BYOK 截图 | 与 Hermes README 同级清晰度 |

### Phase 1 — Setup 体验（P1，对标 `hermes setup`）

| # | 项 | 动作 | 验收 |
|---|-----|------|------|
| 1.1 | FirstRunWizard v2 | 步骤：Provider → **Model 下拉** → Key → Test connection → Folder → Mode | Key 错时有明确错误 |
| 1.2 | Settings 合并 | AI 页 = provider + model + base_url + key；与 wizard 同一数据源 | 改 Settings 即生效 |
| 1.3 | 跳过/稍后 | 「稍后配置」仍进工作台 + ApiKeyBanner | 不阻塞探索 UI |
| 1.4 | 连接测试 | `GET /health` + 一次最小 LLM ping（可选） | -setup 失败可诊断 |

### Phase 2 — Doctor & Install（P1，对标 `hermes doctor` + 安装脚本）

| # | 项 | 动作 | 验收 |
|---|-----|------|------|
| 2.1 | `pnpm doctor` 增强 | 检查：Python、端口 8000/8710、WebView2、MSVC、磁盘、API Key 是否配置 | 输出 fix 建议 |
| 2.2 | Windows 安装脚本 | 根目录 `install.ps1` 调用 `pnpm setup` + 可选 `winget` VS Build Tools 提示 | 非开发者一条命令 |
| 2.3 | `pnpm clean:cache` | ✅ 已有 | 文档 FAQ 链到 doctor |

### Phase 3 — 配置同源（P2，对标 CLI ↔ Desktop 共享）

| # | 项 | 动作 | 验收 |
|---|-----|------|------|
| 3.1 | `~/.fnix/config.json` 规范 | 定义 schema；Desktop Settings 读写 | CLI `fnixagent chat` 读同一 Key |
| 3.2 | Session 路径统一 | Work/Code session id 存 harness | Desktop 开的 session CLI 可 `--resume` |
| 3.3 | 文档 | `docs/CLI_DESKTOP_PARITY.md` | Hermes 式「换壳不换脑」 |

### Phase 4 — Harness 能力故事（P2，差异化 + 部分 Hermes 能力）

| # | 项 | 动作 | 验收 |
|---|-----|------|------|
| 4.1 | MCP | Settings Harness 页完善；默认空，用户自配 | 与 Hermes MCP 文档同级说明 |
| 4.2 | 工作区 Context | `{workspace}/.fnix/AGENTS.md` 或 `context.md` 注入 Work/Code | 对标 Hermes context files |
| 4.3 | Skills（可选） | 导出 KTG 经验为 skill 文件；agentskills.io 兼容只读 | 不阻塞 beta |
| 4.4 | 记忆 | `~/.fnix/memory/` 本地 JSON；Desktop Memory 面板只读本地 | 无云同步 |

### Phase 5 — 文档与增长（P2）

| # | 项 | 动作 |
|---|-----|------|
| 5.1 | Quickstart 2 分钟 | `docs/QUICKSTART.md` 首屏 GIF |
| 5.2 | 对比表 | README：Fnix vs Hermes vs OpenHarness |
| 5.3 | Discussions | 「用法问答」+ issue 模板 |

---

## 6. 架构调整（保持三进程，简化用户感知）

**用户可见**（Hermes 式）：

```text
Fnix.exe  →  一个应用窗口
```

**内部实现**（维持，不对用户暴露）：

```text
Tauri UI
  → agentd :8000（Python 大脑）
  → fnix-local :8710（索引 sidecar）
  → ~/.fnix + {workspace}/.fnix
```

**调整点**：

- Tauri **main 进程**负责 spawn/monitor agentd + fnix-local（已有 bootstrap；Release 需自启无 `pnpm`）
- 健康检查失败 → `BackendOffline` + 一键 retry（已有）
- 端口冲突 → doctor 自动检测并建议

---

## 7. UI/信息架构调整

| Hermes Desktop | Fnix 调整建议 |
|----------------|---------------|
| Chat 为主界面 | **Work / Code** 双 SegmentedControl（保留差异化） |
| Settings：Provider / Model / Tools | Settings：**AI**（provider+model+key）· **Harness**（MCP）· **隐私**（本地） |
| 无用户头像/登录 | 侧栏显示「本地」或工作区名，无 logout |
| Slash commands | Command Palette（已有）+ Composer `@file`（已有） |
| Session 列表 | Work 任务列表 + Code session 列表（已有） |

**不再出现**：手机号、Google、退出登录、PrivacyCenter 账号注销。

---

## 8. 后端 / 安全调整

| 场景 | 策略 |
|------|------|
| `FNIXAGENT_PROFILE=standalone` | `auth_required=false`；principal=anonymous（✅） |
| Desktop BYOK | `FNIX_API_ONLY=1`；LLM 请求带 client `llm` payload（✅） |
| Cloud / 企业 | 保留 `auth.py`、JWT、RBAC；**非**开源 Desktop 路径 |
| CORS | 仅 `127.0.0.1` + Tauri webview origin |
| Key 日志 | 网关审计不记录 Key / Authorization body |

---

## 9. 验收清单（对标 Hermes「2 分钟 Quickstart」）

在**干净 Windows/macOS 机器**上（或 VM）：

- [ ] 从 Release 安装，无需安装 Python/Node/Rust
- [ ] 首次打开无登录页
- [ ] 60 秒内完成：选 Qwen/OpenAI → 填 Key → 选文件夹
- [ ] Work：提交一条任务，流式有响应（需有效 Key）
- [ ] Code：@file 提及文件，Diff 预览出现
- [ ] 重启应用：Key 仍在，工作区仍在
- [ ] `pnpm doctor`（开发者路径）全绿或给出可执行 fix

---

## 10. 总结：一句话定位

> **Fnix Harness = Hermes 式本地自托管体验 + Work/Code 双工作台 + KTG/STP/MFP 自进化内核；开源路径无账号、仅 BYOK、数据在 `~/.fnix`。**

**下一步执行优先级**：Phase 0（Release）→ Phase 1（Setup v2）→ Phase 2（Doctor）→ Phase 3（CLI 同源）。

---

## 附录 A — 能力对照速查

| 能力 | Hermes | Fnix Harness |
|------|--------|--------------|
| 无登录自托管 | ✅ | ✅ |
| BYOK | ✅ | ✅ |
| Desktop GUI | ✅ Electron | ✅ Tauri |
| CLI | ✅ `hermes` | 🟡 `fnixagent` |
| 一条命令安装 | ✅ | 🟡 Release 优先 |
| Setup 向导 | ✅ `hermes setup` | 🟡 FirstRunWizard |
| Doctor | ✅ | 🟡 `pnpm doctor` |
| Memory / Skills | ✅ | 🟡 KTG 内核，UI 待补 |
| Messaging Gateway | ✅ | ❌ |
| Work 办公交付 | ❌ | ✅ |
| Code Diff Accept | ❌ | ✅ |
| 自进化 KTG/STP/MFP | ❌ | ✅ |
