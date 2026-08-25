"""API 路由 — Human-in-the-Loop 审批门。

打通两条此前"已拦截但无法放行"的审批链路:
  1. 工具层: ToolPolicy 拦截 SHELL/DESTRUCTIVE 后, 前端可查 pending → 批准 → agent 重试即通过
  2. 守门层: HumanInTheLoop 门(before_skill_evolution 等) 的 approve/reject

端点:
  GET  /api/v1/hitl/pending                     — 两层待审批汇总
  POST /api/v1/hitl/tool/{key}/approve|reject   — 工具调用审批(idempotency_key)
  POST /api/v1/hitl/gate/{request_id}/approve|reject — 守门审批
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/hitl", tags=["hitl"])


class ApprovalAction(BaseModel):
    """审批动作载荷。"""

    feedback: str = Field(default="", max_length=2000)


@router.get("/pending")
async def list_pending() -> dict[str, Any]:
    """当前所有待人工审批项(工具层 + 守门层)。"""
    from fnixagent.core.skills.evolver import get_hitl
    from fnixagent.core.tools.policy import get_tool_policy

    policy = get_tool_policy()
    hitl = get_hitl()
    return {
        "tool_approvals": policy.pending_approvals(),
        "gates": hitl.get_pending_approvals(),
        "auto_approve_gates": list(hitl.auto_approve_gates),
    }


@router.post("/tool/{idempotency_key}/approve")
async def approve_tool_call(idempotency_key: str, action: ApprovalAction) -> dict[str, Any]:
    """批准被拦截的高风险工具调用(同参重试即放行)。"""
    from fnixagent.core.tools.policy import get_tool_policy

    if not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key is required")
    get_tool_policy().approve(idempotency_key)
    return {"ok": True, "idempotency_key": idempotency_key, "feedback": action.feedback}


@router.post("/tool/{idempotency_key}/reject")
async def reject_tool_call(idempotency_key: str, action: ApprovalAction) -> dict[str, Any]:
    """拒绝高风险工具调用(后续同参调用返回 denied_by_user)。"""
    from fnixagent.core.tools.policy import get_tool_policy

    if not idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key is required")
    get_tool_policy().reject(idempotency_key)
    return {"ok": True, "idempotency_key": idempotency_key, "reason": action.feedback}


@router.post("/gate/{request_id}/approve")
async def approve_gate(request_id: str, action: ApprovalAction) -> dict[str, Any]:
    """批准守门请求(同签名上下文后续直接放行)。"""
    from fnixagent.core.skills.evolver import get_hitl

    ok = await get_hitl().approve(request_id, feedback=action.feedback)
    if not ok:
        raise HTTPException(status_code=404, detail=f"approval request not found: {request_id}")
    return {"ok": True, "request_id": request_id}


@router.post("/gate/{request_id}/reject")
async def reject_gate(request_id: str, action: ApprovalAction) -> dict[str, Any]:
    """拒绝守门请求。"""
    from fnixagent.core.skills.evolver import get_hitl

    ok = await get_hitl().reject(request_id, reason=action.feedback)
    if not ok:
        raise HTTPException(status_code=404, detail=f"approval request not found: {request_id}")
    return {"ok": True, "request_id": request_id}


__all__ = ["router"]
