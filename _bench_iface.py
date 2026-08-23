"""Interface-level benchmark: run real web-bench tasks through /api/v1/chat/agent.

Captures done status, review notes, files written, errors, elapsed. Writes JSONL.
"""
import json
import os
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
URL = "http://127.0.0.1:8003/api/v1/chat/agent"
OUT = os.path.join(ROOT, "bench_iface_results.jsonl")
WS_ROOT = r"E:\FNIX\_bench_ws"

SELECTED = ["angular--task-1", "angular--task-2", "angular--task-3"]

# load prompts
recs = [json.loads(l) for l in open(os.path.join(ROOT, "benchmarks/benchforge/datasets/web-bench/tasks.jsonl"), encoding="utf-8") if l.strip()]
by_id = {r["task_id"]: r for r in recs}


def run_one(tid):
    rec = by_id[tid]
    prompt = rec["prompt"]
    ws = os.path.join(WS_ROOT, tid.replace("/", "_"))
    os.makedirs(ws, exist_ok=True)
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "workspace": ws,
        "preview": False,
        "session_id": None,
        "llm": None,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/x-ndjson",
    })
    t0 = time.time()
    done = None
    steps = 0
    files_seen = set()
    errors = []
    last_evt = t0
    try:
        with urllib.request.urlopen(req, timeout=420) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                now = time.time()
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                etype = obj.get("type")
                if etype == "step_start":
                    steps += 1
                elif etype == "file_change":
                    p = (obj.get("file_change") or {}).get("path") or obj.get("path")
                    if p:
                        files_seen.add(p)
                elif etype == "error":
                    errors.append(str(obj)[:300])
                elif etype == "done":
                    done = obj
                last_evt = now
    except urllib.error.HTTPError as e:
        errors.append(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
    dt = time.time() - t0
    # real files written to workspace
    real_files = []
    for root, _, fs in os.walk(ws):
        for f in fs:
            if ".fnix" in root:
                continue
            real_files.append(os.path.relpath(os.path.join(root, f), ws))
    status = (done or {}).get("status") if done else "no_done_event"
    review = (done or {}).get("review") if done else None
    notes = ""
    if isinstance(review, dict):
        notes = review.get("notes") or review.get("comment") or ""
    elif isinstance(review, str):
        notes = review
    result = {
        "task_id": tid,
        "status": status,
        "elapsed_s": round(dt, 1),
        "steps": steps,
        "files_seen_in_stream": len(files_seen),
        "real_files_written": real_files,
        "review_notes": str(notes)[:400],
        "errors": errors[:5],
        "done_detail": str((done or {}).get("detail") or (done or {}).get("message") or "")[:400],
    }
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"[{tid}] status={status} elapsed={dt:.1f}s steps={steps} files={len(real_files)} notes={notes[:80]!r}", flush=True)
    return result


if __name__ == "__main__":
    print("bench start", flush=True)
    for tid in SELECTED:
        if tid not in by_id:
            print("skip missing", tid, flush=True)
            continue
        run_one(tid)
    print("bench done -> ", OUT, flush=True)
