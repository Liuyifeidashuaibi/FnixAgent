"""Harness 本地密钥 — ~/.fnix/secrets.json（CLI 与 Desktop 共享，Hermes 式本机 BYOK）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import fnix_home
from fnixagent.harness.workspace import ensure_home_layout


def secrets_path() -> Path:
    return fnix_home() / "secrets.json"


def read_secrets() -> dict[str, Any]:
    ensure_home_layout()
    path = secrets_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_secrets(data: dict[str, Any]) -> None:
    ensure_home_layout()
    path = secrets_path()
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        if os.name != "nt":
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_llm_api_key() -> str:
    return str(read_secrets().get("llm_api_key") or "").strip()


def set_llm_api_key(api_key: str) -> None:
    data = read_secrets()
    key = (api_key or "").strip()
    if key:
        data["llm_api_key"] = key
    elif "llm_api_key" in data:
        del data["llm_api_key"]
    write_secrets(data)


def secrets_status() -> dict[str, Any]:
    key = get_llm_api_key()
    return {
        "has_api_key": bool(key),
        "key_hint": _mask_key(key),
    }


def _mask_key(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}...{k[-4:]}"
