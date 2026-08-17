# Security Policy

The FnixAgent team takes the security of this project seriously — including the safety of the **data, files, API keys, and sessions** that flow through it. This document explains how to report a vulnerability, what we commit to, and how we handle disclosures.

> 📌 **TL;DR:** Email **liuyifeidashuaibi@gmail.com** (PGP available) for private disclosure. See [Support → Security disclosure](.github/SUPPORT.md#-where-to-get-help) for the workflow.

---

## Table of contents

- [Supported versions](#-supported-versions)
- [Reporting a vulnerability](#-reporting-a-vulnerability)
- [Our commitments](#-our-commitments)
- [Out of scope](#-out-of-scope)
- [Recognition](#-recognition)
- [Past advisories](#-past-advisories)
- [Hardening guide for users](#-hardening-guide-for-users)

---

## ✅ Supported versions

We follow a **rolling N-2 support policy** — the latest stable release and the two previous minor versions receive security updates.

| Version | Support status | End of security support |
|---------|----------------|-------------------------|
| `1.x` (current) | ✅ Full support | _rolling_ |
| `0.9.x` | ⚠️ Critical-only | 6 months after `1.0.0` GA |
| `< 0.9` | ❌ End of life | — |

Beta / RC / nightly builds are **not** eligible for security backports — please reproduce on the latest stable.

---

## 📣 Reporting a vulnerability

**Please do NOT open a public GitHub Issue for security vulnerabilities.** Public issues let attackers exploit the issue before a fix ships.

### Private disclosure channels (preferred)

| Channel | Details |
|---------|---------|
| **Email** | `liuyifeidashuaibi@gmail.com` |
| **PGP fingerprint** | `7C9F 0E2B 4A1C 8D55 3B2E  F8A4 6D12 9C3E 0B7A 1F4D` |
| **GitHub private disclosure** | Repository → Security tab → "Report a vulnerability" |
| **Response time** | **< 48 hours** to acknowledge |

### What to include

The more of these you can provide, the faster we can act:

```text
1. Summary        — one-paragraph description
2. Impact         — what can an attacker do? (RCE / info-disclosure / DoS / etc.)
3. Severity       — your estimate (CVSS v3.1 vector if you have one)
4. Affected       — component, version, commit SHA
5. Reproduction   — minimal steps, PoC code, payload
6. Environment    — OS, architecture, install method
7. Suggested fix  — optional, but appreciated
8. Discovery date — when you found it
9. Public disclosure plans (if any)
```

> 🛡️ **Safe harbor:** We will not pursue legal action against researchers who follow this policy, make a good-faith effort to avoid privacy violations and disruption, and stop testing as soon as a vulnerability is confirmed.

---

## 🤝 Our commitments

When you report a vulnerability via the channels above, we commit to:

| Stage | Commitment |
|-------|------------|
| **Acknowledgement** | < 48 hours from receipt |
| **Triage** | < 7 days; we confirm or re-classify severity |
| **Status updates** | At least every 14 days until resolution |
| **Fix for critical** | < 30 days from acknowledgement |
| **Fix for high** | < 60 days from acknowledgement |
| **Fix for medium/low** | < 90 days from acknowledgement |
| **CVE assignment** | For issues at or above CVSS 4.0 (medium) |
| **Coordinated disclosure** | 90 days default, extendable on request |
| **Credit** | We will credit you in the advisory unless you prefer to remain anonymous |

We follow the [Google Project Zero disclosure policy](https://googleprojectzero.blogspot.com/p/disclosure-policy.html) and the [CERT/CC coordinated disclosure guidelines](https://vuls.cert.org/confluence/display/CVD/).

---

## 🚫 Out of scope

The following are **out of scope** for our security reward / disclosure program:

- Vulnerabilities in **third-party** dependencies — please report upstream and CC us.
- Issues that **only** affect an **unsupported** version.
- Issues that require the user to **disable browser / OS security features**.
- Social engineering of FnixAgent maintainers or community members.
- Spam, phishing, or volumetric DoS against the project's infrastructure.
- "Theoretical" vulnerabilities without a PoC (we still want to hear about them, just not under the SLA above).
- Issues in **example code** in `demos/` or `experiments/` that are clearly marked as non-production.
- Missing security headers in our **documentation site** (it's static HTML).
- **Self-XSS**: pasting attacker-controlled content into your own session.

If you're unsure whether something is in scope, **ask first** at `liuyifeidashuaibi@gmail.com`.

---

## 🏆 Recognition

We follow a **named-credit-first** model:

- Reporters are listed in the advisory's `Credits` section by default.
- We are happy to coordinate **CVE assignment** with you via GitHub Security Advisories.
- High-impact reporters may be added to our **Security Hall of Fame** below.

### Security Hall of Fame

> _Be the first — report a qualifying issue and get listed here._

---

## 📜 Past advisories

| ID | Date | Title | Severity | CVE |
|----|------|-------|----------|-----|
| _none yet_ | — | — | — | — |

All historical advisories are also published via **GitHub Security Advisories** on this repository.

---

## 🛡️ Hardening guide for users

Even though FnixAgent is local-first, you should still follow these best practices:

### API key hygiene

- **Never** paste API keys into Issues, Discussions, or PRs.
- Store your API key in the OS keychain (Keychain on macOS, Credential Manager on Windows, Secret Service on Linux). The Tauri 2 desktop does this by default.
- Rotate keys at least every 90 days, or immediately if you suspect exposure.
- Use **scoped / project-limited** keys where the provider supports it (OpenAI project keys, Anthropic workspace keys, etc.).

### Workspace isolation

- Run FnixAgent in a **dedicated user account** if you plan to point it at sensitive directories.
- The Workbench's **Code mode** is sandboxed by default — don't disable the sandbox unless you understand the implications.
- Treat `~/.fnix/sessions/` as sensitive: it contains full session transcripts. Encrypt the volume if you travel with a laptop.

### Network

- The agent only talks to the **LLM provider** you configured and the **Tauri update server** (if enabled). There is no telemetry to FnixAgent servers.
- If you want belt-and-suspenders, point the LLM at a **local proxy** (e.g., `litellm`, `oneapi`) so you can audit traffic.

### Updates

- Subscribe to **GitHub Security Advisories** for this repository (Watch → Custom → Security advisories).
- Always run the latest **stable** release — the Tauri updater will notify you.

### Reporting suspicious behavior

If you ever see unexpected network traffic, file-access, or model calls, please:

1. Capture a `pnpm doctor` + a `strace` / `lldb` / `procmon` trace if possible.
2. Open a private report at `liuyifeidashuaibi@gmail.com`.
3. Don't post logs publicly until we've reviewed them.

---

## 📜 Policy version

This policy is versioned at the bottom of this file. Material changes are announced in [Discussions → Announcements](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions/categories/announcements).

---

_Version: 2.0 · Last updated: 2026-08-17_
