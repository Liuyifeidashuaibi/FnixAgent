"""
Agent 调度中枢 (Orchestrator)。

串联全部引擎,实现完整请求生命周期:
  用户输入 → 安全校验 → 记忆加载 → 推理模式选择 → 推理执行
  → 结果校验反思 → 输出审核 → 记忆保存 → 返回回复
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.orchestrator.context import OrchestratorContext
from fnixagent.core.orchestrator.lifecycle import Lifecycle, PipelineResult
from fnixagent.core.orchestrator.scheduler import AgentResponse, AgentScheduler

__all__ = [
    "AgentResponse",
    "AgentScheduler",
    "Lifecycle",
    "OrchestratorContext",
    "PipelineResult",
]
