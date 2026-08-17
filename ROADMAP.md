# 🗺️ Roadmap

This is the public roadmap for **Fnix Harness**. It is a **living document** — we update it as priorities shift. Timelines are best-effort and not commitments.

> 🧭 **Navigation:** [Now](#-now) · [Next](#-next) · [Later](#-later) · [Maybe](#-maybe) · [Done](#-done)

---

## 🎯 Mission

Make every developer and knowledge worker 10× more productive on their own machine — without giving up control of their data, their model, or their workflow.

---

## 🚧 Now (in progress — current sprint)

These are the items the core team is actively working on.

- [ ] **v1.0.0 GA** — Tauri 2 desktop, three-process harness, BYOK-only GA
- [ ] **Work mode artifact pipeline** — DOCX / XLSX / PDF generation with template support
- [ ] **Code mode diff review** — `@file` references, Accept/Reject per hunk, multi-file plans
- [ ] **KTG / STP / MFP self-evolution kernel** — Knowledge-Task Graph, Skill-Task Pipeline, Memory-Formation Protocol
- [ ] **Standalone installer** — Windows NSIS, macOS DMG (notarize), Linux deb + AppImage
- [ ] **Documentation site v1** — [docs/INDEX.md](docs/INDEX.md), getting started, architecture deep-dive, API reference

---

## ⏭️ Next (planned — this quarter)

- [ ] **fnix-local Rust port** — high-performance local sidecar (PDG indexer, sandbox runner)
- [ ] **Skills marketplace** — shareable, versioned, signed skill bundles
- [ ] **MCP registry UI** — discover, install, and configure MCP servers from the workbench
- [ ] **Session replay & export** — share reproducible transcripts
- [ ] **i18n framework** — first-class EN + ZH-CN, infrastructure for JA / KO / FR
- [ ] **Plugin SDK GA** — stable `DocumentConverter` + `MemoryBackend` entry points (PEP 621)

---

## 🔭 Later (next 2–3 quarters)

- [ ] **Multi-agent coordination** — Plan / Worker / Reviewer roles, DAG orchestration
- [ ] **Web / mobile companion** — read-only access from phone/tablet, run jobs on desktop
- [ ] **Local RAG over your entire workspace** — semantic + lexical hybrid, ~1M tokens
- [ ] **Voice in / voice out** — Whisper.cpp + local TTS, fully offline
- [ ] **VS Code & JetBrains extensions** — share the same Work/Code runtime
- [ ] **Observability stack** — OpenTelemetry traces, Prometheus metrics, structured logs

---

## 💭 Maybe (exploratory — not yet committed)

- [ ] **Collaborative sessions** — multi-user editing of an agent session
- [ ] **Code interpreter sandbox** — built-in Jupyter-like execution with sandbox
- [ ] **Native Git integration UI** — visual diff, conflict resolution, branch planning
- [ ] **Self-hostable cloud sync** — opt-in E2E-encrypted session sync
- [ ] **Model fine-tuning hooks** — LoRA adapters for local models

> Ideas here are **not promises** — they're on the wall to gather signal. Vote in [Discussions → Polls](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/polls) to influence priority.

---

## ✅ Done (recent milestones)

### 2026-Q3

- ✅ **v1.0.0-beta.1** — Tauri 2 desktop, three-process harness, BYOK-only
- ✅ **MarkdownMemoryStore** — Markdown source-of-truth memory (EverOS pattern)
- ✅ **RetrievalGate** — complexity-aware memory retrieval
- ✅ **MemoryConsolidator** — periodic fact extraction & dedup
- ✅ **ReflectionEngine** — offline memory evolution
- ✅ **SkillEvaluator** — 9-dimension skill scoring
- ✅ **SkillEvolver** — ratcheted skill evolution
- ✅ **HumanInTheLoop** — three-layer confirmation gate

### 2026-Q2

- ✅ **Self-evolution flywheel** — daily / weekly / monthly schedulers
- ✅ **Architecture diagrams** — 6 SVG diagrams (overview, data flow, memory, security, evolution, deploy)
- ✅ **AG-UI SSE** — `/api/v1/ag-ui/work/stream` event stream
- ✅ **Standalone three-process** — Tauri + agentd + fnix-local

### 2026-Q1

- ✅ **KTG / STP / MFP kernel** — knowledge / skill / memory subsystems
- ✅ **OpenAPI 3.1 contract** — `openapi.json` + TS SDK generation
- ✅ **CI matrix** — Python 3.11/3.12/3.13, ruff + pyright + pytest

See [CHANGELOG.md](CHANGELOG.md) for the full history.

---

## 📊 How we prioritize

We score every candidate feature on four axes (each 1–5):

| Axis | Question |
|------|----------|
| **Impact** | How many users benefit, and how much? |
| **Fit** | How well does it advance the mission above? |
| **Cost** | How much engineering, design, and ongoing maintenance? |
| **Risk** | Security, privacy, or stability risk? |

A feature moves from **Maybe → Later → Next** when its `Impact × Fit - Cost - Risk` clears the threshold, **or** when a community poll gives it strong signal.

---

## 🤝 How to influence the roadmap

1. **Open a discussion** in [Ideas](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/ideas) — small ideas are welcome.
2. **Open an RFC** using the [RFC template](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=rfc.md) for large changes.
3. **Vote in polls** — we run ~1 per month.
4. **Ship it yourself** — contributors who deliver a feature can land it on the roadmap retroactively.

---

_Last updated: 2026-08-17 · Next review: monthly_
