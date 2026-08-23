import json, os, urllib.request, urllib.error, sys

WS = "E:/FNIX/_probe_ws"
os.makedirs(WS, exist_ok=True)

body = {
    "messages": [{"role": "user", "content": "写一个 hello.py，内容只有一行：print('hello fnix')"}],
    "workspace": WS,
    "preview": True,
    "llm": {"provider": "siliconflow", "model": "deepseek-ai/DeepSeek-V4-Flash"},
    "session_id": None,
}

req = urllib.request.Request(
    "http://127.0.0.1:8003/api/v1/chat/agent",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

print("=== NDJSON STREAM (probe) ===", flush=True)
try:
    with urllib.request.urlopen(req, timeout=400) as res:
        buf = ""
        for raw in res:
            buf += raw.decode("utf-8", "replace")
            while "\n" in buf:
                ln, buf = buf.split("\n", 1)
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    ev = json.loads(ln)
                except Exception as e:
                    print("PARSE_ERR", repr(e), ln[:200], flush=True)
                    continue
                t = ev.get("type")
                if t == "file_change":
                    keys = list(ev.keys())
                    print(f"[FILE_CHANGE] keys={keys}", flush=True)
                    print(f"   path={ev.get('path')!r} file_path={ev.get('file_path')!r}", flush=True)
                    print(f"   action={ev.get('action')!r} file_action={ev.get('file_action')!r}", flush=True)
                    print(f"   content_present={ev.get('content') is not None} content_len={len(ev.get('content') or '')}", flush=True)
                    print(f"   diff_present={ev.get('diff') is not None}", flush=True)
                elif t == "done":
                    print(f"[DONE] keys={list(ev.keys())}", flush=True)
                    ch = ev.get("changes")
                    print(f"   changes={json.dumps(ch, ensure_ascii=False)[:600] if ch is not None else None}", flush=True)
                    print(f"   status={ev.get('status')!r} error={ev.get('error')!r}", flush=True)
                elif t == "error":
                    print(f"[ERROR] {json.dumps(ev, ensure_ascii=False)[:400]}", flush=True)
                elif t in ("thinking", "plan", "step_start", "step_end", "review", "message", "heartbeat", "heal"):
                    snippet = str(ev.get("content") or ev.get("status") or ev.get("steps") or ev.get("notes") or "")[:80]
                    print(f"[{t}] {snippet}", flush=True)
                else:
                    print(f"[{t}] {str(ev)[:120]}", flush=True)
except urllib.error.HTTPError as e:
    print("HTTPError", e.code, e.read().decode("utf-8", "replace")[:400], flush=True)
except Exception as e:
    print("EXC", type(e).__name__, e, flush=True)

print("=== DISK ===", flush=True)
for root, dirs, files in os.walk(WS):
    for f in files:
        p = os.path.join(root, f)
        print(p, flush=True)
