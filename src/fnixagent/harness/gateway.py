"""Harness gateway — 本地门面状态与启动初始化。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fnixagent.core.profile import profile_info
from fnixagent.harness.local_bridge import get_local_bridge
from fnixagent.harness.paths import fnix_home, sessions_dir
from fnixagent.harness.session import get_session_store
from fnixagent.harness.workspace import ensure_home_layout, read_home_config


def init_harness() -> None:
    """应用启动时初始化 Harness 目录。"""
    ensure_home_layout()
    store = get_session_store()
    try:
        store.compact_old_sessions(max_keep=200)
    except Exception:
        pass
    try:
        from fnixagent.harness.config import reload_harness_mcp

        reload_harness_mcp()
    except Exception:
        pass


def get_harness_status() -> dict[str, Any]:
    """供 /harness/status 与 Desktop 使用。"""
    from fnixagent.harness.secrets import secrets_status

    home = fnix_home()
    bridge = get_local_bridge()
    sidecar = bridge.health()
    cfg = read_home_config()
    sec = secrets_status()
    ready = bool(cfg.get("provider") and sec.get("has_api_key"))

    runtime = (
        "rust"
        if sidecar.version and "rust" in sidecar.version.lower()
        else ("python" if sidecar.available else "offline")
    )
    return {
        "ok": True,
        "harness": "fnix-local-harness",
        "home": str(home),
        "profile": profile_info(),
        "ready": ready,
        "degraded": not sidecar.available,
        "setup": {
            "has_provider": bool(cfg.get("provider")),
            "has_model": bool(cfg.get("model")),
            "has_api_key": bool(sec.get("has_api_key")),
            "key_hint": sec.get("key_hint", ""),
        },
        "config": {
            "provider": cfg.get("provider", ""),
            "model": cfg.get("model", ""),
            "base_url": cfg.get("base_url", ""),
        },
        "sidecar": {
            "available": sidecar.available,
            "url": sidecar.url,
            "version": sidecar.version,
            "runtime": runtime,
            "message": sidecar.message,
            "fallback": None if sidecar.available else "python-workspace-tools",
        },
        "sessions_dir": str(sessions_dir()),
    }
