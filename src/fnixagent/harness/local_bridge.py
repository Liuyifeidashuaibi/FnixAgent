"""fnix-local sidecar 桥接 — Python agentd ↔ fnix-local HTTP。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_LOCAL_URL = "http://127.0.0.1:8710"
_TIMEOUT = float(os.getenv("FNIX_LOCAL_TIMEOUT", "30"))


@dataclass
class LocalBridgeStatus:
    available: bool
    url: str
    version: str
    message: str


class LocalBridge:
    """Python ↔ fnix-local RPC 封装。"""

    def __init__(self, base_url: str | None = None) -> None:
        raw = (
            base_url
            or os.getenv("FNIX_LOCAL_URL", "")
            or os.getenv("FNIX_LOCAL_GRPC_URL", "")
            or DEFAULT_LOCAL_URL
        ).rstrip("/")
        self.base_url = raw
        self._available: bool | None = None
        self._version: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout or _TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"fnix-local HTTP {e.code}: {detail}") from e
        except URLError as e:
            raise RuntimeError(f"fnix-local unreachable: {e.reason}") from e

    def health(self) -> LocalBridgeStatus:
        if not self.enabled:
            return LocalBridgeStatus(
                available=False,
                url="",
                version="",
                message="fnix-local 未配置",
            )
        try:
            data = self._request("GET", "/health", timeout=3.0)
            ok = bool(data.get("ok"))
            version = str(data.get("version") or "")
            self._available = ok
            self._version = version
            return LocalBridgeStatus(
                available=ok,
                url=self.base_url,
                version=version,
                message="fnix-local 就绪" if ok else "health check failed",
            )
        except Exception as e:
            self._available = False
            return LocalBridgeStatus(
                available=False,
                url=self.base_url,
                version="",
                message=f"fnix-local 离线: {e}",
            )

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        return self.health().available

    def index_workspace(
        self,
        workspace: str,
        *,
        force: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "session_id": "", "message": "sidecar offline"}
        try:
            payload: dict[str, Any] = {"workspace": workspace, "force": force}
            if session_id:
                payload["session_id"] = session_id
            return self._request("POST", "/v1/index", payload, timeout=120.0)
        except Exception as e:
            return {"ok": False, "session_id": "", "message": str(e)}

    def get_context(
        self,
        *,
        workspace: str | None = None,
        session_id: str | None = None,
        query: str | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "symbols": [], "pdg_digest": "", "vector_hits": []}
        params: list[str] = []
        if workspace:
            params.append(f"workspace={_quote(workspace)}")
        if session_id:
            params.append(f"session_id={_quote(session_id)}")
        if query:
            params.append(f"query={_quote(query)}")
        params.append(f"top_k={top_k}")
        qs = "&".join(params)
        try:
            return self._request("GET", f"/v1/context?{qs}", timeout=60.0)
        except Exception as e:
            return {
                "ok": False,
                "symbols": [],
                "pdg_digest": "",
                "vector_hits": [],
                "message": str(e),
            }

    def run_command(
        self,
        workspace: str,
        command: str,
        *,
        cwd: str | None = None,
        timeout: int = 60,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "stdout": "", "stderr": "sidecar offline", "exit_code": 1}
        try:
            return self._request(
                "POST",
                "/v1/run",
                {
                    "workspace": workspace,
                    "command": command,
                    "cwd": cwd,
                    "timeout": timeout,
                },
                timeout=float(timeout + 5),
            )
        except Exception as e:
            return {"ok": False, "stdout": "", "stderr": str(e), "exit_code": 1}

    def read_file(
        self,
        workspace: str,
        file_path: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_available():
            return {"ok": False, "content": "", "message": "sidecar offline"}
        params = [
            f"workspace={_quote(workspace)}",
            f"path={_quote(file_path)}",
            f"offset={offset}",
        ]
        if limit is not None:
            params.append(f"limit={limit}")
        qs = "&".join(params)
        try:
            return self._request("GET", f"/v1/read?{qs}", timeout=30.0)
        except Exception as e:
            return {"ok": False, "content": "", "message": str(e)}


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def format_local_context_block(ctx: dict[str, Any], *, max_chars: int = 8000) -> str:
    """将 sidecar 上下文格式化为 LLM prompt 块。"""
    if not ctx.get("ok"):
        return ""

    parts: list[str] = ["\n\n## 本地代码索引（fnix-local / PDG）"]
    stats = ctx.get("stats")
    if isinstance(stats, dict):
        parts.append(
            f"- 已索引文件: {stats.get('indexed_files', '?')} / "
            f"{stats.get('total_files', '?')} · 符号: {stats.get('total_symbols', '?')}"
        )

    digest = str(ctx.get("pdg_digest") or "")
    if digest:
        parts.append("\n### 项目结构摘要\n```")
        parts.append(digest[: max_chars - 500])
        parts.append("```")

    hits = ctx.get("vector_hits") or []
    if hits:
        parts.append("\n### 相关代码片段")
        for hit in hits[:6]:
            if not isinstance(hit, dict):
                continue
            parts.append(
                f"- `{hit.get('file')}:{hit.get('lines')}` "
                f"**{hit.get('symbol')}** — {str(hit.get('preview', ''))[:120]}"
            )

    block = "\n".join(parts)
    return block[:max_chars]


_bridge: LocalBridge | None = None


def get_local_bridge() -> LocalBridge:
    global _bridge
    if _bridge is None:
        _bridge = LocalBridge()
    return _bridge
