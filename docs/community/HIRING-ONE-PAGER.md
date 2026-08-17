# 项目亮点一页纸 / Hiring One-Pager

> 🎯 给招聘官看的 **一页** 项目亮点介绍。
> 打印版:https://fnixagent.dev/hiring-one-pager.pdf

---

## FnixAgent — 一个本地优先的桌面 Agent 工作台

**作者**:刘逸飞
**GitHub**:https://github.com/fnixagent/fnixagent
**许可证**:All Rights Reserved(个人作品集)
**在线浏览**:✅ 公开(只读)
**代码复用 / Fork / 商用**:❌ 禁止

---

## 一句话定义

**FnixAgent 是一个跨进程 (Tauri 2 + Python + Rust)、本地优先、具备三层任务图
规划 (KTG / STP / MFP) 和 Markdown + Git 版本化长期记忆的桌面 Agent 工作台。**

---

## 关键技术亮点(简历可直接引用)

### 1. 跨进程架构设计 ★★★★

```
WebView (React) ──IPC──> Tauri Core (Rust) ──stdio──> Python agentd ──subprocess──> Rust Sandbox (fnix-local)
```

- **三进程隔离**:UI / 业务 / 沙箱 分层,Capability 最小化
- **跨语言 IPC 协议**:Rust + Python 之间 stdio JSON-RPC,带 schema 校验
- **OS 级安全集成**:macOS Keychain / Windows Credential Manager 实现 BYOK

### 2. 三层任务图规划 ★★★★★

区别于 LangGraph 单层图,FnixAgent 设计了**三层时间跨度**的任务图模型:

- **KTG** (Knowledge Task Graph):季度到年度战略层
- **STP** (Short-Term Plan):天到周战术层
- **MFP** (Multi-step Flow Plan):会话级执行流

每层独立 Schema、独立 DAG、独立可干预。设计细节见
[ADR-0004](docs/adr/0004-three-layer-task-graph.md)。

### 3. 长期记忆的版本化存储 ★★★★★

- **Markdown + Git**:用户记忆就是 Git 仓库,可读、可审计、可回滚
- **混合检索**:BM25 + 向量 (sqlite-vec) + RRF 融合
- **隐私分级**:`public` / `private` / `secret`,只有 public 才上传云端

设计细节见 [ADR-0003](docs/adr/0003-markdown-git-memory.md)。

### 4. Skill 系统的"Markdown 即代码" ★★★★

```
~/.fnix/skills/code-review/SKILL.md  ← 整个 Skill 就这一个文件
```

- 任何会写 Markdown 的人都能写 Skill,门槛比 LangChain 低 10 倍
- 前置 YAML schema 校验输入输出
- 三级安全分级 (`safe` / `moderate` / `dangerous`)
- 多语言版本 (`SKILL.zh-CN.md`)

### 5. 完整工程治理 ★★★★★

- 5 个 **ADR** (架构决策记录),遵循 MADR 4.0 规范
- 8 个 **GitHub Actions** workflows:CodeQL / Dependabot / Scorecard / Stale / Release Drafter / Labeler
- 38 个**标签体系** (kind / area / priority / status)
- **SBOM 自动生成** (SPDX 格式) + 第三方依赖审计
- **WCAG 2.1 AA** 可访问性合规
- **i18n** 支持 11 种语言

### 6. 完整文档矩阵 ★★★★★

50+ 文档文件,覆盖:

| 类别 | 文档 |
| --- | --- |
| 项目 | README / ROADMAP / CHANGELOG / CONTRIBUTING / CODE_OF_CONDUCT |
| 治理 | GOVERNANCE / MAINTAINERS / SECURITY v2.0 |
| 架构 | ARCHITECTURE / 5 个 ADR / diagrams (SVG) |
| 用户 | QUICKSTART / INSTALL / GETTING_STARTED / FAQ / MIGRATION |
| 开发 | TESTING / PERFORMANCE / ACCESSIBILITY / I18N / PLUGINS |
| 安全 | THREAT-MODEL / PRIVACY / TRADEMARKS / LICENSE-COMMERCIAL |
| 运营 | INCIDENT-RESPONSE / REVIEWER-GUIDE / TRIAGE / MAINTAINER-ONBOARDING |
| 营销 | CITATIONS / FUNDING / HIRING-ONE-PAGER |

