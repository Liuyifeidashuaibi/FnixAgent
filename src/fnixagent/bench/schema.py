"""BenchForge — 全量基准评测核心数据结构。

统一抽象六大基准数据集（Web-Bench / WorkBuddy-Bench / Vibe-Code-Bench /
PrototypeBench / GAIA / SWE-bench Lite）的任务、运行结果、判定结论与统计汇总。

硬性约束（见任务规格书）:
  1. 不抽样、不筛选、不跳过任何任务
  2. 原始 prompt 原样传入，不修改、不改写
  3. 所有轨迹 / 回归集 / 报告写入本地文件
  4. 单任务异常不中断整体评测
  5. 数据仅用于优化 Agent 控制层 (Runtime / MCP / 记忆 / Workflow)，禁止 SFT
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# 数据集目录
# ---------------------------------------------------------------------------

DATASET_TOTALS: dict[str, int] = {
    "web-bench": 1000,          # 50 项目 × 20 子任务
    "workbuddy-bench": 260,     # Web70 / Code80 / Office50 / Security60
    "vibe-code-bench": 100,     # 验证集50 + 测试集50
    "prototypebench": 123,      # 前端52 + 后端71
    "gaia": 166,                # 公开验证集
    "swe-bench-lite": 300,      # Lite 版本
}

DATASET_SOURCES: dict[str, dict[str, str]] = {
    "web-bench": {
        "repo": "https://github.com/bytedance/web-bench",
        "prompt_field": "description",
        "rule": "所有任务独立运行，不继承上一个任务的输出上下文",
    },
    "workbuddy-bench": {
        "repo": "https://github.com/Tencent/workbuddy-bench",
        "hf": "tencent/workbuddy-bench",
        "prompt_field": "description",
    },
    "vibe-code-bench": {
        "repo": "https://github.com/ArjunDivecha/vibe-code-bench",
        "prompt_field": "prompt",
    },
    "prototypebench": {
        "repo": "https://github.com/prototypebench/prototypebench",
        "hf": "banyaaiofficial/prototypebench-v1",
        "prompt_field": "description",
    },
    "gaia": {
        "hf": "gaia-benchmark/GAIA",
        "prompt_field": "Question",
    },
    "swe-bench-lite": {
        "repo": "https://github.com/SWE-bench/SWE-bench",
        "hf": "princeton-nlp/SWE-bench_Lite",
        "prompt_field": "problem_statement",
    },
}

# ---------------------------------------------------------------------------
# 失败类型（六类，与任务规格书一致）
# ---------------------------------------------------------------------------

class FailureType(str, Enum):
    """失败分类 — 评测报告按此六类统计。"""

    PLANNING_ERROR = "planning_error"              # 规划拆解错误
    MCP_CALL_ERROR = "mcp_call_error"              # MCP/工具调用异常
    PATH_ERROR = "path_error"                      # 多文件路径错误
    CONTEXT_LOSS = "context_loss"                  # 上下文记忆丢失
    REQUIREMENT_MISUNDERSTANDING = "requirement_misunderstanding"  # 需求理解偏差
    CRASH = "crash"                                # 运行崩溃（异常/超时/中断）
    INCOMPLETE_OUTPUT = "incomplete_output"        # 输出残缺
    OTHER = "other"                                # 其他错误


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    FETCH_ERROR = "fetch_error"    # 数据集下载/解析异常
    SKIPPED = "skipped"            # 仅 checkpoint 恢复时标记；正常流程禁止跳过
    INFRA_SKIP = "infra_skip"      # 基础设施错误（模型配额耗尽/鉴权失败）——
                                   # 不是 Agent 能力失败，断点续跑时必须重试


# ---------------------------------------------------------------------------
# 任务定义
# ---------------------------------------------------------------------------

@dataclass
class BenchTask:
    """一条基准任务（标准化后的最小单元）。"""

    dataset: str          # 数据集名（web-bench / gaia / ...）
    task_id: str          # 数据集内唯一 ID
    prompt: str           # 原始 prompt —— 严禁改写，原样传给 Agent
    subset: str = ""      # 子集（workbuddy 的 web/code/office/security 等）
    expected: Any = None  # 参考答案（GAIA 的 final answer / SWE 的 patch 等）
    meta: dict[str, Any] = field(default_factory=dict)  # 原始记录全量字段

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "subset": self.subset,
            "expected": self.expected,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BenchTask:
        return cls(
            dataset=d["dataset"], task_id=d["task_id"], prompt=d["prompt"],
            subset=d.get("subset", ""), expected=d.get("expected"),
            meta=d.get("meta", {}),
        )


# ---------------------------------------------------------------------------
# 运行轨迹与判定
# ---------------------------------------------------------------------------

@dataclass
class TaskRun:
    """一条任务的完整运行记录（轨迹 + 判定）。"""

    dataset: str
    task_id: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    failure_type: str = ""           # FailureType.value，成功时为空
    failure_evidence: str = ""       # 判定证据摘要
    final_response: str = ""         # Agent 最终输出
    steps: list[dict[str, Any]] = field(default_factory=list)  # 每步轨迹
    tool_calls: list[dict[str, Any]] = field(default_factory=list)  # 工具调用日志
    files_written: list[str] = field(default_factory=list)
    total_tokens: int = 0
    duration_ms: float = 0.0
    error: str = ""                  # 运行时异常原文
    judge_method: str = "heuristic"  # heuristic / llm / golden-match
    started_at: float = field(default_factory=time.time)
    workspace: str = ""              # 本任务的隔离工作区路径

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "status": self.status.value,
            "failure_type": self.failure_type,
            "failure_evidence": self.failure_evidence,
            "final_response": self.final_response,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "files_written": self.files_written,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "judge_method": self.judge_method,
            "started_at": self.started_at,
            "workspace": self.workspace,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskRun:
        r = cls(dataset=d["dataset"], task_id=d["task_id"], prompt=d["prompt"])
        r.status = TaskStatus(d.get("status", "pending"))
        r.failure_type = d.get("failure_type", "")
        r.failure_evidence = d.get("failure_evidence", "")
        r.final_response = d.get("final_response", "")
        r.steps = d.get("steps", [])
        r.tool_calls = d.get("tool_calls", [])
        r.files_written = d.get("files_written", [])
        r.total_tokens = d.get("total_tokens", 0)
        r.duration_ms = d.get("duration_ms", 0.0)
        r.error = d.get("error", "")
        r.judge_method = d.get("judge_method", "heuristic")
        r.started_at = d.get("started_at", 0.0)
        r.workspace = d.get("workspace", "")
        return r


# ---------------------------------------------------------------------------
# 统计汇总
# ---------------------------------------------------------------------------

@dataclass
class DatasetStats:
    dataset: str
    total: int = 0
    success: int = 0
    failure: int = 0
    fetch_error: int = 0
    infra_skip: int = 0            # 配额/鉴权等基础设施错误（不计能力失败，可重跑）
    failure_type_counts: dict[str, int] = field(default_factory=dict)

    @property
    def judged(self) -> int:
        """有效判定样本数（剔除基础设施挂起），成功率以此作分母。"""
        return self.success + self.failure

    @property
    def success_rate(self) -> float:
        return self.success / self.judged if self.judged else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "total": self.total,
            "success": self.success,
            "failure": self.failure,
            "fetch_error": self.fetch_error,
            "infra_skip": self.infra_skip,
            "success_rate": round(self.success_rate, 4),
            "failure_type_counts": self.failure_type_counts,
        }


@dataclass
class RunSummary:
    """一次评测运行的整体汇总。"""

    run_id: str
    model: str
    started_at: float
    finished_at: float = 0.0
    datasets: dict[str, DatasetStats] = field(default_factory=dict)
    total_tokens: int = 0
    note: str = ""

    def add_run(self, run: TaskRun) -> None:
        ds = self.datasets.setdefault(run.dataset, DatasetStats(dataset=run.dataset))
        ds.total += 1
        if run.status == TaskStatus.SUCCESS:
            ds.success += 1
        elif run.status == TaskStatus.FETCH_ERROR:
            ds.fetch_error += 1
        elif run.status == TaskStatus.INFRA_SKIP:
            # 基础设施错误（配额/鉴权）：不计能力失败，可断点重跑
            ds.infra_skip += 1
        else:
            ds.failure += 1
            ft = run.failure_type or FailureType.OTHER.value
            ds.failure_type_counts[ft] = ds.failure_type_counts.get(ft, 0) + 1
        self.total_tokens += run.total_tokens

    @property
    def totals(self) -> dict[str, Any]:
        success = sum(d.success for d in self.datasets.values())
        failure = sum(d.failure for d in self.datasets.values())
        fetch_err = sum(d.fetch_error for d in self.datasets.values())
        infra = sum(d.infra_skip for d in self.datasets.values())
        total = sum(d.total for d in self.datasets.values())
        judged = success + failure
        merged: dict[str, int] = {}
        for d in self.datasets.values():
            for k, v in d.failure_type_counts.items():
                merged[k] = merged.get(k, 0) + v
        return {
            "total": total, "success": success, "failure": failure,
            "fetch_error": fetch_err, "infra_skip": infra,
            "success_rate": round(success / judged, 4) if judged else 0.0,
            "failure_type_counts": merged,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "totals": self.totals,
            "total_tokens": self.total_tokens,
            "note": self.note,
            "datasets": {k: v.to_dict() for k, v in self.datasets.items()},
        }
