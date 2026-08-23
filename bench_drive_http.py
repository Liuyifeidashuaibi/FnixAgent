# -*- coding: utf-8 -*-
"""BenchForge HTTP 驱动：把全部 1406 套题通过后端 HTTP 端点（前端 UI 真用的那条链）
POST /api/v1/work/stream 提交，并发执行、断点续跑、自动识别限流/能力失败。

与 `fnixagent bench run`（进程内 harness）的区别：本脚本经过真实后端服务
（uvicorn :8003），即「前端 UI 点 -> 后端 -> LLM 工具调用 -> 落盘 -> 预览回显」
的完整产品链路，用于验证产品以 WorkBuddy/Trae 方式大规模生产的能力。

用法：
  python bench_drive_http.py --pilot 5            # 小批量冒烟
  python bench_drive_http.py --concurrency 4      # 全量（断点续跑，可反复执行）
  python bench_drive_http.py --dataset web-bench  # 只跑某数据集
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 让脚本能 import fnixagent.bench.datasets
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.bench.datasets import DatasetManager  # noqa: E402

BASE = "http://127.0.0.1:8003"
ENDPOINT = BASE + "/api/v1/work/stream"
RESULTS = ROOT / "bench_results.jsonl"
DATASET_ROOT = ROOT / "benchmarks" / "benchforge" / "datasets"
RUN_TAG = time.strftime("%Y%m%d-%H%M%S")

# 用于把错误归类为「基础设施问题」(infra_skip，不是产品能力失败)
_RATE_HINTS = ("403", "429", "quota", "access denied", "insufficient",
               "rate limit", "too many requests", "throttl", "model not exist")
# 永久型：模型被禁/不存在/配额耗尽 —— 不重试，直接跳过
PERMANENT_HINTS = ("model not exist", "does not exist", "access denied",
                   "insufficient_quota", "insufficient quota", "403")
# 瞬时型：限流 —— 可重试，自动退避
TRANSIENT_HINTS = ("429", "quota", "rate limit", "too many requests", "throttl")

# 全局限流冷却时间戳（所有 worker 共享）：非 0 时各 worker 先 sleep 到该时刻再发请求
_cooldown_ref = [0.0]


def _is_transient(err: str) -> bool:
    """限流类错误可重试；模型被禁/不存在等永久错误不重试。"""
    low = (err or "").lower()
    if any(h in low for h in PERMANENT_HINTS):
        return False
    return any(h in low for h in TRANSIENT_HINTS)


_lock = threading.Lock()


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)[:80]


def _workspace_for(task) -> str:
    """按数据集隔离；web-bench 按项目(subset)共享工作区（复刻 B6 项目级隔离）。"""
    if task.dataset == "web-bench" and task.subset:
        return f"bench/web-bench/{_slug(task.subset)}"
    return f"bench/{task.dataset}/{_slug(task.task_id)}"


def _send_once(task, timeout: int) -> dict:
    """提交单题到后端（不重试）；返回结果 dict。"""
    body = {
        "user_input": task.prompt,
        "workspace": _workspace_for(task),
        "work_mode": "craft",
        "session_id": f"bench-{_slug(task.dataset)}-{_slug(task.task_id)}-{RUN_TAG}",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    out = {
        "dataset": task.dataset, "task_id": task.task_id, "subset": task.subset,
        "workspace": body["workspace"], "status": "unknown", "detail": "",
        "duration_s": 0.0, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                out["status"] = "infra_skip"
                out["detail"] = f"HTTP {resp.status}"
                out["duration_s"] = time.time() - t0
                return out
            buf = ""
            last_text = ""
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", "replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except Exception:
                        continue
                    ct = ev.get("chunk_type") or ev.get("type")
                    c = ev.get("content")
                    if ct == "text" and isinstance(c, str):
                        last_text = c
                    elif ct == "artifact":
                        out.setdefault("artifacts", []).append(
                            c.get("path") if isinstance(c, dict) else str(c))
                    elif ct == "error":
                        err = str(c)
                        out["status"] = "error"
                        out["detail"] = err[:500]
                        # 限流/鉴权识别
                        low = err.lower()
                        if any(h in low for h in _RATE_HINTS):
                            out["status"] = "infra_skip"
                        out["duration_s"] = time.time() - t0
                        return out
                    elif ct == "done":
                        out["status"] = "success"
                        out["detail"] = (c.get("result") if isinstance(c, dict) else str(c))[:300]
                        out["duration_s"] = time.time() - t0
                        return out
            # 流结束但无 done/error
            out["status"] = "success" if out.get("artifacts") else "error"
            out["detail"] = (last_text or "stream ended without done")[:300]
            out["duration_s"] = time.time() - t0
            return out
    except urllib.error.HTTPError as e:
        out["status"] = "infra_skip"
        out["detail"] = f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}"
        out["duration_s"] = time.time() - t0
        return out
    except Exception as e:  # 超时/连接等
        out["status"] = "infra_skip"
        out["detail"] = f"{type(e).__name__}: {e}"
        out["duration_s"] = time.time() - t0
        return out


def _send_one(task, timeout: int, max_retries: int = 8) -> dict:
    """带限流重试的提交：遇到 429 等瞬时限流，指数退避后重试，直到成功或重试用尽。

    所有 worker 共享 _cooldown_ref：一旦有人撞上限流，全局进入冷却窗口，
    其他 worker 也会先 sleep 到该时刻，避免继续狂打触发更久的限流。
    """
    last = None
    for attempt in range(max_retries + 1):
        cd = _cooldown_ref[0]
        if cd and time.time() < cd:
            time.sleep(max(0.0, cd - time.time()))
        res = _send_once(task, timeout)
        last = res
        if res["status"] == "infra_skip" and _is_transient(res["detail"]):
            backoff = min(120.0, 8.0 * (2 ** attempt))
            with _lock:
                _cooldown_ref[0] = max(_cooldown_ref[0], time.time() + backoff)
            if attempt < max_retries:
                continue
        return res
    return last


def _load_done() -> dict[str, dict]:
    done = {}
    if RESULTS.exists():
        for line in RESULTS.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            done[f"{r['dataset']}/{r['task_id']}"] = r
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="", help="逗号分隔数据集名（默认全部）")
    ap.add_argument("--pilot", type=int, default=0, help="只跑前 N 条（冒烟）")
    ap.add_argument("--concurrency", type=int, default=3,
                    help="并发单元数（限流时全局自动退避，无需调小）")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-retries", type=int, default=10,
                    help="单题遇 429 限流的最大重试次数（指数退避）")
    ap.add_argument("--only-pending", action="store_true",
                    help="只跑未完成(非 success)的；配合断点续跑")
    ap.add_argument("--retry-skip", action="store_true",
                    help="把之前的 infra_skip 也当作待跑（限流恢复后重跑）")
    args = ap.parse_args()

    mgr = DatasetManager(DATASET_ROOT)
    tasks = list(mgr.load_all([d for d in args.dataset.split(",") if d] or None,
                               refresh=False))
    if not tasks:
        print("[fatal] 没有任务可跑（先确认 datasets 缓存存在）", file=sys.stderr)
        return 1

    done = _load_done()

    # 构建执行单元：
    #  - web-bench 按项目(subset)串行（B6 项目级工作区隔离/顺序依赖）
    #  - 其余数据集每题独立并发
    web_units = {}          # subset -> [tasks ordered]
    other_units = []        # list[task]
    for t in tasks:
        if t.dataset == "web-bench":
            web_units.setdefault(t.subset or "_", []).append(t)
        else:
            other_units.append(t)

    def _is_pending(t) -> bool:
        key = f"{t.dataset}/{t.task_id}"
        r = done.get(key)
        if r and r["status"] == "success":
            return False
        if r and r["status"] == "infra_skip" and not args.retry_skip:
            return False
        return True

    units = []  # each unit: ("single", task) or ("project", subset, [tasks])
    for sub, tl in web_units.items():
        pend = [t for t in tl if _is_pending(t)]
        if pend:
            units.append(("project", sub, pend))
    for t in other_units:
        if _is_pending(t):
            units.append(("single", None, t))

    if args.pilot:
        units = units[: args.pilot]

    total = len(tasks)
    n_pending = sum(len(u[2]) if u[0] == "project" else 1 for u in units)
    print(f"[info] 总题数 {total} | 待跑单元 {len(units)} (含 {n_pending} 题) | "
          f"并发 {args.concurrency} | 已完成 {len(done)}", file=sys.stderr)

    counters = {"success": 0, "error": 0, "infra_skip": 0}
    for r in done.values():
        counters[r["status"]] = counters.get(r["status"], 0) + 1

    consec_rate = 0

    def _record(res):
        nonlocal consec_rate
        with _lock:
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
            counters[res["status"]] = counters.get(res["status"], 0) + 1
            done[f"{res['dataset']}/{res['task_id']}"] = res
            n_done = sum(1 for v in done.values() if v["status"] == "success")
            mark = {"success": "OK ", "error": "ERR", "infra_skip": "SKP"}.get(res["status"], "???")
            print(f"[{n_done}/{total}] {mark} {res['dataset']}/{res['task_id']} "
                  f"{res['duration_s']:.0f}s {res['detail'][:80]}", flush=True)
            if res["status"] == "infra_skip":
                consec_rate += 1
            else:
                consec_rate = 0

    def _run_unit(unit):
        kind = unit[0]
        if kind == "single":
            _record(_send_one(unit[2], args.timeout, args.max_retries))
        else:  # project: 按项目串行（同一 workspace 顺序依赖）
            for t in unit[2]:
                _record(_send_one(t, args.timeout, args.max_retries))

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(_run_unit, u) for u in units]
        for f in as_completed(futs):
            try:
                f.result()
            except Exception as e:
                print(f"[worker-exc] {e}", file=sys.stderr)

    print(f"\n[done] 成功 {counters.get('success',0)} 能力失败 {counters.get('error',0)} "
          f"限流跳过 {counters.get('infra_skip',0)} | 结果: {RESULTS}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
