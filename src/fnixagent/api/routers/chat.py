"""
API 路由 - Agent 对话接口。

支持两种模式:
  1. 传统模式: AgentScheduler(scheduler.process)— 向后兼容
  2. 自进化模式: LangGraph(graph.invoke + MFP 飞轮闭环)— 推荐

模式选择由 app.state 决定:
  - app.state.scheduler 存在 → 传统模式
  - app.state.graph_components 存在 → 自进化模式

Phase 3.2: 接入内容审核(输入/输出双向审核)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import json
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from fnixagent.api.schemas.models import (
    BaseResponse,
    ChatRequest,
    ChatResponse,
    SessionCreate,
    SessionResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_request_ip(request: Request) -> str:
    """从 Request 提取客户端 IP。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _get_user_id_from_request(request: Request) -> int | None:
    """从 Request 的 state 中提取 user_id(若已鉴权)。"""
    return getattr(request.state, "user_id", None)


def _moderate_input(text: str, request: Request) -> None:
    """对用户输入做内容审核(违规时抛 400)。

    Phase 3.2:违规输入在 100ms 内拦截,自动写入审计日志。
    """
    try:
        from fnixagent.services.moderation import get_moderation_service

        svc = get_moderation_service()
        if not svc.config.enabled or not svc.config.input_enabled:
            return
        user_id = _get_user_id_from_request(request)
        ip = _get_request_ip(request)
        result = svc.moderate_input(text, user_id=user_id, ip_address=ip)
        if not result.passed:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "input_blocked",
                    "issues": result.issues,
                    "categories": result.categories,
                    "risk_score": result.risk_score,
                },
            )
    except HTTPException:
        raise
    except Exception:
        # 审核服务异常不应阻断主流程
        pass


def _moderate_output(text: str, request: Request) -> str:
    """对 LLM 输出做内容审核,返回脱敏后的文本。

    Phase 3.2:违规输出不展示,自动写入审计日志。
    """
    try:
        from fnixagent.services.moderation import get_moderation_service

        svc = get_moderation_service()
        if not svc.config.enabled or not svc.config.output_enabled:
            return text
        user_id = _get_user_id_from_request(request)
        ip = _get_request_ip(request)
        result = svc.moderate_output(text, user_id=user_id, ip_address=ip)
        if not result.passed:
            # 违规输出替换为提示信息(不展示原文)
            return "[内容审核:该回复包含违规内容,已被系统拦截]"
        return result.sanitized_text
    except Exception:
        # 审核服务异常不应阻断主流程,返回原文
        return text


def _get_scheduler(request: Request):
    """从应用状态获取 AgentScheduler。"""
    if not hasattr(request.app.state, "scheduler"):
        raise RuntimeError("Scheduler not initialized")
    return request.app.state.scheduler


def _get_graph_components(request: Request):
    """从应用状态获取 GraphComponents(自进化模式)。

    若未初始化则返回 None。
    """
    return getattr(request.app.state, "graph_components", None)


@router.post("/session", response_model=SessionResponse)
async def create_session(request: SessionCreate, http_request: Request):
    """创建新会话。"""
    scheduler = _get_scheduler(http_request)
    session_id = str(uuid.uuid4())[:16]

    # 重置记忆(新会话)
    scheduler.reset_session()

    return SessionResponse(
        id=session_id,
        title=request.title or "New Session",
        status="active",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest, http_request: Request):
    """发送消息并获取 Agent 响应(非流式)。"""
    scheduler = _get_scheduler(http_request)

    # Phase 3.2: 输入审核
    _moderate_input(request.user_input, http_request)

    # 调用 Agent 调度器处理用户输入
    response = scheduler.process(
        user_input=request.user_input,
        session_id=str(request.session_id) if request.session_id else "",
    )

    # Phase 3.2: 输出审核 + 脱敏
    final_answer = _moderate_output(response.final_answer, http_request)

    return ChatResponse(
        session_id=str(request.session_id or 1),
        message_id=0,
        response=final_answer,
        trace_id=response.trace.trace_id if response.trace else "",
        duration_ms=response.duration_ms,
        stats=response.stats,
    )


