"""Markdown/JSON report for benchmark runs."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fnixagent.core.code.benchmark.scorer import BenchmarkReport


def write_report(report: BenchmarkReport, out_dir: Path, label: str = "") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    json_path = out_dir / f"fcs-{stamp}{suffix}.json"
    md_path = out_dir / f"fcs-{stamp}{suffix}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# Fnix Code Score Report",
        "",
        f"- **FCS**: {report.fcs}",
        f"- **Hard pass rate**: {report.hard_pass_rate}%",
        f"- **Tasks**: {report.task_count}",
        "",
        "## By capability",
        "",
    ]
    for cap, score in sorted(report.by_capability.items()):
        lines.append(f"- `{cap}`: {score}")
    lines.extend(["", "## By difficulty", ""])
    for diff, score in sorted(report.by_difficulty.items()):
        lines.append(f"- L{diff}: {score}")
    lines.extend(["", "## Failed / low score tasks", ""])
    for t in sorted(report.tasks, key=lambda x: x.task_score):
        if not t.hard_pass or t.task_score < 70:
            lines.append(f"- `{t.task_id}` score={t.task_score} hard={t.hard_pass}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path
