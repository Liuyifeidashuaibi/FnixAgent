"""API — 全链路系统基准测试（前端可触发）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


class ClientStage(BaseModel):
    id: str
    category: str = "frontend"
    ok: bool
    score: float = 100.0
    message: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class BenchmarkRunRequest(BaseModel):
    workspace: str | None = Field(default=None, max_length=4096)
    include_llm: bool = False
    fcs_limit: int = Field(default=3, ge=1, le=20)
    fcs_tag: str = Field(default="smoke", max_length=32)
    agent_base: str | None = Field(default=None, max_length=512)
    client_stages: list[ClientStage] = Field(default_factory=list)


@router.get("/suites")
async def list_suites():
    """可用测试套件说明。"""
    return {
        "ok": True,
        "suites": [
            {
                "id": "full_chain",
                "name": "Full Chain",
                "description": "Infra → Harness → Work → Code → FCS (optional LLM)",
                "stages": [
                    "frontend.*",
                    "infra.health",
                    "infra.harness_status",
                    "work.engine",
                    "harness.workspace",
                    "harness.config",
                    "code.apply",
                    "code.sessions",
                    "fcs.manifest | fcs.smoke",
                    "llm.connectivity",
                ],
            }
        ],
    }


@router.post("/run")
async def run_benchmark(body: BenchmarkRunRequest, request: Request):
    """流式执行全链路基准测试 — NDJSON：stage / done。"""
    from fnixagent.core.benchmark.system_runner import run_full_chain

    agent_base = body.agent_base or str(request.base_url).rstrip("/")

    async def generate():
        async for event in run_full_chain(
            app_state=request.app.state,
            workspace=body.workspace,
            include_llm=body.include_llm,
            fcs_limit=body.fcs_limit,
            fcs_tag=body.fcs_tag,
            agent_base=agent_base,
            client_stages=[s.model_dump() for s in body.client_stages],
        ):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")
