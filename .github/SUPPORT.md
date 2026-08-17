# Support

This document explains **where to get help** with Fnix Harness and **how to ask effectively** so the community can help you faster.

> 📌 **TL;DR:** Q&A and troubleshooting go to [GitHub Discussions → Q&A](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/q-a). **Security issues go to the private channel in [SECURITY.md](SECURITY.md).** GitHub Issues are reserved for bugs, feature requests, and documentation problems.

---

## Where to get help

| Need | Channel | Notes |
|------|---------|-------|
| **Q&A, "how do I…", configuration** | [Discussions → Q&A](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/q-a) | Best for open-ended questions. |
| **Bug report** | [Issues → Bug report](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=bug_report.md) | Use only after reproducing on the latest release. |
| **Feature idea** | [Discussions → Ideas](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/ideas) first, then promote to an issue. | For large changes, use the [RFC template](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=rfc.md). |
| **Docs problem** | [Issues → Documentation](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=documentation.md) | Typo, broken link, missing topic. |
| **Performance** | [Issues → Performance](https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new?template=performance.md) | Include a profile (py-spy / flamegraph). |
| **Security vulnerability** | **Private:** `security@fnixagent.dev` (see [SECURITY.md](SECURITY.md)) | **Never** use a public issue. |
| **Commercial / enterprise support** | Email `sales@fnixagent.dev` | SLA, custom builds, training. |
| **中文用户群** | See [README.md → Community](README.md#community) | WeChat / Discord / Telegram links. |

---

## Before you ask

1. **Check the docs** — [docs/INDEX.md](docs/INDEX.md) is the table of contents.
2. **Search existing threads** — many questions are already answered.
3. **Update to the latest release** — your bug may already be fixed.
4. **Run the doctor** — `fnixagent doctor` diagnoses ~80% of common problems.
5. **Gather repro details** — see template below.

---

## How to ask a good question

A good question includes:

```text
## What I'm trying to do
<one sentence goal>

## Environment
- OS: Windows 11 23H2 / macOS 14.5 / Ubuntu 24.04
- Fnix Harness version: v1.x.y (run `fnixagent --version`)
- Install method: Release installer / from source / pnpm dev
- LLM provider: OpenAI / Anthropic / Qwen / GLM / DeepSeek / other
- Model: gpt-4o / claude-3-5-sonnet / qwen-long / etc.

## What I tried
1. ...
2. ...

## What happened
<paste exact error, log lines, or screenshot>

## What I expected
<one sentence>
```

---

## Response time expectations

This is an open-source project maintained by a small core team in their spare time (and by an amazing community).

| Channel | Best-effort response time |
|---------|---------------------------|
| 🛡️ Security disclosures | **< 48 h** to acknowledge (see [SECURITY.md](SECURITY.md)) |
| 🐛 Confirmed reproducible bugs | **3–7 days** to first maintainer response |
| 💡 Ideas / Q&A | **1–2 weeks**, but community often replies sooner |
| 🌐 i18n / docs typos | **1–4 weeks** |

There are **no SLAs** for community support. For guaranteed response times, contact `sales@fnixagent.dev` for commercial support.

---

## Code of Conduct

All community spaces (issues, discussions, chat) are governed by our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be kind, be specific, and assume good faith.
