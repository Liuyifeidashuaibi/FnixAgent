"""API — FnixForge：第三方 Agent 测评与自动修复（前端可触发）。

端点:
  GET  /forge/suites            列出内置 benchmark 套件
  POST /forge/probe             探测目标 Agent 调用方式
  POST /forge/run               执行测评/修复闭环（SSE 事件流，或 sync 汇总）
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/forge", tags=["forge"])

def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))

class ProbeRequest(BaseModel):
    target: str = Field(..., max_length=4096)

class ForgeRunRequest(BaseModel):
    target: str = Field(..., max_length=4096)
    suite: str = Field(default="core", max_length=64)
    mode: str = Field(default="test", pattern="^(test|fix)$")
    max_rounds: int = Field(default=3, ge=1, le=10)
    threshold: float = Field(default=90.0, ge=0.0, le=100.0)
    adapter_config: dict[str, Any] | None = None
    stream: bool = True

@router.get("/suites")
async def list_forge_suites():
    from fnixagent.core.forge import list_suites

    return {"ok": True, "suites": _jsonable(list_suites())}

@router.post("/probe")
async def probe_target_endpoint(req: ProbeRequest):
    from fnixagent.core.forge import probe_target

    target = Path(req.target)
    if not target.is_dir():
        return {"ok": False, "error": f"目标目录不存在: {req.target}"}
    return {"ok": True, "probe": _jsonable(probe_target(target).to_dict())}

@router.post("/run")
async def run_forge_endpoint(req: ForgeRunRequest):
    from fnixagent.core.forge import AdapterConfig, ForgeLoop

    target = Path(req.target)
    if not target.is_dir():
        return {"ok": False, "error": f"目标目录不存在: {req.target}"}

    config = AdapterConfig.from_dict(req.adapter_config) if req.adapter_config else None

    if not req.stream:
        try:
            loop = ForgeLoop(
                target, suite=req.suite, mode=req.mode,
                max_rounds=req.max_rounds, adapter_config=config,
                fix_threshold=req.threshold,
            )
            result = await asyncio.to_thread(loop.run)
        except (RuntimeError, FileNotFoundError) as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "result": _jsonable(result.to_dict())}

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        loop_ref = asyncio.get_running_loop()

        def sink(ev: dict) -> None:
            loop_ref.call_soon_threadsafe(queue.put_nowait, ev)

        def _work() -> dict[str, Any]:
            from fnixagent.core.forge import ForgeLoop as _Loop

            fl = _Loop(
                target, suite=req.suite, mode=req.mode,
                max_rounds=req.max_rounds, adapter_config=config,
                fix_threshold=req.threshold, on_event=sink,
            )
            return fl.run().to_dict()

        fut = asyncio.ensure_future(asyncio.to_thread(_work))
        try:
            while True:
                if fut.done() and queue.empty():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(_jsonable(ev), ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    continue
            try:
                result = fut.result()
                yield f"data: {json.dumps({'event': 'result', 'result': _jsonable(result)}, ensure_ascii=False)}\n\n"
            except (RuntimeError, FileNotFoundError) as e:
                yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            if not fut.done():
                fut.cancel()
        yield "data: {\"event\": \"eof\"}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
