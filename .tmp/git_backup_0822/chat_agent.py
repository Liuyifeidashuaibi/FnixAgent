"""API 路由 - Agent 流式聊天端点。

提供基于 NDJSON 的流式编码 Agent 聊天接口,
支持实时反馈 Agent 的思考、计划、执行和审查过程。

设计要点:
  - 流式响应: 使用 StreamingResponse 返回 NDJSON (每行一个 JSON 对象)
  - 事件类型: thinking / plan / step_start / step_end / file_change / message / done
  - 智能体复用: 通过 IDEServer 懒加载 CodingAgent 单例
  - 鉴权: 复用 verify_jwt_token 依赖
  - router 前缀: /chat (由主流程在 main.py 注册时挂到 /api/v1 下)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fnixagent.api.routers.auth import verify_jwt_token_optional
from fnixagent.core.code.agent import (
    CodingAgent,
    CodingTask,
)
from fnixagent.core.code.server import IDEServer
from fnixagent.harness.paths import default_workspace

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================================
# IDEServer 单例管理
# ============================================================================

_server: IDEServer | None = None
_server_workspace: str | None = None


def get_server(workspace: str | None = None) -> IDEServer:
    """懒加载 IDEServer 单例。

    首次调用, 或请求的 workspace 与当前实例不一致时创建新实例;
    其余调用直接复用单例。

    Args:
        workspace: 工作区路径, 缺省取默认工作区(~/.fnix/workspaces/default)。

    Returns:
        IDEServer 实例。
    """
    global _server, _server_workspace
    ws = workspace or str(default_workspace())
    if _server is None or _server_workspace != ws:
        _server = IDEServer(project_root=ws)
        _server_workspace = ws
    return _server


# ============================================================================
# 请求模型
# ============================================================================


class ChatMessage(BaseModel):
    """聊天消息。"""

    role: str  # "user" 或 "assistant"
    content: str


class ChatAgentRequest(BaseModel):
    """Agent 聊天请求。

    Attributes:
        messages: 对话消息列表, 每条消息包含 role 和 content。
        workspace: 可选的工作区路径, 指定 Agent 操作的代码项目根目录。
        preview: True 时写操作 dry-run（先审后写），由客户端 Accept 落盘。
        session_id: Harness session ID（可选，用于持久化 Code 任务）。
        llm: Desktop BYOK 请求级 LLM 覆盖。
    """

    messages: list[ChatMessage]
    workspace: str | None = None
    preview: bool = True
    session_id: str | None = None
    llm: dict[str, Any] | None = None


class _AdapterLLMBackend:
    """Wrap LLMAdapter for CodingAgent._call_llm."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    async def complete(self, payload: Any, **kwargs: Any) -> str:
        messages = payload.get("messages", []) if isinstance(payload, dict) else payload
        result = await self._adapter.chat(messages if isinstance(messages, list) else [])
        choices = result.get("choices") or [{}]
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")


# ============================================================================
# 流式响应辅助
# ============================================================================


def _ndjson_line(data: dict[str, Any]) -> str:
    """将字典序列化为一行 NDJSON 字符串。

    Args:
        data: 待序列化的字典。

    Returns:
        单行 JSON 字符串 (末尾带换行符)。
    """
    return json.dumps(data, ensure_ascii=False, default=str) + "\n"


def _is_admin_payload(payload: dict | None) -> bool:
    """从 JWT payload / 本地 dev principal 判断是否管理员。

    与 work.py 的 principal_is_admin(request) 语义对齐：
      - role == "admin" 或 scope 含 "admin" → True
      - 本地 dev（无 Token，via=dev）且服务端已配置 LLM Key → True
    """
    if not payload or not isinstance(payload, dict):
        return False
    if payload.get("role") == "admin" or "admin" in (payload.get("scope") or []):
        return True
    if payload.get("via") == "dev":
        from fnixagent.services.llm_policy import server_llm_configured

        return server_llm_configured()
    return False


# ============================================================================
# 流式 Agent 聊天端点
# ============================================================================


