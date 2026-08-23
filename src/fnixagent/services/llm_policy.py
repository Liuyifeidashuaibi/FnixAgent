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
    """Desktop 产品是否强制仅接用户 API Key。

    standalone 模式下默认允许服务端 Key（方便本地开发/测试），
    仅在显式设置 FNIX_API_ONLY=1 时才强制 BYOK。

    B3 修复：profile 环境变量与 core/profile.py 保持一致（FNIXAGENT_PROFILE），
    之前的 FNIX_PROFILE 与 get_profile() 读取的 FNIXAGENT_PROFILE 不一致，
    导致 standalone 默认被误判为强制 BYOK，admin 用户无自带 key 时 chat/agent 直接失败。
    """
    raw = os.getenv("FNIX_API_ONLY", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    # 默认：检查是否 standalone / 本地开发模式（与 core/profile.py 的 get_profile 同源）
    profile = os.getenv("FNIXAGENT_PROFILE", "standalone").strip().lower()
    if profile in ("standalone", "local", "local-stack", "docker", "dev"):
        return False
    return True  # 云端/生产模式默认 BYOK


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

    # 提取并校验请求级 LLM 请求超时（仅透传合法正值）
    def _extract_timeout(src: dict) -> float | None:
        raw = src.get("timeout") or src.get("timeout_s")
        if raw is None:
            return None
        try:
            t = float(raw)
        except (TypeError, ValueError):
            return None
        return t if t > 0 else None

    req_timeout = _extract_timeout(llm)
    llm.pop("timeout", None)
    llm.pop("timeout_s", None)
    # llm 是后续所有 return llm, ... 路径返回的同一 dict 对象，直接挂上即可透传
    if req_timeout is not None:
        llm["timeout"] = req_timeout

    use_server = bool(llm.pop("use_server_key", False) or llm.pop("useServerKey", False))
    api_key = (llm.get("api_key") or llm.get("apiKey") or "").strip()

    # B3 加固：管理员优先于 api_only_mode 检查。
    # 若调用方已明确携带 admin JWT（principal_is_admin / _is_admin_payload），
    # 且服务端已配置 LLM Key，则允许使用服务端 Key，避免 BYOK 误伤本机管理员。
    if is_admin and server_llm_configured() and (use_server or not api_key):
        # 去掉客户端 Key，强制服务端环境
        llm.pop("api_key", None)
        llm.pop("apiKey", None)
        if not llm.get("provider"):
            llm["provider"] = server_llm_profile()["provider"]
        if not llm.get("model"):
            m = server_llm_profile().get("model")
            if m:
                llm["model"] = m
        if llm.get("model"):
            llm["model"] = normalize_llm_model(
                str(llm.get("model") or ""), str(llm.get("provider") or "")
            )
        return llm or None, None

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
