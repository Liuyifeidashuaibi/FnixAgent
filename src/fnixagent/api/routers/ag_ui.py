"""API 路由 — AG-UI 协议桥（README 承诺的 /api/v1/ag-ui/work/stream）。

将 Work NDJSON 内部流实时转译为 AG-UI 标准 SSE 事件流,
供任何符合 AG-UI Protocol 的前端/第三方直接消费。

设计:
  - 内部复用 work.work_stream 的生成器(单一事实来源), 保证与
    /work/stream 行为完全一致(guardrail/artifact/trace_id 全保留);
  - 仅在出口做 chunk_type → AG-UI 事件映射(core/ag_ui/mapper.py);
  - 失败不静默: 解析失败的行跳过并计数, 不中断流。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from fnixagent.api.routers.work import WorkStreamRequest
from fnixagent.core.ag_ui.mapper import (
    ALL_EVENT_TYPES,
    CHUNK_MAP,
    encode_sse,
    map_work_chunk,
    new_run_id,
    run_error,
    run_started,
)

router = APIRouter(prefix="/ag-ui", tags=["ag-ui"])


@router.get("/events")
async def list_events() -> dict[str, Any]:
    """AG-UI 事件类型清单(前端/SDK 对齐用)。"""
    return {
        "protocol": "AG-UI",
        "version": "1.0",
        "event_types": list(ALL_EVENT_TYPES),
        "chunk_map": dict(CHUNK_MAP),
    }


@router.post("/work/stream")
async def agui_work_stream(
    body: WorkStreamRequest,
    request: Request,
):
    """Work 模式 AG-UI SSE 流 — 与 POST /work/stream 等价, 协议不同。"""
    from fnixagent.api.routers.work import work_stream
    inner = await work_stream(body, request)
    run_id = new_run_id()

    async def sse():
        yield run_started(run_id)
        parsed = 0
        skipped = 0
        try:
            async for line in inner.body_iterator:
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                text = str(line).strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                parsed += 1
                chunk_type = str(obj.get("chunk_type", ""))
                content = obj.get("content")
                yield encode_sse(map_work_chunk(chunk_type, content, run_id))
        except Exception as exc:  # noqa: BLE001 — 上游异常转为 RUN_ERROR 事件
            yield run_error(run_id, str(exc))
            return
        # 流正常结束(done/error chunk 已映射), 附带统计便于调试
        yield encode_sse(
            {
                "type": "STATE_SNAPSHOT",
                "runId": run_id,
                "snapshot": {"chunks_parsed": parsed, "chunks_skipped": skipped},
            }
        )

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