@router.post("/agent")
async def chat_agent(
    req: ChatAgentRequest,
    _payload: dict = Depends(verify_jwt_token_optional),
):
    """Agent 流式聊天端点。

    接收自然语言编码任务, 以 NDJSON 流式返回 Agent 的思考、计划、
    执行步骤和最终结果。

    请求体:
        messages: 对话消息列表 ([{"role": "user"|"assistant", "content": "..."}])
        workspace: 可选的工作区路径

    流式响应 (NDJSON, 每行一个 JSON 对象):
        {"type": "thinking", "content": "..."}  - Agent 思考过程
        {"type": "plan", "steps": [...]}        - 执行计划
        {"type": "step_start", "step": {...}}   - 步骤开始
        {"type": "step_end", "step": {...}}     - 步骤完成
        {"type": "file_change", "path": "...", "action": "...", "diff": "..."}  - 文件变更
        {"type": "message", "content": "..."}   - 文本消息
        {"type": "done", "status": "completed"|"failed", "changes": [...]}  - 最终结果
    """
    # B3 修复：从 JWT payload 判断 admin，而非用 api_only_mode 反向推断。
    # 之前 is_admin=not api_only_mode() 导致 admin 用户（owner 登录）也被强制 BYOK，
    # chat/agent 在无自带 key 时直接 failed，而 work/jobs 用 principal_is_admin 却正常。
    is_admin = _is_admin_payload(_payload)
    return StreamingResponse(
        _stream_agent_response(req, is_admin=is_admin),
        media_type="application/x-ndjson",
    )


async def _stream_agent_response(
    req: ChatAgentRequest,
    is_admin: bool = False,
) -> AsyncGenerator[str, None]:
    """流式生成 Agent 响应事件。

    复制 CodingAgent.execute_task 的 Plan → Execute → Review 流程,
    在每个阶段之间产出 NDJSON 事件, 实现实时流式反馈。

    Args:
        req: 聊天请求。
        is_admin: 请求方是否为管理员（决定 BYOK / 服务端 Key 解析）。

    Yields:
        NDJSON 格式的事件行。
    """
    # 获取 IDEServer 并确保初始化
    server = get_server(req.workspace)
    server._ensure_initialized()
    agent: CodingAgent = server._agent  # type: ignore[assignment]

    from fnixagent.services.llm_policy import resolve_llm_for_request
    from fnixagent.services.work_agent import adapter_from_llm_override

    llm_raw = dict(req.llm or {})
    llm_dict, llm_err = resolve_llm_for_request(
        llm_raw,
        is_admin=is_admin,
    )
    if llm_err:
        yield _ndjson_line(
            {
                "type": "done",
                "status": "failed",
                "changes": [],
                "error": llm_err,
            }
        )
        return
    if llm_dict is not None:
        try:
            agent._llm = _AdapterLLMBackend(adapter_from_llm_override(llm_dict))
        except Exception as exc:
            yield _ndjson_line(
                {
                    "type": "done",
                    "status": "failed",
                    "changes": [],
                    "error": f"LLM 配置无效: {exc}",
                }
            )
            return

    # 行业编码工具-style review-before-apply
    if getattr(agent, "_tools", None) is not None:
        agent._tools.preview_mode = bool(req.preview)

    # 提取用户最后一条消息作为任务描述
    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        yield _ndjson_line(
            {
                "type": "done",
                "status": "failed",
                "changes": [],
                "error": "未提供用户消息",
            }
        )
        return

    task_description = user_messages[-1].content
    workspace = req.workspace or str(default_workspace())
    sid = req.session_id or f"code-{uuid.uuid4().hex[:12]}"

    from fnixagent.harness.session import get_session_store
    from fnixagent.harness.workspace import ensure_project_layout

    try:
        ensure_project_layout(workspace)
    except Exception:
        pass

    store = get_session_store()
    title = task_description.splitlines()[0][:80] or "Code 任务"
    if store.get(sid) is None:
        store.create(
            session_id=sid,
            user_id="desktop",
            workspace=workspace,
            title=title,
            description=task_description,
            mode="code",
        )
    else:
        store.update(sid, status="running", result="")

    # fnix-local PDG 上下文（sidecar 离线时静默跳过）
    local_prompt = ""
    try:
        from fnixagent.harness.local_context import local_context_prompt

        local_prompt = local_context_prompt(workspace, query=task_description[:800])
    except Exception:
        local_prompt = ""

    if local_prompt:
        task_description = f"{task_description}\n{local_prompt}"

    # Code 模式路径契约：工程文件写项目相对路径，勿进 Work artifacts
    task_description = (
        f"{task_description}\n\n"
        "【Code 写盘规则】按任务指定文件名写入项目根/相对路径；"
        "禁止写入 `.fnix/artifacts/`（除非用户明确要求）。"
        "测试文件与实现文件须同级或可 import。"
    )

    task = CodingTask(description=task_description)

    changes: list[dict[str, Any]] = []
    session_status = "running"
    session_result = ""

    try:
        # Unified RunEngine over CodingAgent.streaming_execute (Plan→Execute→Review→Heal).
        from fnixagent.core.run import RunCheckpointStore, RunEngine
        from fnixagent.core.run.engine import code_agent_source

        engine = RunEngine(store=RunCheckpointStore())
        async for event in engine.run_stream(
            code_agent_source(agent, task),
            channel="code",
            session_id=sid,
            # Spec 4: meta 持久化, resume 时用于恢复 workspace / llm
            meta={
                "user_input": task_description[:500],
                "workspace": workspace,
                "llm": llm_dict,
            },
        ):
            if event.type == "file_change" and isinstance(event.data, dict):
                changes.append(
                    {
                        "path": event.data.get("path"),
                        "action": event.data.get("action"),
                        "diff": event.data.get("diff"),
                        "content": event.data.get("content"),
                        "old_content": event.data.get("old_content"),
                    }
                )
            line = event.to_code_ndjson()
            if event.type == "done":
                line["changes"] = changes
                line["session_id"] = sid
                if line.get("status") == "failed":
                    session_status = "failed"
                    session_result = str(line.get("error") or line.get("review_notes") or "")
                else:
                    session_status = "completed"
                    session_result = "ok"
            yield _ndjson_line(line)

    except Exception as exc:
        session_status = "failed"
        session_result = str(exc)
        yield _ndjson_line(
            {
                "type": "message",
                "content": f"Agent 执行异常: {type(exc).__name__}: {exc}",
            }
        )
        yield _ndjson_line(
            {
                "type": "done",
                "status": "failed",
                "changes": changes,
                "error": str(exc),
                "session_id": sid,
            }
        )

    finally:
        try:
            store.update(sid, status=session_status, result=session_result[:4000])
        except Exception:
            pass
        # 清理活跃任务
        agent._active_tasks.pop(task.id, None)
        agent._task_changesets.pop(task.id, None)


