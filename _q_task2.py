import sqlite3, json
db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db)
cur = con.cursor()
# find runs table schema
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)
for t in tables:
    try:
        cur.execute(f"SELECT * FROM {t} LIMIT 1")
        cols = [d[0] for d in cur.description]
        print(f"  {t}: {cols}")
    except Exception as e:
        print(f"  {t}: ERR {e}")
con.close()
