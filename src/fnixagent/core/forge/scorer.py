"""FnixForge — 评分与能力矩阵聚合。

- 任务级得分: required checks 全过 = 满分；部分过时按 weight 的比例给分（required 失败则封顶 40%）。
- 套件级: 按 capability 维度聚合，难度加权，输出能力矩阵（每个维度的加权通过率与样本数）。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.forge.checks import CheckResult
from fnixagent.core.forge.spec import DIFFICULTY_WEIGHT, ForgeTask

@dataclass
class TaskScore:
    task_id: str
    capability: str
    difficulty: int
    score: float                 # 0-100
    passed: bool                 # required 全过
    checks: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "capability": self.capability,
            "difficulty": self.difficulty,
            "score": round(self.score, 2),
            "passed": self.passed,
            "elapsed_s": round(self.elapsed_s, 2),
            "error": self.error,
            "checks": self.checks,
        }

def score_task(task: ForgeTask, check_results: list[CheckResult], elapsed_s: float,
               error: str = "") -> TaskScore:
    total_w = sum(c.weight for c in task.checks) or 1.0
    gained = 0.0
    required_failed = False
    for spec, res in zip(task.checks, check_results):
        if res.ok:
            gained += spec.weight
        elif spec.required:
            required_failed = True
    raw = 100.0 * gained / total_w
    if required_failed:
        # required 未过不能拿高分：封顶 40%，保证"部分分"不会误判为接近合格
        score = min(raw, 40.0)
    else:
        score = raw
    passed = all(r.ok for r in check_results if r.required) and not error
    return TaskScore(
        task_id=task.id,
        capability=task.capability,
        difficulty=task.difficulty,
        score=score,
        passed=passed,
        elapsed_s=elapsed_s,
        error=error,
        checks=[
            {
                "function": r.function, "ok": r.ok, "message": r.message,
                "required": r.required, "weight": r.weight,
            }
            for r in check_results
        ],
    )

def aggregate(scores: list[TaskScore]) -> dict[str, Any]:
    """聚合为能力矩阵: 难度加权通过率（required 全过才算通过）。"""
    by_cap: dict[str, list[TaskScore]] = {}
    for s in scores:
        by_cap.setdefault(s.capability, []).append(s)

    matrix: dict[str, Any] = {}
    total_weight = 0.0
    total_earned = 0.0
    for cap, items in sorted(by_cap.items()):
        w_sum = sum(DIFFICULTY_WEIGHT.get(s.difficulty, 1.0) for s in items) or 1.0
        earned = sum(
            DIFFICULTY_WEIGHT.get(s.difficulty, 1.0) * (1.0 if s.passed else s.score / 100.0)
            for s in items
        )
        matrix[cap] = {
            "tasks": len(items),
            "passed": sum(1 for s in items if s.passed),
            "weighted_pass_rate": round(100.0 * earned / w_sum, 2),
            "mean_score": round(sum(s.score for s in items) / len(items), 2),
        }
        total_weight += w_sum
        total_earned += earned

    overall = round(100.0 * total_earned / total_weight, 2) if total_weight else 0.0
    return {
        "overall_score": overall,
        "tasks": len(scores),
        "passed": sum(1 for s in scores if s.passed),
        "capabilities": matrix,
    }

def production_readiness(suite_result: dict[str, Any], threshold: float = 90.0) -> dict[str, Any]:
    """生产级判定: 总加权分 ≥ threshold 且全部 required 通过。"""
    caps = suite_result.get("capabilities") or {}
    weak = [c for c, m in caps.items() if m["weighted_pass_rate"] < threshold]
    ready = suite_result.get("overall_score", 0.0) >= threshold and not weak
    return {
        "ready": ready,
        "threshold": threshold,
        "overall_score": suite_result.get("overall_score", 0.0),
        "weak_capabilities": weak,
    }
