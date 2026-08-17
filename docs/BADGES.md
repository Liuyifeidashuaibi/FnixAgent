# Badges

The badges used across the `FnixAgent` repo, centralized so we can update them in one place.

> 📌 **Note:** The README on `main` shows the curated set below. Add new badges sparingly — every badge is a third-party request from a visitor's browser.

---

## 🟢 Tier 1 — always shown

These are part of the canonical README header.

### Build & release

```markdown
[![CI](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Liuyifeidashuaibi/FnixAgent?include_prereleases&label=Release)](https://github.com/Liuyifeidashuaibi/FnixAgent/releases)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/Liuyifeidashuaibi/FnixAgent/badge)](https://scorecard.dev/viewer/?uri=github.com/Liuyifeidashuaibi/FnixAgent)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/0000/badge)](https://www.bestpractices.dev/projects/0000)
```

### License

```markdown
[![License](https://img.shields.io/badge/License-Proprietary-red)](LICENSE)
[![License: MIT (engine)](https://img.shields.io/badge/engine-MIT-blue)](LICENSE)
```

### Tech stack

```markdown
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Tauri](https://img.shields.io/badge/Tauri-2-orange?logo=tauri&logoColor=white)](https://v2.tauri.app/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6%2B-3178c6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![React](https://img.shields.io/badge/React-18-61dafb?logo=react&logoColor=black)](https://react.dev/)
[![Rust](https://img.shields.io/badge/Rust-stable-orange?logo=rust&logoColor=white)](https://www.rust-lang.org/)
```

### Code quality

```markdown
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type Checked: pyright strict](https://img.shields.io/badge/type--checked-pyright%20strict-blue)](https://github.com/microsoft/pyright)
[![CodeQL](https://img.shields.io/github/actions/workflow/status/Liuyifeidashuaibi/FnixAgent/codeql.yml?label=CodeQL&logo=github)](https://github.com/Liuyifeidashuaibi/FnixAgent/actions/workflows/codeql.yml)
```

---

## 🟡 Tier 2 — context-dependent

Show these in sub-docs or specific READMEs.

### Downloads / adoption

```markdown
[![Downloads](https://img.shields.io/github/downloads/Liuyifeidashuaibi/FnixAgent/total)](https://github.com/Liuyifeidashuaibi/FnixAgent/releases)
[![Stars](https://img.shields.io/github/stars/Liuyifeidashuaibi/FnixAgent?style=social)](https://github.com/Liuyifeidashuaibi/FnixAgent/stargazers)
[![Forks](https://img.shields.io/github/forks/Liuyifeidashuaibi/FnixAgent?style=social)](https://github.com/Liuyifeidashuaibi/FnixAgent/network/members)
[![Contributors](https://img.shields.io/github/contributors/Liuyifeidashuaibi/FnixAgent)](https://github.com/Liuyifeidashuaibi/FnixAgent/graphs/contributors)
```

### Coverage

```markdown
[![codecov](https://codecov.io/gh/Liuyifeidashuaibi/FnixAgent/branch/main/graph/badge.svg)](https://codecov.io/gh/Liuyifeidashuaibi/FnixAgent)
[![Coverage Status](https://coveralls.io/repos/github/Liuyifeidashuaibi/FnixAgent/badge.svg?branch=main)](https://coveralls.io/github/Liuyifeidashuaibi/FnixAgent?branch=main)
```

### Activity

```markdown
[![Last commit](https://img.shields.io/github/last-commit/Liuyifeidashuaibi/FnixAgent)](https://github.com/Liuyifeidashuaibi/FnixAgent/commits/main)
[![Commit activity](https://img.shields.io/github/commit-activity/m/Liuyifeidashuaibi/FnixAgent)](https://github.com/Liuyifeidashuaibi/FnixAgent/graphs/commit-activity)
[![Issues](https://img.shields.io/github/issues/Liuyifeidashuaibi/FnixAgent)](https://github.com/Liuyifeidashuaibi/FnixAgent/issues)
[![PRs](https://img.shields.io/github/issues-pr/Liuyifeidashuaibi/FnixAgent)](https://github.com/Liuyifeidashuaibi/FnixAgent/pulls)
```

### Specific tech

```markdown
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-blueviolet)](https://langchain-ai.github.io/langgraph/)
[![Pydantic](https://img.shields.io/badge/Pydantic-2-e92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Tailwind](https://img.shields.io/badge/Tailwind-3-38bdf8?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
```

---

## 🔴 Tier 3 — project-internal / use with care

### Dependabot

```markdown
[![Dependabot Status](https://api.dependabot.com/badges/status?host=github&repo=Liuyifeidashuaibi/FnixAgent)](https://github.com/Liuyifeidashuaibi/FnixAgent/network/updates)
```

### Code coverage by file

Use Codecov's per-file table — usually too noisy for a top-level README.

---

## 🧪 How to add a new badge

1. Add the source markdown to this file under the right tier.
2. Use the official `img.shields.io` or `github.com/.../badge.svg` endpoint.
3. Always link the badge to the **thing it claims to measure**.
4. **Don't** use badges that send tracking pixels.

When in doubt, **don't add it**. A small, honest badge set is better than a noisy wall.

---

_Last updated: 2026-08-17_
