import sqlite3, json
db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("SELECT run_id, channel, status, meta_json, created_at FROM runs ORDER BY created_at DESC LIMIT 12")
runs = cur.fetchall()
for run_id, channel, status, meta, created in runs:
    try:
        m = json.loads(meta) if meta else {}
    except Exception:
        m = {}
    tid = m.get("task_id") or m.get("taskId") or m.get("title") or (str(m.get("prompt","")).strip().encode("unicode_escape").decode()[:40])
    print(f"{run_id} | ch={channel} | status={status} | meta_task={tid} | created={created}")
con.close()
