"""Interface-level smoke test for FnixAgent chat/agent with SiliconFlow DeepSeek-V4-Flash."""
import json
import os
import sys
import time
import urllib.request
import urllib.error

URL = "http://127.0.0.1:8003/api/v1/chat/agent"
WS = r"E:\FNIX\_smoke_ws"
os.makedirs(WS, exist_ok=True)

payload = {
    "messages": [
        {"role": "user", "content": "Write a Python file calc.py in the workspace that defines add(a,b) and mul(a,b) and prints add(2,3) and mul(4,5). Just create the file, no extra chat."}
    ],
    "workspace": WS,
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
print("POST ->", URL)
last = t0
try:
    with urllib.request.urlopen(req, timeout=200) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            now = time.time()
            try:
                obj = json.loads(line)
            except Exception:
                print(f"[{now-t0:.1f}s] RAW: {line[:200]}")
                continue
            etype = obj.get("type")
            if etype == "done":
                print(f"[{now-t0:.1f}s] DONE status={obj.get('status')} changes={len(obj.get('changes') or [])}")
                print("  detail:", str(obj.get('detail') or obj.get('message') or '')[:300])
            elif etype in ("step_start", "step_end"):
                step = obj.get("step") or {}
                print(f"[{now-t0:.1f}s] {etype}: {step.get('action') or step.get('title') or ''}")
            elif etype == "thinking":
                c = obj.get("content") or ""
                print(f"[{now-t0:.1f}s] thinking: {c[:80]}...")
            elif etype == "message":
                print(f"[{now-t0:.1f}s] message: {(obj.get('content') or '')[:120]}")
            elif etype == "error":
                print(f"[{now-t0:.1f}s] ERROR: {obj}")
            else:
                print(f"[{now-t0:.1f}s] {etype}: {str(obj)[:120]}")
            last = now
except urllib.error.HTTPError as e:
    print("HTTPError", e.code, e.read().decode("utf-8", "replace")[:500])
except Exception as e:
    print("EXC", type(e).__name__, e)
finally:
    print(f"elapsed={time.time()-t0:.1f}s")
    print("=== workspace files ===")
    for root, _, files in os.walk(WS):
        for f in files:
            p = os.path.join(root, f)
            print("  ", os.path.relpath(p, WS), os.path.getsize(p), "bytes")
