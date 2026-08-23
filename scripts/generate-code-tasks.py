#!/usr/bin/env python3
"""Generate Fnix Code Benchmark manifest and generated tasks."""

from __future__ import annotations
# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.code.benchmark.generator import generate_tasks, write_generated


def seed_ids(seed_dir: Path) -> list[str]:
    return sorted(p.stem for p in seed_dir.glob("*.json"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate code benchmark tasks")
    ap.add_argument("--count", type=int, default=1000, help="Total tasks in manifest")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for generated tasks")
    ap.add_argument(
        "--benchmark-root",
        type=Path,
        default=ROOT / "benchmarks" / "code",
    )
    args = ap.parse_args()

    root = args.benchmark_root
    seed_dir = root / "seed"
    gen_dir = root / "generated"
    seed_dir.mkdir(parents=True, exist_ok=True)

    seeds = seed_ids(seed_dir)
    gen_count = max(0, args.count - len(seeds))
    generated = generate_tasks(gen_count, seed=args.seed)
    gen_ids = write_generated(generated, gen_dir)

    all_ids = seeds + gen_ids
    manifest = {
        "version": 1,
        "total": len(all_ids),
        "seed_count": len(seeds),
        "generated_count": len(gen_ids),
        "tasks": all_ids,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {manifest_path}")
    print(f"  seed: {len(seeds)}")
    print(f"  generated: {len(gen_ids)}")
    print(f"  total: {len(all_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
