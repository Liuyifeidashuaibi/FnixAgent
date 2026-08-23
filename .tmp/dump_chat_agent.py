import json, urllib.request
BASE = "http://127.0.0.1:8003"
def post(path, body, token=None, timeout=90):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(BASE+path, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")
st, body = post("/api/v1/auth/owner/login", {"username":"admin","owner_token":"fnix-owner-local-2026"})
token = json.loads(body)["access_token"]
st, raw = post("/api/v1/chat/agent", {
    "messages": [{"role":"user","content":"只回答一句话：1+1=几？"}],
    "workspace": r"C:/Users/liuyi/.fnix/workspaces/default",
    "session_id": "chat-test-verify-004",
    "preview": True,
    "llm": {"provider":"qwen","model":"qwen3.7-max-2026-05-17"},
}, token)
print("HTTP", st)
print(repr(raw[:2000]))
