# Fnix Harness — 产品设计（主文档）

> **原则**：**学参考、定自己的产品**。  
> Hermes / Cursor / Trae / Codex 是体验与工程参考，不是要抄成第 N 个 Hermes。  
> 本文件是 Fnix 的冻结主设计；`HERMES_ALIGNMENT.md` 仅作对照笔记。

---

## 0. 我们向谁学什么（只学模式，不抄产品）

| 参考 | 学什么 | **明确不抄** |
|------|--------|--------------|
| **Hermes** | 下载即用、无云账号、本机 home、`setup`/`doctor`、CLI↔GUI 同源配置 | 消息网关、Portal OAuth、Electron、多云 terminal backend |
| **Cursor** | Composer、`@file`、Diff Apply、侧栏会话感 | 云订阅账号体系、封闭 IDE 全家桶 |
| **Trae** | Work / Code 双模式 Living Workbench | 其云侧与账号 |
| **Codex** | CLI Agent loop、任务清晰、可脚本化 | 绑定单一厂商模型 |

**Fnix 自己的产品主张**：本地优先的 **Work + Code 双工作台**，自带 API Key，数据在 `~/.fnix`，内核是 **KTG / STP / MFP + PDG**。

---

## 1. 产品一句话

**Fnix Harness** = 打开就能用的本地 AI 工作台：  
选文件夹 → 填自己的 Key → **Work**（办公 + 轻量建站，直写产物）/ **Code**（项目工程，Preview→Accept）；无注册、无托管 LLM。

---

## 2. 目标用户与路径（Fnix 自己的）

```text
GitHub FnixAgent
      │
      ├── A 最终用户（~90%）  Releases 安装包 → 打开 → 引导 BYOK → 工作区 → Work|Code
      ├── B 开发者（~8%）    clone → pnpm setup → pnpm doctor → pnpm dev
      └── C 贡献者（~2%）    + verify:beta / check:plan / PR
```

| 绝不要求最终用户 | 原因 |
|------------------|------|
| 注册 / 手机号 / Google | 开源本机工具，不是 SaaS |
| 装 Rust / 改 `.env` | Release 内嵌运行时 |
| 理解 agentd 端口 | Tauri 自动拉起 |

---

## 3. 信息架构（Desktop 主产品）

对标 **Trae Work / Code** 与 **WorkBuddy Work**：双模式共用工作区，**不是**「Work 不能写代码」。

```text
┌──────────────────────────────────────────────────────────┐
│  Fnix  [ Work | Code ]     工作区文件夹    设置           │
├────────────┬─────────────────────────────────────────────┤
│ 任务/会话  │  Work：Ask|Plan|Craft + 任务条 + Results 栏  │
│ 列表       │  Code：Composer · Diff · Accept             │
└────────────┴─────────────────────────────────────────────┘
```

| 模式 | 对标 | 用户要完成的事 | 写盘 | 验收 |
|------|------|----------------|------|------|
| **Work** | Trae Work + WorkBuddy | 办公 + **轻量建站/脚本**；Composer 选 Ask/Plan/Craft | Craft：`write_file` **直写**；Ask/Plan 禁写盘 | Results：Artifacts / Files / Changes / Preview |
| **Code** | Trae Code / Codex | 项目内工程改动、多文件迭代、Review | **Preview → Accept** | Diff 侧栏；须 Open project |

**Work 三态（对标 WorkBuddy）：**

| 子模式 | 含义 | 行为 |
|--------|------|------|
| **Ask** | 问一问 | 只答/解释；剥离写盘工具 |
| **Plan** | 想一想 | 先出可执行计划；不写盘 |
| **Craft** | 做一做（默认） | 执行并落盘到 `.fnix/artifacts/` |

**边界（学 Trae，保留 Fnix 本地 BYOK）：**

- Work **可以**做 MBTI 站、单页 HTML、小脚本（同 Trae Work App generation / WorkBuddy Craft）
- 大仓库、修 bug、多轮工程改动 → 切 **Code**
- 两者共用 `{workspace}/.fnix`；无项目时 Work 仍可交付 artifacts

设置页只服务产品：AI（BYOK）/ Harness（MCP）/ 隐私（本地说明）/ 关于。  
**无**退出登录、账号注销。

---

## 4. 配置与数据（Fnix 约定）

```text
~/.fnix/                      # 用户级（全局）
  config.toml                 # provider / model / base_url
  secrets.json                # API Key（本机）
  SOUL.md · memories/ · skills/
  sessions/ · logs/ · mcp.json

{workspace}/.fnix/            # 项目级
  artifacts/ · skills/ · index/ · topology/ · rules.md
```

规则：

1. Desktop 设置 ↔ CLI ↔（可选）Dashboard **读写同一 `~/.fnix`**
2. Key 可进 OS Keychain；绝不默认上传
3. `FNIX_API_ONLY=1`：无服务端代付 LLM

---

## 5. 运行时架构（已冻结）

```text
Tauri 2（apps/workbench）
    → React + Tailwind + Monaco UI（:5175）
    → agentd :8000（Python：Work/Code · KTG/STP/MFP）
    → fnix-local :8710（索引/沙箱；可降级 Python）
    → ~/.fnix + {workspace}/.fnix
```

前端栈冻结：**React 19 + Tauri 2 + Tailwind 4 + Monaco**。主 UI 为 **Fnix Workbench**（自有维护；源自 PunamIDE MIT 改造，见 [STRUCTURE](./STRUCTURE.md) · [L4d](./layers/L4d-workbench.md)）。

