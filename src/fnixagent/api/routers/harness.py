"""API 路由 — Harness 本地门面（workspace / skills / status）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/harness", tags=["harness"])


class EnsureWorkspaceRequest(BaseModel):
    workspace: str = Field(..., min_length=1, max_length=4096)


class ReloadSkillsRequest(BaseModel):
    workspace: str = Field(..., min_length=1, max_length=4096)


class ConfigUpdateRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class LlmTestRequest(BaseModel):
    provider: str | None = None
    model: str | None = Field(default="", max_length=128)
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str = Field(..., min_length=1, max_length=4096)


class SecretsUpdateRequest(BaseModel):
    api_key: str | None = Field(default=None, max_length=4096)


class McpConfigUpdateRequest(BaseModel):
    version: int = 1
    servers: list[dict[str, Any]] = Field(default_factory=list)


class McpTrustApproveRequest(BaseModel):
    server_id: str = Field(..., min_length=1, max_length=256)
    command: str | None = Field(default=None, max_length=1024)
    args: list[str] | None = None
    remote_url: str = Field(default="", max_length=2048)
    auth_type: str = Field(default="none", max_length=32)
    notes: str = Field(default="", max_length=2000)


class McpTrustDenyRequest(BaseModel):
    server_id: str = Field(..., min_length=1, max_length=256)
    notes: str = Field(default="", max_length=2000)


class IndexWorkspaceRequest(BaseModel):
    workspace: str = Field(..., min_length=1, max_length=4096)
    force: bool = False
    session_id: str | None = None


class MemoryUpdateRequest(BaseModel):
    soul: str | None = Field(default=None, max_length=100_000)
    memories: dict[str, str] | None = None


@router.post("/index")
async def index_workspace(body: IndexWorkspaceRequest):
    """触发 fnix-local 索引 workspace（PDG）。"""
    from fnixagent.harness.local_bridge import get_local_bridge

    bridge = get_local_bridge()
    result = bridge.index_workspace(
        body.workspace,
        force=body.force,
        session_id=body.session_id,
    )
    return {"ok": bool(result.get("ok", True)), **result}


@router.get("/status")
async def harness_status():
    """Harness 本地状态：home 目录、sidecar、profile。"""
    from fnixagent.harness.gateway import get_harness_status

    return get_harness_status()


@router.post("/workspace/ensure")
async def ensure_workspace(body: EnsureWorkspaceRequest):
    """绑定 workspace 时创建 {path}/.fnix 布局。"""
    from fnixagent.harness.workspace import ensure_project_layout

    try:
        layout = ensure_project_layout(body.workspace)
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {"ok": True, **layout}


@router.get("/skills")
async def list_skills(workspace: str):
    """列出 workspace/.fnix/skills 下的技能（含 frontmatter 字段 + enabled 状态）。"""
    # 路径安全校验：拒绝路径遍历攻击
    if ".." in workspace:
        raise HTTPException(status_code=400, detail="workspace 路径不允许包含 '..'")
    from fnixagent.harness.skills_loader import load_workspace_skills

    skills = load_workspace_skills(workspace)
    return {
        "ok": True,
        "workspace": workspace,
        "count": len(skills),
        "skills": [
            {
                "name": s.name,
                "path": s.path,
                "preview": s.content[:200],
                "content": s.content,
                "description": s.description,
                "triggers": list(s.triggers),
                "priority": s.priority,
                "enabled": s.enabled,
            }
            for s in skills
        ],
    }


@router.post("/skills/reload")
async def reload_skills(body: ReloadSkillsRequest):
    """热加载 skills 缓存。"""
    from fnixagent.harness.skills_loader import reload_workspace_skills

    skills = reload_workspace_skills(body.workspace)
    return {
        "ok": True,
        "count": len(skills),
        "skills": [s.name for s in skills],
    }


# ---------------------------------------------------------------------------
# 技能管理系统：CRUD + 启停（技能系统 + 项目规则）
# ---------------------------------------------------------------------------


class WriteSkillRequest(BaseModel):
    workspace: str = Field(..., min_length=1, max_length=4096)
    name: str = Field(..., min_length=1, max_length=128)
    content: str = Field(..., min_length=1, max_length=65536)
    description: str = Field(default="", max_length=2000)
    triggers: list[str] = Field(default_factory=list)
    priority: str = Field(default="normal", pattern="^(high|normal|low)$")
    enabled: bool = True


class DeleteSkillRequest(BaseModel):
    workspace: str = Field(..., min_length=1, max_length=4096)


class ToggleSkillRequest(BaseModel):
    workspace: str = Field(..., min_length=1, max_length=4096)
    enabled: bool


@router.post("/skills/write")
async def write_skill(body: WriteSkillRequest):
    """创建或更新一个静态技能（.fnix/skills/{name}.md）。"""
    from fnixagent.harness.skills_loader import write_workspace_skill

    try:
        skill = write_workspace_skill(
            body.workspace,
            body.name,
            body.content,
            description=body.description,
            triggers=body.triggers,
            priority=body.priority,
            enabled=body.enabled,
        )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")
    return {
        "ok": True,
        "skill": {
            "name": skill.name,
            "path": skill.path,
            "description": skill.description,
            "triggers": list(skill.triggers),
            "priority": skill.priority,
            "enabled": skill.enabled,
        },
    }


@router.delete("/skills/{name}")
async def delete_skill(name: str, workspace: str):
    """删除静态技能。"""
    from fnixagent.harness.skills_loader import delete_workspace_skill

    ok = delete_workspace_skill(workspace, name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    return {"ok": True, "deleted": name}


@router.post("/skills/{name}/toggle")
async def toggle_skill(name: str, body: ToggleSkillRequest):
    """切换技能 enabled 状态。"""
    from fnixagent.harness.skills_loader import toggle_workspace_skill

    skill = toggle_workspace_skill(body.workspace, name, body.enabled)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"技能 {name} 不存在")
    return {
        "ok": True,
        "skill": {
            "name": skill.name,
            "enabled": skill.enabled,
        },
    }


@router.get("/config")
async def get_harness_config():
    """读取 ~/.fnix/config.toml 摘要。"""
    from fnixagent.harness.config import read_config_toml
    from fnixagent.harness.secrets import secrets_status

    cfg = read_config_toml()
    sec = secrets_status()
    return {
        "ok": True,
        "provider": cfg.get("provider", ""),
        "model": cfg.get("model", ""),
        "base_url": cfg.get("base_url", ""),
        **sec,
    }


@router.get("/local-bootstrap")
async def local_llm_bootstrap(request: Request):
    """本机回环专用：把进程环境里的 BYOK（仓库 .env）交给桌面壳。"""
    host = (request.client.host if request.client else "") or ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="localhost only")

    provider = (os.getenv("LLM_PROVIDER") or "qwen").strip()
    provider_key = provider.lower()
    model = (os.getenv("LLM_MODEL") or "qwen-plus-2025-07-28").strip()

    # provider → (api_key 候选环境变量, base_url 候选环境变量, 默认 base_url)。
    # 单次启动必须返回「同一 provider 的同一把 key + 同一端点」：
    # 前端 boot 会经 PUT /config 把此处返回的 api_key / base_url 写回
    # ~/.fnix/secrets.json + config.toml，任何跨 provider 混搭都会让后续
    # 所有请求 401/404 并错误触发 fallback 熔断级联。
    # 注意顺序敏感：历史事故有二——
    #  1) glm provider 取到 DASHSCOPE_API_KEY（阿里云 MaaS key 打在智谱端点鉴权失败）；
    #  2) siliconflow provider 走 else 分支取到 DASHSCOPE_API_KEY + DASHSCOPE_BASE_URL
    #     （模型名 deepseek-ai/* 打在阿里云 MaaS 端点 404 → 级联熔断到失效）。
    _key_envs_map = {
        "glm": ("GLM_API_KEY", "CUSTOM_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"),
        "siliconflow": ("SILICONFLOW_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY"),
        "deepseek": ("DEEPSEEK_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY"),
        "openai": ("OPENAI_API_KEY", "CUSTOM_API_KEY"),
        "custom": ("CUSTOM_API_KEY",),
        "qwen": ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY"),
        "dashscope": ("DASHSCOPE_API_KEY", "QWEN_API_KEY", "CUSTOM_API_KEY", "OPENAI_API_KEY"),
    }
    _base_envs_map = {
        "glm": ("GLM_BASE_URL", "CUSTOM_BASE_URL", "OPENAI_BASE_URL"),
        "siliconflow": ("SILICONFLOW_BASE_URL", "CUSTOM_BASE_URL", "OPENAI_BASE_URL"),
        "deepseek": ("DEEPSEEK_BASE_URL", "CUSTOM_BASE_URL", "OPENAI_BASE_URL"),
        "openai": ("OPENAI_BASE_URL", "CUSTOM_BASE_URL"),
        "custom": ("CUSTOM_BASE_URL",),
        "qwen": ("DASHSCOPE_BASE_URL", "QWEN_BASE_URL"),
        "dashscope": ("DASHSCOPE_BASE_URL", "QWEN_BASE_URL"),
    }
    _default_base_map = {
        "glm": "https://open.bigmodel.cn/api/paas/v4",
        "siliconflow": "https://api.siliconflow.cn/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "openai": "https://api.openai.com/v1",
        "custom": "",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }

    def _first_env(names: tuple[str, ...]) -> str:
        for n in names:
            v = (os.getenv(n) or "").strip()
            if v:
                return v
        return ""

    if provider_key in _key_envs_map:
        key_envs = _key_envs_map[provider_key]
        base_envs = _base_envs_map[provider_key]
        default_base = _default_base_map[provider_key]
    else:
        # 未知 provider：保守回退 CUSTOM_*（一般即该 provider 的 OpenAI 兼容端点）
        key_envs = ("CUSTOM_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY")
        base_envs = ("CUSTOM_BASE_URL", "DASHSCOPE_BASE_URL", "OPENAI_BASE_URL")
        default_base = ""

    api_key = _first_env(key_envs)
    base_url = _first_env(base_envs) or default_base
    provider_name = "DashScope (Qwen)" if provider_key in {"qwen", "dashscope"} else provider

    return {
        "ok": True,
        "provider": provider,
        "provider_name": provider_name,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "has_api_key": bool(api_key),
    }


@router.put("/config")
async def update_harness_config(body: ConfigUpdateRequest):
    """更新 ~/.fnix/config.toml（Desktop Settings 同步）。"""
    from fnixagent.harness.config import read_config_toml, write_config_toml
    from fnixagent.harness.secrets import set_llm_api_key

    current = read_config_toml()
    if body.provider is not None:
        current["provider"] = body.provider
    if body.model is not None:
        current["model"] = body.model
    if body.base_url is not None:
        current["base_url"] = body.base_url
    write_config_toml(current)
    if body.api_key is not None:
        set_llm_api_key(body.api_key)
    from fnixagent.harness.secrets import secrets_status

    return {"ok": True, **current, **secrets_status()}


@router.put("/secrets")
async def update_secrets(body: SecretsUpdateRequest):
    """更新 ~/.fnix/secrets.json（仅本机，供 CLI 读取）。"""
    from fnixagent.harness.secrets import secrets_status, set_llm_api_key

    if body.api_key is not None:
        set_llm_api_key(body.api_key)
    return {"ok": True, **secrets_status()}


@router.post("/llm/test")
async def test_llm_connection(body: LlmTestRequest):
    """最小 LLM 连通性测试（Setup 向导用）。"""
    from fnixagent.core.llm.adapter import LLMAdapter

    base = (body.base_url or "").strip()
    model = (body.model or "").strip()
    adapter = LLMAdapter(
        api_key=body.api_key.strip(),
        base_url=base,
        model_name=model,
        provider_name=(body.provider or "").strip(),
    )
    if not adapter.is_configured:
        raise HTTPException(status_code=400, detail="LLM 未配置：请检查 API Key 与 Base URL")
    try:
        result = await adapter.chat(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            tools=None,
            model=model,
            max_tokens=16,
            temperature=0,
        )
        content = ""
        choices = result.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = str(msg.get("content") or "")[:120]
        return {
            "ok": True,
            "provider": body.provider or adapter.provider_name,
            "model": model or adapter.provider_name,
            "preview": content or "connected",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/memory")
async def get_harness_memory():
    """读取 ~/.fnix SOUL / memories / skills 摘要。"""
    from fnixagent.harness.memory import get_memory_bundle

    return get_memory_bundle()


@router.put("/memory")
async def update_harness_memory(body: MemoryUpdateRequest):
    """更新 SOUL.md 与 memories/*.md。"""
    from fnixagent.harness.memory import (
        get_memory_bundle,
        write_memory_file,
        write_soul,
    )

    if body.soul is not None:
        write_soul(body.soul)
    if body.memories:
        for name, content in body.memories.items():
            try:
                write_memory_file(name, content)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
    return get_memory_bundle()


@router.get("/memory/injection")
async def get_memory_injection_preview(workspace: str | None = None):
    """预览即将注入 Agent 的记忆块（不含大段全文）。"""
    from fnixagent.harness.memory import memory_injection_summary

    extra = ""
    if workspace:
        try:
            from fnixagent.harness.local_context import local_context_prompt

            extra = local_context_prompt(workspace, query="")
        except Exception:
            extra = ""
    return memory_injection_summary(extra=extra)


@router.get("/mcp")
async def get_mcp_config():
    """读取 ~/.fnix/mcp.json。"""
    from fnixagent.harness.config import read_mcp_config

    return {"ok": True, **read_mcp_config()}


@router.put("/mcp")
async def update_mcp_config(body: McpConfigUpdateRequest):
    """更新 ~/.fnix/mcp.json 并尝试热加载 MCP。"""
    from fnixagent.harness.config import write_mcp_config

    payload = {"version": body.version, "servers": body.servers}
    write_mcp_config(payload)

    try:
        from fnixagent.harness.config import reload_harness_mcp

        loaded = reload_harness_mcp()
    except Exception:
        loaded = 0

    return {"ok": True, "loaded": loaded, **payload}


@router.get("/mcp/trust")
async def get_mcp_trust():
    """列出 MCP trust ledger + mcp.json servers（含审批状态）。"""
    from dataclasses import asdict

    from fnixagent.core.mcp.trust import get_entry, list_entries
    from fnixagent.harness.config import list_mcp_servers

    ledger = [asdict(e) for e in list_entries()]
    # Never expose PKCE verifier / token refs to the UI
    for row in ledger:
        row.pop("pkce_verifier", None)
        row.pop("access_token_ref", None)
        row.pop("refresh_token_ref", None)

    servers_out: list[dict[str, Any]] = []
    for server in list_mcp_servers():
        name = str(server.get("name") or "").strip()
        if not name:
            continue
        entry = get_entry(name)
        command = server.get("command")
        cmd = ""
        args: list[str] = []
        if isinstance(command, str):
            parts = command.split()
            cmd = parts[0] if parts else ""
            args = parts[1:]
        elif isinstance(command, list) and command:
            cmd = str(command[0])
            args = [str(x) for x in command[1:]]
        servers_out.append(
            {
                "name": name,
                "enabled": bool(server.get("enabled", True)),
                "command": cmd,
                "args": args,
                "url": str(server.get("url") or ""),
                "trust_status": entry.status if entry else "missing",
                "command_hash": entry.command_hash if entry else "",
                "notes": entry.notes if entry else "",
            }
        )

    return {"ok": True, "servers": servers_out, "ledger": ledger}


@router.post("/mcp/trust/approve")
async def approve_mcp_trust(body: McpTrustApproveRequest):
    """Approve an MCP server for register/connect (fail-closed trust ledger)."""
    from dataclasses import asdict

    from fnixagent.core.mcp.trust import approve_server
    from fnixagent.harness.config import reload_harness_mcp

    auth = body.auth_type if body.auth_type in ("none", "token", "oauth") else "none"
    entry = approve_server(
        body.server_id,
        auth_type=auth,  # type: ignore[arg-type]
        command=body.command,
        args=body.args,
        remote_url=body.remote_url,
        notes=body.notes,
    )
    loaded = 0
    try:
        loaded = reload_harness_mcp()
    except Exception:
        loaded = 0
    payload = asdict(entry)
    payload.pop("pkce_verifier", None)
    payload.pop("access_token_ref", None)
    payload.pop("refresh_token_ref", None)
    return {"ok": True, "loaded": loaded, "entry": payload}


@router.post("/mcp/trust/deny")
async def deny_mcp_trust(body: McpTrustDenyRequest):
    """Deny / revoke an MCP server in the trust ledger."""
    from dataclasses import asdict

    from fnixagent.core.mcp.trust import deny_server

    entry = deny_server(body.server_id, notes=body.notes)
    payload = asdict(entry)
    payload.pop("pkce_verifier", None)
    payload.pop("access_token_ref", None)
    payload.pop("refresh_token_ref", None)
    return {"ok": True, "entry": payload}
