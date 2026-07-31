#!/usr/bin/env python3
"""Run Work golden scenarios — artifacts must land under .fnix/artifacts/."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
GOLDEN = ROOT / "benchmarks" / "work" / "golden"


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
        "model": os.environ.get("LLM_MODEL", "qwen3.7-plus"),
        "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
        "base_url": os.environ.get(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    }


def expand_brace_glob(pattern: str) -> list[str]:
    """Expand a single `{a,b}` brace group into multiple globs."""
    m = re.search(r"\{([^{}]+)\}", pattern)
    if not m:
        return [pattern]
    opts = [o.strip() for o in m.group(1).split(",") if o.strip()]
    return [pattern[: m.start()] + opt + pattern[m.end() :] for opt in opts] or [pattern]


def collect_hits(ws: Path, expect_glob: str) -> list[Path]:
    hits: list[Path] = []
    for pat in expand_brace_glob(expect_glob.replace("\\", "/")):
        for p in ws.glob(pat):
            if p.is_file():
                hits.append(p)
    if hits:
        return hits
    # Fallback: any file under .fnix/artifacts whose relative path matches prefix dir
    art = ws / ".fnix" / "artifacts"
    if not art.is_dir():
        return []
    prefix = expect_glob.replace("\\", "/").split("**")[0].rstrip("/")
    prefix = prefix.replace(".fnix/artifacts/", "").strip("/")
    for p in art.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(art).as_posix()
        if not prefix or rel.startswith(prefix + "/") or rel.startswith(prefix):
            # suffix filter from glob tail
            if "." in expect_glob.rsplit("/", 1)[-1]:
                tail = expect_glob.rsplit("/", 1)[-1]
                suffs = expand_brace_glob(tail.replace("*", ""))
                suffs = [s for s in suffs if s.startswith(".")]
                if suffs and p.suffix.lower() not in {s.lower() for s in suffs}:
                    continue
            hits.append(p)
    return hits


def stream_work(
    base: str,
    prompt: str,
    workspace: str,
    work_mode: str,
    timeout: int,
    session_id: str,
) -> dict:
    body = {
        "user_input": prompt,
        "workspace": workspace,
        "work_mode": work_mode,
        "llm": llm(),
        "session_id": session_id,
    }
    headers = {"Content-Type": "application/json"}
    cap = (os.environ.get("FNIX_CAPABILITY_TOKEN") or "").strip()
    if cap:
        headers["X-Fnix-Capability"] = cap
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/work/stream",
        data=json.dumps(body).encode(),
        method="POST",
        headers=headers,
    )
    arts: list[str] = []
    err = ""
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            ev = json.loads(line)
            ct = ev.get("chunk_type") or ev.get("type")
            content = ev.get("content") if "content" in ev else ev.get("data")
            if ct == "artifact" and isinstance(content, dict) and content.get("path"):
                arts.append(str(content["path"]))
            elif ct == "error":
                err = str(content)
            elif ct == "done" and isinstance(content, dict):
                for a in content.get("artifacts") or []:
                    if isinstance(a, dict) and a.get("path"):
                        arts.append(str(a["path"]))
    return {"artifacts": arts, "error": err}


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("VITE_API_BASE", "http://127.0.0.1:8003"))
    ap.add_argument("--limit", type=int, default=0, help="0 = all scenarios")
    ap.add_argument("--min-pass", type=int, default=8, help="Beta gate for full run")
    args = ap.parse_args()

    if not llm().get("api_key"):
        if os.environ.get("GATE_FCS_LIVE", "").strip() in ("1", "true", "yes"):
            print("FAIL: GATE_FCS_LIVE=1 but DASHSCOPE_API_KEY is empty")
            return 1
        print("SKIP: no DASHSCOPE_API_KEY")
        return 0

    scenarios = sorted(GOLDEN.glob("*.json"))
    if args.limit and args.limit > 0:
        scenarios = scenarios[: args.limit]
    if not scenarios:
        print("no golden scenarios")
        return 1

    fails = 0
    with tempfile.TemporaryDirectory(prefix="fnix-work-golden-") as tmp:
        ws = Path(tmp)
        for path in scenarios:
            sc = json.loads(path.read_text(encoding="utf-8"))
            sid = f"e2e-work-golden-{sc.get('id', path.stem)}"
            print(f"\n== {sc['id']} ==")
            res = stream_work(
                args.base,
                sc["prompt"],
                str(ws),
                sc.get("work_mode", "craft"),
                int(sc.get("timeout_s", 180)),
                sid,
            )
            if res["error"]:
                print(f"  FAIL stream: {res['error']}")
                err_l = res["error"].lower()
                if "freetier" in err_l or "quota" in err_l or "额度" in res["error"]:
                    print("       hint: DashScope 免费额度耗尽 — 换模型/充值后重试")
                fails += 1
                continue
            hits = collect_hits(ws, sc["expect_glob"])
            under_art = [
                h
                for h in hits
                if ".fnix" in h.as_posix() and "artifacts" in h.as_posix()
            ]
            min_files = int(sc.get("expect_min_files") or 1)
            if len(under_art) < min_files:
                print(
                    f"  FAIL need ≥{min_files} under expect "
                    f"(got {len(under_art)}; stream arts={res['artifacts']})"
                )
                fails += 1
                continue

            from fnixagent.core.benchmark.work_openability import score_artifacts

            min_open = float(sc.get("min_openability") or os.environ.get("FNIX_WORK_MIN_OPEN", "0.8"))
            openness = score_artifacts(under_art, min_score=min_open)
            if not openness["ok"]:
                print(
                    f"  FAIL openability mean={openness['mean']} "
                    f"openable={openness['openable']}/{openness['count']} (min={min_open})"
                )
                for it in openness["items"][:5]:
                    print(f"       {it['score']} {it['reason']}  {it['path']}")
                fails += 1
                continue

            print(
                f"  OK  {len(under_art)} artifact(s) · openability={openness['mean']}"
            )
            for h in under_art[:5]:
                print(f"       {h}")

    passed = len(scenarios) - fails
    total = len(scenarios)
    gate = args.min_pass if total >= 10 and (args.limit == 0) else total
    ok = passed >= gate if total >= 10 and args.limit == 0 else fails == 0
    label = "PASS" if ok else "FAIL"
    print(f"\n{label} — {passed}/{total} (beta gate ≥{gate})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
