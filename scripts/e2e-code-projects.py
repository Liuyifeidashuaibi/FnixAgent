#!/usr/bin/env python3
"""Code 模式写代码项目批量 E2E — preview → Accept、多文件、修 bug。"""
from __future__ import annotations
# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BASE = os.environ.get("VITE_API_BASE", "http://127.0.0.1:8003")
DEFAULT_WS = Path(os.environ.get("E2E_CODE_WS", r"E:\临时文件\test2"))


def load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def llm() -> dict:
    return {
        "provider": os.environ.get("LLM_PROVIDER", "qwen"),
        "model": os.environ.get("LLM_MODEL", "qwen-plus-2025-07-28"),
        "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    }


def http_json(method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stream_agent(messages: list[dict], workspace: str, preview: bool = True, timeout: int = 600) -> dict:
    body = {
        "messages": messages,
        "workspace": workspace,
        "preview": preview,
        "llm": llm(),
        "session_id": "e2e-code-batch",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/v1/chat/agent",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    changes: list[dict] = []
    texts: list[str] = []
    err = ""
    status = ""
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = ""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                ev = json.loads(line)
                t = ev.get("type")
                if t == "file_change":
                    changes.append(
                        {
                            "path": ev.get("path"),
                            "action": ev.get("action") or "modify",
                            "content": ev.get("content"),
                            "old_content": ev.get("old_content"),
                            "diff": ev.get("diff"),
                        }
                    )
                elif t == "message":
                    c = ev.get("content")
                    if c:
                        texts.append(str(c))
                elif t == "error":
                    err = str(ev.get("content") or ev.get("error") or ev)
                elif t == "done":
                    status = str(ev.get("status") or "")
                    if ev.get("error"):
                        err = str(ev.get("error"))
                    for ch in ev.get("changes") or []:
                        if isinstance(ch, dict) and ch.get("path"):
                            existing = next((c for c in changes if c["path"] == ch["path"]), None)
                            if existing:
                                existing.update({k: v for k, v in ch.items() if v is not None})
                            else:
                                changes.append(
                                    {
                                        "path": ch.get("path"),
                                        "action": ch.get("action") or "modify",
                                        "content": ch.get("content"),
                                        "old_content": ch.get("old_content"),
                                    }
                                )
    # dedupe by path
    by_path: dict[str, dict] = {}
    for c in changes:
        p = str(c.get("path") or "")
        if p:
            by_path[p] = {**by_path.get(p, {}), **c}
    return {"changes": list(by_path.values()), "texts": texts, "error": err, "status": status}


def apply_changes(workspace: str, changes: list[dict]) -> dict:
    return http_json(
        "POST",
        "/api/v1/chat/agent/apply",
        {"workspace": workspace, "changes": changes},
        timeout=120,
    )


def test_offline_code_tools() -> list[str]:
    import asyncio
    from fnixagent.core.code.tools import CodeTools

    errs: list[str] = []

    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tools = CodeTools(str(root))
            w = await tools.write("src/hello.py", "def greet():\n    return 'hi'\n")
            if not w.success:
                errs.append(f"write: {w.error}")
            r = await tools.read("src/hello.py")
            if not r.success or "greet" not in str(r.output):
                errs.append("read failed")
            e = await tools.edit("src/hello.py", "return 'hi'", "return 'hello'")
            if not e.success:
                errs.append(f"edit: {e.error}")
            r2 = await tools.read("src/hello.py")
            if "hello" not in str(r2.output):
                errs.append("edit not applied")

    asyncio.run(run())
    if not errs:
        print("  OK  offline CodeTools write/read/edit")
    return errs


def test_offline_apply_api() -> list[str]:
    from fastapi.testclient import TestClient
    from fnixagent.main import app

    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        client = TestClient(app)
        os.environ["FNIXAGENT_PROFILE"] = "standalone"
        res = client.post(
            "/api/v1/chat/agent/apply",
            json={
                "workspace": str(ws),
                "changes": [
                    {"path": "pkg/main.py", "action": "create", "content": "print(1)\n"},
                    {"path": "pkg/util.py", "action": "create", "content": "X=1\n"},
                ],
            },
        )
        if res.status_code != 200 or not res.json().get("ok"):
            errs.append(f"apply multi: {res.status_code} {res.text[:200]}")
        elif not (ws / "pkg" / "main.py").is_file():
            errs.append("main.py missing after apply")
        elif not (ws / "pkg" / "util.py").is_file():
            errs.append("util.py missing after apply")
    if not errs:
        print("  OK  offline apply multi-file")
    return errs


def test_codex_create_module(ws: Path) -> list[str]:
    proj = ws / ".fnix_e2e_code" / "calc"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    http_json("POST", "/api/v1/harness/workspace/ensure", {"workspace": str(proj)})

    task = (
        "在项目根目录创建 calc.py，实现 add(a,b) 和 multiply(a,b) 两个函数，"
        "并创建 test_calc.py 用 assert 测试这两个函数。只改项目内文件。"
    )
    stream = stream_agent([{"role": "user", "content": task}], str(proj), preview=True, timeout=300)
    if stream["error"]:
        return [f"create stream: {stream['error']}"]
    if not stream["changes"]:
        return [f"create: no file_change (status={stream['status']})"]

    apply_res = apply_changes(str(proj), stream["changes"])
    if not apply_res.get("ok"):
        return [f"create apply: {apply_res.get('error')}"]

    calc = proj / "calc.py"
    if not calc.is_file():
        # maybe nested path
        found = list(proj.rglob("calc.py"))
        if not found:
            return [f"calc.py missing; changes={[c.get('path') for c in stream['changes']]}"]
        calc = found[0]

    text = calc.read_text(encoding="utf-8")
    if "def add" not in text or "def multiply" not in text:
        return [f"calc.py incomplete: {text[:200]}"]
    print(f"  OK  codex create module ({len(stream['changes'])} files)")
    return []


def test_codex_fix_bug(ws: Path) -> list[str]:
    proj = ws / ".fnix_e2e_code" / "fixbug"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    (proj / "math_utils.py").write_text(
        "def subtract(a, b):\n    return a + b  # bug\n",
        encoding="utf-8",
    )
    http_json("POST", "/api/v1/harness/workspace/ensure", {"workspace": str(proj)})

    task = "math_utils.py 里 subtract 函数有 bug（用了加法），请 fix 为正确减法，preview 模式给出 diff。"
    stream = stream_agent([{"role": "user", "content": task}], str(proj), preview=True, timeout=240)
    if stream["error"]:
        return [f"fix stream: {stream['error']}"]
    if not stream["changes"]:
        return ["fix: no file_change"]

    apply_res = apply_changes(str(proj), stream["changes"])
    if not apply_res.get("ok"):
        return [f"fix apply: {apply_res.get('error')}"]

    target = proj / "math_utils.py"
    if not target.is_file():
        found = list(proj.rglob("math_utils.py"))
        target = found[0] if found else target
    if not target.is_file():
        return ["math_utils.py missing after fix"]

    text = target.read_text(encoding="utf-8")
    if "a + b" in text and "a - b" not in text:
        return [f"bug not fixed: {text}"]
    print("  OK  codex fix bug")
    return []


def main() -> int:
    load_dotenv()
    all_errs: list[str] = []

    print(f"[code-e2e] BASE={BASE}")
    print("\n== Offline ==")
    all_errs.extend(test_offline_code_tools())
    all_errs.extend(test_offline_apply_api())

    print("\n== API health ==")
    try:
        h = http_json("GET", "/health")
        print(f"  OK  health {h.get('status')}")
    except Exception as e:
        all_errs.append(f"health: {e}")
        print("\nFAILED (no agentd)")
        for e in all_errs:
            print(" -", e)
        return 1

    if not llm().get("api_key"):
        print("  SKIP LLM codex tests (no DASHSCOPE_API_KEY)")
    else:
        ws = DEFAULT_WS
        if not ws.is_dir():
            all_errs.append(f"workspace missing: {ws}")
        else:
            print("\n== Codex LLM ==")
            all_errs.extend(test_codex_create_module(ws))
            all_errs.extend(test_codex_fix_bug(ws))

    if all_errs:
        print(f"\nFAILED ({len(all_errs)}):")
        for e in all_errs:
            print(" -", e)
        return 1
    print("\nALL PASS — Code project E2E")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
