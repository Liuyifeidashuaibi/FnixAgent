"""桌面驱动 API — 前端桌面面板与 cua-driver 交互（GUI_DRIVER_DESIGN.md P2/P3）。

  GET  /desktop/state        桌面截图 + 模式 + degraded
  GET  /desktop/apps        应用列表
  GET  /desktop/windows     窗口列表
  POST /desktop/action      动作转发（click/type/hotkey/scroll/launch/kill/bring_front/state）
  POST /desktop/confirm     高危动作确认
  GET  /desktop/events      事件时间线（增量）

安全：localhost 服务 + 上游网关 token 鉴权（与 browser router 一致）。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fnixagent.core.tools.desktop import DesktopDriver, _build_args, _OP_TO_TOOL

router = APIRouter(prefix="/desktop", tags=["desktop"])

_driver = DesktopDriver.instance()


class ActionRequest(BaseModel):
    op: Literal[
        "state", "screen_size", "apps", "windows", "window_state",
        "click", "type", "hotkey", "scroll", "launch", "kill", "bring_front",
    ]
    x: int | None = None
    y: int | None = None
    text: str | None = None
    keys: str | None = None
    direction: str | None = None
    amount: int | None = None
    pid: int | None = None
    window_id: int | None = None
    name: str | None = None
    on_screen_only: bool | None = None


class ConfirmRequest(BaseModel):
    confirmation_id: str = Field(..., min_length=1)
    approve: bool


def _as_action(op: str) -> str:
    """前端 op 名 → desktop_* op 名。"""
    return {
        "state": "desktop_state",
        "screen_size": "desktop_screen_size",
        "apps": "desktop_apps",
        "windows": "desktop_windows",
        "window_state": "desktop_window_state",
        "click": "desktop_click",
        "type": "desktop_type",
        "hotkey": "desktop_hotkey",
        "scroll": "desktop_scroll",
        "launch": "desktop_launch",
        "kill": "desktop_kill",
        "bring_front": "desktop_bring_front",
    }[op]


@router.get("/state")
async def desktop_state() -> dict[str, Any]:
    res = await _driver.call("get_desktop_state", {}, label="desktop_state")
    return {
        "ok": res.ok,
        "mode": _driver.mode,
        "screenshot_b64": res.screenshot_b64,
        "degraded": res.degraded,
        "error": res.error,
    }


@router.get("/screen_size")
async def desktop_screen_size() -> dict[str, Any]:
    res = await _driver.call("get_screen_size", {}, label="desktop_screen_size")
    return {"ok": res.ok, "summary": res.summary, "degraded": res.degraded, "error": res.error}


@router.get("/apps")
async def desktop_apps() -> dict[str, Any]:
    res = await _driver.call("list_apps", {}, label="desktop_apps")
    return {"ok": res.ok, "summary": res.summary, "data": res.structured, "degraded": res.degraded, "error": res.error}


@router.get("/windows")
async def desktop_windows(on_screen_only: bool | None = None) -> dict[str, Any]:
    args: dict[str, Any] = {}
    if on_screen_only is not None:
        args["on_screen_only"] = on_screen_only
    res = await _driver.call("list_windows", args, label="desktop_windows")
    return {"ok": res.ok, "summary": res.summary, "data": res.structured, "degraded": res.degraded, "error": res.error}


@router.post("/action")
async def desktop_action(req: ActionRequest) -> dict[str, Any]:
    op = _as_action(req.op)
    action = {
        "x": req.x,
        "y": req.y,
        "text": req.text,
        "keys": req.keys,
        "direction": req.direction,
        "amount": req.amount,
        "pid": req.pid,
        "window_id": req.window_id,
        "name": req.name,
        "on_screen_only": req.on_screen_only,
    }
    entry = _OP_TO_TOOL.get(op)
    if entry is None:
        return {"ok": False, "error": f"未知桌面操作: {req.op}"}
    tool, high_risk = entry
    args = _build_args(op, action)
    if args is None:
        return {"ok": False, "error": f"{req.op} 必填参数缺失"}
    res = await _driver.call(tool, args, high_risk=high_risk, label=op)
    return {
        "ok": res.ok,
        "summary": res.summary,
        "screenshot_b64": res.screenshot_b64,
        "degraded": res.degraded,
        "error": res.error,
        "requires_confirmation": res.requires_confirmation,
        "confirmation_id": res.confirmation_id,
        "data": res.structured,
    }


@router.post("/confirm")
async def desktop_confirm(req: ConfirmRequest) -> dict[str, Any]:
    _driver.confirm(req.confirmation_id, req.approve)
    return {"ok": True, "confirmation_id": req.confirmation_id, "approve": req.approve}


@router.get("/events")
async def desktop_events(since: int = 0) -> dict[str, Any]:
    events, last_id = await _driver.recent_events(since)
    return {"ok": True, "events": events, "last_id": last_id}
