"""直接测试 dashscope API key 是否有效。"""
import urllib.request
import urllib.error
import json
from pathlib import Path

api_key = ""
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DASHSCOPE_API_KEY="):
        api_key = line.split("=", 1)[1].strip()
        break

print(f"key length: {len(api_key)}")
print(f"key prefix: {api_key[:15]}...")

req = urllib.request.Request(
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    data=json.dumps(
        {"model": "qwen-plus", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    ).encode("utf-8"),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=20) as r:
        print("STATUS:", r.status)
        body = r.read().decode("utf-8")
        print("BODY:", body[:400])
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"HTTPError {e.code}: {body[:400]}")
except Exception as e:
    print("ERR:", type(e).__name__, str(e))
