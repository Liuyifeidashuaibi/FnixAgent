"""验证 BUG-5 修复：file_change 事件现在有 path/content"""
import json, urllib.request, time

url = "http://127.0.0.1:8003/api/v1/chat/agent"
body = json.dumps({
    "messages": [{"role": "user", "content": "写一个 hello.py，内容是 print('hello')"}],
    "workspace": r"E:\FNIX\_bug5_probe3",
    "preview": False
}).encode()

req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=120) as r:
    raw = r.read().decode()

lines = [json.loads(l) for l in raw.strip().splitlines() if l.strip()]
fc = [l for l in lines if l.get("type") == "file_change"]
done = [l for l in lines if l.get("type") == "done"]
print(f"file_change count: {len(fc)}")
if fc:
    keys = [k for k in fc[0] if fc[0][k]]
    print(f"file_change[0] non-null keys: {keys}")
    print(f"path: {fc[0].get('path', 'MISSING')}")
    content = fc[0].get("content", "")
    print(f"content (first 80): {content[:80] if content else 'MISSING'}")
    print(f"diff (first 80): {fc[0].get('diff', '')[:80]}")
print(f"done status: {done[0].get('status') if done else 'N/A'}")
print(f"done.changes count: {len(done[0].get('changes', [])) if done else 0}")
if done and done[0].get("changes"):
    c = done[0]["changes"][0]
    print(f"done.changes[0] keys: {[k for k in c if c[k]]}")
    print(f"done.changes[0].path: {c.get('path', 'MISSING')}")
