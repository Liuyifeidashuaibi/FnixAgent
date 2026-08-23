#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FnixAgent 全量编码 Agent 基准评测 Harness
==========================================

驱动真实的 FnixAgent 后端 (POST /api/v1/work/jobs + 轮询 /jobs/{sid}/events) 来
执行公开编码 Agent 基准数据集，记录完整轨迹、判定成功/失败、产出回归测试集与统计报告。

设计原则（对齐用户硬性约束）:
- 不抽样、不筛选: 默认加载并运行所有数据集的全部任务。
- 不改写任务: 原样传入数据集中的原始 prompt。
- 轨迹/回归/统计全部落盘，不只在控制台输出。
- 单条任务互不继承上下文（每次 dispatch 用独立 workspace）。
- 遇到解析/下载异常只记录、不中断整体流程。

用法:
  # 列出各数据集可加载的任务数
  python benchrunner.py list

  # 运行（小批量冒烟，默认 qwen-turbo 避免 120s 超时）
  python benchrunner.py run --datasets web-bench,vibe-code-bench --limit 3 --model qwen-turbo

  # 全量（后台长任务）
  python benchrunner.py run --datasets all --concurrency 2

  # 生成汇总报告 + 回归集
  python benchrunner.py report --run <run_id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = REPO_ROOT / "test-results" / "benchmark" / "datasets"
DEFAULT_BASE_URL = "http://127.0.0.1:8003"
RUNS_DIR = Path(__file__).resolve().parent / "runs"

FAILURE_TYPES = [
    "planning",          # 规划拆解错误
    "mcp_error",         # MCP/工具调用异常
    "incomplete_output", # 输出残缺
    "wrong_path",        # 多文件路径错误
    "context_loss",      # 上下文记忆丢失
    "requirement_mismatch",  # 需求理解偏差
    "crash",             # 运行崩溃
    "timeout",           # 超时
    "other",
]


# ----------------------------------------------------------------------------
# Task model
# ----------------------------------------------------------------------------
@dataclass
class Task:
    dataset: str
    task_id: str
    prompt: str
    meta: dict = field(default_factory=dict)
    setup: dict = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.dataset}::{self.task_id}"


# ----------------------------------------------------------------------------
# Config / env
# ----------------------------------------------------------------------------
def load_server_api_key() -> str | None:
    """从仓库根 .env 读取 DASHSCOPE_API_KEY，作为评测的 BYOK key（用户自有 key）。"""
    envpath = REPO_ROOT / ".env"
    if not envpath.exists():
        return None
    for line in envpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DASHSCOPE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


# ----------------------------------------------------------------------------
# Dataset loaders  (raw prompt, unmodified)
# ----------------------------------------------------------------------------
def _iter_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def load_web_bench(root: Path) -> list[Task]:
    base = root / "web-bench" / "projects"
    out: list[Task] = []
    if not base.exists():
        return out
    for pj in sorted(base.iterdir()):
        if not pj.is_dir():
            continue
        tj = pj / "tasks.jsonl"
        if not tj.exists():
            continue
        for rec in _iter_jsonl(tj):
            desc = rec.get("description")
            if not desc:
                continue
            out.append(Task(
                dataset="web-bench",
                task_id=f"{pj.name}/{rec.get('id')}",
                prompt=desc,
                meta={"project": pj.name, "level": rec.get("level"), "date": rec.get("date")},
                setup={"kind": "scaffold", "src": str(pj)},
            ))
    return out


def load_vibe(root: Path) -> list[Task]:
    base = root / "vibe-code-bench" / "eval_cases"
    out: list[Task] = []
    if not base.exists():
        return out
    for case in sorted(base.iterdir()):
        if not case.is_dir():
            continue
        spec = case / "spec.md"
        if not spec.exists():
            continue
        out.append(Task(
            dataset="vibe-code-bench",
            task_id=case.name,
            prompt=spec.read_text(encoding="utf-8"),
            meta={"case": case.name},
            setup={"kind": "fresh"},
        ))
    return out


