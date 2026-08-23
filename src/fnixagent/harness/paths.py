"""Harness 路径约定 — ~/.fnix 与 {workspace}/.fnix（对齐 Fnix ~/.fnix）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
from pathlib import Path


def fnix_home() -> Path:
    """用户级 Harness 根目录（默认 ~/.fnix；Windows 可用 FNIX_HOME）。"""
    raw = os.getenv("FNIX_HOME", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    # Fnix 在 Windows 用 LOCALAPPDATA；Fnix 统一 ~/.fnix，可用环境变量覆盖
    return Path.home() / ".fnix"


def sessions_dir() -> Path:
    return fnix_home() / "sessions"


def config_path() -> Path:
    return fnix_home() / "config.toml"


def secrets_path() -> Path:
    return fnix_home() / "secrets.json"


def logs_dir() -> Path:
    return fnix_home() / "logs"


def memories_dir() -> Path:
    return fnix_home() / "memories"


def skills_dir() -> Path:
    return fnix_home() / "skills"


def soul_path() -> Path:
    return fnix_home() / "SOUL.md"


def mcp_path() -> Path:
    return fnix_home() / "mcp.json"


def default_workspace() -> Path:
    """服务端默认工作区（未显式指定时）。

    解析顺序：FNIXAGENT_WORKSPACE 环境变量 > ~/.fnix/workspaces/default。
    绝不回落到进程 cwd —— 那通常是应用安装目录，会把用户产物写进
    安装目录/源码仓库（D1 缺陷修复）。
    """
    raw = os.getenv("FNIXAGENT_WORKSPACE", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    ws = fnix_home() / "workspaces" / "default"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def project_fnix_dir(workspace: str | os.PathLike[str]) -> Path:
    return Path(workspace).expanduser().resolve() / ".fnix"


def project_skills_dir(workspace: str | os.PathLike[str]) -> Path:
    return project_fnix_dir(workspace) / "skills"


def project_artifacts_dir(workspace: str | os.PathLike[str]) -> Path:
    return project_fnix_dir(workspace) / "artifacts"


def coerce_craft_artifact_path(rel_path: str, *, default_name: str = "output.txt") -> str:
    """Force Craft deliverables under `.fnix/artifacts/` (posix-style relative).

    Already-correct paths are returned unchanged. Bare filenames and scattered
    relative paths are nested under the artifacts root.
    """
    raw = (rel_path or "").strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    raw = raw.lstrip("/")
    if not raw:
        raw = default_name

    lower = raw.lower()
    marker = ".fnix/artifacts/"
    idx = lower.find(marker)
    if idx >= 0:
        return raw[idx:]

    if lower.startswith("artifacts/"):
        return f".fnix/{raw}"

    return f".fnix/artifacts/{raw}"


def project_topology_dir(workspace: str | os.PathLike[str]) -> Path:
    return project_fnix_dir(workspace) / "topology"


def project_index_dir(workspace: str | os.PathLike[str]) -> Path:
    return project_fnix_dir(workspace) / "index"
