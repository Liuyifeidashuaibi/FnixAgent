"""
桌面驱动 relay 子进程（GUI_DRIVER_DESIGN.md P3）

独立进程跑 cua-driver，实现权限/崩溃隔离：
  - UIPI 提权场景只有 relay 子进程需要管理员权限，FastAPI 主进程保持普通权限
  - 原生运行时段错误不拖垮后端
  - GUI 会话可独立于 API 服务重启

传输契约：stdout JSONL
  请求一行  {"id": int, "tool": str, "args": {...}}
  响应一行  {"id": int, "ok": bool, "summary": str, "screenshot_b64": str|null, "degraded": bool, "error": str|null}
  控制      {"cmd": "shutdown"}
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from typing import Any


def _first_image_b64(images: Any) -> str | None:
    if not images:
        return None
    try:
        img = images[0]
        if hasattr(img, "data_base64") and img.data_base64:
            return img.data_base64
        if isinstance(img, bytes):
            return base64.b64encode(img).decode("ascii")
    except Exception:  # noqa: BLE001
        return None
    return None


async def _call(d: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        r = await d.call_tool(tool, json.dumps(args, ensure_ascii=False))
        return {
            "ok": not bool(getattr(r, "is_error", False)),
            "summary": (getattr(r, "text", "") or "")[:500],
            "screenshot_b64": _first_image_b64(getattr(r, "images", None)),
            "degraded": bool(getattr(r, "degraded", False)),
            "error": getattr(r, "error_code", None),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "summary": "", "screenshot_b64": None, "degraded": False, "error": str(e)}


async def _run() -> None:
    import cua_driver as cd

    d = cd.CuaDriver.create()
    reader = asyncio.StreamReader()
    # 用线程读 stdin 喂给 StreamReader（stdin 是阻塞文件描述符）
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    out = sys.stdout
    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if req.get("cmd") == "shutdown":
            break
        rid = req.get("id")
        tool = req.get("tool", "")
        args = req.get("args") or {}
        resp = await _call(d, tool, args)
        resp["id"] = rid
        out.write(json.dumps(resp, ensure_ascii=False) + "\n")
        out.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="FnixAgent desktop relay subprocess")
    parser.add_argument("--mode", default="relay")
    parser.parse_args()
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
