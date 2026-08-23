"""前端驱动评测器 — 通过 Tauri 前端同款 HTTP 链路跑全量评测。

链路（与 apps/workbench/src/shell/desktop/fnixRuntime.ts 完全一致）：
  1. POST  /api/v1/auth/owner/login          → 拿 admin token（前端 owner 通道）
  2. POST  /api/v1/work/jobs                 → 派发任务（前端 enqueueJob）
  3. GET   /api/v1/work/jobs/{sid}/events    → 轮询进度（前端 getJobEvents）
  4. GET   /api/v1/work/jobs                 → 列表确认（前端 listJobs）

判定：启发式（无 LLM 判定，省配额）。支持断点续跑：跳过已成功任务。
配额感知：连续基础设施错误（403/429）熔断停止，剩余保持 pending 待续跑。
"""
import asyncio
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(r"E:\FNIX\FnixAgent")
sys.path.insert(0, str(ROOT / "src"))

BASE = "http://127.0.0.1:8003"
MODEL = os.environ.get("BENCH_MODEL", "qwen-turbo")
RUN_DIR = ROOT / "benchmarks/benchforge/runs/batch-v6-frontend-20260822"
RESULTS = RUN_DIR / "results.jsonl"
WORKSPACES_ROOT = RUN_DIR / "workspaces"

# 从 .env 读取 API key（不打印）
_env = {}
for _line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        _env[_k.strip()] = _v.strip()
API_KEY = _env.get("CUSTOM_API_KEY", "")

_token: str = ""


# ── HTTP 基础 ──────────────────────────────────────────────────────────────

def _req(method: str, path: str, body: dict | None = None, timeout: float = 60) -> dict:
    headers = {"Content-Type": "application/json"}
    if _token:
        headers["Authorization"] = f"Bearer {_token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return {"ok": True, "status": resp.status, "json": json.loads(raw)}
            except Exception:
                return {"ok": True, "status": resp.status, "json": {"raw": raw}}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return {"ok": False, "status": e.code, "json": json.loads(raw)}
        except Exception:
            return {"ok": False, "status": e.code, "json": {"detail": raw[:300]}}
    except Exception as e:
        return {"ok": False, "status": 0, "json": {"detail": str(e)[:200]}}


# ── 任务数据 ───────────────────────────────────────────────────────────────

def load_tasks() -> list[dict]:
    """直接从缓存目录读取全部任务（避免依赖 CLI 模块）。"""
    from fnixagent.bench.datasets import DatasetManager
    mgr = DatasetManager(ROOT / "benchmarks/benchforge/datasets")
    tasks = list(mgr.load_all([], refresh=False))
    # 排序：web-bench 按项目分组 + init 优先（B6 语义）
    tasks.sort(
        key=lambda t: (
            t.dataset,
            t.subset if t.dataset == "web-bench" else "",
            0 if t.task_id.endswith("--init") else int(
                "".join(ch for ch in t.task_id.rsplit("--", 1)[-1] if ch.isdigit()) or 0
            ),
        )
    )
    return [
        {"dataset": t.dataset, "task_id": t.task_id, "prompt": t.prompt, "subset": t.subset}
        for t in tasks
    ]


def load_completed() -> set[str]:
    """从历史批次收集已成功任务（断点续跑）。"""
    done: set[str] = set()
    for p in [
        ROOT / "benchmarks/benchforge/runs/batch-v3-20260822/results.jsonl",
        ROOT / "benchmarks/benchforge/runs/batch-v4-20260822/results.jsonl",
        RESULTS,
    ]:
        if not p.exists():
            continue
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("status") == "success":
                done.add(f"{rec.get('dataset')}/{rec.get('task_id')}")
    return done


# ── 单任务执行（前端链路）───────────────────────────────────────────────────

