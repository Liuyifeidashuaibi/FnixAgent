import urllib.request, json

KEY = "sk-ws-H.EYHELPR.9KBq.MEUCIQC0N1pUNBFroOihSHQqrhCfHvIdYzRNxZK5Gz1U7KuivgIge-HLC0QCl-Y4dMs6_P1_FChvJJxeoWY95_lQyBQeNbw"
BASE = "https://ws-6d3gio8qx49xqswm.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"

# 1) try listing models
print("=== GET /models ===")
req = urllib.request.Request(BASE + "/models",
    headers={"Authorization": "Bearer " + KEY}, method="GET")
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
        ids = [m.get("id") for m in data.get("data", [])]
        print("count:", len(ids))
        for i in ids:
            print("  ", i)
except urllib.error.HTTPError as e:
    print("models list HTTP", e.code, e.read().decode("utf-8","replace")[:200])
except Exception as e:
    print("models list ERR", type(e).__name__, e)

# 2) fallback: try chat on candidate models
cands = ["glm-4.7-flash","glm-4.6v-flash","glm-4.5-flash","glm-4.5","glm-4.6",
         "glm-4-plus","glm-4-flash","glm-4-air","glm-4v-flash","glm-4.7"]
print("=== chat probe ===")
for m in cands:
    body = json.dumps({"model": m, "messages":[{"role":"user","content":"hi"}], "max_tokens":1}).encode()
    req = urllib.request.Request(BASE + "/chat/completions", data=body,
        headers={"Content-Type":"application/json","Authorization":"Bearer "+KEY}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"[200] {m}  OK")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {m}  {e.read().decode('utf-8','replace')[:140]}")
    except Exception as e:
        print(f"[ERR] {m}  {type(e).__name__}: {e}")