def load_prototype(root: Path) -> list[Task]:
    base = root / "prototypebench" / "tasks"
    out: list[Task] = []
    if not base.exists():
        return out
    for f in sorted(base.glob("instances*.jsonl")):
        for rec in _iter_jsonl(f):
            ps = rec.get("problem_statement")
            if not ps:
                continue
            out.append(Task(
                dataset="prototypebench",
                task_id=str(rec.get("instance_id") or rec.get("id") or f.name),
                prompt=ps,
                meta={
                    "pr_title": rec.get("pr_title"),
                    "repo": rec.get("repo") or (rec.get("environment") or {}).get("repo"),
                    "pr_url": rec.get("pr_url"),
                },
                setup={"kind": "fresh"},
            ))
    return out


def load_workbuddy(root: Path) -> list[Task]:
    base = root / "workbuddy-bench" / "extracted"
    out: list[Task] = []
    if not base.exists():
        return out
    try:
        import tomllib
    except Exception:
        tomllib = None  # type: ignore

    def read_toml(p: Path) -> dict:
        if tomllib is None or not p.exists():
            return {}
        try:
            with p.open("rb") as f:
                return tomllib.load(f)
        except Exception:
            return {}

    for subset in sorted(base.iterdir()):
        if not subset.is_dir() or not subset.name.startswith("wb-bench-"):
            continue
        sname = subset.name[len("wb-bench-"):-len("-v1.0")]  # code/office/sec/web
        tasks_dir = subset / "tasks"
        if not tasks_dir.exists():
            continue
        for task_dir in sorted(tasks_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            instr = task_dir / "instruction.md"
            if not instr.exists():
                continue
            prompt = instr.read_text(encoding="utf-8").strip()
            if not prompt:
                continue
            toml = read_toml(task_dir / "task.toml")
            meta = {}
            if toml:
                t = toml.get("task", {})
                m = toml.get("metadata", {})
                meta = {
                    "subset": sname,
                    "name": t.get("name"),
                    "difficulty": m.get("difficulty"),
                    "category": m.get("category"),
                    "subcategory": m.get("subcategory"),
                    "repo": m.get("repo"),
                }
            out.append(Task(
                dataset="workbuddy-bench",
                task_id=f"{sname}/{task_dir.name}",
                prompt=prompt,
                meta=meta,
                setup={"kind": "fresh"},
            ))
    return out


def load_gaia(root: Path) -> list[Task]:
    """GAIA 以 parquet 存储；若未下载则跳过并记录。"""
    out: list[Task] = []
    # 支持已下载的 parquet
    for pf in (root / "gaia-hf").rglob("*.parquet"):
        try:
            import pyarrow.parquet as pq
            tbl = pq.read_table(pf)
            for row in tbl.to_pylist():
                q = row.get("Question") or row.get("question")
                if not q:
                    continue
                out.append(Task(
                    dataset="gaia",
                    task_id=str(row.get("task_id") or row.get("id") or len(out)),
                    prompt=q,
                    meta={"file_name": row.get("file_name"), "steps": row.get("steps"),
                          "final_answer": row.get("final_answer")},
                    setup={"kind": "fresh", "attached_file": row.get("file_name")},
                ))
        except Exception as e:
            print(f"[gaia] 读取 {pf} 失败: {e}", file=sys.stderr)
    return out


def load_swebench_lite(root: Path) -> list[Task]:
    base = root / "swe-bench-lite-hf" / "data"
    out: list[Task] = []
    if not base.exists():
        return out
    import pyarrow.parquet as pq
    for pf in sorted(base.glob("*.parquet")):
        tbl = pq.read_table(pf)
        for row in tbl.to_pylist():
            ps = row.get("problem_statement")
            if not ps:
                continue
            out.append(Task(
                dataset="swe-bench-lite",
                task_id=str(row.get("instance_id") or len(out)),
                prompt=ps,
                meta={"repo": row.get("repo"), "base_commit": row.get("base_commit"),
                      "patch": (row.get("patch") or "")[:200]},
                setup={"kind": "repo", "repo": row.get("repo"), "base_commit": row.get("base_commit")},
            ))
    return out


LOADERS = {
    "web-bench": load_web_bench,
    "vibe-code-bench": load_vibe,
    "prototypebench": load_prototype,
    "workbuddy-bench": load_workbuddy,
    "gaia": load_gaia,
    "swe-bench-lite": load_swebench_lite,
}


def load_all(root: Path, only: Iterable[str] | None = None) -> dict[str, list[Task]]:
    result: dict[str, list[Task]] = {}
    for name, fn in LOADERS.items():
        if only and name not in only:
            continue
        try:
            tasks = fn(root)
            result[name] = tasks
            print(f"[load] {name}: {len(tasks)} 任务", file=sys.stderr)
        except Exception as e:
            print(f"[load] {name} 失败: {e}", file=sys.stderr)
            traceback.print_exc()
            result[name] = []
    return result


# ----------------------------------------------------------------------------
# Workspace setup
# ----------------------------------------------------------------------------
EXCLUDE_DIRS = {".git", "node_modules", ".vite", "__pycache__", ".fnix"}


def setup_workspace(task: Task, ws_root: Path) -> tuple[Path, set[str], dict]:
    """为任务准备独立 workspace，返回 (workspace_path, baseline_files, baseline_mtime)。"""
    ws = ws_root / task.dataset / task.task_id.replace("/", "__")
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    baseline: set[str] = set()
    baseline_mtime: dict = {}
    kind = task.setup.get("kind")
    if kind == "scaffold":
        src = Path(task.setup["src"])
        # 复制项目脚手架（排除重目录），agent 在其上修改
        for p in src.rglob("*"):
            if any(part in EXCLUDE_DIRS for part in p.relative_to(src).parts):
                continue
            rel = p.relative_to(src)
            target = ws / rel
            if p.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
        baseline = _snapshot(ws)
        baseline_mtime = _snapshot_mtime(ws)
    else:
        baseline = set()
        baseline_mtime = {}
    return ws, baseline, baseline_mtime


def _snapshot(ws: Path) -> set[str]:
    files = set()
    for p in ws.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(ws).parts):
            continue
        if p.is_file():
            files.add(str(p.relative_to(ws).as_posix()))
    return files