# ============================================================================
# Accept / Apply — Desktop Diff 验收后落盘
# ============================================================================


class AgentFileChange(BaseModel):
    """单个文件变更（来自 file_change 事件）。"""

    path: str
    action: str = "modify"  # create | modify | delete
    content: str | None = None
    old_content: str | None = None


class AgentApplyRequest(BaseModel):
    """批量应用 Code Agent 预览变更。"""

    workspace: str
    changes: list[AgentFileChange]


@router.post("/agent/apply")
async def agent_apply_changes(
    req: AgentApplyRequest,
    _payload: dict = Depends(verify_jwt_token_optional),
):
    """将 preview 模式下的 file_change 真正写入 workspace。"""
    from fnixagent.core.code.diff import ChangeSetBuilder, DiffEngine
    from fnixagent.harness.changeset_journal import save_changeset

    if not req.changes:
        return {"ok": True, "applied": 0}

    engine = DiffEngine(project_root=req.workspace)
    builder = ChangeSetBuilder("Desktop accept")

    for ch in req.changes:
        action = (ch.action or "modify").strip().lower()
        if action == "create":
            builder.create_file(ch.path, ch.content or "")
        elif action == "delete":
            builder.delete_file(ch.path, ch.old_content or "")
        else:
            builder.modify_file(ch.path, ch.old_content or "", ch.content or "")

    cs = builder.build()
    result = await engine.apply(cs, dry_run=False)
    if result.success:
        try:
            save_changeset(
                req.workspace,
                cs.id,
                [
                    {
                        "path": ch.path,
                        "action": (ch.action or "modify").strip().lower(),
                        "content": ch.content,
                        "old_content": ch.old_content,
                    }
                    for ch in req.changes
                ],
            )
        except Exception:
            pass
    err = result.error or ""
    conflict = (not result.success) and (
        "冲突" in err
        or "conflict" in err.lower()
        or "并发编辑" in err
        or "内容已变更" in err
        or "文件已存在" in err
    )
    return {
        "ok": result.success,
        "applied": len(req.changes) if result.success else 0,
        "error": err,
        "conflict": conflict,
        "failed_file": getattr(result, "failed_file", None),
        "changeset_id": cs.id,
    }


class AgentRollbackRequest(BaseModel):
    """撤销最近一次（或指定）Accept 变更。"""

    workspace: str
    changeset_id: str | None = None


@router.post("/agent/rollback")
async def agent_rollback_changes(
    req: AgentRollbackRequest,
    _payload: dict = Depends(verify_jwt_token_optional),
):
    """一键撤销已 Accept 的变更集（读 `{workspace}/.fnix/changesets`）。"""
    from fnixagent.harness.changeset_journal import rollback_persisted_async

    return await rollback_persisted_async(req.workspace, req.changeset_id)