@router.post("/stream")
async def stream_chat(request: ChatRequest, http_request: Request):
    """流式对话 — 复用 WorkPipeline 9 步流水线（work_mode=ask）。

    chat 模式与 work 模式区别仅在 work_mode：chat=ask（只问答，不写盘）。
    9 步流水线全跑：安全 → 记忆 → 意图 → KTG/STP → AgenticLoop → 反思 → 审核 → MFP。
    输出格式与 /api/v1/work/stream 完全一致（chunk_type + content + done + trace_id）。
    """
    # Phase 3.2: 输入审核
    _moderate_input(request.user_input, http_request)

    # Phase 2.10: 记录聊天消息指标
    try:
        from fnixagent.core.observability.metrics import record_chat_message

        mode = os.getenv("FNIXAGENT_MODE", "legacy").lower()
        record_chat_message(mode=mode)
    except Exception:
        pass

    async def generate():
        """流式生成器 — 复用 work_pipeline.run_work_stream（9 步流水线）"""
        try:
            from fnixagent.services.llm_policy import principal_is_admin, resolve_llm_for_request
            from fnixagent.services.work_pipeline import run_work_stream

            workspace = None
            if request.context and isinstance(request.context, dict):
                workspace = request.context.get("workspace") or request.context.get(
                    "workspace_path"
                )
            workspace = workspace or os.getenv("FNIXAGENT_WORKSPACE") or os.getcwd()

            raw_llm = request.llm.model_dump(exclude_none=True) if request.llm else None
            llm_dict, llm_err = resolve_llm_for_request(
                raw_llm,
                is_admin=principal_is_admin(http_request),
            )
            if llm_err:
                yield _chat_ndjson("error", llm_err, True)
                return

            trace_id = ""
            async for event in run_work_stream(
                user_input=request.user_input,
                workspace=workspace,
                llm=llm_dict,
                session_id=str(request.session_id) if request.session_id else None,
                user_id="desktop",
                app_state=http_request.app.state,
                work_mode="ask",
            ):
                et = event.get("type", "")
                data = event.get("data", "")

                if isinstance(data, dict) and data.get("trace_id"):
                    trace_id = data["trace_id"]

                if et == "evolution":
                    yield _chat_ndjson("evolution", data, False, trace_id)
                elif et == "mission":
                    yield _chat_ndjson("mission", data, False, trace_id)
                elif et == "pipeline":
                    yield _chat_ndjson("pipeline", data, False, trace_id)
                elif et == "thinking":
                    yield _chat_ndjson("thought", str(data), False, trace_id)
                elif et == "tool_call":
                    yield _chat_ndjson("action", data, False, trace_id)
                elif et == "tool_result":
                    yield _chat_ndjson("observation", str(data), False, trace_id)
                elif et == "text":
                    final = _moderate_output(str(data), http_request)
                    yield _chat_ndjson("text", final, True, trace_id)
                elif et == "done":
                    yield _chat_ndjson("done", data, True, trace_id)
                elif et == "error":
                    yield _chat_ndjson("error", str(data), True, trace_id)
                else:
                    yield _chat_ndjson(et or "event", data, False, trace_id)

        except Exception as e:
            yield _chat_ndjson("error", str(e), True)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