def _snapshot_mtime(ws: Path) -> dict[str, float]:
    m: dict[str, float] = {}
    for p in ws.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(ws).parts):
            continue
        if p.is_file():
            try:
                m[str(p.relative_to(ws).as_posix())] = p.stat().st_mtime
            except OSError:
                pass
    return m


def _count_fnix_artifacts(ws: Path) -> int:
    art = ws / ".fnix" / "artifacts"
    if not art.is_dir():
        return 0
    n = 0
    for p in art.rglob("*"):
        if p.is_file():
            n += 1
    return n


def workspace_changes(ws: Path, baseline: set[str], baseline_mtime: dict | None = None) -> dict:
    after = _snapshot(ws)
    new = after - baseline
    removed = baseline - after
    modified = 0
    if baseline_mtime:
        after_mtime = _snapshot_mtime(ws)
        for rel, mt in baseline_mtime.items():
            if rel in after_mtime and abs(after_mtime[rel] - mt) > 0.5:
                modified += 1
    return {"new": len(new), "removed": len(removed), "modified": modified,
            "total_after": len(after), "new_files": sorted(list(new))[:50]}


# ----------------------------------------------------------------------------
# Backend client
# ----------------------------------------------------------------------------
def dispatch_job(base_url: str, prompt: str, workspace: str, llm: dict, timeout_s: int) -> str:
    body = {
        "user_input": prompt,
        "workspace": workspace,
        "llm": llm,
        "priority": 10,
    }
    r = requests.post(f"{base_url}/api/v1/work/jobs", json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"dispatch rejected: {data}")
    return data.get("session_id")


