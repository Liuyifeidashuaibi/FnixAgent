# -*- coding: utf-8 -*-
import json, sys, time, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SF_KEY = "sk-enoehoumlbqlwoigjtqcuossucfqcuqyeotwjwgzmkwwevrj"

candidates = [
    "deepseek-ai/DeepSeek-V3.2",
    "Qwen/Qwen3-8B",
    "Qwen/Qwen2.5-7B-Instruct",
    "THUDM/GLM-4-9B-0414",
    "Qwen/Qwen3-14B",
]
for m in candidates:
    req = urllib.request.Request(
        "https://api.siliconflow.cn/v1/chat/completions",
        data=json.dumps({"model": m, "max_tokens": 8,
            "messages": [{"role": "user", "content": "say OK"}]}).encode(),
        headers={"Authorization": f"Bearer {SF_KEY}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = json.loads(r.read().decode())
            print(f"{m}: 200 {time.time()-t0:.1f}s -> {b['choices'][0]['message'].get('content','')[:30]!r}")
    except urllib.error.HTTPError as e:
        print(f"{m}: HTTP {e.code} {e.read().decode(errors='replace')[:150]}")
    except Exception as e:
        print(f"{m}: ERR {repr(e)[:150]}")
