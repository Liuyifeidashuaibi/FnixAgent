#!/usr/bin/env python3
"""一键运行全部实验的编排脚本。

对应论文章节：Section 5 — Experiments (全量编排)

依次运行 exp1 → exp2 → exp3 → exp4:
    - exp1: FCS 基准扩大 + 统计 (纯本地, 无 LLM)
    - exp2: KTG 消融 (检索本地, score 需 agentd, 可降级)
    - exp3: MFP x DAAO 析因消融 (路由本地, score 需 agentd, 可降级)
    - exp4: 纵向自进化模拟 (纯本地, 无 LLM)

汇总结果到 paper/experiments/results/all_results.json, 输出摘要表到 stdout。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER_ROOT = ROOT / "paper"
RESULTS_DIR = PAPER_ROOT / "experiments" / "results"
EXPERIMENTS_DIR = PAPER_ROOT / "experiments"

EXPERIMENTS = [
    ("exp1_fcs_scale", "exp1_fcs_scale.py"),
    ("exp2_ktg_ablation", "exp2_ktg_ablation.py"),
    ("exp3_mfp_daao_ablation", "exp3_mfp_daao_ablation.py"),
    ("exp4_longitudinal", "exp4_longitudinal.py"),
]

RESULT_FILES = {
    "exp1_fcs_scale": "exp1_fcs_stats.json",
    "exp2_ktg_ablation": "exp2_ktg_ablation.json",
    "exp3_mfp_daao_ablation": "exp3_ablation.json",
    "exp4_longitudinal": "exp4_longitudinal.json",
}


def run_experiment(script: str, extra_args: list[str]) -> tuple[int, str]:
    """运行单个实验脚本, 返回 (exit_code, 末尾输出)。"""
    cmd = [sys.executable, str(EXPERIMENTS_DIR / script)] + extra_args
    print(f"\n{'=' * 70}")
    print(f"[run_all] running {script} ...")
    print(f"{'=' * 70}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min per experiment
        )
        # 打印实验输出
        if proc.stdout:
            print(proc.stdout[-3000:])
        if proc.stderr:
            print("[stderr]", proc.stderr[-1500:], file=sys.stderr)
        return proc.returncode, proc.stdout[-500:]
    except subprocess.TimeoutExpired:
        print(f"[run_all] TIMEOUT: {script}")
        return -1, "timeout"
    except Exception as exc:
        print(f"[run_all] ERROR running {script}: {exc}")
        return -2, str(exc)


def load_result(name: str) -> dict | None:
    """加载实验结果 JSON。"""
    path = RESULTS_DIR / RESULT_FILES[name]
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run all FSE 2027 experiments in sequence")
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Task limit passed to exp2/exp3 (0 = default per script)",
    )
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8003",
        help="agentd base URL passed to exp2/exp3",
    )
    ap.add_argument(
        "--no-agent",
        action="store_true",
        help="Skip agentd for exp2/exp3 (local metrics only)",
    )
    ap.add_argument(
        "--skip",
        nargs="*",
        default=[],
        choices=["exp1", "exp2", "exp3", "exp4"],
        help="Experiments to skip",
    )
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    skip_set = set(args.skip)
    statuses: dict[str, dict] = {}
    t0 = time.time()

    for name, script in EXPERIMENTS:
        short = name.split("_")[0]
        if short in skip_set:
            print(f"\n[run_all] skipping {name}")
            statuses[name] = {"status": "skipped", "exit_code": None}
            continue

        extra: list[str] = []
        if short in ("exp2", "exp3"):
            if args.limit > 0:
                extra += ["--limit", str(args.limit)]
            extra += ["--base", args.base]
            if args.no_agent:
                extra.append("--no-agent")

        exit_code, tail = run_experiment(script, extra)
        statuses[name] = {
            "status": "ok" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "tail": tail,
        }

    elapsed = round(time.time() - t0, 1)

    # ---- 汇总结果 ----
    all_results: dict[str, dict | None] = {}
    for name, _ in EXPERIMENTS:
        all_results[name] = load_result(name)

    summary = {
        "experiment": "run_all",
        "paper_section": "Section 5 — Experiments",
        "statuses": statuses,
        "total_elapsed_s": elapsed,
        "results": all_results,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    out_path = RESULTS_DIR / "all_results.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[run_all] aggregated results -> {out_path}")

    # ---- 摘要表 ----
    print("\n" + "=" * 70)
    print("=== FSE 2027 Experiments Summary ===")
    print("=" * 70)
    print(f"{'experiment':>24} {'status':>8} {'exit':>5}")
    for name, _ in EXPERIMENTS:
        st = statuses.get(name, {})
        print(f"{name:>24} {st.get('status', '?'):>8} {str(st.get('exit_code', '?')):>5}")
    print(f"\n  total elapsed: {elapsed}s")

    # 关键指标摘要
    print("\n--- Key Metrics ---")
    exp1 = all_results.get("exp1_fcs_scale") or {}
    if exp1:
        print(
            f"  exp1: tasks={exp1.get('total_tasks')} "
            f"valid_rate={exp1.get('valid_rate')}% "
            f"effective={exp1.get('effective_rate_percent')}%"
        )
    exp4 = all_results.get("exp4_longitudinal") or {}
    if exp4 and exp4.get("horizons"):
        h90 = next((h for h in exp4["horizons"] if h["horizon_days"] == 90), exp4["horizons"][-1])
        print(
            f"  exp4 (90d): nodes={h90.get('final', {}).get('active_nodes')} "
            f"solidified={h90.get('final', {}).get('solidified_patterns')} "
            f"retrieval_hit={h90.get('retrieval_hit_rate_percent')}%"
        )
    exp3 = all_results.get("exp3_mfp_daao_ablation") or {}
    if exp3:
        print(f"  exp3: self_evolution_gain={exp3.get('self_evolution_gain')}")
    exp2 = all_results.get("exp2_ktg_ablation") or {}
    if exp2 and exp2.get("summary"):
        full = exp2["summary"].get("full_ktg", {})
        no_ktg = exp2["summary"].get("no_ktg", {})
        print(
            f"  exp2: full_ktg hit={full.get('retrieval_hit_rate_percent')}% "
            f"vs no_ktg hit={no_ktg.get('retrieval_hit_rate_percent')}%"
        )

    failed = [n for n, s in statuses.items() if s.get("status") == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
