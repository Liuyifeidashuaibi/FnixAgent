import sys, json, sqlite3
sys.path.insert(0, "src")
from pathlib import Path
from fnixagent.core.code.agent import CodingAgent

WS = {
    "208dfc02878c482b": r"E:\FNIX\_bench_ws\angular--task-1",
    "3b26a313fbfc4582": r"E:\FNIX\_bench_ws\angular--task-2",
}
TASK_DESC = {
    "208dfc02878c482b": "1) Create components/header/header.component.ts that displays 'Hello Blog'... 2) Create components/main/main.component.ts ... 3) Develop components/blog/blog.component.ts that accepts 'title' and 'detail'... 4) Include header.component.ts and main.component.ts in app.component.ts 5) blog-title class ... width fit-content fontSize 24px",
    "3b26a313fbfc4582": "1) Create a blog-list component that accepts an array of blogs as input property and displays titles in div with class 'list-item'. 2) In main.component.ts mock blog data... 3) Position blog-list on left with width 300px; each blog item height 40px border-box. 4) Only one blog.component.ts occupies remaining space. 5) Angular V19",
}

class FakeTools:
    preview_mode = False
class S:
    def __init__(self, action, target, status, result=None):
        self.action=action; self.target=target; self.status=status; self.result=result

db = "C:/Users/liuyi/.fnix/runs.sqlite3"
con = sqlite3.connect(db); cur = con.cursor()

EXPL = {"read","search","grep","ls","explore","view","cat","find","glob","inspect","open","list","stat","diff","describe"}

def reconstruct(run):
    cur.execute("SELECT sequence, event_type, payload_json FROM run_events WHERE run_id=? ORDER BY sequence ASC", (run,))
    rows = cur.fetchall()
    starts=[]; ends=[]
    for seq, etype, pj in rows:
        p=json.loads(pj); d=p.get("data",p)
        if etype=="step_start": starts.append({"action":d.get("action"),"target":d.get("target"),"status":None})
        elif etype=="step_end": ends.append({"action":d.get("action"),"target":d.get("target"),"status":d.get("status")})
    steps=[]; rem=list(ends)
    for st in starts:
        for i,e in enumerate(rem):
            if e["action"]==st["action"] and e["target"]==st["target"] and e["status"] is not None:
                steps.append(S(st["action"],st["target"],e["status"])); rem.pop(i); break
        else:
            steps.append(S(st["action"],st["target"],"unknown"))
    return steps

def simulate(run):
    root = WS[run]
    ft = FakeTools(); ft._root = root
    agent = object.__new__(CodingAgent); agent._tools = ft
    steps = reconstruct(run)
    desc = TASK_DESC[run]
    required_bases = {CodingAgent._normalize_code_target(r).replace("\\","/").split("/")[-1] for r in CodingAgent._infer_required_files(desc)}
    # failed (new logic)
    failed=[]
    for s in steps:
        if s.status!="failed": continue
        a=(s.action or "").strip().lower()
        if a in EXPL: continue
        t=(s.target or "").strip()
        if not t: continue
        base=CodingAgent._normalize_code_target(t).replace("\\","/").split("/")[-1]
        if base not in required_bases: continue
        if CodingAgent._deliverable_present(agent, t, steps): continue
        failed.append((s.action,s.target))
    # missing (new logic)
    missing=CodingAgent._missing_deliverables(agent, steps)
    for req in CodingAgent._infer_required_files(desc):
        if req not in missing and not CodingAgent._deliverable_present(agent, req, steps):
            missing.append(req)
    return required_bases, failed, missing

for run in WS:
    rb, failed, missing = simulate(run)
    print(f"\n==== run {run} ({WS[run].split('/')[-1]}) ====")
    print(" required_bases:", sorted(rb))
    print(" failed (fatal) :", failed)
    print(" missing        :", missing)
    print(" -> passed(static, ignoring llm):", (not failed and not missing))