| 组件 | 职责 | 非目标 |
|------|------|--------|
| Tauri + React + Tailwind | UI（`apps/workbench`）+ spawn 后端 | 不做 Electron / Vue / Mantine 主路径 |
| agentd | 业务与 Agent | 不做公网多租户默认 |
| fnix-local | 性能路径 | 可不装 Rust（降级） |
| CLI | setup/doctor/chat/serve | 不是主 UI |
| Dashboard :9119 | 可选本机管理 | 不是第二套产品 |

`standalone`：网关对本机匿名放行。`cloud`：保留 JWT（企业部署，非开源主路径）。

---

## 6. CLI 面（服务开发者与自动化，不是产品中心）

| 命令 | 用途 |
|------|------|
| `fnixagent setup` | 写 `~/.fnix` BYOK |
| `fnixagent doctor` | 环境诊断 |
| `fnixagent serve` | 启 agentd |
| `fnixagent chat` / `run` | 无 UI 对话 |
| `fnixagent dashboard` | 可选本机管理页 |
| `fnixagent model` | 查看/切换模型 |

主路径永远是：**Desktop 打开即用**。CLI 是增强，不是门槛。

---

## 7. 差异化（必须做厚，别做成「又一个 Chat」）

| 能力 | 产品表现 | 参考灵感 |
|------|----------|----------|
| Work 流水线 | 任务 → 流式进度 → 可打开产物 | Trae Work |
| Code Diff Accept | 改前预览，用户确认才写盘 | Cursor / Codex |
| `@file` / 工作区 | 提及文件进上下文 | Cursor |
| KTG / STP / MFP | 拓扑检索、技能管道、多帧规划 | **Fnix 独有** |
| PDG 索引 | fnix-local 加速 Code | FnixAi 姊妹能力 |
| 零账号 BYOK | 开源友好、可审计 | Hermes 模式 |

---

## 8. 明确不做（避免做成 Hermes 克隆）

- 手机号 / Google / 云账号
- Telegram / Discord / WhatsApp Gateway
- Nous Portal 一类「一订阅包打天下」
- 默认遥测、强制联网账号
- Electron 回归
- 以 Web Dashboard 替代 Desktop 主产品

---

## 9. 六层架构（做厚顺序，已冻结）

自下而上实现；每层完成后写报告到 [`docs/layers/`](./layers/00-INDEX.md)。

```text
L1 需求架构 → L2 底层引擎 → L3 编辑器内核
           → L4 AI Harness → L5 上层产品 → L6 商业化打包
```

| 层 | 职责 | 验收要点 |
|----|------|----------|
| **L1** | 产品契约、边界、OSS/企业双轨定义 | 本文 + layers 索引一致 |
| **L2** | KTG/STP/MFP、fnix-local/PDG、LLM BYOK | 健康可观测、可降级、可测 |
| **L3** | Monaco、`@file`、Diff Accept/Reject | 可控写盘 |
| **L4** | 会话/工具/skills/memory/CLI/AG-UI | smoke + doctor 绿 |
| **L5** | Tauri Work/Code、引导、设置、无登录 | §10 六条场景 |
| **L6** | Community 安装包 + Enterprise 部署边界 | Release + COMMERCIAL |

硬约束（全层适用）：**无强制账号** · **BYOK / API-only** · **Tauri-only（主路径）** · **数据在 `~/.fnix`**。

开源 / 商业边界见 [`docs/layers/COMMERCIAL.md`](./layers/COMMERCIAL.md)。

---

## 10. 实施计划（按 Fnix 优先级，不是按 Hermes 清单）

### P0 — 能像「正经桌面产品」用起来

1. 无登录启动 → FirstRunWizard（Key + 文件夹 + Work/Code）
2. BYOK 强制 + Key 进 `~/.fnix` / Keychain
3. Work 流式任务可跑通（有效 Key）
4. Code Diff Accept + `@file`
5. `pnpm setup` / `doctor` / `dev`；Windows MSVC 文档
6. Release CI 可打安装包（首 tag）

### P1 — 打磨「比聊天壳更强」

1. Settings AI 与 harness 配置同源、可测连接
2. `fnixagent setup|doctor|chat` 稳定（Windows 控制台编码 OK）
3. SOUL / memories 注入 Work/Code 上下文
4. ApiKeyBanner、无 Key 不可提交
5. `pnpm smoke:hermes`（名字保留作回归脚本，验的是 **Fnix 路径**）

### P2 — 增长与分发

1. `v1.0.0-beta.1` Release + README Demo
2. 可选 Dashboard（不抢 Desktop 主路径）
3. Skills / MCP 体验文档化

---

## 11. 验收标准（Fnix 自己的）

| # | 场景 | 通过条件 |
|---|------|----------|
| 1 | 打开 Desktop | 无登录页；后端健康或可 Retry |
| 2 | 首次引导 | 填 Key → 选夹 → 进 Work 或 Code |
| 3 | Work | 一条任务有流式响应或明确 Key 错误 |
| 4 | Code | `@file` + Diff 可 Accept |
| 5 | 重启 | Key 与工作区仍在 |
| 6 | CLI | `setup` 后 `doctor` 不崩；`chat` 能读 `~/.fnix` |

---

## 12. 文档索引

| 文档 | 角色 |
|------|------|
| **本文件** | 产品主设计（冻结） |
| [layers/00-INDEX.md](./layers/00-INDEX.md) | 六层实施报告总索引 |
| [layers/COMMERCIAL.md](./layers/COMMERCIAL.md) | 开源 / 企业双轨边界 |
| [OPEN_SOURCE_DESIGN.md](./OPEN_SOURCE_DESIGN.md) | 三类用户路径 / 安装 |
| [HERMES_ALIGNMENT.md](./HERMES_ALIGNMENT.md) | 参考对照（非需求清单） |
| [GETTING_STARTED.md](./GETTING_STARTED.md) | 2 分钟上手 |
| `_references/hermes-agent/` | 只读学习材料 |
