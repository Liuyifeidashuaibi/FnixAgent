"""前端链路烟雾测试：跑 web-bench bom 项目链前 3 条（init + task-1 + task-2）。"""
import asyncio, sys, os
sys.path.insert(0, r"E:/FNIX/FnixAgent/.tmp")
os.environ.setdefault("BENCH_MODEL", "qwen-turbo")

from frontend_eval import load_tasks, run_one_frontend, heuristic_judge, append_result

async def main():
    tasks = load_tasks()
    # 取 bom 项目链前 3 条
    bom = [t for t in tasks if t["dataset"] == "web-bench" and t["subset"] == "bom"][:3]
    print(f"烟雾测试: {[t['task_id'] for t in bom]}")
    for t in bom:
        rec = await run_one_frontend(t, heuristic_judge)
        print(f"  {t['task_id']}: {rec['status']} | {rec.get('failure_type','')} | {rec.get('failure_evidence','')[:60]}")
        print(f"    files: {rec.get('files_written', [])[:3]}")
        print(f"    resp: {rec.get('final_response','')[:80]!r}")
        # append_result(rec)

asyncio.run(main())
