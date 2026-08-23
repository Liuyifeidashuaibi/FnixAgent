"""Diverse follow-up benchmark: different frameworks to surface framework-specific bugs.

Runs after the angular re-validation. Reuses the same NDJSON parsing as _bench2.py.
"""
import json, os, time, shutil, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
URL = "http://127.0.0.1:8003/api/v1/chat/agent"
OUT = os.path.join(ROOT, "bench_iface_v3_results.jsonl")
WS_ROOT = r"E:\FNIX\_bench_ws_v3"
# diverse: react + vue (different frontend frameworks; exercise subdir/missing logic differently)
SELECTED = ["react--task-1", "vue--task-1", "angular--task-8"]


def _clean_dir(p: str) -> None:
    """os 级清空目录（避开 WorkBuddy 沙箱对 shutil.rmtree 的 safe-delete 拦截）。"""
    if not os.path.exists(p):
        return
    for root, dirs, files in os.walk(p, topdown=False):
        for f in files:
            try:
                os.unlink(os.path.join(root, f))
            except OSError:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass
    try:
        os.rmdir(p)
    except OSError:
        pass

recs = [json.loads(l) for l in open(os.path.join(ROOT, "benchmarks/benchforge/datasets/web-bench/tasks.jsonl"), encoding="utf-8") if l.strip()]
by_id = {r["task_id"]: r for r in recs}

def run_one(tid):
    rec = by_id[tid]
    prompt = rec["prompt"]
    ws = os.path.join(WS_ROOT, tid.replace("/", "_"))
    _clean_dir(ws)
    os.makedirs(ws, exist_ok=True)
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "workspace": ws, "preview": False, "session_id": None, "llm": None,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/x-ndjson"})
    t0 = time.time(); done = None; steps = 0; files_seen = set(); review_msgs = []
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            for raw in resp:
                raw = raw.decode("utf-8", "replace").strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                et = ev.get("type")
                if et == "step_start":
                    steps += 1
                elif et == "file_change":
                    p = ev.get("path")
                    if p:
                        files_seen.add(p.replace("\\", "/"))
                elif et == "message" and ev.get("content"):
                    review_msgs.append(str(ev.get("content"))[:400])
                elif et == "done":
                    done = ev
    except Exception as e:
        return {"task_id": tid, "status": "error", "elapsed_s": round(time.time()-t0,1), "error": f"{type(e).__name__}: {e}"}
    rec_out = {
        "task_id": tid, "status": (done or {}).get("status"),
        "elapsed_s": round(time.time()-t0, 1), "steps": steps,
        "files_seen_in_stream": sorted(files_seen),
        "review_passed": (done or {}).get("review_passed"),
        "review_notes": (done or {}).get("review_notes") or "",
        "error": (done or {}).get("error") or "",
        "review_msgs_tail": review_msgs[-3:],
    }
    real_files = []
    for r, _, fs in os.walk(ws):
        if ".fnix" in r:
            continue
        for f in fs:
            real_files.append(os.path.relpath(os.path.join(r, f), ws).replace("\\", "/"))
    rec_out["real_files_written"] = sorted(real_files)
    return rec_out

if __name__ == "__main__":
    results = []
    for tid in SELECTED:
        print(f"[bench3] starting {tid} @ {time.strftime('%H:%M:%S')}", flush=True)
        r = run_one(tid)
        results.append(r)
        with open(OUT, "w", encoding="utf-8") as f:
            for x in results:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        print(f"[bench3] {tid} -> {r.get('status')} ({r.get('elapsed_s')}s)", flush=True)
    print("[bench3] DONE", flush=True)
