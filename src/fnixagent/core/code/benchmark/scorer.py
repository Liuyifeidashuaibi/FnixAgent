"""Aggregate task scores into Fnix Code Score (FCS)."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.code.benchmark.checks import CheckResult
from fnixagent.core.code.benchmark.schema import DIFFICULTY_WEIGHT, TaskSpec


@dataclass
class TaskRunMeta:
    elapsed_s: float = 0.0
    steps: int = 0
    heal_rounds: int = 0
    tool_calls: int = 0
    agent_error: str = ""


@dataclass
class TaskScore:
    task_id: str
    capability: list[str]
    difficulty: int
    hard_pass: bool
    task_score: float
    correctness: float
    completeness: float
    process: float
    safety: float
    speed: float
    check_results: list[CheckResult] = field(default_factory=list)
    meta: TaskRunMeta = field(default_factory=TaskRunMeta)


def _rate_weighted(results: list[CheckResult]) -> float:
    if not results:
        return 100.0
    total_w = sum(r.weight for r in results)
    if total_w <= 0:
        return 0.0
    got = sum(r.weight for r in results if r.ok)
    return 100.0 * got / total_w


def score_task(
    task: TaskSpec,
    check_results: list[CheckResult],
    meta: TaskRunMeta,
) -> TaskScore:
    required = [r for r in check_results if r.required]
    optional = [r for r in check_results if not r.required]

    correctness = 100.0 if all(r.ok for r in required) else 0.0
    completeness = (
        _rate_weighted(optional) if optional else (100.0 if correctness == 100.0 else 0.0)
    )

    # Process: budget steps + heal
    step_budget = 8 + task.difficulty * 4
    step_penalty = max(0, meta.steps - step_budget) * 3
    heal_penalty = max(0, meta.heal_rounds - 2) * 5
    process = max(0.0, 100.0 - step_penalty - heal_penalty)

    safety_checks = [
        r for r in check_results if r.function in ("no_stub_content", "file_not_contains")
    ]
    safety = _rate_weighted(safety_checks) if safety_checks else 100.0

    if meta.elapsed_s <= task.timeout_s:
        speed = 100.0
    else:
        over = meta.elapsed_s - task.timeout_s
        speed = max(0.0, 100.0 - over * 2)

    task_score = (
        0.50 * correctness + 0.20 * completeness + 0.15 * process + 0.10 * safety + 0.05 * speed
    )

    hard_pass = correctness >= 100.0 and safety >= 80.0 and not meta.agent_error

    return TaskScore(
        task_id=task.id,
        capability=task.capability,
        difficulty=task.difficulty,
        hard_pass=hard_pass,
        task_score=round(task_score, 2),
        correctness=round(correctness, 2),
        completeness=round(completeness, 2),
        process=round(process, 2),
        safety=round(safety, 2),
        speed=round(speed, 2),
        check_results=check_results,
        meta=meta,
    )


@dataclass
class BenchmarkReport:
    fcs: float
    hard_pass_rate: float
    task_count: int
    by_capability: dict[str, float]
    by_difficulty: dict[int, float]
    tasks: list[TaskScore]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fcs": self.fcs,
            "hard_pass_rate": self.hard_pass_rate,
            "task_count": self.task_count,
            "by_capability": self.by_capability,
            "by_difficulty": {str(k): v for k, v in self.by_difficulty.items()},
            "tasks": [
                {
                    "task_id": t.task_id,
                    "hard_pass": t.hard_pass,
                    "task_score": t.task_score,
                    "capability": t.capability,
                    "difficulty": t.difficulty,
                    "subscores": {
                        "correctness": t.correctness,
                        "completeness": t.completeness,
                        "process": t.process,
                        "safety": t.safety,
                        "speed": t.speed,
                    },
                }
                for t in self.tasks
            ],
        }


def aggregate_scores(scores: list[TaskScore]) -> BenchmarkReport:
    if not scores:
        return BenchmarkReport(0.0, 0.0, 0, {}, {}, [])

    total_w = 0.0
    weighted = 0.0
    cap_sum: dict[str, float] = {}
    cap_w: dict[str, float] = {}
    diff_sum: dict[int, float] = {}
    diff_w: dict[int, float] = {}

    for s in scores:
        w = DIFFICULTY_WEIGHT.get(s.difficulty, 1.0)
        total_w += w
        weighted += s.task_score * w

        diff_sum[s.difficulty] = diff_sum.get(s.difficulty, 0.0) + s.task_score * w
        diff_w[s.difficulty] = diff_w.get(s.difficulty, 0.0) + w

        for cap in s.capability:
            cap_sum[cap] = cap_sum.get(cap, 0.0) + s.task_score * w
            cap_w[cap] = cap_w.get(cap, 0.0) + w

    hard = sum(1 for s in scores if s.hard_pass) / len(scores)

    return BenchmarkReport(
        fcs=round(weighted / total_w, 2) if total_w else 0.0,
        hard_pass_rate=round(100.0 * hard, 2),
        task_count=len(scores),
        by_capability={k: round(cap_sum[k] / cap_w[k], 2) for k in cap_sum},
        by_difficulty={k: round(diff_sum[k] / diff_w[k], 2) for k in diff_sum},
        tasks=scores,
    )
