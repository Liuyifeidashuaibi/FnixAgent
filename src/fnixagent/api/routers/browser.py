"""内置浏览器 API — 前端与 Playwright 会话交互。

  GET  /browser/state?since=N   轮询会话状态（version 不变时轻量返回）
  POST /browser/navigate        用户地址栏导航
  POST /browser/action          用户在截图上的点击/滚动/历史/视口转发
  POST /browser/close           关闭浏览器释放资源
  POST /browser/trajectory/...  录制 / 重放动作轨迹（Phase 5）

安全：localhost 服务 + 上游网关 token 鉴权；URL 协议白名单在 BrowserSession 内校验。
轨迹里的输入内容默认不落盘（演示登录时那就是密码），重放时当次传入。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fnixagent.core.tools.browser import BrowserSession
from fnixagent.core.tools.browser_trajectory import (
    Trajectory,
    TrajectoryRecorder,
    TrajectoryReplayer,
)

router = APIRouter(prefix="/browser", tags=["browser"])

_session = BrowserSession.instance()


class NavigateRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)
    # L1 新域确认闸：拦截后携令牌重试（单次消费）
    confirmation_id: str | None = None


class ActionRequest(BaseModel):
    """用户在浏览器面板上的操作转发。

    click/scroll 坐标为页面原始坐标（前端按显示缩放比换算后传入）。
    """

    type: Literal["click", "scroll", "back", "forward", "refresh", "viewport"]
    x: int | None = None
    y: int | None = None
    direction: Literal["up", "down"] | None = None
    amount: int | None = None
    width: int | None = None
    height: int | None = None


@router.get("/state")
async def browser_state(since: int = 0, screenshot: bool = True) -> dict[str, Any]:
    """前端轮询：version 未变时返回轻量响应（省截图带宽）。"""
    st = _session.state
    if st.version == since:
        return {
            "ok": True,
            "unchanged": True,
            "version": st.version,
            "busy": st.busy,
            "driver_mode": st.driver_mode,
        }
    payload = st.to_dict(include_screenshot=screenshot)
    payload["unchanged"] = False
    return payload


@router.post("/navigate")
async def browser_navigate(req: NavigateRequest) -> dict[str, Any]:
    st = await _session.navigate(req.url, confirmation_id=req.confirmation_id)
    payload = st.to_dict()
    payload["unchanged"] = False
    if st.error and not st.requires_confirmation:
        payload["ok"] = False
    return payload


@router.post("/action")
async def browser_action(req: ActionRequest) -> dict[str, Any]:
    st: Any = None
    if req.type == "click":
        if req.x is None or req.y is None:
            return {"ok": False, "error": "click 需要 x/y 坐标"}
        st = await _session.click(req.x, req.y)
    elif req.type == "scroll":
        st = await _session.scroll(req.direction or "down", req.amount or 480)
    elif req.type in ("back", "forward", "refresh"):
        st = await _session.history(req.type)
    elif req.type == "viewport":
        st = await _session.set_viewport(
            req.width or st_width_default(), req.height or st_height_default()
        )
    if st is None:
        return {"ok": False, "error": f"未知操作: {req.type}"}
    payload = st.to_dict()
    payload["unchanged"] = False
    if st.error:
        payload["ok"] = False
    return payload


@router.post("/close")
async def browser_close() -> dict[str, Any]:
    await _session.close()
    return {"ok": True}


# ── 域名信任策略 ──────────────────────────────────────────────────────
#
# 判定逻辑早就接在 navigate 上了，但**没有任何接口让用户配置**——只能手工
# 去改 ~/.local/share/fnixagent/browser_policy.json。文档写的是"用户可配置
# 的受信任域列表"（对标 Trae「配置受信任的域」），代码里却是"用户得会找
# 隐藏文件并手写 JSON"。这是文档与实现不一致，补上接口让名副其实。


class DomainPolicyPatch(BaseModel):
    mode: Literal["ask_new", "allowlist", "denylist", "open"] | None = None
    allowed: list[str] | None = None
    denied: list[str] | None = None
    persist_approvals: bool | None = None


class DomainRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)


@router.get("/domain-policy")
async def domain_policy_get() -> dict[str, Any]:
    """当前域名策略，外加各模式的人话说明——前端设置面板直接消费。"""
    from fnixagent.core.tools.browser_policy import MODES, MODE_LABELS, load_policy

    p = load_policy()
    return {
        "ok": True,
        "policy": p.to_dict(),
        "modes": [{"id": m, "label": MODE_LABELS[m]} for m in MODES],
        # 两条硬规则必须在界面上说清楚，否则用户配了 allowlist 会发现本地
        # 开发全挂，然后以为功能坏了
        "rules": [
            "本机地址（localhost / 127.0.0.1）任何模式都不拦截",
            "拒绝列表在所有模式下生效，包括开放模式",
        ],
    }


@router.put("/domain-policy")
async def domain_policy_put(patch: DomainPolicyPatch) -> dict[str, Any]:
    from fnixagent.core.tools.browser_policy import load_policy, save_policy

    p = load_policy()
    if patch.mode is not None:
        p.mode = patch.mode
    if patch.allowed is not None:
        p.allowed = [d.strip().lower() for d in patch.allowed if d.strip()]
    if patch.denied is not None:
        p.denied = [d.strip().lower() for d in patch.denied if d.strip()]
    if patch.persist_approvals is not None:
        p.persist_approvals = patch.persist_approvals
    save_policy(p)
    # navigate 每次都重新 load_policy，所以这里不用通知会话——改完立即生效
    return {"ok": True, "policy": p.to_dict()}


@router.post("/domain-policy/approve")
async def domain_policy_approve(req: DomainRequest) -> dict[str, Any]:
    from fnixagent.core.tools.browser_policy import load_policy, save_policy

    p = load_policy()
    p.approve(req.domain)
    save_policy(p)
    return {"ok": True, "approved": p.approved}


@router.post("/domain-policy/revoke")
async def domain_policy_revoke(req: DomainRequest) -> dict[str, Any]:
    from fnixagent.core.tools.browser_policy import load_policy, save_policy

    p = load_policy()
    removed = p.revoke(req.domain)
    if removed:
        save_policy(p)
    return {"ok": True, "removed": removed, "approved": p.approved}


@router.post("/domain-policy/check")
async def domain_policy_check(req: DomainRequest) -> dict[str, Any]:
    """试算：这个域名现在会被放行、拒绝还是询问。不改任何状态。

    用户配白名单时最容易踩的坑是"配完才发现自己常用的站被挡了"。先在设置里
    试算一遍，比等 AI 跑一半撞墙再回头改要省事得多。
    """
    from fnixagent.core.tools.browser_policy import load_policy

    verdict, why = load_policy().decide(req.domain, set())
    return {"ok": True, "domain": req.domain, "verdict": verdict, "reason": why}


class RealRenderRequest(BaseModel):
    """真实渲染窗口登记（Phase 4）。

    前端用 Tauri 打开带 CDP 的浏览器窗口后，把端口告知后端；后端 attach 到
    同一个页面实例，于是用户看到的与 AI 驱动的是同一个浏览器——而不是"看着
    截图猜"。port=0 表示不可用（非 Windows），后端回退托管 Chromium + 截图流。
    """

    port: int = Field(0, ge=0, le=65535)


@router.post("/real-render")
async def browser_real_render(req: RealRenderRequest) -> dict[str, Any]:
    from fnixagent.core.tools.driver_router import get_driver_router

    router_ = get_driver_router()
    router_.set_builtin_cdp_port(req.port or None)
    # 端口变了就必须重建会话，否则还连在旧的 headless 实例上
    if req.port:
        await _session.close()
    return {
        "ok": True,
        "real_render": bool(req.port),
        "port": req.port or None,
    }


@router.get("/real-render")
async def browser_real_render_state() -> dict[str, Any]:
    """当前真实渲染状态：前端据此决定显示真实窗口提示还是截图流。"""
    from fnixagent.core.tools.driver_router import get_driver_router

    port = get_driver_router().builtin_cdp_port
    return {
        "ok": True,
        "real_render": port is not None,
        "port": port,
        "driver_mode": _session.state.driver_mode,
    }


@router.get("/events")
async def browser_events(since: int = 0) -> dict[str, Any]:
    """驱动事件时间线（降级/模式切换等），与桌面事件共用 DriverRouter 事件流。"""
    from fnixagent.core.tools.driver_router import get_driver_router

    events, last_id = await get_driver_router().recent_events(since)
    return {"ok": True, "events": events, "last_id": last_id}


# ============================================================================
# Phase 5 · 录制 / 重放
#
# 为什么走 API 而不是再加两个工具：Phase 5 刚把模型可见的浏览器工具从 8 个
# 收到 2 个，依据就是"每多一个工具，模型就多一次选错的机会"。录制是**用户**
# 在面板上演示，重放是**编排层**调用——两者都不需要模型在工具列表里做选择，
# 所以暴露成接口而不是工具，收敛成果不被破坏。
# ============================================================================

_TRAJ_DIR = Path.home() / ".fnix" / "trajectories"
# 录制会话在内存中（进程内），key = record_id；stop 时才落盘
_RECORDERS: dict[str, Any] = {}


def _traj_path(tid: str) -> Path:
    """轨迹 id → 文件路径。

    id 会被拼进路径，所以白名单收紧到"首字符必须是字母数字或下划线"——
    既挡住 ../ 这类穿越，也挡掉 "." / ".." 这种退化名字（虽然它们只是
    生成 ..json 这种怪文件名，但既然是白名单，就该让合法集合一眼看得完）。
    """
    if not tid or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tid):
        raise ValueError("轨迹 id 非法")
    return _TRAJ_DIR / f"{tid}.json"


def _traj_id_for(name: str, rid: str) -> str:
    """由轨迹名生成 id，并保证唯一。

    名字是用户随便起的，而且**很可能是中文**——一开始只做字符替换，结果
    "登录演示" 和 "搜索流程" 都会被清成 "____"，两条轨迹互相覆盖。
    所以统一在名字后面带上录制会话 id：ASCII 名保持可读，中文名（清洗后
    为空）退化为 traj-<rid>，两种情况都不会撞车。
    """
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_.-")[:64]
    return f"{slug}-{rid}" if slug else f"traj-{rid}"


class RecordStartRequest(BaseModel):
    name: str = Field("", max_length=128)
    # 连输入内容一起录（录搜索关键词这类非敏感场景才开）
    capture_values: bool = False


class RecordStepRequest(BaseModel):
    action: Literal["goto", "click", "type", "scroll", "back", "forward", "refresh"]
    url: str | None = None
    ref: str | None = None
    text: str | None = None
    into: str | None = None
    submit: bool = False
    direction: Literal["up", "down"] | None = None
    amount: int | None = None


class ReplayRequest(BaseModel):
    """重放：按 id 或内联轨迹二选一。

    values 是**当次**提供的输入值（不落盘），键可以是步骤序号或元素名。
    heal=True 时接自愈层，元素漂移到同名失效目标时能自动换目标。
    """

    trajectory_id: str | None = None
    trajectory: dict[str, Any] | None = None
    values: dict[str, str] = Field(default_factory=dict)
    heal: bool = True


@router.post("/trajectory/record/start")
async def trajectory_record_start(req: RecordStartRequest) -> dict[str, Any]:
    rid = uuid4().hex[:12]
    _RECORDERS[rid] = TrajectoryRecorder(
        _session, name=req.name, capture_values=req.capture_values
    )
    return {"ok": True, "record_id": rid}


@router.post("/trajectory/record/{rid}/step")
async def trajectory_record_step(rid: str, req: RecordStepRequest) -> dict[str, Any]:
    rec = _RECORDERS.get(rid)
    if rec is None:
        return {"ok": False, "error": "录制会话不存在或已结束"}
    params: dict[str, Any] = {k: v for k, v in req.model_dump().items() if v is not None}
    params.pop("action", None)
    try:
        state = await rec.record(req.action, **params)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {
        "ok": not getattr(state, "error", None),
        "error": getattr(state, "error", None),
        "step_count": len(rec.trajectory),
    }


@router.post("/trajectory/record/{rid}/stop")
async def trajectory_record_stop(rid: str) -> dict[str, Any]:
    rec = _RECORDERS.pop(rid, None)
    if rec is None:
        return {"ok": False, "error": "录制会话不存在或已结束"}
    traj = rec.trajectory
    tid = _traj_id_for(traj.name, rid)
    path = _traj_path(tid)
    traj.save(path)
    return {
        "ok": True,
        "trajectory_id": tid,
        "path": str(path),
        "step_count": len(traj),
        "trajectory": traj.to_dict(),
    }


@router.get("/trajectory")
async def trajectory_list() -> dict[str, Any]:
    if not _TRAJ_DIR.is_dir():
        return {"ok": True, "items": []}
    items = []
    for p in sorted(_TRAJ_DIR.glob("*.json")):
        try:
            t = Trajectory.load(p)
        except Exception:  # noqa: BLE001
            continue
        items.append(
            {
                "id": p.stem,
                "name": t.name,
                "step_count": len(t),
                "start_url": t.start_url,
                "created_at": t.created_at,
            }
        )
    return {"ok": True, "items": items}


@router.get("/trajectory/{tid}")
async def trajectory_get(tid: str) -> dict[str, Any]:
    try:
        path = _traj_path(tid)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not path.exists():
        return {"ok": False, "error": "轨迹不存在"}
    return {"ok": True, "trajectory": Trajectory.load(path).to_dict()}


@router.delete("/trajectory/{tid}")
async def trajectory_delete(tid: str) -> dict[str, Any]:
    try:
        path = _traj_path(tid)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not path.exists():
        return {"ok": False, "error": "轨迹不存在"}
    path.unlink()
    return {"ok": True}


@router.post("/trajectory/replay")
async def trajectory_replay(req: ReplayRequest) -> dict[str, Any]:
    if req.trajectory is not None:
        traj = Trajectory.from_dict(req.trajectory)
    elif req.trajectory_id:
        try:
            path = _traj_path(req.trajectory_id)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        if not path.exists():
            return {"ok": False, "error": "轨迹不存在"}
        traj = Trajectory.load(path)
    else:
        return {"ok": False, "error": "需要 trajectory_id 或 trajectory"}

    healer = None
    if req.heal:
        from fnixagent.core.tools.browser_healing import BrowserHealer

        healer = BrowserHealer(_session)

    res = await TrajectoryReplayer(_session, values=req.values, healer=healer).replay(traj)
    return {
        "ok": res.ok,
        "steps_ok": res.steps_ok,
        "total": res.total,
        "failed_step": res.failed_step,
        "error": res.error,
        "assert_failures": res.assert_failures,
        "warnings": res.warnings,
    }


def st_width_default() -> int:
    return _session.state.viewport.get("width", 1280)


def st_height_default() -> int:
    return _session.state.viewport.get("height", 800)
