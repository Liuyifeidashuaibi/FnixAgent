"""fnix-local HTTP sidecar — FastAPI 应用。

安全模型(与 Rust 版 fnix-local 对齐):
    - 所有 /v1/* 端点要求请求头 ``x-fnix-capability`` 与本机 capability
      令牌一致,否则 fail-closed 返回 401。
    - 令牌解析顺序: 环境变量 FNIX_CAPABILITY_TOKEN(桌面壳启动时注入) →
      ``~/.fnix/local_capability_token`` 文件(独立启动时自动生成并落盘,
      供同机 agentd 发现)。绝不 fail-open。
    - CORS 仅放行本地桌面 origin,与 Rust sidecar 白名单一致。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hmac
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

VERSION = "0.3.0-python"

CAPABILITY_HEADER = "x-fnix-capability"

# 与 Rust sidecar (apps/fnix-local) 保持一致的本地 origin 白名单
_LOCAL_ORIGINS: list[str] = [
    "http://127.0.0.1:5175",
    "http://localhost:5175",
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "tauri://localhost",
    "https://tauri.localhost",
]


def _fnix_home() -> Path:
    """~/.fnix 目录(可被 FNIX_HOME 覆盖),与 harness.paths.fnix_home 语义一致。"""
    env = (os.getenv("FNIX_HOME") or "").strip()
    if env:
        return Path(env)
    return Path.home() / ".fnix"


def _token_file() -> Path:
    return _fnix_home() / "local_capability_token"


def _persist_token(token: str) -> None:
    """尽力落盘令牌文件(best-effort,失败不影响服务)。"""
    try:
        home = _fnix_home()
        home.mkdir(parents=True, exist_ok=True)
        path = _token_file()
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(token + "\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, path)
    except OSError:
        pass


def resolve_capability_token() -> str:
    """解析本机 capability 令牌;环境变量缺失时自动生成并落盘(fail-closed)。"""
    env_token = (os.getenv("FNIX_CAPABILITY_TOKEN") or "").strip()
    if env_token:
        _persist_token(env_token)
        return env_token
    try:
        existing = _token_file().read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    generated = uuid.uuid4().hex
    _persist_token(generated)
    return generated


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
        allow_origins=_LOCAL_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.capability_token = resolve_capability_token()

    @app.middleware("http")
    async def capability_gate(request: Request, call_next):
        """令牌闸门: /health 与 CORS 预检放行,其余端点 fail-closed。"""
        if request.url.path == "/health" or request.method == "OPTIONS":
            return await call_next(request)
        expected: str = app.state.capability_token
        presented = (request.headers.get(CAPABILITY_HEADER) or "").strip()
        if not expected or not hmac.compare_digest(expected, presented):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid capability token"},
            )
        return await call_next(request)

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
