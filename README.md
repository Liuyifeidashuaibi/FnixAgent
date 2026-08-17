<div align="center">

<!-- Logo / Hero -->

<p align="center">
  <img src="assets/brand/logo.svg" alt="FnixAgent Logo" width="140" />
</p>

# FnixAgent

[![All Rights Reserved](https://img.shields.io/badge/license-All%20Rights%20Reserved-red)](LICENSE)
[![CI](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/ci.yml)
[![Releases](https://img.shields.io/github/v/release/Liuyifeidashuaibi/FnixAgent?include_prereleases&label=release)](https://github.com/Liuyifeidashuaibi/FnixAgent/releases)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Built with Tauri](https://img.shields.io/badge/built%20with-Tauri%202-4FB8FF)](https://tauri.app)

### Local-first AI workspace — Work & Code on your machine, BYOK only.

**🔒 All Rights Reserved — see [LICENSE](LICENSE)**
**🚫 不接受外部代码贡献 / No external code contributions accepted**
**Built with** Tauri 2 · Python 3.11+ · React 18 · FastAPI · LangGraph

[Get started](#-quick-start) · [Documentation](docs/INDEX.md) · [Releases](https://github.com/Liuyifeidashuaibi/FnixAgent/releases) · [Roadmap](docs/ROADMAP.md) · [Discussions](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions)

---

<!-- One-line value prop: tell me what this is, in 12 words or less. -->

A **drop-in, no-account, BYOK-only** AI workspace for the desktop. Work on documents,
Code on projects, and a self-evolving kernel that gets smarter the more you use it.

</div>

---

## Table of contents

- [Why FnixAgent?](#-why-fnixagent)
- [Features](#-features)
- [Quick start](#-quick-start)
- [Architecture](#-architecture)
- [Tech stack](#-tech-stack)
- [Project status](#-project-status)
- [Documentation](#-documentation)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [Community](#-community)
- [Security](#-security)
- [Maintainers](#-maintainers)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)

---

## ❓ Why FnixAgent?

Most AI tools force you to choose between **convenience** (cloud SaaS, your data leaves your machine, vendor lock-in) and **control** (BYO model, BYO keys, but you wire up a dozen scripts). FnixAgent is the missing middle:

| Concern                  | Cloud SaaS     | DIY scripts   | **FnixAgent**                       |
| ------------------------ | -------------- | ------------- | ----------------------------------- |
| Account / sign-up        | Required       | None          | **None**                            |
| Where your data lives    | Their cloud    | Your disk     | **Your disk**                       |
| Who pays for the LLM     | They (markup)  | You (BYOK)    | **You (BYOK, no markup)**           |
| How smart it gets        | Static prompt  | Static prompt | **Self-evolving (KTG / STP / MFP)** |
| Work + Code in one place | Separate tools | Glue scripts  | **First-class**                     |
| Sandboxed execution      | Trust them     | Roll your own | **Built-in**                        |

> 🔑 **BYOK = Bring Your Own Key.** We never see your API key. It lives in your OS keychain.

---

## ✨ Features

### 🪟 Work mode — office work that actually finishes

- Streamed, **multi-step task execution** that produces real artifacts (`docx`, `xlsx`, `pdf`, …).
- **`@file` references** — point the agent at specific files and it reads them deterministically.
- **Tool-calling** with structured outputs and validation.
- **Templates & skills** — community-shareable, versioned, signed.

### 🧑‍💻 Code mode — agent ↔ human review loop

- **Plan / execute / review** cycles.
- **Diff preview** with per-hunk **Accept / Reject** before anything hits disk.
- **AG-UI** — Server-Sent Events stream (`/api/v1/ag-ui/work/stream`) you can hook up to any frontend.
- **Multi-file plans** that survive a 24-hour coffee break.

### 🧠 Self-evolving kernel

- **KTG** (Knowledge-Task Graph) — turns your sessions into a queryable graph.
- **STP** (Skill-Task Pipeline) — every successful task becomes a reusable skill.
- **MFP** (Memory Formation Protocol) — long-term, source-of-truth Markdown memory you can `git diff`.
- **SkillEvaluator** (9 dimensions) + **SkillEvolver** (ratcheted) — quality only goes up.
- **HumanInTheLoop** — three-layer confirmation gate for high-risk operations.

### 🛡️ Security & privacy

- **Local-first**: data and sessions stay in `~/.fnix/` and `{workspace}/.fnix/`.
- **No telemetry**, no analytics, no tracking pixels.
- **Sandboxed shell**, **JWT auth**, **injection guards** at the API boundary.
- See [SECURITY.md](SECURITY.md) for our coordinated disclosure process.

### 📦 Distribution

- **Windows** — NSIS installer, portable ZIP.
- **macOS** — DMG (notarized for Gatekeeper).
- **Linux** — `.deb`, AppImage, and `.rpm` (planned).
- **Auto-updates** via Tauri's built-in updater.

---

## 🚀 Quick start

### Option 1 — download a release (recommended for users)

1. Grab the latest installer for your platform from the [Releases page](https://github.com/Liuyifeidashuaibi/FnixAgent/releases).
2. Install.
3. Open the app. On first launch, paste your LLM provider API key — it's stored in your **OS keychain**, never on our servers.
4. Pick a folder → choose **Work** (office tasks) or **Code** (project work) → start.

### Option 2 — build from source (for developers)

Prerequisites:

- **Node.js** ≥ 18.12 (we test on 20 LTS)
- **pnpm** ≥ 9.15 (`corepack enable && corepack prepare pnpm@9.15.9 --activate`)
- **Python** ≥ 3.11 (we test on 3.11 / 3.12 / 3.13)
- **Rust** (stable) — only required for Tauri builds
- **Platform extras**:
  - Windows: _Visual Studio Build Tools 2022_ with the C++ workload
  - macOS: Xcode Command Line Tools
  - Linux: `libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev`, `patchelf`

Then:

```bash
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent

pnpm setup          # install JS + Python deps, set up pre-commit hooks
pnpm doctor         # verify the environment

pnpm dev            # start the Tauri desktop (no login, no sign-up)
# or
pnpm dev:api        # start just the agentd :8003 + fnix-local :8710
```

CLI one-liners (after `pnpm setup`):

```bash
fnixagent setup         # configure API key + model → ~/.fnix/
fnixagent doctor        # diagnose the environment
fnixagent dashboard     # open the web admin at http://127.0.0.1:9119
fnixagent chat          # terminal chat with the agent
```

### First task

```bash
fnixagent chat "summarize README.md into 5 bullet points"
```

Or open the desktop, hit ⌘N / Ctrl-N, and type the same thing. The agent will plan, call tools, show diffs, and write the result.

---

## 🏗️ Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                    Tauri 2 Desktop (apps/workbench)                     │
│                       React 18 + Tailwind + TS 5.6                      │
└───────────────┬────────────────────────────────────┬───────────────────┘
                │ HTTP/JSON                          │ PTY (portable-pty)
                │ :8003                              │ local shell
┌───────────────▼────────────────────────────────────▼───────────────────┐
│  fnix-agentd (Python, src/fnixagent)               port 8003            │
│  • FastAPI + JWT    • LangGraph orchestrator   • Work/Code router       │
│  • KTG / STP / MFP  • Skill registry           • AG-UI SSE             │
└───────────────┬────────────────────────────────────┬───────────────────┘
                │ UNIX/TCP                           │ local
                │ sandbox                            │ index
┌───────────────▼────────────────────────────────────▼───────────────────┐
│  fnix-local (Rust, apps/fnix-local)                port 8710            │
│  • PDG indexer       • Sandbox command runner   • Workspace scanner     │
└────────────────────────────────────────────────────────────────────────┘
                ↘                          ↙
            ~/.fnix/               {workspace}/.fnix/
            (sessions,             (per-project
             skills,                memory, plans,
             keys)                  scratch)
```

For a deeper dive — including the **self-evolution flywheel**, **security layers**, and **deployment topology** — see [`docs/STRUCTURE.md`](docs/STRUCTURE.md) and the architecture SVGs in [`docs/`](docs/).

---

## 🧰 Tech stack

| Layer         | Choice                                 | Why                                                                   |
| ------------- | -------------------------------------- | --------------------------------------------------------------------- |
| Desktop shell | **Tauri 2**                            | Small binary, native webview, first-class IPC.                        |
| UI            | **React 18 + Tailwind + Radix**        | Composable, accessible, no global runtime.                            |
| Agent runtime | **Python 3.11+ / FastAPI**             | Best LLM ecosystem, async-native.                                     |
| Orchestration | **LangGraph + custom**                 | DAGs are easier to debug than opaque chains.                          |
| LLM           | **OpenAI-compatible**                  | Works with OpenAI / Anthropic / Qwen / GLM / DeepSeek / 本地推理引擎. |
| Local sidecar | **Rust**                               | Predictable latency, no GIL, small binary.                            |
| Storage       | **SQLite (local) + Markdown (memory)** | Source-of-truth, version-controllable.                                |
| CI/CD         | **GitHub Actions**                     | Pinned actions, matrix builds, signed releases.                       |
| Test          | **pytest + vitest + Playwright**       | Unit + E2E in one box.                                                |
| Lint / format | **ruff + pyright + ESLint + Prettier** | Fast, opinionated, zero-config.                                       |

---

## 📈 Project status

| Component                                             | Status         | Version      | Notes                                                      |
| ----------------------------------------------------- | -------------- | ------------ | ---------------------------------------------------------- |
| Three-process harness (Desktop / agentd / fnix-local) | ✅ Stable      | 1.0.0-beta.1 | Tauri 2, BYOK-only                                         |
| Work mode (artifact generation)                       | ✅ Beta        | 1.0.0-beta.1 | DOCX/XLSX/PDF                                              |
| Code mode (diff review)                               | ✅ Beta        | 1.0.0-beta.1 | Multi-file plans                                           |
| Self-evolution kernel (KTG/STP/MFP)                   | ✅ Beta        | 1.0.0-beta.1 | Markdown source-of-truth                                   |
| fnix-local Rust port                                  | 🚧 In progress | —            | See [Roadmap](docs/ROADMAP.md#-next-planned--this-quarter) |
| Skills marketplace                                    | 🚧 Planned     | —            | —                                                          |
| Plugin SDK GA                                         | 🚧 Planned     | —            | —                                                          |

We follow [semver](https://semver.org/). The [CHANGELOG](CHANGELOG.md) is the source of truth.

---

## 📚 Documentation

- 📖 [docs/INDEX.md](docs/INDEX.md) — the table of contents
- 🚀 [docs/QUICKSTART.md](docs/QUICKSTART.md) — get going in 5 minutes
- 🏛️ [docs/STRUCTURE.md](docs/STRUCTURE.md) — system architecture
- 🛠️ [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — developer's guide
- 🚢 [.github/RELEASE.md](.github/RELEASE.md) — how to cut a release
- 🤝 [CONTRIBUTING.md](CONTRIBUTING.md) — how to contribute
- 🛡️ [SECURITY.md](SECURITY.md) — how to report a vulnerability
- 🗺️ [docs/ROADMAP.md](docs/ROADMAP.md) — what we're building next

---

## 🗺️ Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the long view. Short version:

- **Now:** v1.0.0 GA · Tauri 2 desktop · Work/Code modes · KTG/STP/MFP kernel · Standalone installer
- **Next:** fnix-local Rust port · Skills marketplace · MCP registry UI · i18n
- **Later:** Multi-agent coordination · Mobile companion · Local RAG · Voice I/O

Vote on priorities in [Discussions → Polls](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/polls).

---

## 🤝 Contributing

**本项目目前不接受外部代码贡献。**(详见 [LICENSE](LICENSE))

- ❌ **不接受** Pull Request / 代码合并
- ✅ 欢迎**报告 Bug**(GitHub Issue)
- ✅ 欢迎**讨论设计**(GitHub Discussion)
- ✅ 欢迎**提文档改进建议**

如果你想学习本项目的设计,请**基于自己的理解**写自己的代码,
不要直接复制本项目代码,也不要创建实质相似的 fork。

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

**This project does NOT accept external code contributions at this time.** See [LICENSE](LICENSE).

- ❌ Pull Requests / code merging not accepted
- ✅ Bug reports and design discussions are welcome
- ❌ Do not copy or create substantially similar forks

---

## 💬 Community

| Channel                                                                          | Best for                            |
| -------------------------------------------------------------------------------- | ----------------------------------- |
| [GitHub Discussions](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions) | Q&A, ideas, show-and-tell           |
| [GitHub Issues](https://github.com/Liuyifeidashuaibi/FnixAgent/issues)           | Bug reports, feature requests, RFCs |
| 💬 WeChat `15515797178`                                                          | 直接联系作者 / Direct contact       |
| ✉️ Email `liuyifeidashuaibi@gmail.com`                                           | Anything else                       |

---

## 🛡️ Security

Found a vulnerability? **Please do not open a public issue.** See [SECURITY.md](SECURITY.md) for the private disclosure process and our response-time commitments.

---

## 👥 Maintainers

See [.github/MAINTAINERS.md](.github/MAINTAINERS.md) and [.github/GOVERNANCE.md](.github/GOVERNANCE.md).

---

## ✨ Contributors

> 本项目所有代码、文档、设计均由 Liu Yifei ([liuyifeidashuaibi](https://github.com/Liuyifeidashuaibi)) 独立完成。
> 由于 [LICENSE](LICENSE) 限制,不接受外部代码贡献,故不设 Contributors 名单。
>
> 第三方组件致谢见 [NOTICE](NOTICE)。

---

## 📜 License

本项目整体以 **All Rights Reserved** 方式发布(详见 [LICENSE](LICENSE))。

- ❌ 禁止复制、修改、商用、Fork、衍生创作
- ✅ 仅允许在 GitHub / 网页浏览器中**阅读浏览**单个文件
- ⚠️ 第三方组件各自按其原始许可证约束(详见 [NOTICE](NOTICE))
- 💼 商用请联系 [docs/LICENSE-COMMERCIAL.md](docs/LICENSE-COMMERCIAL.md)

This repository is **All Rights Reserved**. See [LICENSE](LICENSE).

- ❌ No copying, modification, commercial use, forking, or derivative works
- ✅ Read-only viewing on GitHub / web browser is permitted
- ⚠️ Third-party components retain their original licenses (see [NOTICE](NOTICE))
- 💼 Commercial licensing: see [docs/LICENSE-COMMERCIAL.md](docs/LICENSE-COMMERCIAL.md)

---

## 🌟 Acknowledgments

FnixAgent stands on the shoulders of giants. Key inspirations and dependencies:

- 🦀 [Tauri](https://tauri.app/) — desktop shell
- ⚡ [FastAPI](https://fastapi.tiangolo.com/) — agentd API
- 🧠 [LangGraph](https://langchain-ai.github.io/langgraph/) — orchestration
- 🤖 [OpenAI Python SDK](https://github.com/openai/openai-python) — LLM client
- 🗂️ [SQLite](https://www.sqlite.org/) — local storage
- 🛠️ [ruff](https://github.com/astral-sh/ruff), [pyright](https://github.com/microsoft/pyright), [Playwright](https://playwright.dev/) — dev tooling

And the open-source community — thank you for the inspiration and tools that make projects like this possible.

---

<div align="center">

**[⭐ Star this repo](https://github.com/Liuyifeidashuaibi/FnixAgent) · [📣 Discuss](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions)**

<sub>Maintained by Liu Yifei · 💬 WeChat 15515797178 · ✉️ liuyifeidashuaibi@gmail.com</sub>

</div>