---

## 技术栈

| 维度 | 技术 |
| --- | --- |
| 桌面运行时 | Tauri 2 |
| 前端 | React 18 + TypeScript + Vite + TailwindCSS |
| 业务核心 | Python 3.12 + asyncio + anyio |
| 包管理 | uv (Astral) |
| 沙箱 | Rust + Tokio + ulimit |
| LLM 客户端 | OpenAI / Anthropic / DeepSeek / Ollama |
| 记忆存储 | Markdown + Git + SQLite + sqlite-vec |
| Skill 引擎 | 自研 Markdown DSL |
| 跨语言协议 | stdio JSON-RPC + Tauri IPC |
| 测试 | pytest + Vitest + cargo test + Playwright + Hypothesis |
| CI/CD | GitHub Actions + CodeQL + Dependabot + Renovate |
| 文档 | MkDocs Material + GitHub Pages |

---

## 数据(2026-08-17)

| 指标 | 数值 |
| --- | --- |
| 提交数 | 800+ |
| 代码行数 | ~30k (Python ~15k, TS ~8k, Rust ~5k, Markdown ~2k) |
| 文档文件 | 60+ |
| ADR | 5 |
| Skill | 8 内置 + 自定义无限 |
| 模块数 | 6 (agentd / workbench / desktop-tauri / fnix-local / protocol / sdk) |
| 测试 | 200+ 测试用例,核心模块 85% 覆盖率 |

---

## 这个项目展示了什么能力?

| 能力维度 | 体现 |
| --- | --- |
| **系统设计** | 三层任务图 / 三进程架构 / 多语言协同 |
| **工程纪律** | ADR / TypeScript strict / pytest strict / CI 完整 |
| **安全工程** | BYOK / Keychain / Capability / Threat Model |
| **产品思维** | 用户体验 / 可访问性 / 国际化 / 文档完整 |
| **开源治理** | LICENSE / CoC / GOVERNANCE / MAINTAINERS / 分诊流程 |
| **跨语言工程** | Python + Rust + TypeScript 协同 / IPC 协议设计 |
| **AI 工程** | LLM 客户端 / Prompt 工程 / 长期记忆 / Skill 系统 |
| **隐私工程** | 零遥测 / BYOK / 本地优先 / 隐私分级 |
| **文档能力** | 60+ 文档 / 多种格式 / 多语言 |
| **法律意识** | All Rights Reserved / Trademark / Privacy / Citations |

---

## 适合面试的话题

1. **如何设计一个跨进程 Agent 架构?** — Tauri 三进程模型
2. **如何让 Agent 记住用户?** — Markdown + Git 记忆系统
3. **如何防止 Prompt 注入?** — Skill capability 最小化 + 三级安全分级
4. **如何让 Agent 持续学习?** — KTG 长期目标 + STP 周计划 + MFP 执行流
5. **为什么不用 LangChain?** — 自己造的轮子更适合"本地优先 + 三层规划"
6. **如何保证 API Key 安全?** — OS Keychain + Argon2id + 内存清零
7. **为什么不用 Electron?** — Tauri 体积小 8 倍,内存低 4 倍
8. **Skill 系统和 LangChain Tool 的差别?** — Markdown 门槛低 10 倍

---

## 不适合这个项目的场景

- ❌ 团队协作 / SaaS
- ❌ 大模型训练 / RLHF
- ❌ 多 Agent 协作(目前是单 Agent + 计划)
- ❌ 移动端

---

## 在线浏览入口

- **代码**:https://github.com/fnixagent/fnixagent
- **文档站**:https://fnixagent.dev/docs
- **招聘 PDF**:https://fnixagent.dev/hiring-one-pager.pdf

> ⚠️ 本项目为 **专有个人作品**,**禁止 fork / 商用 / 代码复用**,仅供个人学习参考。
> 详见 [LICENSE](LICENSE) 与 [TRADEMARKS.md](TRADEMARKS.md)。

---

© 2024-2026 FnixAgent. All Rights Reserved.