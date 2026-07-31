#!/usr/bin/env python3
"""离线 + 在线 Work 能力批量验收（Trae Work / WorkBuddy）。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.services.work_pipeline import merge_artifact, normalize_artifact_path

BASE = os.environ.get("VITE_API_BASE", "http://127.0.0.1:8003")
WS = Path(os.environ.get("FNIX_TEST_WS", r"E:\临时文件\test2"))


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


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


def test_offline_mission_schema() -> list[str]:
    from fnixagent.services.work_agent import strip_mutating_tools
    from fnixagent.services.work_pipeline import build_mission_schema, merge_artifact, normalize_artifact_path
    from fnixagent.core.tools.registry import ToolRegistry
    from fnixagent.core.tools.workspace import register_workspace_tools

    errs: list[str] = []
    m = build_mission_schema("解释一下 MBTI 四个维度", work_mode="ask")
    if m["workspace_kind"] == "code":
        errs.append("ask+explain should not be code")
    else:
        ok("ask explain → not code")

    m2 = build_mission_schema("在 .fnix/artifacts/x 做网站", work_mode="craft")
    if m2["workspace_kind"] != "code":
        errs.append("craft site should be code")
    else:
        ok("craft site → code")

    arts: list[dict[str, str]] = []
    merge_artifact(arts, ".fnix/artifacts/a.html", str(WS))
    merge_artifact(arts, str(WS / ".fnix/artifacts/a.html"))
    if len(arts) != 1:
        errs.append(f"merge_artifact dedupe failed: {arts}")
    else:
        ok("artifact path dedupe")

    reg = ToolRegistry()
    register_workspace_tools(reg, str(WS))
    strip_mutating_tools(reg)
    if "write_file" in reg._tools:
        errs.append("strip_mutating_tools failed")
    else:
        ok("ask/plan strip write_file")

    if normalize_artifact_path("", str(WS)):
        errs.append("empty path normalized")
    else:
        ok("normalize empty path")

    return errs


def test_api_health() -> list[str]:
    errs: list[str] = []
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            data = json.loads(r.read().decode())
        if data.get("status") != "healthy":
            errs.append(f"health bad: {data}")
        else:
            ok(f"health @ {BASE}")
    except Exception as e:
        errs.append(f"health: {e}")
    return errs


def test_work_status() -> list[str]:
    errs: list[str] = []
    try:
        with urllib.request.urlopen(f"{BASE}/api/v1/work/status", timeout=8) as r:
            data = json.loads(r.read().decode())
        if "ktg" not in str(data).lower() and "evolution" not in str(data).lower():
            errs.append(f"work/status unexpected: {list(data)[:5]}")
        else:
            ok("GET /work/status")
    except Exception as e:
        errs.append(f"work/status: {e}")
    return errs


def test_work_stream_no_key() -> list[str]:
    errs: list[str] = []
    body = json.dumps(
        {"user_input": "hi", "work_mode": "ask", "workspace": str(WS)}
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/api/v1/work/stream",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            first = r.read(2048).decode("utf-8", errors="replace")
        if "error" not in first and "BYOK" not in first and "API Key" not in first:
            errs.append("no-key stream should error with BYOK hint")
        else:
            ok("no-key stream rejects with BYOK")
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403, 422):
            ok("no-key stream HTTP error (expected)")
        else:
            errs.append(f"no-key HTTP {e.code}")
    except Exception as e:
        errs.append(f"no-key stream: {e}")
    return errs


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


def stream_work(user_input: str, work_mode: str, timeout: int = 300) -> dict:
    body = {
        "user_input": user_input,
        "workspace": str(WS),
        "session_id": f"batch-{work_mode}",
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
    seen: set[str] = set()
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
                    if key and key not in seen:
                        seen.add(key)
                        artifacts.append({"path": key, "name": c.get("name")})
                elif t == "done" and isinstance(c, dict):
                    for a in c.get("artifacts") or []:
                        if isinstance(a, dict) and a.get("path"):
                            key = normalize_artifact_path(str(a["path"]), ws)
                            if key and key not in seen:
                                seen.add(key)
                                artifacts.append({"path": key, "name": a.get("name")})
    paths = [a.get("path", "") for a in artifacts]
    unique = set(paths)
    return {
        "mission": mission,
        "texts": texts,
        "artifacts": artifacts,
        "unique_paths": len(unique),
        "err": err,
        "full_text": "".join(texts),
    }


def dedupe_artifacts(paths: list[str]) -> list[str]:
    arts: list[dict[str, str]] = []
    for p in paths:
        merge_artifact(arts, p, str(WS))
    return [a["path"] for a in arts]


def test_llm_modes() -> list[str]:
    if not llm_payload().get("api_key"):
        print("  SKIP LLM tests (no DASHSCOPE_API_KEY)")
        return []

    errs: list[str] = []

    ask = stream_work("用三句话解释 MBTI E/I 维度", "ask", timeout=120)
    if ask["err"]:
        errs.append(f"ask: {ask['err']}")
    elif ask["mission"] and ask["mission"].get("workspace_kind") == "code":
        errs.append("ask mission code")
    elif ask["artifacts"]:
        errs.append(f"ask artifacts: {ask['artifacts']}")
    elif len(ask["texts"]) > 1 and ask["texts"][0] == ask["texts"][-1]:
        errs.append("ask duplicate text chunks")
    elif "未检测到写入文件" in ask["full_text"]:
        errs.append("ask got craft warning")
    else:
        ok(f"ask stream ({len(ask['full_text'])} chars)")

    plan = stream_work(
        "规划 MBTI 单页站：只列步骤和文件路径，不要写盘",
        "plan",
        timeout=120,
    )
    if plan["err"]:
        errs.append(f"plan: {plan['err']}")
    elif plan["artifacts"]:
        errs.append(f"plan artifacts: {len(plan['artifacts'])}")
    else:
        ok(f"plan stream no artifacts")

    craft = stream_work(
        "在 .fnix/artifacts/e2e_ping 写 ping.txt 内容为 pong",
        "craft",
        timeout=180,
    )
    ping = WS / ".fnix" / "artifacts" / "e2e_ping" / "ping.txt"
    if craft["err"]:
        errs.append(f"craft: {craft['err']}")
    elif not ping.is_file() and not craft["artifacts"]:
        errs.append("craft ping.txt missing")
    else:
        ok("craft write ping.txt")

    if craft["unique_paths"] > 3 and craft["artifacts"]:
        deduped = dedupe_artifacts([a["path"] for a in craft["artifacts"]])
        if len(deduped) < len(craft["artifacts"]):
            ok(f"craft dedupe would shrink {len(craft['artifacts'])} → {len(deduped)}")
        else:
            errs.append(f"craft too many duplicate artifacts: {craft['unique_paths']}")

    return errs


def main() -> int:
    load_dotenv()
    print(f"Work batch test  BASE={BASE}  WS={WS}")
    all_errs: list[str] = []

    section("Offline")
    all_errs.extend(test_offline_mission_schema())

    section("API (no LLM)")
    all_errs.extend(test_api_health())
    all_errs.extend(test_work_status())
    all_errs.extend(test_work_stream_no_key())

    section("API (LLM)")
    all_errs.extend(test_llm_modes())

    if all_errs:
        print(f"\nFAILED ({len(all_errs)}):")
        for e in all_errs:
            print(" -", e)
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
