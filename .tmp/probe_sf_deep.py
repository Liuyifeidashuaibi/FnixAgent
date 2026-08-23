# -*- coding: utf-8 -*-
"""探测 DeepSeek-V4-Flash 完整行为: think 标签 / JSON plan 输出 / 免费兜底模型"""
import json, sys, time, urllib.request, urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SF_KEY = "sk-enoehoumlbqlwoigjtqcuossucfqcuqyeotwjwgzmkwwevrj"
BASE = "https://api.siliconflow.cn/v1"

def post(payload, timeout=120):
    req = urllib.request.Request(
        BASE + "/chat/completions", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {SF_KEY}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, time.time()-t0, json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return e.code, time.time()-t0, None, e.read().decode(errors="replace")[:300]
    except Exception as e:
        return None, time.time()-t0, None, repr(e)[:200]

print("1) 完整问答, 看是否带 <think>")
st, dt, body, err = post({"model": "deepseek-ai/DeepSeek-V4-Flash", "max_tokens": 512,
    "messages": [{"role": "user", "content": "1+1=? 直接答数字"}]})
print("status:", st, f"{dt:.1f}s")
if body:
    msg = body["choices"][0]["message"]
    print("content:", repr(msg.get("content", ""))[:400])
    print("reasoning_content:", repr(msg.get("reasoning_content", ""))[:300])
    print("usage:", body.get("usage"))
if err: print("err:", err)

print()
print("2) JSON plan 输出能力(模拟 agent _plan)")
prompt = '''你是代码规划器。只输出一个 JSON 对象: {"steps":[{"action":"write","target":"path","description":"完整源码"}]}。
任务: 创建 components/header/header.component.ts, 显示标题 "My Blog", 高60px 灰底。'''
st, dt, body, err = post({"model": "deepseek-ai/DeepSeek-V4-Flash", "max_tokens": 2048,
    "messages": [{"role": "user", "content": prompt}]})
print("status:", st, f"{dt:.1f}s")
if body:
    msg = body["choices"][0]["message"]
    c = msg.get("content", "") or ""
    print("content 头300:", repr(c[:300]))
    print("content 尾300:", repr(c[-300:]))
    print("reasoning 长度:", len(msg.get("reasoning_content") or ""))
    print("usage:", body.get("usage"))
if err: print("err:", err)
