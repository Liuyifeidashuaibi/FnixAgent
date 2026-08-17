"""fnixagent model — 查看/切换默认模型。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations


def run_model(
    *, provider: str | None = None, model: str | None = None, base_url: str | None = None
) -> int:
    from fnixagent.harness.config import read_config_toml, write_config_toml
    from fnixagent.harness.secrets import secrets_status
    from fnixagent.harness.workspace import ensure_home_layout

    ensure_home_layout()
    cfg = read_config_toml()

    if provider or model or base_url:
        if provider is not None:
            cfg["provider"] = provider
        if model is not None:
            cfg["model"] = model
        if base_url is not None:
            cfg["base_url"] = base_url
        write_config_toml(cfg)
        print(f"[OK] updated: {cfg.get('provider')} / {cfg.get('model')}")
        return 0

    sec = secrets_status()
    print("Current model (~/.fnix):")
    print(f"  provider : {cfg.get('provider') or '(unset)'}")
    print(f"  model    : {cfg.get('model') or '(unset)'}")
    print(f"  base_url : {cfg.get('base_url') or '(default)'}")
    print(f"  api_key  : {sec.get('key_hint') or '(unset)'}")
    print("\nSwitch: fnixagent model --provider qwen --model qwen-plus")
    return 0
