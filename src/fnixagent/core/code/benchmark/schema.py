"""Fnix Code Benchmark — task schema and validation."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CAPABILITIES = frozenset(
    {
        "write",
        "edit",
        "bugfix",
        "test_gen",
        "refactor",
        "search",
        "multi_file",
        "api",
        "cli",
        "heal",
    }
)

DIFFICULTY_WEIGHT = {1: 1.0, 2: 1.2, 3: 1.5, 4: 2.0, 5: 2.5}


@dataclass
class CheckSpec:
    function: str
    args: dict[str, Any] = field(default_factory=dict)
    required: bool = True
    weight: float = 1.0


@dataclass
class TaskSpec:
    id: str
    prompt: str
    capability: list[str]
    difficulty: int
    language: str
    checks: list[CheckSpec]
    title: str = ""
    tags: list[str] = field(default_factory=list)
    timeout_s: int = 180
    setup: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskSpec:
        checks = [
            CheckSpec(
                function=c["function"],
                args=c.get("args") or {},
                required=c.get("required", True),
                weight=float(c.get("weight", 1.0)),
            )
            for c in data["checks"]
        ]
        return cls(
            id=data["id"],
            title=data.get("title") or data["id"],
            prompt=data["prompt"],
            capability=list(data["capability"]),
            difficulty=int(data["difficulty"]),
            language=data["language"],
            tags=list(data.get("tags") or []),
            timeout_s=int(data.get("timeout_s", 180)),
            setup=dict(data.get("setup") or {}),
            checks=checks,
        )


def load_task(path: Path) -> TaskSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    return TaskSpec.from_dict(data)


def validate_task(task: TaskSpec) -> list[str]:
    errors: list[str] = []
    if not task.id:
        errors.append("missing id")
    if not task.prompt.strip():
        errors.append("empty prompt")
    if not task.checks:
        errors.append("no checks")
    for cap in task.capability:
        if cap not in CAPABILITIES:
            errors.append(f"unknown capability: {cap}")
    if task.difficulty not in DIFFICULTY_WEIGHT:
        errors.append(f"invalid difficulty: {task.difficulty}")
    return errors
