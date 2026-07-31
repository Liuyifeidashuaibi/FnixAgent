"""Fnix Code Benchmark package."""

from fnixagent.core.code.benchmark.checks import CheckResult, run_check
from fnixagent.core.code.benchmark.generator import generate_tasks, write_generated
from fnixagent.core.code.benchmark.report import write_report
from fnixagent.core.code.benchmark.runner import RunOptions, load_manifest, run_task
from fnixagent.core.code.benchmark.schema import TaskSpec, load_task
from fnixagent.core.code.benchmark.scorer import (
    BenchmarkReport,
    TaskScore,
    aggregate_scores,
    score_task,
)

__all__ = [
    "BenchmarkReport",
    "CheckResult",
    "RunOptions",
    "TaskScore",
    "TaskSpec",
    "aggregate_scores",
    "generate_tasks",
    "load_manifest",
    "load_task",
    "run_check",
    "run_task",
    "score_task",
    "write_generated",
    "write_report",
]
