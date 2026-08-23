import sqlite3, json
db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()
run = "3b26a313fbfc4582"
cur.execute("SELECT sequence, event_type, payload_json FROM run_events WHERE run_id=? ORDER BY sequence ASC", (run,))
rows = cur.fetchall()
print("TOTAL EVENTS:", len(rows))
for seq, etype, pj in rows:
    if etype in ("done", "review", "heal"):
        try:
            p = json.loads(pj)
        except Exception as e:
            p = {"_raw": pj[:200], "_err": str(e)}
        if etype == "done":
            print(f"\n[{seq}] {etype}:")
            print(json.dumps(p, ensure_ascii=False, indent=2)[:3500])
        elif etype == "review":
            print(f"\n[{seq}] {etype}: {json.dumps(p, ensure_ascii=False)[:900]}")
        elif etype == "heal":
            print(f"\n[{seq}] {etype}: {json.dumps(p, ensure_ascii=False)[:500]}")
con.close()
