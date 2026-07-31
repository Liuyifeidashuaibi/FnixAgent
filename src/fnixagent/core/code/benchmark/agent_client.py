"""HTTP client for running benchmark tasks against agentd."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentRunResult:
    changes: list[dict[str, Any]]
    error: str
    status: str
    steps: int
    heal_rounds: int
    tool_calls: int
    elapsed_s: float


def _llm_config() -> dict[str, str]:
    return {
        "provider": os.environ.get("LLM_PROVIDER", "qwen"),
        "model": os.environ.get("LLM_MODEL", "qwen-plus-2025-07-28"),
        "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    }


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    cap = (os.environ.get("FNIX_CAPABILITY_TOKEN") or "").strip()
    if cap:
        headers["X-Fnix-Capability"] = cap
    return headers


def http_json(
    base: str, method: str, path: str, body: dict | None = None, timeout: int = 60
) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        method=method,
        headers=_auth_headers(),
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stream_agent(
    base: str,
    prompt: str,
    workspace: str,
    *,
    preview: bool = True,
    timeout: int = 600,
) -> AgentRunResult:
    import time

    body = {
        "messages": [{"role": "user", "content": prompt}],
        "workspace": workspace,
        "preview": preview,
        "llm": _llm_config(),
        "session_id": "fcs-benchmark",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/chat/agent",
        data=data,
        method="POST",
        headers=_auth_headers(),
    )

    changes: list[dict] = []
    err = ""
    status = ""
    tool_calls = 0
    heal_rounds = 0
    t0 = time.perf_counter()

    try:
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
                    elif t == "tool_call":
                        tool_calls += 1
                    elif t == "heal":
                        heal_rounds += 1
                    elif t == "error":
                        err = str(ev.get("content") or ev.get("error") or ev)
                    elif t == "done":
                        status = str(ev.get("status") or "")
                        if ev.get("error"):
                            err = str(ev.get("error"))
                        for ch in ev.get("changes") or []:
                            if isinstance(ch, dict) and ch.get("path"):
                                existing = next(
                                    (c for c in changes if c["path"] == ch["path"]), None
                                )
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
    except urllib.error.HTTPError as e:
        err = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"
    except Exception as e:
        err = str(e)

    by_path: dict[str, dict] = {}
    for c in changes:
        p = str(c.get("path") or "")
        if p:
            by_path[p] = {**by_path.get(p, {}), **c}

    elapsed = time.perf_counter() - t0
    steps = max(tool_calls, len(by_path))

    return AgentRunResult(
        changes=list(by_path.values()),
        error=err,
        status=status,
        steps=steps,
        heal_rounds=heal_rounds,
        tool_calls=tool_calls,
        elapsed_s=elapsed,
    )


def apply_changes(base: str, workspace: str, changes: list[dict]) -> dict:
    return http_json(
        base,
        "POST",
        "/api/v1/chat/agent/apply",
        {"workspace": workspace, "changes": changes},
        timeout=120,
    )


def ensure_workspace(base: str, workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        http_json(base, "POST", "/api/v1/harness/workspace/ensure", {"workspace": str(workspace)})
    except Exception:
        pass
