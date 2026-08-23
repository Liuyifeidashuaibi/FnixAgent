import sys, json, sqlite3
sys.path.insert(0, "src")
from pathlib import Path
from fnixagent.core.code.agent import CodingAgent

ROOT = r"E:\FNIX\_bench_ws\angular--task-2"
class FakeTools:
    _root = ROOT
    preview_mode = False

class S:
    def __init__(self, action, target, status, result=None):
        self.action = action; self.target = target; self.status = status; self.result = result

# reconstruct steps from run events
db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db); cur = con.cursor()
run = "3b26a313fbfc4582"
cur.execute("SELECT sequence, event_type, payload_json FROM run_events WHERE run_id=? ORDER BY sequence ASC", (run,))
rows = cur.fetchall()
starts = []
ends = []
for seq, etype, pj in rows:
    p = json.loads(pj); d = p.get("data", p)
    if etype == "step_start":
        starts.append({"action": d.get("action"), "target": d.get("target"), "status": None})
    elif etype == "step_end":
        ends.append({"action": d.get("action"), "target": d.get("target"), "status": d.get("status")})
# pair ends to starts (FIFO by action+target)
steps = []
import copy
rem = list(ends)
for st in starts:
    for i,e in enumerate(rem):
        if e["action"]==st["action"] and e["target"]==st["target"] and e["status"] is not None:
            steps.append(S(st["action"], st["target"], e["status"])); rem.pop(i); break
    else:
        steps.append(S(st["action"], st["target"], "unknown"))

agent = object.__new__(CodingAgent)
agent._tools = FakeTools()

# inferred required from task description
desc = "Angular blog app with header/main/blog components, list-item 40px border-box, flex layout, mock data"
reqs = CodingAgent._infer_required_files(desc)
print("inferred required (dummy desc):", reqs)

# Now test against actual files present on disk
present_files = [str(p) for p in Path(ROOT).rglob("*") if p.is_file() and ".fnix" not in str(p)]
print("\non-disk code files:", [Path(f).relative_to(ROOT).as_posix() for f in present_files if f.endswith(('.ts','.tsx','.js','.jsx','.html','.css','.json'))])

print("\n=== _deliverable_present checks ===")
for t in ["main.component.ts","blog.component.ts","app.component.ts","styles.css","package.json"]:
    print(f"  {t}: {CodingAgent._deliverable_present(agent, t, steps)}")

print("\n=== _missing_deliverables ===")
print(CodingAgent._missing_deliverables(agent, steps))
