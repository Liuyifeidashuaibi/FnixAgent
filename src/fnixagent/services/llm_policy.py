"""LLM 访问策略：Desktop 产品模式强制 BYOK（API-only）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
from typing import Any


def api_only_mode() -> bool:
    """Desktop 产品是否强制仅接用户 API Key。"""
    return os.getenv("FNIX_API_ONLY", "1").strip().lower() in ("1", "true", "yes", "on")


def _mask_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 10:
        return "****"
    return f"{key[:6]}****{key[-4:]}"


# DashScope model ids that commonly 403 / are unavailable on consumer keys.
_DASHSCOPE_MODEL_ALIASES = {
    "qwen3.7-plus": "qwen-plus",
    "qwen3-plus": "qwen-plus",
    "qwen3.5-plus": "qwen-plus",
    "qwen-3.7-plus": "qwen-plus",
}


def normalize_llm_model(model: str, provider: str = "") -> str:
    """Rewrite known-bad / alias model ids to a working DashScope chat model.

    Only models explicitly listed in _DASHSCOPE_MODEL_ALIASES are rewritten.
    qwen3-max / qwen3.6-plus / qwen3-235b-a22b etc. are real, working models on
    the DashScope platform and must pass through unchanged.
    """
    name = (model or "").strip()
    if not name:
        return name
    key = name.lower()
    alias = _DASHSCOPE_MODEL_ALIASES.get(key)
    if alias:
        return alias
    return name


def server_llm_configured() -> bool:
    """服务端是否已配置可用 Key（管理员通道用）。"""
    return bool(
        (
            os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("QWEN_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("CUSTOM_API_KEY")
            or ""
        ).strip()
    )


def server_key_hint() -> str:
    key = (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("QWEN_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    return _mask_key(key) or "not-configured"


def server_llm_profile() -> dict[str, Any]:
    """给 Desktop 管理员预填展示用（不含真实 Key）。"""
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        if os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY"):
            provider = "qwen"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        elif os.getenv("GLM_API_KEY"):
            provider = "glm"
        elif os.getenv("DEEPSEEK_API_KEY"):
            provider = "deepseek"
        else:
            provider = "qwen"
    model = normalize_llm_model(
        os.getenv("LLM_MODEL")
        or os.getenv("QWEN_MODEL")
        or ("qwen-plus-2025-07-28" if provider == "qwen" else ""),
        provider,
    )
    return {
        "ok": True,
        "configured": server_llm_configured(),
        "provider": provider,
        "model": model,
        "key_hint": server_key_hint(),
        "source": "server-env",
        "message": "管理员使用服务端 Key；普通用户请在设置中填写自己的 API Key",
    }


def principal_is_admin(request: Any) -> bool:
    """从 Gateway Principal 判断是否管理员。"""
    try:
        principal = getattr(getattr(request, "state", None), "principal", None)
        if principal is None:
            return False
        scopes = getattr(principal, "scope", None) or []
        if "admin" in scopes:
            return True
        via = getattr(principal, "via", "")
        # 本机开发无 Token 时仍允许走服务端 Key（你是唯一管理员）
        if via == "dev" and server_llm_configured():
            return True
        return False
    except Exception:
        return False


def resolve_llm_for_request(
    llm: dict | None,
    *,
    is_admin: bool,
) -> tuple[dict | None, str | None]:
    """按角色解析请求级 LLM。

    Returns:
        (llm_dict, error_message)
        - 管理员：允许 use_server_key / 无 api_key → 走服务端 .env
        - 普通用户：必须自带 api_key
    """
    llm = dict(llm or {})
    use_server = bool(llm.pop("use_server_key", False) or llm.pop("useServerKey", False))
    api_key = (llm.get("api_key") or llm.get("apiKey") or "").strip()

    if api_only_mode():
        if not api_key:
            return None, "请先在 Desktop 设置中填写您自己的 API Key（Fnix 仅支持 BYOK）"
        if llm.get("model"):
            llm["model"] = normalize_llm_model(
                str(llm.get("model") or ""), str(llm.get("provider") or "")
            )
        return llm, None

    # MockLLM fallback: 非 API-only 模式下, 若服务端未配置任何真实 Key 且用户也未提供 Key,
    # 说明处于离线/测试环境, 放行让调度器回退到 MockLLMProvider。
    # 避免普通用户(含 dev principal)在无 Key 时被 LLM 策略阻断, 无法使用 Mock。
    if not api_key and not server_llm_configured():
        return None, None

    if is_admin:
        if use_server or not api_key:
            if not server_llm_configured():
                return None, "服务端未配置管理员 LLM Key（DASHSCOPE_API_KEY / QWEN_API_KEY）"
            # 去掉客户端 Key，强制服务端环境
            llm.pop("api_key", None)
            llm.pop("apiKey", None)
            if not llm.get("provider"):
                profile = server_llm_profile()
                llm["provider"] = profile["provider"]
            if not llm.get("model"):
                profile = server_llm_profile()
                if profile.get("model"):
                    llm["model"] = profile["model"]
            if llm.get("model"):
                llm["model"] = normalize_llm_model(
                    str(llm.get("model") or ""),
                    str(llm.get("provider") or ""),
                )
            return llm or None, None
        if llm.get("model"):
            llm["model"] = normalize_llm_model(
                str(llm.get("model") or ""), str(llm.get("provider") or "")
            )
        return llm, None

    # 普通用户：BYOK
    if not api_key:
        return None, "请先在设置中填写你自己的 API Key（普通用户不使用管理员服务端 Key）"
    if llm.get("model"):
        llm["model"] = normalize_llm_model(
            str(llm.get("model") or ""), str(llm.get("provider") or "")
        )
    return llm, None
