#!/usr/bin/env python3
"""实验 1：FCS 基准扩大到千级 + 统计分析。

对应论文章节：Section 5.1 — Benchmark Scale-up & Coverage Analysis

目的:
    - 将 FCS (Fnix Code Score) 基准从 9 个 seed 任务扩大到千级
    - 统计任务数量、能力维度分布、难度分布
    - 用 dry_checks_only 模式 (不调 LLM) 跑全部任务的 checks, 验证任务包有效性
    - 输出 capability×difficulty 分布矩阵, 供论文图表使用

纯本地实验: 不依赖 agentd / LLM, 可独立运行。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.code.benchmark.runner import RunOptions, run_task
from fnixagent.core.code.benchmark.schema import (
    CAPABILITIES,
    DIFFICULTY_WEIGHT,
    load_task,
    validate_task,
)

BENCHMARK_ROOT = ROOT / "benchmarks" / "code"
PAPER_ROOT = ROOT / "paper"
RESULTS_DIR = PAPER_ROOT / "experiments" / "results"
FIGURES_DIR = PAPER_ROOT / "figures"


def discover_tasks(root: Path) -> list[Path]:
    """扫描 seed/ 与 generated/ 目录, 收集全部任务 JSON 文件。"""
    tasks: list[Path] = []
    for sub in ("seed", "generated"):
        d = root / sub
        if d.is_dir():
            tasks.extend(sorted(d.glob("*.json")))
    return tasks


def build_distribution_matrix(tasks: list[Path]) -> dict:
    """构建 capability × difficulty 任务分布矩阵。"""
    difficulties = sorted(DIFFICULTY_WEIGHT.keys())
    matrix: dict[str, dict[str, int]] = {}
    for cap in sorted(CAPABILITIES):
        matrix[cap] = {str(d): 0 for d in difficulties}

    cap_counter: dict[str, int] = {cap: 0 for cap in CAPABILITIES}
    diff_counter: dict[str, int] = {str(d): 0 for d in difficulties}
    lang_counter: dict[str, int] = {}

    for p in tasks:
        try:
            task = load_task(p)
        except Exception:
            continue
        for cap in task.capability:
            if cap in cap_counter:
                cap_counter[cap] += 1
                matrix[cap][str(task.difficulty)] += 1
        diff_counter[str(task.difficulty)] = diff_counter.get(str(task.difficulty), 0) + 1
        lang_counter[task.language] = lang_counter.get(task.language, 0) + 1

    return {
        "matrix": matrix,
        "by_capability": cap_counter,
        "by_difficulty": diff_counter,
        "by_language": lang_counter,
        "capabilities": sorted(CAPABILITIES),
        "difficulties": [str(d) for d in difficulties],
    }


def run_dry_checks(tasks: list[Path], limit: int) -> list[dict]:
    """用 dry_checks_only 模式跑 checks, 验证任务包有效性。

    dry_checks_only 不调 LLM, 仅在临时工作区物化 setup.files 后跑声明式 checks。
    对于 setup 已含正确解的生成任务, checks 应通过; 对空 setup 的 seed 任务, checks
    会因文件缺失而失败 (符合预期 — 这些任务需要 LLM 生成产物)。
    """
    opts = RunOptions(dry_checks_only=True, agent_base_url="", skip_agent=True)
    sample = tasks if limit <= 0 else tasks[:limit]
    results: list[dict] = []
    t0 = time.perf_counter()
    for i, p in enumerate(sample, 1):
        try:
            score = run_task(p, opts)
            results.append(
                {
                    "task_id": score.task_id,
                    "task_score": score.task_score,
                    "hard_pass": score.hard_pass,
                    "correctness": score.correctness,
                    "completeness": score.completeness,
                    "difficulty": score.difficulty,
                    "capability": score.capability,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "task_id": p.stem,
                    "task_score": 0.0,
                    "hard_pass": False,
                    "correctness": 0.0,
                    "completeness": 0.0,
                    "difficulty": 0,
                    "capability": [],
                    "error": str(exc),
                }
            )
        if i % 100 == 0:
            elapsed = time.perf_counter() - t0
            print(f"  [dry-check {i}/{len(sample)}] elapsed={elapsed:.1f}s")
    return results


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Exp1: FCS benchmark scale-up + statistical analysis (no LLM)"
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap dry-check validation sample (0 = all tasks). Stats always run on all.",
    )
    ap.add_argument(
        "--benchmark-root",
        type=Path,
        default=BENCHMARK_ROOT,
        help="Benchmark root directory",
    )
    args = ap.parse_args()

    bench_root = args.benchmark_root
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("[exp1] discovering tasks ...")
    tasks = discover_tasks(bench_root)
    print(f"[exp1] discovered {len(tasks)} task files ({bench_root})")

    # ---- 统计分析 (全部任务, 纯 JSON 加载, 秒级) ----
    print("[exp1] building distribution matrix ...")
    dist = build_distribution_matrix(tasks)

    total_valid = 0
    total_invalid = 0
    invalid_details: list[dict] = []
    for p in tasks:
        try:
            task = load_task(p)
            errors = validate_task(task)
            if errors:
                total_invalid += 1
                invalid_details.append({"task": p.name, "errors": errors})
            else:
                total_valid += 1
        except Exception as exc:
            total_invalid += 1
            invalid_details.append({"task": p.name, "errors": [f"load_error: {exc}"]})

    seed_count = sum(1 for p in tasks if p.parent.name == "seed")
    gen_count = sum(1 for p in tasks if p.parent.name == "generated")
    effective_rate = 0.0

    # ---- dry-check 有效性验证 ----
    dry_limit = args.limit if args.limit > 0 else len(tasks)
    print(f"[exp1] running dry-checks on {dry_limit} tasks (dry_checks_only, no LLM) ...")
    dry_results = run_dry_checks(tasks, args.limit)
    dry_pass = sum(1 for r in dry_results if r["hard_pass"])
    if dry_results:
        effective_rate = round(100.0 * dry_pass / len(dry_results), 2)
    # dry-check FCS 估计: 取样本 task_score 的均值 (dry 模式下生成任务 setup 含解, 应接近满分)
    dry_fcs_estimate = (
        round(sum(r["task_score"] for r in dry_results) / len(dry_results), 2)
        if dry_results
        else 0.0
    )

    stats = {
        "experiment": "exp1_fcs_scale",
        "paper_section": "Section 5.1 — Benchmark Scale-up & Coverage",
        "benchmark_root": str(bench_root),
        "total_tasks": len(tasks),
        "seed_count": seed_count,
        "generated_count": gen_count,
        "valid_tasks": total_valid,
        "invalid_tasks": total_invalid,
        "valid_rate": round(100.0 * total_valid / max(1, len(tasks)), 2),
        "dry_check_sample": len(dry_results),
        "dry_check_hard_pass": dry_pass,
        "effective_rate_percent": effective_rate,
        "by_capability": dist["by_capability"],
        "by_difficulty": dist["by_difficulty"],
        "by_language": dist["by_language"],
        "invalid_details": invalid_details[:20],
        "dry_check_fcs_estimate": dry_fcs_estimate,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # ---- 输出分布矩阵 (供论文图表) ----
    fcs_dist_path = FIGURES_DIR / "fcs_distribution.json"
    fcs_dist_path.write_text(
        json.dumps(dist, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[exp1] distribution matrix -> {fcs_dist_path}")

    # ---- 输出完整统计 ----
    stats_path = RESULTS_DIR / "exp1_fcs_stats.json"
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[exp1] stats -> {stats_path}")

    # ---- 摘要 ----
    print("\n=== Exp1 Summary ===")
    print(f"  total tasks      : {len(tasks)} (seed={seed_count}, gen={gen_count})")
    print(f"  valid (schema)   : {total_valid}/{len(tasks)} ({stats['valid_rate']}%)")
    print(f"  dry-check sample : {len(dry_results)}, hard_pass={dry_pass} ({effective_rate}%)")
    print(f"  capabilities     : {len(dist['by_capability'])} dims")
    print(f"  difficulties     : {dist['by_difficulty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
