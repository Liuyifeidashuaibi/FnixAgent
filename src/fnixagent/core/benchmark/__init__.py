"""Fnix full-chain system benchmark."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.benchmark.optimizer import build_recommendations
from fnixagent.core.benchmark.system_runner import (
    StageResult,
    SystemBenchmarkReport,
    run_full_chain,
)

__all__ = [
    "StageResult",
    "SystemBenchmarkReport",
    "build_recommendations",
    "run_full_chain",
]