def poll_job(base_url: str, sid: str, timeout_s: int, interval: float = 2.0) -> tuple[str, list, dict]:
    seen: dict[str, dict] = {}
    status = "pending"
    session: dict = {}
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            r = requests.get(f"{base_url}/api/v1/work/jobs/{sid}/events",
                             params={"limit": 200}, timeout=30)
            j = r.json()
            session = j.get("session") or {}
            for e in (j.get("events") or []):
                key = (e.get("type"), hashlib.sha1(
                    json.dumps(e.get("data", ""), ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12])
                seen[key] = e
            status = session.get("status", status)
        except Exception as e:
            print(f"  [poll] {sid} 轮询异常: {e}", file=sys.stderr)
        if status in ("completed", "failed", "cancelled"):
            break
        time.sleep(interval)
    else:
        status = "timeout"
    return status, list(seen.values()), session


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------
def score_run(status: str, events: list, session: dict, ws: Path, baseline: set[str],
              baseline_mtime: dict, setup_kind: str) -> tuple[str, str | None, str]:
    txt = json.dumps(events, ensure_ascii=False)
    err = (session.get("error") or "")
    combined = (err + " " + txt).lower()

    if status == "timeout":
        return "fail", "timeout", "超过任务级超时，后台 job 未结束"
    if status == "cancelled":
        return "fail", "other", "任务被取消"
    if status == "failed":
        if "readtimeout" in combined or "timeout" in combined:
            return "fail", "timeout", f"失败含超时信息: {err[:200]}"
        if "tool" in combined and ("error" in combined or "exception" in combined):
            return "fail", "mcp_error", f"工具/MCP 调用异常: {err[:200]}"
        return "fail", "crash", f"运行崩溃: {err[:200]}"

    # completed
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    artifacts_events = [e for e in events if e.get("type") == "artifact"]
    session_artifacts = session.get("artifacts") or []
    fnix_n = _count_fnix_artifacts(ws)
    changes = workspace_changes(ws, baseline, baseline_mtime)
    natural_produced = (changes.get("new", 0) > 0) or (changes.get("modified", 0) > 0) \
        or (changes.get("total_after", 0) > 0 if not baseline else False)
    produced = bool(artifacts_events) or bool(session_artifacts) or natural_produced or fnix_n > 0

    if not tool_calls:
        return "fail", "requirement_mismatch", "agent 完成但无任何工具调用（需求未被执行/理解偏差）"
    if not produced:
        return "fail", "incomplete_output", "agent 完成但未产出任何文件/产物"

    # scaffold 任务：若只写到 .fnix/artifacts 镜像、未就地修改/新建脚手架文件 → 路径错误
    if setup_kind == "scaffold" and not natural_produced and fnix_n > 0:
        return "fail", "wrong_path", (
            f"agent 仅写入 .fnix/artifacts 镜像({fnix_n} 个)，未就地修改/新建脚手架文件"
            f"(new={changes.get('new')}, modified={changes.get('modified')})")

    note = (f"完成，工作区 new={changes.get('new')} modified={changes.get('modified')} "
            f".fnix镜像={fnix_n} 工具调用={len(tool_calls)}")
    return "pass", None, note


# ----------------------------------------------------------------------------
# Run orchestration
# ----------------------------------------------------------------------------
def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--datasets", default="all", help="逗号分隔；all=全部")
    p.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--limit", type=int, default=0, help="每数据集最多运行 N 条（0=全部）")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--model", default="qwen-turbo")
    p.add_argument("--provider", default="qwen")
    p.add_argument("--llm-timeout", type=float, default=600, help="单条 LLM 请求超时(秒)，透传给后端")
    p.add_argument("--timeout", type=int, default=600, help="单任务超时(秒)")
    p.add_argument("--api-key", default=None, help="默认读 .env DASHSCOPE_API_KEY")
    p.add_argument("--run-id", default=None)
    p.add_argument("--redo", action="store_true", help="忽略已完成，重跑")
    args = p.parse_args(argv)

    api_key = args.api_key or load_server_api_key()
    if not api_key:
        print("错误: 未找到 DASHSCOPE_API_KEY（.env 或 --api-key）。", file=sys.stderr)
        sys.exit(2)

    only = None
    if args.datasets != "all":
        only = [d.strip() for d in args.datasets.split(",") if d.strip()]

    root = Path(args.data_root)
    all_tasks = load_all(root, only)
    # 扁平化 + 可选 limit
    plan: list[Task] = []
    for name, tasks in all_tasks.items():
        if args.limit:
            tasks = tasks[:args.limit]
        plan.extend(tasks)

    run_id = args.run_id or time.strftime("run-%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    traj_dir = run_dir / "trajectories"
    traj_dir.mkdir(exist_ok=True)
    ws_root = run_dir / "workspaces"
    ws_root.mkdir(exist_ok=True)

    results_jsonl = run_dir / "results.jsonl"
    done_keys = set()
    if results_jsonl.exists() and not args.redo:
        for line in results_jsonl.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                done_keys.add(f"{rec['dataset']}::{rec['task_id']}")
            except Exception:
                continue

    todo = [t for t in plan if t.key() not in done_keys]
    print(f"[run] run_id={run_id}  计划={len(plan)}  已完成={len(done_keys)}  待跑={len(todo)}  "
          f"并发={args.concurrency} 模型={args.model}", file=sys.stderr)

    llm = {"provider": args.provider, "model": args.model, "api_key": api_key,
           "timeout": args.llm_timeout}

    # 顺序执行（controllayer 评测先求稳；并发可后续开）
    successes = 0
    failures = 0
    for idx, task in enumerate(todo):
        print(f"\n=== [{idx+1}/{len(todo)}] {task.key()} ===", file=sys.stderr)
        rec: dict = asdict(task)
        rec.update({"run_id": run_id, "started_at": time.time()})
        try:
            ws, baseline, baseline_mtime = setup_workspace(task, ws_root)
            rec["workspace"] = str(ws)
            rec["baseline_files"] = sorted(baseline)
            sid = dispatch_job(args.base_url, task.prompt, str(ws), llm, args.timeout)
            rec["session_id"] = sid
            print(f"  dispatched session={sid}", file=sys.stderr)
            status, events, session = poll_job(args.base_url, sid, args.timeout)
            rec["status"] = status
            rec["session_status"] = session.get("status")
            rec["events"] = events
            rec["session"] = session
            verdict, ftype, note = score_run(status, events, session, ws, baseline,
                                              baseline_mtime, task.setup.get("kind", ""))
            rec["verdict"] = verdict
            rec["failure_type"] = ftype
            rec["notes"] = note
            rec["finished_at"] = time.time()
            rec["duration_s"] = round(rec["finished_at"] - rec["started_at"], 1)
            # 写单条轨迹
            (traj_dir / f"{task.dataset}__{task.task_id.replace('/', '__')}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            # 追加到 results
            with results_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps({k: v for k, v in rec.items() if k != "events"}, ensure_ascii=False) + "\n")
                # events 另存，避免 jsonl 过大
            (traj_dir / f"{task.dataset}__{task.task_id.replace('/', '__')}.events.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
            if verdict == "pass":
                successes += 1
                print(f"  ✅ PASS ({status}) {note}", file=sys.stderr)
            else:
                failures += 1
                print(f"  ❌ FAIL [{ftype}] ({status}) {note}", file=sys.stderr)
        except Exception as e:
            rec["verdict"] = "fail"
            rec["failure_type"] = "crash"
            rec["notes"] = f"harness 异常: {e}"
            rec["error"] = traceback.format_exc()
            rec["finished_at"] = time.time()
            rec["duration_s"] = round(rec["finished_at"] - rec["started_at"], 1)
            (traj_dir / f"{task.dataset}__{task.task_id.replace('/', '__')}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            with results_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps({k: v for k, v in rec.items() if k != "events"}, ensure_ascii=False) + "\n")
            failures += 1
            print(f"  ❌ HARNESS-CRASH: {e}", file=sys.stderr)

    print(f"\n[run] 完成。PASS={successes} FAIL={failures} (本轮) 结果: {results_jsonl}", file=sys.stderr)
    # 立即生成报告
    build_report(run_dir)
    return run_dir


# ----------------------------------------------------------------------------
# Report / regression
# ----------------------------------------------------------------------------
def build_report(run_dir: Path) -> dict:
    results_jsonl = run_dir / "results.jsonl"
    rows: list[dict] = []
    if results_jsonl.exists():
        for line in results_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue

    per_ds: dict[str, dict] = {}
    for r in rows:
        ds = r.get("dataset")
        d = per_ds.setdefault(ds, {"total": 0, "pass": 0, "fail": 0,
                                   "failure_types": {ft: 0 for ft in FAILURE_TYPES}})
        d["total"] += 1
        if r.get("verdict") == "pass":
            d["pass"] += 1
        else:
            d["fail"] += 1
            ft = r.get("failure_type") or "other"
            d["failure_types"][ft] = d["failure_types"].get(ft, 0) + 1

    # 失败类型总览
    failure_overview: dict[str, int] = {ft: 0 for ft in FAILURE_TYPES}
    for r in rows:
        if r.get("verdict") != "pass":
            ft = r.get("failure_type") or "other"
            failure_overview[ft] = failure_overview.get(ft, 0) + 1

    total = len(rows)
    stats = {
        "run_id": run_dir.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": total,
        "pass": sum(1 for r in rows if r.get("verdict") == "pass"),
        "fail": sum(1 for r in rows if r.get("verdict") != "pass"),
        "success_rate": round(sum(1 for r in rows if r.get("verdict") == "pass") / total, 4) if total else 0,
        "per_dataset": per_ds,
        "failure_overview": failure_overview,
    }
    (run_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    # 回归集（仅失败任务，含原始 prompt 便于后续重跑）
    regressions = [{
        "dataset": r.get("dataset"),
        "task_id": r.get("task_id"),
        "prompt": r.get("prompt"),
        "meta": r.get("meta"),
        "failure_type": r.get("failure_type"),
        "notes": r.get("notes"),
        "session_id": r.get("session_id"),
    } for r in rows if r.get("verdict") != "pass"]
    (run_dir / "regression.json").write_text(json.dumps(regressions, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"评测报告  run_id={run_dir.name}", file=sys.stderr)
    print(f"总任务={stats['total']}  成功={stats['pass']}  失败={stats['fail']}  "
          f"成功率={stats['success_rate']:.1%}", file=sys.stderr)
    print(f"{'-'*60}", file=sys.stderr)
    for ds, d in per_ds.items():
        rate = (d["pass"] / d["total"]) if d["total"] else 0
        print(f"  {ds:18s} 总={d['total']:4d} 成功={d['pass']:4d} 失败={d['fail']:4d} 成功率={rate:.1%}", file=sys.stderr)
    print(f"{'-'*60}", file=sys.stderr)
    print(f"失败类型分布:", file=sys.stderr)
    for ft, c in failure_overview.items():
        if c:
            print(f"  {ft:22s} {c}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"回归集: {run_dir/'regression.json'}  ({len(regressions)} 条)", file=sys.stderr)
    return stats


def report(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True, help="run_id 或 runs/<id> 路径")
    args = p.parse_args(argv)
    run_dir = Path(args.run)
    if not run_dir.exists():
        run_dir = RUNS_DIR / args.run
    if not run_dir.exists():
        print(f"未找到 run: {args.run}", file=sys.stderr)
        sys.exit(2)
    build_report(run_dir)


def list_cmd(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    p.add_argument("--datasets", default="all")
    args = p.parse_args(argv)
    only = None if args.datasets == "all" else [d.strip() for d in args.datasets.split(",")]
    all_tasks = load_all(Path(args.data_root), only)
    total = 0
    print(f"{'数据集':18s} {'任务数':>8s}")
    for name, tasks in all_tasks.items():
        print(f"{name:18s} {len(tasks):>8d}")
        total += len(tasks)
    print(f"{'—'*28}\n{'合计':18s} {total:>8d}")


def main():
    cmds = {"run": run, "report": report, "list": list_cmd}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    fn = sys.argv[1]
    cmds[fn](sys.argv[2:])


if __name__ == "__main__":
    main()