def _workspace_for(task: dict) -> Path:
    """web-bench 项目级共享工作区；其他数据集独立工作区。"""
    if task["dataset"] == "web-bench" and task.get("subset"):
        proj = "".join(c if c.isalnum() or c in "._-" else "_" for c in task["subset"])
        ws = WORKSPACES_ROOT / f"web-bench__{proj}__shared"
    else:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in task["task_id"])
        ws = WORKSPACES_ROOT / f"{task['dataset']}__{safe}"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _is_infra_err(text: str) -> bool:
    t = (text or "").lower()
    for pat in (
        "insufficient_quota", "free quota exhausted", "invalid_api_key",
        "http 401", "http 403", "http 404", "http 429", "http 402",
        "rate limit", "too many requests", "throttl",
    ):
        if pat in t:
            return True
    return False


async def run_one_frontend(task: dict, judge_heuristic) -> dict:
    """通过前端链路跑单任务：POST jobs → 轮询 events → 判定。"""
    ws = _workspace_for(task)
    rec = {
        "dataset": task["dataset"], "task_id": task["task_id"],
        "prompt": task["prompt"], "workspace": str(ws),
        "status": "pending", "failure_type": "", "failure_evidence": "",
        "final_response": "", "error": "", "steps": [], "tool_calls": [],
        "files_written": [], "total_tokens": 0, "duration_ms": 0,
        "judge_method": "heuristic-frontend", "started_at": time.time(),
    }
    started = time.time()
    # 1) 派发（前端 enqueueJob 同款请求体）
    r = _req("POST", "/api/v1/work/jobs", {
        "user_input": task["prompt"],
        "workspace": str(ws),
        "llm": {"provider": "qwen", "model": MODEL, "api_key": API_KEY},
        "user_id": "admin",
        "priority": 10,
    }, timeout=30)
    if not r["ok"]:
        rec["error"] = f"enqueue failed: {r['json'].get('detail', r['status'])}"
        if _is_infra_err(str(rec["error"])):
            rec["status"] = "infra_skip"
            rec["failure_evidence"] = f"基础设施错误(派发): {rec['error'][:150]}"
        else:
            rec["status"] = "failure"
            rec["failure_type"] = "other"
            rec["failure_evidence"] = rec["error"][:150]
        rec["duration_ms"] = int((time.time() - started) * 1000)
        return rec
    sid = r["json"].get("session_id") or r["json"].get("id") or ""
    if not sid:
        rec["status"] = "failure"
        rec["failure_type"] = "other"
        rec["failure_evidence"] = f"派发响应无 session_id: {json.dumps(r['json'])[:120]}"
        rec["duration_ms"] = int((time.time() - started) * 1000)
        return rec

    # 2) 轮询 events（前端 getJobEvents，最多 10 分钟）
    deadline = time.time() + 600
    last_session = None
    while time.time() < deadline:
        await asyncio.sleep(3)
        er = _req("GET", f"/api/v1/work/jobs/{sid}/events?limit=200", timeout=20)
        if not er["ok"]:
            continue
        ev = er["json"]
        session = ev.get("session") or {}
        last_session = session
        st = session.get("status")
        if st in ("completed", "failed", "cancelled", "error"):
            rec["final_response"] = str(session.get("result") or "")
            rec["error"] = str(session.get("error") or "")
            if st == "failed" and _is_infra_err(rec["error"]):
                rec["status"] = "infra_skip"
                rec["failure_evidence"] = f"基础设施错误(执行): {rec['error'][:150]}"
            else:
                # 交给启发式判定器
                rec["steps"] = [s for s in session.get("steps") or []]
                v = judge_heuristic(task, rec, st)
                rec["status"] = v["status"]
                rec["failure_type"] = v["failure_type"]
                rec["failure_evidence"] = v["evidence"]
            rec["duration_ms"] = int((time.time() - started) * 1000)
            return rec

    # 超时
    rec["status"] = "failure"
    rec["failure_type"] = "other"
    rec["failure_evidence"] = f"轮询超时(600s) status={last_session.get('status') if last_session else 'none'}"
    rec["duration_ms"] = int((time.time() - started) * 1000)
    return rec


# ── 启发式判定（与 bench/judge.py 同语义，无 LLM）──────────────────────────

