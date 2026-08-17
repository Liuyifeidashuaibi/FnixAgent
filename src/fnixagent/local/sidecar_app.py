"""fnix-local HTTP sidecar — FastAPI 应用。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

VERSION = "0.2.0-python"


class IndexRequest(BaseModel):
    workspace: str = Field(..., min_length=1)
    force: bool = False
    session_id: str | None = None


class RunRequest(BaseModel):
    workspace: str = Field(..., min_length=1)
    command: str = Field(..., min_length=1)
    cwd: str | None = None
    timeout: int = Field(default=60, ge=1, le=600)


def create_app() -> FastAPI:
    app = FastAPI(
        title="fnix-local",
        version=VERSION,
        description="Fnix 本地算力 sidecar（索引 / PDG / 命令）",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "fnix-local",
            "version": VERSION,
            "runtime": "python",
        }

    @app.post("/v1/index")
    async def index_workspace(body: IndexRequest) -> dict[str, Any]:
        from fnixagent.local.index_store import get_index_store

        store = get_index_store()
        try:
            session = await store.index_workspace(
                body.workspace,
                force=body.force,
                session_id=body.session_id,
            )
        except NotADirectoryError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        return {
            "ok": True,
            "session_id": session.session_id,
            "workspace": session.workspace,
            "stats": session.stats,
        }

    @app.get("/v1/context")
    async def get_context(
        workspace: str | None = Query(default=None),
        session_id: str | None = Query(default=None),
        query: str | None = Query(default=None),
        top_k: int = Query(default=8, ge=1, le=20),
    ) -> dict[str, Any]:
        from fnixagent.local.index_store import get_index_store

        if not workspace and not session_id:
            raise HTTPException(status_code=400, detail="workspace or session_id required")

        store = get_index_store()
        ctx = await store.build_context(
            session_id=session_id,
            workspace=workspace,
            query=query,
            top_k=top_k,
        )
        return ctx

    @app.post("/v1/run")
    async def run_command(body: RunRequest) -> dict[str, Any]:
        from fnixagent.core.tools.workspace import WorkspaceTools

        tools = WorkspaceTools(body.workspace)
        result = await tools.run_command(
            body.command,
            cwd=body.cwd,
            timeout=body.timeout,
        )
        return {
            "ok": result.success,
            "stdout": result.content,
            "stderr": result.error,
            "exit_code": (result.metadata or {}).get("exit_code", 1 if not result.success else 0),
        }

    @app.get("/v1/read")
    async def read_file(
        workspace: str = Query(...),
        path: str = Query(..., alias="path"),
        offset: int = Query(default=0, ge=0),
        limit: int | None = Query(default=None, ge=1),
    ) -> dict[str, Any]:
        from fnixagent.core.tools.workspace import WorkspaceTools

        tools = WorkspaceTools(workspace)
        result = tools.read_file(path, offset=offset, limit=limit)
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        return {"ok": True, "content": result.content, "metadata": result.metadata}

    return app


def main() -> None:
    import uvicorn

    host = os.getenv("FNIX_LOCAL_HOST", "127.0.0.1")
    port = int(os.getenv("FNIX_LOCAL_PORT", "8710"))
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
