"""Localhost capability token gate for desktop-managed agentd.

When FNIX_CAPABILITY_TOKEN is set (Tauri runtime bootstrap), mutating and
authenticated control-plane routes require a matching X-Fnix-Capability header.
Health/docs remain public so process readiness checks keep working.
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
from typing import Any

CAPABILITY_HEADER = b"x-fnix-capability"
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)


def capability_token() -> str:
    return (os.getenv("FNIX_CAPABILITY_TOKEN") or "").strip()


def capability_required() -> bool:
    return bool(capability_token())


def _header_value(scope: dict, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            try:
                return value.decode("utf-8").strip()
            except UnicodeDecodeError:
                return ""
    return ""


def _query_token(scope: dict) -> str:
    raw = scope.get("query_string") or b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    for part in text.split("&"):
        if part.startswith("capability="):
            return part.split("=", 1)[1].strip()
    return ""


def extract_presented_token(scope: dict) -> str:
    header = _header_value(scope, CAPABILITY_HEADER)
    if header:
        return header
    auth = _header_value(scope, b"authorization")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return _query_token(scope)


def path_is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    # Allow OpenAPI assets under /docs
    return path.startswith("/docs/")


def _request_origin(scope: dict) -> str:
    return _header_value(scope, b"origin")


def _cors_reject_headers(scope: dict) -> list[tuple[bytes, bytes]]:
    """Capability sits outside Starlette CORS — echo Origin so browsers can read 401."""
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
    ]
    origin = _request_origin(scope)
    if origin:
        headers.append((b"access-control-allow-origin", origin.encode("utf-8")))
        headers.append((b"access-control-allow-credentials", b"true"))
        headers.append(
            (
                b"access-control-allow-headers",
                b"authorization,content-type,x-fnix-capability",
            )
        )
        headers.append(
            (b"access-control-allow-methods", b"DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT")
        )
        headers.append((b"vary", b"Origin"))
    return headers


def check_capability(scope: dict) -> bool:
    """Return True if the request may proceed."""
    expected = capability_token()
    if not expected:
        return True
    # CORS preflight must pass through; CORSMiddleware (inner) answers OPTIONS.
    if (scope.get("method") or "").upper() == "OPTIONS":
        return True
    path = scope.get("path") or ""
    if path_is_public(path):
        return True
    presented = extract_presented_token(scope)
    return bool(presented) and presented == expected


class CapabilityMiddleware:
    """ASGI middleware that enforces FNIX_CAPABILITY_TOKEN when configured."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if check_capability(scope):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send(
                {
                    "type": "websocket.close",
                    "code": 4401,
                    "reason": "Missing or invalid capability token",
                }
            )
            return

        body = b'{"detail":"Missing or invalid capability token"}'
        headers = _cors_reject_headers(scope)
        headers.append((b"content-length", str(len(body)).encode("ascii")))
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})
