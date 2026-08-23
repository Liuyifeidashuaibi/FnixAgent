"""FnixForge — 测评任务 schema。

任务以 JSON 存储于 benchmarks/forge/suites/<suite>/ 下，每个文件一道题。
任务驱动 *被测 Agent*（SUT）在独立沙箱中完成一件事，再由确定性 checks 判定。
"""

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

# 能力维度（每题可归入 1 个主能力；用于能力矩阵报告）
CAPABILITIES = frozenset(
    {
        "instruction_following",  # 精确指令遵循
        "file_edit",              # 精确文件编辑（最小改动）
        "code_gen",               # 代码生成与缺陷修复
        "tool_use",               # 工具/命令使用
        "multi_step",             # 多步规划与跨文件协作
        "context_retrieval",      # 上下文读取与引用
        "output_contract",        # 输出契约（JSON schema / stdout 格式）
        "error_recovery",         # 失败后自我纠错
        "safety",                 # 作用域安全（不越界改动、不碰敏感文件）
        "language",               # 多语言（中文语义精确性）
    }
)

DIFFICULTY_WEIGHT = {1: 1.0, 2: 1.25, 3: 1.5, 4: 2.0, 5: 2.5}


@dataclass
class ForgeCheck:
    function: str
    args: dict[str, Any] = field(default_factory=dict)
    required: bool = True
    weight: float = 1.0
    desc: str = ""


@dataclass
class ForgeTask:
    id: str
    prompt: str
    capability: str
    difficulty: int
    checks: list[ForgeCheck]
    title: str = ""
    tags: list[str] = field(default_factory=list)
    timeout_s: int = 240
    setup: dict[str, Any] = field(default_factory=dict)   # {"files": {rel: content}}
    # scope 声明本任务允许目标 Agent 在工作区中改动的 glob（用于 safety 判定）；空 = 不限
    allowed_scope: list[str] = field(default_factory=list)
    protected: list[str] = field(default_factory=list)    # 禁止改动的相对路径（glob）

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ForgeTask":
        checks = [
            ForgeCheck(
                function=c["function"],
                args=c.get("args") or {},
                required=c.get("required", True),
                weight=float(c.get("weight", 1.0)),
                desc=c.get("desc", ""),
            )
            for c in data.get("checks") or []
        ]
        return cls(
            id=data["id"],
            title=data.get("title") or data["id"],
            prompt=data["prompt"],
            capability=data["capability"],
            difficulty=int(data.get("difficulty", 2)),
            tags=list(data.get("tags") or []),
            timeout_s=int(data.get("timeout_s", 240)),
            setup=dict(data.get("setup") or {}),
            allowed_scope=list(data.get("allowed_scope") or []),
            protected=list(data.get("protected") or []),
            checks=checks,
        )


def load_task(path: Path) -> ForgeTask:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ForgeTask.from_dict(data)


def validate_task(task: ForgeTask) -> list[str]:
    errors: list[str] = []
    if not task.id:
        errors.append("missing id")
    if not task.prompt.strip():
        errors.append(f"{task.id}: empty prompt")
    if task.capability not in CAPABILITIES:
        errors.append(f"{task.id}: unknown capability {task.capability!r}")
    if task.difficulty not in DIFFICULTY_WEIGHT:
        errors.append(f"{task.id}: difficulty must be 1-5, got {task.difficulty}")
    if not task.checks:
        errors.append(f"{task.id}: no checks")
    for c in task.checks:
        if c.weight <= 0:
            errors.append(f"{task.id}: check {c.function} weight must be > 0")
    return errors


def load_suite(suite_dir: Path) -> list[ForgeTask]:
    tasks: list[ForgeTask] = []
    for p in sorted(Path(suite_dir).glob("*.json")):
        if p.name.startswith("_") or p.name == "manifest.json":
            continue
        tasks.append(load_task(p))
    return tasks


def load_manifest(root: Path) -> dict[str, Any]:
    p = Path(root) / "manifest.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
