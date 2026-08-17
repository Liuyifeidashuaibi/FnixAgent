#!/usr/bin/env python3
"""E2E: Trae Work / WorkBuddy 三态 Ask / Plan / Craft 验收。"""
from __future__ import annotations
# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.services.work_pipeline import normalize_artifact_path

BASE = os.environ.get("VITE_API_BASE", "http://127.0.0.1:8003")
WS = Path(os.environ.get("FNIX_TEST_WS", ""))  # set in main() if empty


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


def llm_payload() -> dict:
    return {
        "provider": os.environ.get("LLM_PROVIDER", "qwen"),
        "model": os.environ.get("LLM_MODEL", "qwen3.7-plus"),
        "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    }


def stream_work(user_input: str, work_mode: str, timeout: int = 300) -> dict:
    body = {
        "user_input": user_input,
        "workspace": str(WS),
        "session_id": f"e2e-{work_mode}",
        "work_mode": work_mode,
        "llm": llm_payload(),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/v1/work/stream",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    texts: list[str] = []
    mission: dict | None = None
    artifacts: list[dict] = []
    seen_art: set[str] = set()
    err = ""
    ws = str(WS)
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
                t = ev.get("chunk_type") or ev.get("type")
                c = ev.get("content")
                if t == "error":
                    err = str(c)
                elif t == "mission" and isinstance(c, dict):
                    mission = c
                elif t == "text":
                    texts.append(str(c))
                elif t == "artifact" and isinstance(c, dict) and c.get("path"):
                    key = normalize_artifact_path(str(c["path"]), ws)
                    if key and key not in seen_art:
                        seen_art.add(key)
                        artifacts.append({"path": key, "name": c.get("name") or os.path.basename(key)})
                elif t == "done" and isinstance(c, dict):
                    for a in c.get("artifacts") or []:
                        if isinstance(a, dict) and a.get("path"):
                            key = normalize_artifact_path(str(a["path"]), ws)
                            if key and key not in seen_art:
                                seen_art.add(key)
                                artifacts.append(
                                    {"path": key, "name": a.get("name") or os.path.basename(key)}
                                )
    full = "".join(texts)
    return {
        "work_mode": work_mode,
        "mission": mission,
        "texts": texts,
        "text_len": len(full),
        "artifacts": artifacts,
        "error": err,
        "full": full[:500],
    }


def main() -> int:
    import tempfile

    global WS
    load_dotenv()
    if not llm_payload().get("api_key"):
        print("SKIP: no DASHSCOPE_API_KEY")
        return 0

    tmp_ctx = None
    if not str(WS):
        tmp_ctx = tempfile.TemporaryDirectory(prefix="fnix-work-modes-")
        WS = Path(tmp_ctx.name)

    print(f"[e2e-work] BASE={BASE} WS={WS}")
    failures: list[str] = []

    try:
        return _run_modes(failures)
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


def _run_modes(failures: list[str]) -> int:
    # Ask
    ask = stream_work("解释一下 MBTI 四个维度", "ask", timeout=180)
    print(f"[ask] mission={ask['mission'] and ask['mission'].get('workspace_kind')} "
          f"texts={len(ask['texts'])} arts={len(ask['artifacts'])} err={ask['error'][:80] if ask['error'] else ''}")
    if ask["error"]:
        failures.append(f"ask error: {ask['error']}")
    if ask["mission"] and ask["mission"].get("workspace_kind") == "code":
        failures.append("ask misclassified as code")
    if len(ask["texts"]) > 1 and ask["texts"][0] == ask["texts"][-1]:
        failures.append("ask duplicate full text chunks")
    if ask["artifacts"]:
        failures.append(f"ask wrote artifacts: {ask['artifacts']}")
    if "未检测到写入文件" in "".join(ask["texts"]):
        failures.append("ask got craft write warning")

    # Plan
    plan = stream_work(
        "规划在 .fnix/artifacts/mbti_test 做 MBTI 站：列出文件与步骤，本回合不写盘",
        "plan",
        timeout=180,
    )
    print(f"[plan] mission={plan['mission'] and plan['mission'].get('workspace_kind')} "
          f"texts={len(plan['texts'])} arts={len(plan['artifacts'])}")
    if plan["error"]:
        failures.append(f"plan error: {plan['error']}")
    if plan["artifacts"]:
        failures.append(f"plan wrote artifacts: {plan['artifacts']}")
    if plan["text_len"] < 80:
        failures.append("plan response too short")

    # Craft (short prompt — full MBTI in e2e-mbti-mvp)
    craft = stream_work(
        "在 .fnix/artifacts/mbti_test 做一个简单 MBTI 测验单页 index.html（含内联 css/js）",
        "craft",
        timeout=420,
    )
    print(f"[craft] arts={len(craft['artifacts'])} texts={len(craft['texts'])}")
    if craft["error"]:
        failures.append(f"craft error: {craft['error']}")
    art_dir = WS / ".fnix" / "artifacts" / "mbti_test"
    if not any(art_dir.glob("*.html")) and not craft["artifacts"]:
        failures.append("craft no html artifact")
    if len(craft["artifacts"]) > 5:
        failures.append(f"craft too many unique artifacts: {len(craft['artifacts'])}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("\nPASS: Ask/Plan/Craft e2e")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

