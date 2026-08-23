import sqlite3, json, os
db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()
run = "3b26a313fbfc4582"
cur.execute("SELECT sequence, event_type, payload_json FROM run_events WHERE run_id=? ORDER BY sequence ASC", (run,))
rows = cur.fetchall()
for seq, etype, pj in rows:
    try:
        p = json.loads(pj)
    except Exception:
        continue
    d = p.get("data", p)
    if etype == "step_start":
        a = d.get("action"); t = d.get("target")
        if a in ("write","edit","read") or t:
            print(f"[{seq}] {etype}: action={a} target={t}")
    elif etype == "step_end":
        print(f"[{seq}] step_end: status={d.get('status')} action={d.get('action')} target={d.get('target')}")
    elif etype == "file_change":
        print(f"[{seq}] file_change: {d.get('path', d)}")
con.close()