def _chat_ndjson(chunk_type: str, content: Any, done: bool = False, trace_id: str = "") -> str:
    """与 work._ndjson 一致的 NDJSON 行序列化。"""
    payload: dict[str, Any] = {
        "chunk_type": chunk_type,
        "content": content,
        "done": done,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return json.dumps(payload, ensure_ascii=False) + "\n"


@router.get("/session/{session_id}/history")
async def get_session_history(session_id: int, http_request: Request):
    """获取会话历史消息(从短期记忆中提取)。"""
    scheduler = _get_scheduler(http_request)
    ctx = scheduler._ctx

    # 从记忆管理器获取短期记忆
    messages = ctx.memory_manager._short.get_messages()

    return [
        {
            "id": i,
            "session_id": session_id,
            "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
            "content": msg.content,
            "content_type": "text",
            "created_at": "2025-01-01T00:00:00",
        }
        for i, msg in enumerate(messages)
    ]


@router.delete("/session/{session_id}")
async def close_session(session_id: int, http_request: Request):
    """关闭会话(清理短期记忆)。"""
    scheduler = _get_scheduler(http_request)
    scheduler.reset_session()
    return BaseResponse(success=True, message="Session closed")


@router.get("/session/{session_id}/context")
async def get_session_context(session_id: int, http_request: Request):
    """获取会话上下文。"""
    scheduler = _get_scheduler(http_request)
    ctx = scheduler._ctx

    return BaseResponse(
        data={
            "session_id": session_id,
            "tool_count": ctx.tool_registry.count,
            "available_tools": [t.name for t in ctx.tool_registry.list_tools()],
            "llm_providers": ctx.llm_router.providers,
        }
    )


# ===========================================================================
# 自进化模式端点(LangGraph + KTG + STP + MFP)
# ===========================================================================


@router.post("/evolve")
async def evolve_message(request: ChatRequest, http_request: Request):
    """自进化模式: 使用 LangGraph + MFP 飞轮闭环处理消息。

    完整闭环:
        飞轮 ① 感知-执行 → 飞轮 ② 知识固化 → (可选)飞轮 ③ 元反思

    需要 app.state.graph_components 已初始化(由 build_graph() 产出)。
    """
    from fnixagent.services.engine import process_with_graph

    components = _get_graph_components(http_request)
    if components is None:
        return BaseResponse(
            success=False,
            message="自进化模式未初始化,请先调用 build_graph()",
        )

    session_id = str(request.session_id) if request.session_id else None
    result = process_with_graph(
        user_input=request.user_input,
        components=components,
        session_id=session_id,
    )

    trace = result.get("trace")
    solidified = result.get("solidified", {})
    reflected = result.get("reflected")

    return BaseResponse(
        success=True,
        message="自进化处理完成",
        data={
            "answer": result.get("answer", ""),
            "trace_id": trace.trace_id if trace else "",
            "task_success": trace.success if trace else False,
            "duration_ms": trace.duration_ms if trace else 0,
            "tool_calls": trace.tool_calls if trace else [],
            "concept_path": trace.concept_path if trace else [],
            "solidified": solidified,
            "reflected": reflected,
        },
    )


@router.get("/topology/stats")
async def get_topology_stats(http_request: Request):
    """获取知识拓扑图统计信息。"""
    components = _get_graph_components(http_request)
    if components is None:
        return BaseResponse(success=False, message="自进化模式未初始化")

    stats = components.topology_graph.stats()
    search_stats = components.search_engine.search_stats("")
    return BaseResponse(
        data={
            "topology": stats,
            "search": search_stats,
            "is_cold_start": components.search_engine.is_cold_start(),
        }
    )


@router.get("/topology/nodes")
async def list_topology_nodes(
    http_request: Request,
    layer: str | None = None,
    node_type: str | None = None,
):
    """列举拓扑图节点。"""
    components = _get_graph_components(http_request)
    if components is None:
        return BaseResponse(success=False, message="自进化模式未初始化")

    from fnixagent.core.types import NodeType, TopologyLayer

    layer_enum = TopologyLayer(layer) if layer else None
    type_enum = NodeType(node_type) if node_type else None
    nodes = components.topology_graph.list_nodes(
        layer=layer_enum,
        node_type=type_enum,
        include_deprecated=False,
    )
    return BaseResponse(
        data=[
            {
                "node_id": n.node_id,
                "layer": n.layer.value,
                "node_type": n.node_type.value,
                "name": n.name,
                "weight": round(n.weight, 4),
                "confidence": round(n.confidence, 4),
                "use_count": n.use_count,
                "deprecated": n.deprecated,
                "skill_binding": n.skill_binding,
            }
            for n in nodes
        ]
    )


@router.post("/flywheel/reflect")
async def trigger_reflection(http_request: Request):
    """手动触发飞轮 ③ 元反思。"""
    components = _get_graph_components(http_request)
    if components is None:
        return BaseResponse(success=False, message="自进化模式未初始化")

    result = components.flywheel_reflection.run()
    return BaseResponse(success=True, data=result)


@router.post("/flywheel/evolve")
async def trigger_evolution(http_request: Request):
    """手动触发飞轮 ④ 爬坡进化。"""
    components = _get_graph_components(http_request)
    if components is None:
        return BaseResponse(success=False, message="自进化模式未初始化")

    try:
        result = components.flywheel_climbing.run()
        return BaseResponse(success=True, data=result)
    except Exception as e:
        return BaseResponse(success=False, message=f"进化失败: {e}")


@router.get("/traces/stats")
async def get_trace_stats(http_request: Request):
    """获取轨迹统计信息。"""
    components = _get_graph_components(http_request)
    if components is None:
        return BaseResponse(success=False, message="自进化模式未初始化")

    stats = components.trace_store.stats()
    return BaseResponse(data=stats)


# ---------------------------------------------------------------------------
# P1-4: AgentRunner 入口(新增,不替换现有端点)
# ---------------------------------------------------------------------------


def _build_agent_loop_for_stream(
    http_request: Request,
    workspace: str | None = None,
    llm: dict | None = None,
):
    """为流式输出构建 AgenticLoop（含办公工具 + 可选请求级 LLM）。"""
    try:
        from fnixagent.services.work_agent import build_work_agent_loop

        root = workspace or os.getenv("FNIXAGENT_WORKSPACE") or os.getcwd()
        return build_work_agent_loop(workspace_root=root, llm=llm)
    except Exception:
        return None


def _get_runner(request: Request):
    """从应用状态获取 AgentRunner(若已初始化)。

    P1-4: app.state.agent_runner 存在时使用 Runner 入口;
    否则返回 None(调用方应回退到 scheduler/graph_components)。
    """
    return getattr(request.app.state, "agent_runner", None)


@router.post("/runner", response_model=BaseResponse)
async def runner_chat(request: ChatRequest, http_request: Request):
    """AgentRunner 统一入口(P1-4)。

    支持 auto/legacy/graph 三种模式,由 app.state.agent_runner 决定。
    若 runner 未初始化,回退到 scheduler 模式。
    """
    runner = _get_runner(http_request)
    if runner is None:
        # 回退:scheduler 模式
        return await send_message(request, http_request)

    from fnixagent.core.runner import RunConfig

    config = RunConfig(
        mode="auto",
        user_id="",
        session_id=str(request.session_id) if request.session_id else "",
    )

    result = runner.run(request.user_input, config=config)

    return BaseResponse(
        success=result.success,
        message=result.answer,
        data={
            "trace_id": result.trace_id,
            "thread_id": result.thread_id,
            "duration_ms": result.duration_ms,
            "steps_taken": result.steps_taken,
            "error": result.error or None,
            "usage": result.to_dict().get("usage"),
        },
    )
