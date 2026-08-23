import urllib.request, json

BASE = "http://localhost:8003"
WS = "E:\\FNIX\\FnixAgent"
body = {
    "user_input": "请用 write_file 工具在 outputs/ 目录下创建文件 diag_glm.txt，文件内容仅一行：glm-toolcall-ok。只做这一件事。",
    "workspace": WS,
    "work_mode": "craft",
    "session_id": "diag-glm-2b8c",
}
data = json.dumps(body).encode()
req = urllib.request.Request(
    BASE + "/api/v1/work/stream", data=data,
    headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=180) as resp:
    buf = ""
    while True:
        chunk = resp.read(4096)
        if not chunk:
            break
        buf += chunk.decode("utf-8", "replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                print("RAW:", line[:300])
                continue
            ct = ev.get("chunk_type") or ev.get("type")
            c = ev.get("content")
            s = json.dumps(ev, ensure_ascii=False)
            if ct == "text":
                print("TEXT:", str(c)[:200])
            elif ct == "artifact":
                print("ARTIFACT:", json.dumps(c, ensure_ascii=False)[:300])
            elif ct == "mission":
                print("MISSION:", json.dumps(c, ensure_ascii=False)[:200])
            elif ct == "error":
                print("ERROR:", str(c)[:600])
            elif ct == "done":
                print("DONE:", json.dumps(c, ensure_ascii=False)[:800])
            else:
                print(f"[{ct}]", s[:200])
