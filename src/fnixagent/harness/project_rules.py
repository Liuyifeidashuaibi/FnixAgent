"""项目规则 — AGENTS.md 兼容分层加载（对标 Codex，落在 Fnix）。

优先级（后写覆盖前写的语义由「越具体越靠后」保证）：
1. {workspace}/.fnix/rules.md          — Fnix 原生
2. 从 workspace 根走到 cwd 路径上各层的 AGENTS.md / AGENTS.override.md
   （override 同层优先于 AGENTS.md）

默认上限 32 KiB（与 Codex 默认量级一致），防止撑爆上下文。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DEFAULT_MAX_CHARS = 32 * 1024
_RULE_NAMES = ("AGENTS.override.md", "AGENTS.md")


def _read_text(path: Path, *, limit: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    text = text.strip()
    if not text:
        return ""
    if len(text) > limit:
        return text[:limit] + "\n\n…(truncated)"
    return text


def _walk_dirs(workspace: Path, cwd: Path | None) -> list[Path]:
    """从 workspace 根沿路径走到 cwd（含两端）。cwd 不在 workspace 内则仅根。"""
    root = workspace.resolve()
    dirs = [root]
    if cwd is None:
        return dirs
    try:
        cur = cwd.expanduser().resolve()
    except OSError:
        return dirs
    try:
        cur.relative_to(root)
    except ValueError:
        return dirs
    if cur == root:
        return dirs
    # 根 → … → cwd
    chain: list[Path] = []
    p = cur
    while True:
        chain.append(p)
        if p == root:
            break
        parent = p.parent
        if parent == p:
            break
        p = parent
    chain.reverse()
    return chain


def load_project_rules(
    workspace: str | os.PathLike[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """加载项目规则，返回结构化结果。"""
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        return {"ok": False, "text": "", "sources": [], "chars": 0}

    cwd_path = Path(cwd).expanduser().resolve() if cwd else root
    remaining = max(1024, int(max_chars))
    chunks: list[str] = []
    sources: list[str] = []

    # 1) Fnix 原生 rules.md
    fnix_rules = root / ".fnix" / "rules.md"
    if fnix_rules.is_file():
        body = _read_text(fnix_rules, limit=remaining)
        if body:
            chunks.append(f"### .fnix/rules.md\n{body}")
            sources.append(str(fnix_rules))
            remaining -= len(body)

    # 2) 目录链 AGENTS*
    if remaining > 0:
        for directory in _walk_dirs(root, cwd_path):
            if remaining <= 0:
                break
            for name in _RULE_NAMES:
                path = directory / name
                if not path.is_file():
                    continue
                body = _read_text(path, limit=remaining)
                if not body:
                    continue
                rel = path.relative_to(root).as_posix()
                chunks.append(f"### {rel}\n{body}")
                sources.append(str(path))
                remaining -= len(body)
                # 同层 override 已读则仍可读 AGENTS.md（两者都注入，override 在前）

    text = "\n\n".join(chunks).strip()
    return {
        "ok": bool(text),
        "text": text,
        "sources": sources,
        "chars": len(text),
    }


def format_project_rules_block(
    workspace: str | os.PathLike[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """供 Prompt 注入的 Markdown 块；无规则时返回空串。"""
    loaded = load_project_rules(workspace, cwd=cwd, max_chars=max_chars)
    if not loaded.get("text"):
        return ""
    return "# Project Rules (AGENTS.md / .fnix/rules.md)\n" + loaded["text"]
