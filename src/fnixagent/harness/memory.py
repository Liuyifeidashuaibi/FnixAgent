"""本地 Memory / SOUL（Harness 核心记忆轨）。

数据落在 ~/.fnix：
  SOUL.md · memories/MEMORY.md · memories/USER.md · skills/*.md
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path
from typing import Any

from fnixagent.harness.paths import memories_dir, skills_dir, soul_path
from fnixagent.harness.workspace import ensure_home_layout

_MEMORY_FILES = ("MEMORY.md", "USER.md")


def read_soul() -> str:
    ensure_home_layout()
    path = soul_path()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_soul(content: str) -> None:
    ensure_home_layout()
    soul_path().write_text((content or "").rstrip() + "\n", encoding="utf-8")


def read_memories() -> str:
    ensure_home_layout()
    parts: list[str] = []
    for name in _MEMORY_FILES:
        p = memories_dir() / name
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(f"## {name}\n{text}")
            except OSError:
                continue
    return "\n\n".join(parts)


def read_memory_file(name: str) -> str:
    """读取 memories/ 下单个文件（仅允许白名单名）。"""
    ensure_home_layout()
    safe = Path(name).name
    if safe not in _MEMORY_FILES:
        raise ValueError(f"不允许的记忆文件: {name}")
    path = memories_dir() / safe
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def write_memory_file(name: str, content: str) -> None:
    ensure_home_layout()
    safe = Path(name).name
    if safe not in _MEMORY_FILES:
        raise ValueError(f"不允许的记忆文件: {name}")
    path = memories_dir() / safe
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((content or "").rstrip() + "\n", encoding="utf-8")


def list_memory_files() -> list[dict[str, Any]]:
    ensure_home_layout()
    out: list[dict[str, Any]] = []
    for name in _MEMORY_FILES:
        p = memories_dir() / name
        text = ""
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
            except OSError:
                text = ""
        out.append(
            {
                "name": name,
                "path": str(p),
                "chars": len(text),
                "preview": text.strip()[:240],
                "exists": p.is_file() and bool(text.strip()),
            }
        )
    return out


def list_global_skills(limit: int = 20) -> list[dict[str, str]]:
    ensure_home_layout()
    out: list[dict[str, str]] = []
    root = skills_dir()
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.md")):
        if path.name.upper() == "README.MD":
            continue
        try:
            preview = path.read_text(encoding="utf-8")[:400]
        except OSError:
            preview = ""
        out.append({"name": path.stem, "path": str(path), "preview": preview})
        if len(out) >= limit:
            break
    return out


def build_local_context_prompt(extra: str = "") -> str:
    """拼装注入 Work/Code / chat 的本地上下文。"""
    chunks: list[str] = []
    soul = read_soul()
    if soul:
        chunks.append("# Agent Identity (SOUL.md)\n" + soul)
    mem = read_memories()
    if mem:
        chunks.append("# Local Memory\n" + mem)
    skills = list_global_skills()
    if skills:
        skill_text = "\n\n".join(f"### {s['name']}\n{s['preview']}" for s in skills[:8])
        chunks.append("# Global Skills\n" + skill_text)
    if extra.strip():
        chunks.append(extra.strip())
    return "\n\n---\n\n".join(chunks)


def memory_injection_summary(extra: str = "") -> dict[str, Any]:
    """供 UI 回显：本次将注入哪些记忆块（不含全文大块）。"""
    ensure_home_layout()
    soul = read_soul()
    mem_files = list_memory_files()
    skills = list_global_skills(limit=8)
    prompt = build_local_context_prompt(extra=extra)
    return {
        "ok": True,
        "soul": {
            "present": bool(soul),
            "chars": len(soul),
            "preview": soul[:200] if soul else "",
        },
        "memories": mem_files,
        "skills": [{"name": s["name"], "preview": s["preview"][:120]} for s in skills],
        "extra_chars": len(extra or ""),
        "injected_chars": len(prompt),
        "blocks": [
            name
            for name, flag in (
                ("SOUL.md", bool(soul)),
                ("memories", any(m.get("exists") for m in mem_files)),
                ("skills", bool(skills)),
                (
                    "project_rules",
                    "Project Rules" in (extra or "") or "AGENTS.md" in (extra or ""),
                ),
                ("extra", bool((extra or "").strip())),
            )
            if flag
        ],
    }


def get_memory_bundle() -> dict[str, Any]:
    """GET /harness/memory 完整包。"""
    ensure_home_layout()
    return {
        "ok": True,
        "soul": read_soul(),
        "memories": {name: read_memory_file(name) for name in _MEMORY_FILES},
        "files": list_memory_files(),
        "skills": list_global_skills(),
        "summary": memory_injection_summary(),
    }
