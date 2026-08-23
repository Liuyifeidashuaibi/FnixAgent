import sqlite3, json
db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()
run = "208dfc02878c482b"
cur.execute("SELECT sequence, event_type, payload_json FROM run_events WHERE run_id=? ORDER BY sequence ASC", (run,))
rows = cur.fetchall()
for seq, etype, pj in rows:
    try:
        p = json.loads(pj)
    except Exception:
        print(f"[{seq}] {etype}: <unparseable {len(pj)}b>")
        continue
    d = p.get("data", p)
    if etype == "step_start":
        print(f"[{seq}] step_start: {json.dumps(d, ensure_ascii=False)[:200]}")
    elif etype == "step_end":
        print(f"[{seq}] step_end: status={d.get('status')} note={str(d.get('note',''))[:160]}")
    elif etype == "file_change":
        print(f"[{seq}] file_change: {str(d.get('path', d))[:160]}")
    elif etype == "plan":
        print(f"[{seq}] plan: {json.dumps(d, ensure_ascii=False)[:200]}")
    elif etype == "thinking":
        print(f"[{seq}] thinking: {str(d).get('text','')[:120] if isinstance(d,dict) else str(d)[:120]}")
    else:
        print(f"[{seq}] {etype}")
con.close()
