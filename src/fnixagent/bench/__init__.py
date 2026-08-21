"""BenchForge — FnixAgent 全量基准评测与自动修复子系统。

子命令:
    fnixagent bench fetch [--dataset ...] [--refresh]
    fnixagent bench run [--dataset ...] [--limit N] [--concurrency N]
    fnixagent bench report [--run DIR]
    fnixagent bench fix  [--run DIR] [--apply]

红线: 基准数据只用于优化 Agent 控制层（Runtime / MCP / 记忆 / Workflow），
绝不用于对基座大模型做 SFT 微调。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.bench.datasets import DatasetManager
from fnixagent.bench.fixloop import (
    analyze_with_llm,
    build_regression_set,
    cluster_failures,
    write_diagnosis,
)
from fnixagent.bench.judge import Judge
from fnixagent.bench.report import write_html, write_markdown
from fnixagent.bench.runner import BenchRunner
from fnixagent.bench.schema import BenchTask, FailureType, RunSummary, TaskRun, TaskStatus

__all__ = [
    "BenchRunner", "BenchTask", "DatasetManager", "FailureType", "Judge",
    "RunSummary", "TaskRun", "TaskStatus", "analyze_with_llm",
    "build_regression_set", "cluster_failures", "write_diagnosis",
    "write_html", "write_markdown",
]
