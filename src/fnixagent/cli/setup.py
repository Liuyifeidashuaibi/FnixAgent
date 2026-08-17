"""fnixagent setup — write BYOK into ~/.fnix (Fnix CLI)."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import sys

PROVIDERS = {
    "1": (
        "qwen",
        "Qwen / DashScope",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
    ),
    "2": ("openai", "openai", "https://api.openai.com/v1", "gpt-4o"),
    "3": ("deepseek", "DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    "4": ("glm", "Zhipu GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4"),
    "5": ("custom", "Custom OpenAI-compatible", "", ""),
}


def run_setup(
    *,
    non_interactive: bool = False,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> int:
    from fnixagent.harness.config import write_config_toml
    from fnixagent.harness.secrets import set_llm_api_key
    from fnixagent.harness.workspace import ensure_home_layout

    home = ensure_home_layout()
    print("\n=== Fnix Harness Setup ===")
    print(f"Home: {home}\n")

    if non_interactive:
        if not provider or not api_key:
            print("non-interactive needs --provider and --api-key", file=sys.stderr)
            return 1
        p = provider.strip().lower()
        preset = next((v for v in PROVIDERS.values() if v[0] == p), None)
        write_config_toml(
            {
                "provider": p,
                "model": model or (preset[3] if preset else ""),
                "base_url": base_url or (preset[2] if preset else ""),
            }
        )
        set_llm_api_key(api_key)
        print("[OK] wrote ~/.fnix/config.toml and secrets.json")
        return 0

    print("Choose LLM provider (BYOK, key stays local):")
    for k, (_, label, _, _) in PROVIDERS.items():
        print(f"  {k}. {label}")
    choice = input("\nNumber [1]: ").strip() or "1"
    if choice not in PROVIDERS:
        print("invalid choice", file=sys.stderr)
        return 1

    pid, label, default_base, default_model = PROVIDERS[choice]
    print(f"\n-> {label}")

    m = input(f"Model [{default_model or 'custom'}]: ").strip() or default_model
    b = default_base
    if pid == "custom" or not b:
        b = input("API Base URL: ").strip()
    key = input("API Key: ").strip()
    if not key:
        print("no API Key — only provider/model saved", file=sys.stderr)

    write_config_toml({"provider": pid, "model": m, "base_url": b})
    if key:
        set_llm_api_key(key)

    print("\n[OK] Setup complete")
    print("  Next:")
    print("    fnixagent doctor")
    print("    fnixagent chat")
    print("    or Desktop: pnpm dev")
    return 0
