# -*- coding: utf-8 -*-
"""接口级测试：直接调用后端 chat/agent 端点，检查 file_change content 是否含字面 \\n。"""
import sys, time, json, requests, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

API = "http://127.0.0.1:8003/api/v1"
WS = Path("E:/FNIX/_api_test_literal_n")

# Clean workspace
if WS.exists():
    for root, dirs, files in os.walk(str(WS), topdown=False):
        for f in files:
            p = os.path.join(root, f)
            try: os.chmod(p, stat.S_IWRITE); os.unlink(p)
            except: pass
        for d in dirs:
            try: os.rmdir(os.path.join(root, d))
            except: pass
    try: os.rmdir(str(WS))
    except: pass
WS.mkdir(parents=True, exist_ok=True)

# Simple prompt
PROMPT = "创建文件 calc.py，内容为：def add(a, b): return a + b，然后创建 test_calc.py 测试它"
print(f"Prompt: {PROMPT}", flush=True)
print(f"Workspace: {WS}", flush=True)

payload = {
    "messages": [{"role": "user", "content": PROMPT}],
    "workspace": str(WS),
    "preview": True,
}

print(f"\nPOST {API}/chat/agent", flush=True)
resp = requests.post(f"{API}/chat/agent", json=payload, stream=True, timeout=300)
print(f"Status: {resp.status_code}", flush=True)

file_changes = []
done_payload = None
all_events = []

for line in resp.iter_lines(decode_unicode=True):
    if not line:
        continue
    try:
        ev = json.loads(line)
    except:
        continue
    all_events.append(ev)
    t = ev.get("type", "")
    if t == "file_change":
        fc = {
            "path": ev.get("path", ""),
            "action": ev.get("action", ""),
            "content": ev.get("content", ""),
        }
        file_changes.append(fc)
        print(f"\n[file_change] path={fc['path']} action={fc['action']}", flush=True)
        content = fc["content"]
        # Check for literal \n (backslash + n) vs real newlines
        has_literal_n = "\\n" in content
        has_real_newlines = "\n" in content
        print(f"  content length: {len(content)}", flush=True)
        print(f"  has literal \\n: {has_literal_n}", flush=True)
        print(f"  has real newlines: {has_real_newlines}", flush=True)
        print(f"  content repr (first 200): {repr(content[:200])}", flush=True)
        # Show the first few lines
        if content:
            lines = content.split("\n")
            print(f"  lines ({len(lines)}): {lines[:5]}", flush=True)
    elif t == "done":
        done_payload = ev
        changes = ev.get("changes", [])
        print(f"\n[done] status={ev.get('status', '')} changes_count={len(changes)}", flush=True)
        for ch in changes:
            content = ch.get("content", "")
            has_literal_n = "\\n" in content
            print(f"  path={ch.get('path','')} has_literal_n={has_literal_n} content_repr={repr(content[:100])}", flush=True)
    elif t == "step_start":
        print(f"[step_start] {ev.get('step', {}).get('action', '')} target={ev.get('step', {}).get('target', '')}", flush=True)
    elif t == "thinking":
        pass  # skip verbose
    elif t == "plan":
        steps = ev.get("steps", [])
        print(f"[plan] {len(steps)} steps", flush=True)
    elif t == "message":
        txt = ev.get("content", "")
        if txt:
            print(f"[message] {txt[:200]}", flush=True)
    elif t == "heartbeat":
        pass
    else:
        print(f"[{t}]", flush=True)

print(f"\n=== SUMMARY ===", flush=True)
print(f"Total events: {len(all_events)}", flush=True)
print(f"File changes: {len(file_changes)}", flush=True)
for fc in file_changes:
    content = fc["content"]
    has_literal_n = "\\n" in content
    print(f"  {fc['path']}: literal_n={has_literal_n} content_preview={repr(content[:150])}", flush=True)

# Check disk after accept (if we were to accept)
disk_files = []
if WS.exists():
    for p in WS.rglob("*"):
        if p.is_file() and ".fnix" not in str(p):
            disk_files.append(str(p.relative_to(WS)).replace("\\", "/"))
print(f"\nDisk files (preview mode, should be empty): {disk_files}", flush=True)
