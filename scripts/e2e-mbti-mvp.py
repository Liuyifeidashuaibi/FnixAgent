#!/usr/bin/env python3
"""E2E: 模拟前端在 test2 工作区创建 MBTI 测验站并验收（Work + Codex Apply）。"""
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
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_WS = Path(r"E:\临时文件\test2")
ART_REL = ".fnix/artifacts/mbti_test"
BASE = os.environ.get("VITE_API_BASE", "http://127.0.0.1:8003")


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


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


def stream_ndjson(path: str, body: dict, timeout: int = 600) -> list[dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    events: list[dict] = []
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
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        if buf.strip():
            try:
                events.append(json.loads(buf.strip()))
            except json.JSONDecodeError:
                pass
    return events


def llm_payload() -> dict:
    return {
        "provider": os.environ.get("LLM_PROVIDER", "qwen"),
        "model": os.environ.get("LLM_MODEL", "qwen-plus-2025-07-28"),
        "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    }


def validate_mbti_site(art_dir: Path) -> list[str]:
    errors: list[str] = []
    required = ("index.html", "style.css", "script.js")
    for name in required:
        p = art_dir / name
        if not p.is_file():
            errors.append(f"缺少 {name}")
            continue
        text = p.read_text(encoding="utf-8")
        if len(text) < 150:
            errors.append(f"{name} 过短 ({len(text)} 字符)")
        if name.endswith(".html") and "<html" not in text.lower():
            errors.append(f"{name} 不是有效 HTML")
        if name.endswith(".css") and "{" not in text:
            errors.append(f"{name} 缺少 CSS 规则")
        if name.endswith(".js") and ("function" not in text and "=>" not in text):
            errors.append(f"{name} 不像有效脚本")
        stub_hints = ("创建项目", "创建文件", "实现逻辑", "定义网站")
        if any(h in text for h in stub_hints) and len(text) < 300:
            errors.append(f"{name} 疑似说明文字而非源码")
    html = (art_dir / "index.html")
    if html.is_file():
        h = html.read_text(encoding="utf-8")
        if "script.js" not in h and 'src="script' not in h.lower():
            errors.append("index.html 未引用 script.js")
        if "style.css" not in h and 'href="style' not in h.lower():
            errors.append("index.html 未引用 style.css")
    js = art_dir / "script.js"
    if js.is_file():
        j = js.read_text(encoding="utf-8")
        if not any(k in j for k in ("QUESTION", "question", "MBTI", "mbti", "类型")):
            errors.append("script.js 缺少测验逻辑")
    return errors


def reset_artifact_dir(ws: Path) -> Path:
    art = ws / ART_REL.replace("/", os.sep)
    if art.exists():
        shutil.rmtree(art)
    art.mkdir(parents=True, exist_ok=True)
    return art


def run_work(ws: Path, task: str) -> tuple[bool, str]:
    print("[e2e] Work stream…")
    events = stream_ndjson(
        "/api/v1/work/stream",
        {
            "user_input": task,
            "workspace": str(ws),
            "session_id": "e2e-mbti-work",
            "llm": llm_payload(),
        },
    )
    err = ""
    for ev in events:
        t = ev.get("chunk_type") or ev.get("type")
        if t == "error":
            err = str(ev.get("content") or ev)
        if t == "done" and isinstance(ev.get("content"), dict):
            r = ev["content"].get("result")
            if isinstance(r, str) and "失败" in r:
                err = r
    return not err, err or "ok"


def run_codex_apply(ws: Path, task: str) -> tuple[bool, str, list[dict]]:
    print("[e2e] Codex stream (preview)…")
    events = stream_ndjson(
        "/api/v1/chat/agent",
        {
            "messages": [{"role": "user", "content": task}],
            "workspace": str(ws),
            "session_id": "e2e-mbti-codex",
            "preview": True,
            "llm": llm_payload(),
        },
    )
    changes: list[dict] = []
    status = "unknown"
    err = ""
    for ev in events:
        t = ev.get("type")
        if t == "file_change":
            changes.append(
                {
                    "path": ev.get("path"),
                    "action": ev.get("action") or "modify",
                    "content": ev.get("content"),
                    "old_content": ev.get("old_content"),
                }
            )
        if t == "done":
            status = str(ev.get("status") or "")
            err = str(ev.get("error") or "")
            for ch in ev.get("changes") or []:
                if isinstance(ch, dict) and ch.get("path"):
                    # merge done payload
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
    if not changes:
        return False, err or f"codex 无 file_change (status={status})", changes

    print(f"[e2e] Apply {len(changes)} change(s)…")
    apply_res = http_json(
        "POST",
        "/api/v1/chat/agent/apply",
        {"workspace": str(ws), "changes": changes},
        timeout=120,
    )
    if not apply_res.get("ok"):
        return False, apply_res.get("error") or "apply failed", changes
    return True, f"applied {apply_res.get('applied', 0)}", changes


def main() -> int:
    load_dotenv()
    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("[e2e] FAIL: 缺少 DASHSCOPE_API_KEY（.env）")
        return 1

    ws = Path(os.environ.get("E2E_WORKSPACE", str(DEFAULT_WS)))
    if not ws.is_dir():
        print(f"[e2e] FAIL: workspace 不存在: {ws}")
        return 1

    health = http_json("GET", "/health")
    print("[e2e] agentd:", health.get("status"), health.get("profile"))

    http_json("POST", "/api/v1/harness/workspace/ensure", {"workspace": str(ws)})
    art = reset_artifact_dir(ws)
    print("[e2e] workspace:", ws)
    print("[e2e] artifact dir cleared:", art)

    task = (
        "在 .fnix/artifacts/mbti_test 目录创建一个完整可运行的 MBTI 十六型人格测验网站。"
        "必须包含 index.html、style.css、script.js 三个文件，content 写完整源码。"
        "要求：12 道选择题、进度条、最后显示四字母类型与简短描述，可双击 index.html 在浏览器打开。"
        "禁止只写「创建文件」这类说明文字。"
    )

    # 1) Work（对标 Trae Work / WorkBuddy — 应直接 write_file 落盘）
    ok_work, msg_work = run_work(ws, task)
    print("[e2e] Work result:", ok_work, msg_work)

    errors = validate_mbti_site(art)
    if not errors:
        print("[e2e] PASS — Work 模式已生成有效 MBTI 站点")
        for f in sorted(art.iterdir()):
            print(f"  OK {f.name} ({f.stat().st_size} B)")
        return 0

    print("[e2e] Work 验收失败:", "; ".join(errors))
    print("[e2e] fallback: Code preview -> Accept")
    reset_artifact_dir(ws)

    # 2) Code (Codex) preview → Accept
    ok_codex, msg_codex, changes = run_codex_apply(ws, task)
    print("[e2e] Code result:", ok_codex, msg_codex, f"changes={len(changes)}")
    errors = validate_mbti_site(art)
    if not errors:
        print("[e2e] PASS — Code + Accept 已生成有效 MBTI 站点")
        for f in sorted(art.iterdir()):
            print(f"  OK {f.name} ({f.stat().st_size} B)")
        return 0

    print("[e2e] FAIL — Code 验收:", "; ".join(errors))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
