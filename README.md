

---

# Fnix Harness



**Local-first AI workspace — Work & Code on your machine, BYOK only**

[![CI](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Liuyifeidashuaibi/FnixAgent?include_prereleases&label=Release)](https://github.com/Liuyifeidashuaibi/FnixAgent/releases)
[![License](https://img.shields.io/github/license/Liuyifeidashuaibi/FnixAgent?label=License)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Tauri](https://img.shields.io/badge/Tauri-2-orange?logo=tauri&logoColor=white)](https://v2.tauri.app/)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

[English](#download) · [安装](#安装) · [文档](#文档) · [架构](#架构总览)



Fnix Harness 是一个**可下载、打开即用**的本地 AI 工作台（灵感来自 Cursor / Trae / Codex / Hermes，产品设计属于 Fnix）：

- **无账号** — 打开即用，无注册 / 手机号 / Google
- **BYOK** — API Key 留本机 `~/.fnix`（Desktop / CLI 同源）
- **Work** — 办公任务交付（文档、表格、规划）
- **Code** — Diff 预览 → Accept 写盘（`@file`）
- **自进化内核** — KTG / STP / MFP + 本地 PDG 索引

**主设计** → [docs/FNIX_PRODUCT.md](docs/FNIX_PRODUCT.md)  
**六层报告** → [docs/layers/00-INDEX.md](docs/layers/00-INDEX.md)  
**开源 / 企业双轨** → [docs/layers/COMMERCIAL.md](docs/layers/COMMERCIAL.md)

| 轨道 | 给谁 | 怎么用 |
|------|------|--------|
| **Community** | 个人 / 开源 | Releases 安装包或 `pnpm dev` · standalone · BYOK · 无账号 |
| **Enterprise** | 团队私有部署 | `FNIXAGENT_PROFILE=cloud` · [DEPLOY.md](docs/DEPLOY.md) |

---



## Download


| 平台                          | 获取方式                                                                             |
| --------------------------- | -------------------------------------------------------------------------------- |
| **Windows / macOS / Linux** | [GitHub Releases](https://github.com/Liuyifeidashuaibi/FnixAgent/releases) 下载安装包 |
| **从源码**                     | 见下方 [5 分钟快速开始](#5-分钟快速开始)                                                        |


安装后：**打开应用 → 首次引导填 API Key** → 打开本地文件夹 → **Work**（办公/轻量建站，直写产物）或 **Code**（项目工程，Preview→Accept）。

> 开源 Desktop **无需注册或登录**（对标 Hermes 自托管体验）。

> 姊妹项目 [FnixAi](https://github.com/Liuyifeidashuaibi/FnixAi)：全 Rust AgentOS（独立仓库）。

---



## 5 分钟快速开始

**最终用户（推荐）** → [GitHub Releases](https://github.com/Liuyifeidashuaibi/FnixAgent/releases) 下载安装包，无需编译。

**开发者（从源码）**

```bash
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git && cd FnixAgent
pnpm setup          # 安装依赖
pnpm doctor         # 检查环境（Windows 需 VS Build Tools 才能编译 Tauri）
pnpm dev            # 启动 Desktop（无登录）
```

**CLI（对标 Hermes）**

```bash
fnixagent setup          # 配置 API Key / 模型 → ~/.fnix
fnixagent doctor         # 诊断
fnixagent dashboard      # Web 管理台 http://127.0.0.1:9119
fnixagent chat           # 终端对话
pnpm smoke:hermes        # 冒烟验证
```

完整设计见 **[docs/FNIX_PRODUCT.md](docs/FNIX_PRODUCT.md)** · **[docs/OPEN_SOURCE_DESIGN.md](docs/OPEN_SOURCE_DESIGN.md)**

### 磁盘清理（C 盘被缓存占满时）

```bash
pnpm clean:cache              # 清理 Cursor sandbox / 项目构建缓存
pnpm clean:cache:aggressive   # 含 npm / pip / cargo + 旧 temp
```

---



## 文档


| 文档                                                                  | 说明                 |
| ------------------------------------------------------------------- | ------------------ |
| [OPEN_SOURCE_DESIGN.md](docs/OPEN_SOURCE_DESIGN.md) | **开源用户使用方案（推荐阅读）** |
| [QUICKSTART.md](docs/QUICKSTART.md)                                 | 快速上手               |
| [ARCHITECTURE_LOCAL_HARNESS.md](docs/ARCHITECTURE_LOCAL_HARNESS.md) | 三进程 Harness 架构     |
| [BETA_RELEASE.md](docs/BETA_RELEASE.md)                             | 打包与 GitHub Release |
| [CONTRIBUTING.md](CONTRIBUTING.md)                                  | 贡献指南               |
| [SECURITY.md](SECURITY.md)                                          | 安全报告               |


---



## 项目简介（技术）

FnixAgent 是一个面向 **学习 / 教育 / 办公 / 本地编程** 的智能 Agent 平台，构建于 **7 层架构 + 自进化内核** 之上。Desktop 产品形态为 **Fnix Harness**（Tauri 2 + Python agentd + fnix-local sidecar）。

### 为什么选择 Fnix Harness？


| 对比维度 | 传统 LLM Agent | Fnix Harness                           |
| ---- | ------------ | -------------------------------------- |
| 部署   | 云端 SaaS      | **本地优先**，Standalone 零 Docker           |
| LLM  | 平台代付         | **BYOK**，Key 在本机                       |
| 模式   | 单一聊天         | **Work + Code** 共用工作区                  |
| 持久化  | 会话丢失         | `~/.fnix/sessions` + workspace `.fnix` |
| 进化   | 静态 Prompt    | **KTG / STP / MFP** 自进化内核              |


---



## 架构总览

```text
Desktop (Tauri 2)  →  agentd :8003  →  fnix-local :8710
        ↘ ~/.fnix + {workspace}/.fnix
```


| 进程            | 端口   | 职责                       |
| ------------- | ---- | ------------------------ |
| Tauri Desktop | —    | Work/Code UI、PTY、BYOK 设置 |
| fnix-agentd   | 8003 | KTG/STP/MFP、Work/Code 大脑 |
| fnix-local    | 8710 | 索引、PDG、沙箱命令              |


详见 [docs/ARCHITECTURE_LOCAL_HARNESS.md](docs/ARCHITECTURE_LOCAL_HARNESS.md) · [docs/architecture.svg](docs/architecture.svg)

---



## 核心能力

- **Work 模式** — 办公任务流式执行，产出 docx/xlsx/pdf 等 artifact
- **Code 模式** — Agent 规划/执行/审查，`@file` 引用，Diff Accept 写盘
- **Harness** — session 持久化、MCP 配置、工作区 `.fnix` 布局
- **安全** — JWT 鉴权、注入防护、沙箱执行、审计链路
- **AG-UI** — `/api/v1/ag-ui/work/stream` SSE 事件流

---



## 开发

```bash
pnpm verify:beta       # pytest + typecheck + 计划验收
pnpm check:plan        # Mega Plan 检查
pnpm e2e:full          # Harness API E2E
pnpm build             # Workbench 生产构建
pnpm build:packaging   # 安装包（走 workbench Tauri build）
```

Monorepo 结构（详见 [docs/STRUCTURE.md](docs/STRUCTURE.md)）：

```text
apps/workbench/       # 唯一日常桌面 UI + Tauri（pnpm dev / build）
apps/desktop-tauri/   # 仅遗留打包壳；勿与 workbench 同时开（会双窗口）
apps/fnix-local/      # 本地 sidecar
src/fnixagent/        # Python agentd
packages/protocol/    # 契约
packages/sdk/         # TS OpenAPI 客户端（可选）
```

---



## 路线图

- [x] Tauri Desktop + Standalone 三进程
- [x] BYOK API-only 产品策略
- [x] GitHub Release CI（Windows / macOS / Linux）
- [ ] 预编译 Release 安装包（tag `v1.0.0-beta.1`）
- [ ] FnixAi 高性能 fnix-local 二进制（PDG 索引）

---



## 社区与贡献

- [CONTRIBUTING.md](CONTRIBUTING.md) — 开发环境与 PR 流程
- [SECURITY.md](SECURITY.md) — 漏洞报告
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — 行为准则
- [Issues](https://github.com/Liuyifeidashuaibi/FnixAgent/issues) · [Discussions](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions)



## License

[Apache License 2.0](LICENSE)