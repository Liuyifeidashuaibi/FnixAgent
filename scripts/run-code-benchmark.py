#!/usr/bin/env python3
"""Run Fnix Code Benchmark and emit FCS report.

Exit codes:
  0 — success (and hard_pass_rate meets --min-hard-pass when set)
  1 — no tasks / validation failure / hard_pass below threshold
"""

from __future__ import annotations
# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.code.benchmark.report import write_report
from fnixagent.core.code.benchmark.runner import RunOptions, load_manifest, resolve_task_paths, run_task
from fnixagent.core.code.benchmark.schema import load_task
from fnixagent.core.code.benchmark.scorer import aggregate_scores


def load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


def filter_tasks(
    benchmark_root: Path,
    task_ids: list[str],
    *,
    tag: str | None,
    capability: str | None,
    limit: int | None,
) -> list[str]:
    out: list[str] = []
    for tid in task_ids:
        matched = False
        for sub in ("seed", "generated"):
            p = benchmark_root / sub / f"{tid}.json"
            if not p.is_file():
                continue
            task = load_task(p)
            if tag and tag not in task.tags:
                continue
            if capability and capability not in task.capability:
                continue
            out.append(tid)
            matched = True
            break
        if not matched:
            continue
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Run Fnix Code Benchmark")
    ap.add_argument("--benchmark-root", type=Path, default=ROOT / "benchmarks" / "code")
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Override manifest path (default: <benchmark-root>/manifest.json)",
    )
    ap.add_argument("--base", default=os.environ.get("VITE_API_BASE", "http://127.0.0.1:8003"))
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--tag", default="", help="Filter by task tag e.g. smoke")
    ap.add_argument("--capability", default="", help="Filter by capability")
    ap.add_argument("--dry-checks", action="store_true", help="Only validate task checks on setup (no LLM)")
    ap.add_argument(
        "--validate-only",
        action="store_true",
        help="Load/validate task JSON only (no workspace checks, no LLM)",
    )
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--report-dir", type=Path, default=ROOT / "reports")
    ap.add_argument("--label", default="")
    ap.add_argument(
        "--min-hard-pass",
        type=float,
        default=None,
        help="Fail if hard_pass_rate (%%) is below this threshold",
    )
    ap.add_argument(
        "--min-tasks",
        type=int,
        default=1,
        help="Fail if fewer than N tasks matched (default 1)",
    )
    args = ap.parse_args()

    manifest_path = args.manifest or (args.benchmark_root / "manifest.json")
    if not manifest_path.is_file():
        print(f"manifest missing: {manifest_path}")
        print("run: python scripts/generate-code-tasks.py --count 1000")
        return 1

    task_ids = load_manifest(manifest_path)
    filtered = filter_tasks(
        args.benchmark_root,
        task_ids,
        tag=args.tag or None,
        capability=args.capability or None,
        limit=args.limit if args.limit > 0 else None,
    )
    paths = resolve_task_paths(args.benchmark_root, filtered)
    if not paths:
        print("no tasks matched filters")
        return 1
    if len(paths) < args.min_tasks:
        print(f"too few tasks: {len(paths)} < min_tasks={args.min_tasks}")
        return 1

    if args.validate_only:
        errors: list[str] = []
        for p in paths:
            try:
                task = load_task(p)
                if not task.id:
                    errors.append(f"{p.name}: missing id")
                if not task.prompt:
                    errors.append(f"{p.name}: missing prompt")
                if not task.checks:
                    errors.append(f"{p.name}: missing checks")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: {exc}")
        if errors:
            print("[fcs] validate FAILED")
            for e in errors:
                print(f"  - {e}")
            return 1
        print(f"[fcs] validated {len(paths)} tasks from {manifest_path.name}")
        return 0

    opts = RunOptions(
        dry_checks_only=args.dry_checks,
        agent_base_url=args.base,
        skip_agent=args.dry_checks,
    )

    print(f"[fcs] tasks={len(paths)} dry_checks={args.dry_checks} base={args.base}")

    scores = []
    if args.parallel <= 1:
        for i, p in enumerate(paths, 1):
            s = run_task(p, opts)
            scores.append(s)
            print(f"  [{i}/{len(paths)}] {s.task_id} score={s.task_score} hard={s.hard_pass}")
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futs = {ex.submit(run_task, p, opts): p for p in paths}
            done = 0
            for fut in as_completed(futs):
                s = fut.result()
                scores.append(s)
                done += 1
                print(f"  [{done}/{len(paths)}] {s.task_id} score={s.task_score} hard={s.hard_pass}")

    report = aggregate_scores(scores)
    md, js = write_report(report, args.report_dir, label=args.label or ("dry" if args.dry_checks else "live"))
    print(f"\nFCS={report.fcs} hard_pass={report.hard_pass_rate}%")
    print(f"Report: {md}")
    print(f"JSON:   {js}")

    # Persist a machine-readable gate summary next to the report
    gate = {
        "task_count": len(scores),
        "fcs": report.fcs,
        "hard_pass_rate": report.hard_pass_rate,
        "min_hard_pass": args.min_hard_pass,
    }
    gate_path = Path(js).with_name(Path(js).stem + ".gate.json")
    gate_path.write_text(json.dumps(gate, indent=2), encoding="utf-8")

    if args.min_hard_pass is not None and report.hard_pass_rate < args.min_hard_pass:
        print(
            f"[fcs] GATE FAIL: hard_pass_rate {report.hard_pass_rate}% "
            f"< min_hard_pass {args.min_hard_pass}%"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
