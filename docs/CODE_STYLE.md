# Code Style

This document is the **source of truth** for how we write code in this repository. It applies to everything: Python, TypeScript, Rust, shell scripts, and Markdown.

> 📌 **TL;DR:** Run `pnpm format && pnpm lint && pnpm typecheck` before opening a PR. CI will block you if you don't.

---

## 🎯 Guiding principles

1. **Boring > clever.** Future-you (and future-them) will read this at 2 a.m. with a production incident. Be kind.
2. **The toolchain is the linter.** Don't argue about style — let `ruff` / `prettier` / `rustfmt` decide.
3. **Names are the API.** A function/variable/file name should tell you what it does and how to use it, without opening the body.
4. **Type everything.** Python type hints, TypeScript strict mode, Rust `Result`/`Option` — all of it. `Any` is a code smell.
5. **Errors are first-class.** Every error path is documented, tested, and surfaced to the user in plain English (or their locale).
6. **No magic.** No hidden globals, no monkey-patching, no reflection. If you need it, document it loudly.

---

## 🐍 Python

We target **Python 3.11+** and use the standard modern stack: type hints everywhere, `dataclass` / `pydantic` for records, async for I/O.

### Style

- **Formatter:** [ruff format](https://docs.astral.sh/ruff/formatter/) (Black-compatible).
- **Linter:** [ruff](https://docs.astral.sh/ruff/) — see `pyproject.toml` for the rule set.
- **Type checker:** [pyright](https://github.com/microsoft/pyright) in `strict` mode.
- **Imports:** sorted by `ruff` (`I` rules). No wildcard imports, no `from x import *`.
- **Line length:** 100.
- **Quotes:** double quotes for strings, single for single-char literals.
- **Docstrings:** [Google style](https://google.github.io/styleguide/pyguide.html#383-functions-and-methods).

### Naming

| Thing | Convention | Example |
|-------|------------|---------|
| Modules / packages | `lower_snake_case` | `memory_store.py` |
| Classes | `PascalCase` | `MemoryConsolidator` |
| Functions / methods | `lower_snake_case` | `consolidate_session()` |
| Variables | `lower_snake_case` | `session_id` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRY_COUNT` |
| Type variables | `PascalCase`, often `T` | `T`, `KT`, `VT` |
| Private | leading `_` | `_internal_helper` |
| Acronyms | 2-letter: uppercase; 3+: title | `id`, `url`; `Http`, `Api` |

### Type hints

```python
# ✅ DO — fully annotated, with a return type
def find_session(
    user_id: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> list[Session]:
    ...

# ❌ DON'T — untyped, ambiguous
def find_session(user_id, limit=50, cursor=None):
    ...
```

### Error handling

- Define **module-level exception types** that inherit from a base.
- Always include a **message**, an **error code** (machine-readable), and the **context**.
- Use `raise ... from err` to preserve chains.

```python
# ✅ DO
try:
    result = await client.complete(...)
except httpx.TimeoutException as err:
    raise LLMTimeoutError(
        code="llm.timeout",
        message=f"Provider {provider} timed out after {timeout}s",
    ) from err

# ❌ DON'T
try:
    result = await client.complete(...)
except Exception:
    pass
```

### Async

- Use `async def` for I/O; use plain `def` for CPU work.
- Never call `requests` / `urllib` / `time.sleep` in an async path.
- Name async functions like their sync counterparts; don't add an `_async` suffix.

### Tests

- **Framework:** `pytest` + `pytest-asyncio`.
- **Layout:** `tests/unit/`, `tests/integration/`, `e2e/`.
- **Naming:** `test_<unit>_<behavior>_<expected_outcome>`.
- **Fixtures:** scope-aware; prefer narrowest scope.
- **Coverage:** target ≥ 80 % per module, 100 % for `core/security/`.

```python
# tests/unit/memory/test_consolidator.py
async def test_consolidate_session_dedupes_by_hash-> None:
    ...
```

---

## ⚛️ TypeScript / React

### Style

- **Formatter:** [Prettier 3](https://prettier.io/) (config in `.prettierrc`).
- **Linter:** [ESLint](https://eslint.org/) (config in `.eslintrc.cjs`).
- **Type checker:** TypeScript in `strict` mode.
- **Line length:** 100.
- **Quotes:** double, no semicolons in `.tsx` (Prettier handles it).

### Naming

| Thing | Convention | Example |
|-------|------------|---------|
| Files (components) | `PascalCase.tsx` | `Workbench.tsx` |
| Files (utilities) | `kebab-case.ts` | `api-client.ts` |
| Files (hooks) | `use-thing.ts` | `use-session.ts` |
| Components | `PascalCase` | `<DiffPreview />` |
| Hooks | `useXxx` | `useSession()` |
| Variables / functions | `camelCase` | `loadSessions` |
| Types / interfaces | `PascalCase`, no `I` prefix | `type Session = ...` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_CONCURRENT` |
| Booleans | `is` / `has` / `should` prefix | `isLoading`, `hasError` |

### React

- **Function components only.** No `class` components.
- **Hooks rules:** no conditional hooks, no hooks in loops. `eslint-plugin-react-hooks` enforces this.
- **State:** start with `useState`, lift to `useReducer` when it grows, lift to a store (Zustand / TanStack Query) when it needs to be shared.
- **Effects:** the dependency array is the contract. Don't lie.
- **Memoization:** default to not memoizing. Add `useMemo` / `useCallback` only after measuring.
- **Props:** destructure on the signature; type as a named `interface` or `type`.

```tsx
// ✅ DO
interface WorkbenchProps {
  initialSessionId?: string;
  onReady?: (api: WorkbenchAPI) => void;
}
export function Workbench({ initialSessionId, onReady }: WorkbenchProps) { ... }

// ❌ DON'T
export const Workbench: React.FC<any> = (props) => { ... }
```

### Imports

- Order: `react` → external → internal (`@fnixagent/...`) → relative (`./`, `../`).
- No default exports for shared utilities — use named.

---

## 🦀 Rust

### Style

- **Formatter:** `cargo fmt` (don't argue with rustfmt).
- **Linter:** `cargo clippy -- -D warnings` in CI.
- **Edition:** 2021.
- **MSRV:** pinned in `Cargo.toml` (currently `1.75`).

### Naming

| Thing | Convention |
|-------|------------|
| Crates | `kebab-case` |
| Modules | `snake_case` |
| Types / traits | `PascalCase` |
| Functions / variables | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Lifetimes | short, lowercase, descriptive (`'src`, `'ctx`) |

### Error handling

- Library code: `thiserror` for typed errors.
- Application code: `anyhow` for context propagation.
- Never `.unwrap()` in non-test code.

---

## 🐚 Shell

- **Formatter:** [shfmt](https://github.com/mvdan/sh#shfmt) (CI runs it).
- **Linter:** [shellcheck](https://www.shellcheck.net/) (CI runs it).
- **Shebang:** `#!/usr/bin/env bash` (not `/bin/bash`).
- **Strict mode:** start every script with `set -euo pipefail`.
- **Variables:** `"${var}"` always quoted. Prefer `"${var}"` over `$var`.
- **Substitution:** `$(command)` not `` `command` ``.
- **Portability:** prefer POSIX + bash 4+; document non-portable bits.

```bash
#!/usr/bin/env bash
set -euo pipefail

# ✅ DO
log_info{ printf '[INFO] %s\n' "$*"; }
log_info "starting ${SCRIPT_NAME}"

# ❌ DON'T
log_info{ echo "[INFO] $1"; }
```

---

## 📝 Markdown

- **Linter:** [markdownlint](https://github.com/DavidAnson/markdownlint) (config in `.markdownlint.json`).
- **Formatter:** [Prettier](https://prettier.io/) handles it.
- **Line length:** soft 120.
- **Headings:** ATX (`#`), one H1 per file, no skipping levels.
- **Code fences:** always specify a language.
- **Links:** use reference-style for repeated URLs; check links with `markdown-link-check`.

---

## 🌍 i18n

- All **user-facing strings** go through the i18n layer.
- **No** hard-coded English in components or Python modules.
- New locales: open an issue to coordinate with translators.

---

## ✅ Pre-commit checklist

Before every commit:

- [ ] `pnpm format` (or `ruff format`, `prettier --write`)
- [ ] `pnpm lint`
- [ ] `pnpm typecheck`
- [ ] `pnpm test`
- [ ] Updated `CHANGELOG.md` under `[Unreleased]`
- [ ] No debug `print()` / `console.log()` left behind
- [ ] No commented-out code (delete it; git remembers)
- [ ] No secrets (we have `gitleaks` in CI; **do not** paste API keys)

CI is authoritative — if it says no, you have to listen.

---

## 📚 Further reading

- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) — our north star for Python.
- [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html) — TypeScript.
- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/) — Rust.
- [Conventional Comments](https://conventionalcomments.org/) — how we argue in PRs.

---

_Last updated: 2026-08-17 · Maintained by the engineering team._
