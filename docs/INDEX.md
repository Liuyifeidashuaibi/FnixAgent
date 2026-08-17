# 📚 Fnix Harness — Documentation

> Welcome! This is the table of contents for the entire project. If you're new here, start with **Quick start** below.

---

## 🚀 Quick start

| Audience | Start here | Time |
|----------|------------|------|
| **End users** (just want to use the app) | [QUICKSTART.md](QUICKSTART.md) → download a [release](https://github.com/Liuyifeidashuaibi/FnixAgent/releases) | 5 min |
| **Developers** (want to build from source) | [INSTALL.md](INSTALL.md) → [DEVELOPMENT.md](../DEVELOPMENT.md) | 30 min |
| **Contributors** (want to ship code) | [CONTRIBUTING.md](../CONTRIBUTING.md) → [CODE_STYLE.md](../CODE_STYLE.md) | 1 h |
| **Security researchers** | [SECURITY.md](../SECURITY.md) | 10 min |
| **Architects / reviewers** | [ARCHITECTURE.md](../ARCHITECTURE.md) | 45 min |

---

## 📖 User guides

- [QUICKSTART.md](QUICKSTART.md) — first 5 minutes
- [INSTALL.md](INSTALL.md) — install on Windows / macOS / Linux
- [GETTING_STARTED.md](GETTING_STARTED.md) — the longer tour
- [STRUCTURE.md](STRUCTURE.md) — what's where in the monorepo
- [DEPLOY.md](DEPLOY.md) — running in production / Docker

## 🏛️ Architecture

- [ARCHITECTURE.md](../ARCHITECTURE.md) — 7-layer system architecture
- [ARCHITECTURE_LOCAL_HARNESS.md](ARCHITECTURE_LOCAL_HARNESS.md) — 3-process Tauri harness
- [TOP_TIER_AGENT_UPGRADE.md](TOP_TIER_AGENT_UPGRADE.md) — what we learned from 11 top Agent projects
- 📊 **Diagrams** (SVG, open in a new tab for full size)
  - [architecture.svg](architecture.svg) — system overview
  - [data-flow.svg](data-flow.svg) — request lifecycle
  - [self-evolution.svg](self-evolution.svg) — the KTG/STP/MFP kernel
  - [security-layers.svg](security-layers.svg) — defense in depth
  - [memory-architecture.svg](memory-architecture.svg) — three-tier memory
  - [deployment-topology.svg](deployment-topology.svg) — prod topology

## 🧠 Self-evolution

- [TOP_TIER_AGENT_UPGRADE.md](TOP_TIER_AGENT_UPGRADE.md) — research summary
- [layers/00-INDEX.md](layers/00-INDEX.md) — six-layer report
- [../agent-research-report.md](../agent-research-report.md) — 11 reference projects
- [../SELF_EVOLUTION_AGENT_PLAN.md](../SELF_EVOLUTION_AGENT_PLAN.md) — implementation plan

## 🛠️ Development

- [DEVELOPMENT.md](../DEVELOPMENT.md) — developer's guide
- [CODE_STYLE.md](../CODE_STYLE.md) — code conventions
- [BETA_RELEASE.md](BETA_RELEASE.md) — Tauri 2 packaging & release
- [RELEASE.md](../RELEASE.md) — release process

## 🛡️ Security

- [SECURITY.md](../SECURITY.md) — coordinated disclosure
- [security-layers.svg](security-layers.svg) — defense-in-depth diagram

## 📊 Reports

- [fnixagent_upgrade_plan.html](fnixagent_upgrade_plan.html) — full upgrade plan
- [paper-evaluation-report.html](paper-evaluation-report.html) — paper evaluation
- [taskboard-compare-report.html](taskboard-compare-report.html) — taskboard benchmark

## 📚 References

- [references/](references/) — papers and prior art
- [../_references/](../_references/) — cloned upstream Agent projects
- [internal/](internal/) — internal RFCs and design notes (contributors only)

## 🇨🇳 中文资源

- [QUICKSTART.md](QUICKSTART.md) — 快速上手
- [ARCHITECTURE.md](../ARCHITECTURE.md) — 架构总览
- [软著申请材料/](软著申请材料/) — 软件著作权申请材料

---

## 🆘 Need help?

- 🐛 **Found a bug?** → [Open an issue](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=bug_report.md)
- 💡 **Have an idea?** → [Start a discussion](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/ideas)
- 🛡️ **Security issue?** → [SECURITY.md](../SECURITY.md) (private)
- 💬 **Question?** → [Q&A](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/q-a)
- 📧 **Other** → `hello@fnixagent.dev`

---

_This index is curated by the docs team. If something is missing or wrong, please [open a docs issue](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=documentation.md)._
