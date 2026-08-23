# -*- coding: utf-8 -*-
"""探测各 LLM 端点与模型可用性 (2026-08-23)"""
import json, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SF_KEY = "sk-enoehoumlbqlwoigjtqcuossucfqcuqyeotwjwgzmkwwevrj"
ZHIPU_KEY = "6e07b8b7a4b04339b4dc85416e0d1605.9aExNzed07Fe81a8"

def post(url, key, payload, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
            return r.status, time.time()-t0, body, None
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors="replace")[:300]
        return e.code, time.time()-t0, None, txt
    except Exception as e:
        return None, time.time()-t0, None, repr(e)[:200]

def get(url, key, timeout=30):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return e.code, None, e.read().decode(errors="replace")[:300]
    except Exception as e:
        return None, None, repr(e)[:200]

print("=" * 60)
print("1) 硅基流动 /user/info (查余额)")
st, body, err = get("https://api.siliconflow.cn/v1/user/info", SF_KEY)
print("status:", st)
if body: print(json.dumps(body, ensure_ascii=False)[:500])
if err: print("err:", err)

print("=" * 60)
print("2) 硅基流动 models 列表(筛 deepseek)")
st, body, err = get("https://api.siliconflow.cn/v1/models?type=text", SF_KEY)
print("status:", st)
if body:
    ids = [m.get("id","") for m in body.get("data",[])]
    ds = [i for i in ids if "deepseek" in i.lower() or "DeepSeek" in i]
    print("deepseek 系列:", ds)
if err: print("err:", err)

print("=" * 60)
print("3) 硅基流动 chat 测试: deepseek-ai/DeepSeek-V4-Flash")
st, dt, body, err = post("https://api.siliconflow.cn/v1/chat/completions", SF_KEY,
    {"model": "deepseek-ai/DeepSeek-V4-Flash", "max_tokens": 16,
     "messages": [{"role": "user", "content": "reply with just: OK"}]})
print("status:", st, f"{dt:.1f}s")
if body:
    try: print("resp:", body["choices"][0]["message"]["content"][:100])
    except Exception: print(json.dumps(body, ensure_ascii=False)[:300])
if err: print("err:", err)

print("=" * 60)
print("4) 智谱 glm 复测 (glm-4.5-flash / glm-4.7-flash)")
for m in ["glm-4.5-flash", "glm-4.7-flash", "glm-4-flash"]:
    st, dt, body, err = post("https://open.bigmodel.cn/api/paas/v4/chat/completions", ZHIPU_KEY,
        {"model": m, "max_tokens": 16, "messages": [{"role": "user", "content": "reply with just: OK"}]})
    print(f"  {m}: status={st} {dt:.1f}s", ("OK" if body and body.get("choices") else (err or "")[:200]))