def heuristic_judge(task: dict, rec: dict, backend_status: str) -> dict:
    files = rec.get("files_written") or []
    resp = rec.get("final_response") or ""
    if backend_status == "failed":
        err = rec.get("error") or ""
        if "deadloop" in err or "死循环" in err or "熔断" in err:
            return {"status": "failure", "failure_type": "incomplete_output",
                    "evidence": f"死循环熔断: {err[:150]}"}
        return {"status": "failure", "failure_type": "crash", "evidence": err[:150]}
    if not resp.strip() and not files:
        # 检查是否有真实产出文件
        return {"status": "failure", "failure_type": "incomplete_output",
                "evidence": "无最终回复且未产出任何文件"}
    return {"status": "success", "failure_type": "", "evidence": ""}


# ── 主流程 ─────────────────────────────────────────────────────────────────

def append_result(rec: dict) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


async def main() -> int:
    global _token
    # 1) owner 登录（前端 owner 通道）
    r = _req("POST", "/api/v1/auth/owner/login",
             {"username": "admin", "owner_token": "fnix-owner-local-2026"})
    if not r["ok"]:
        print(f"[fatal] owner 登录失败: {r['json']}", file=sys.stderr)
        return 1
    _token = r["json"]["access_token"]
    print(f"[auth] owner 登录成功 token_len={len(_token)}")

    # 2) 加载任务 + 断点续跑
    tasks = load_tasks()
    completed = load_completed()
    pending = [t for t in tasks if f"{t['dataset']}/{t['task_id']}" not in completed]
    print(f"[tasks] 总任务 {len(tasks)} | 已完成 {len(completed)} | 待跑 {len(pending)}")
    if not pending:
        print("[done] 无待跑任务")
        return 0

    # 3) 并发执行（web-bench 同项目串行）
    concurrency = 3
    sem = asyncio.Semaphore(concurrency)
    proj_locks: dict[tuple, asyncio.Lock] = {}
    done_count = 0
    infra_streak = 0
    quota_aborted = False

    def proj_lock(task: dict) -> asyncio.Lock | None:
        if task["dataset"] == "web-bench" and task.get("subset"):
            key = (task["dataset"], task["subset"])
            if key not in proj_locks:
                proj_locks[key] = asyncio.Lock()
            return proj_locks[key]
        return None

    async def worker(task: dict) -> None:
        nonlocal done_count, infra_streak, quota_aborted
        async with sem:
            if quota_aborted:
                return
            plock = proj_lock(task)
            try:
                if plock is not None:
                    async with plock:
                        rec = await run_one_frontend(task, heuristic_judge)
                else:
                    rec = await run_one_frontend(task, heuristic_judge)
            except Exception as exc:
                rec = {
                    "dataset": task["dataset"], "task_id": task["task_id"],
                    "prompt": task["prompt"], "status": "failure",
                    "failure_type": "crash", "failure_evidence": f"runner 异常: {exc}",
                    "error": str(exc), "final_response": "", "steps": [],
                    "tool_calls": [], "files_written": [], "duration_ms": 0,
                    "started_at": time.time(),
                }
            append_result(rec)
            mark = "OK " if rec["status"] == "success" else (
                "SKP" if rec["status"] == "infra_skip" else "ERR")
            print(f"[{mark}] {rec['dataset']}/{rec['task_id']} "
                  f"-> {rec['status']} ({rec.get('failure_type','')}) "
                  f"{rec['duration_ms']//1000}s")
            if rec["status"] == "infra_skip":
                infra_streak += 1
                if infra_streak >= 10:
                    quota_aborted = True
                    print("[quota] 连续 10 条基础设施错误，熔断停止（剩余任务保持 pending 待续跑）")
            else:
                infra_streak = 0
            done_count += 1

    await asyncio.gather(*(worker(t) for t in pending))
    # 汇总
    rows = [json.loads(l) for l in RESULTS.read_text("utf-8").splitlines() if l.strip()]
    from collections import Counter
    c = Counter(r["status"] for r in rows)
    print(f"\n[done] 前端链路评测完成: 总记录 {len(rows)} 成功 {c.get('success',0)} "
          f"失败 {c.get('failure',0)} infra_skip {c.get('infra_skip',0)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
