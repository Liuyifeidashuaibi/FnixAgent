"""L3 任务引擎层。

fnixagent 任务引擎:从自然语言任务描述到执行结果的全链路调度。

模块:
  Phase 5.2 任务 DSL 与路由:
    - dsl.TaskType / Intent:        任务类型与用户意图枚举
    - dsl.TaskRequest / TaskResult: 任务请求与结果
    - dsl.TaskStep:                 任务步骤(带依赖关系)
    - router.TaskRouter:            任务路由器(classify + route + 高风险判定)

  Phase 5.4 批量处理管道:
    - pipeline.Pipeline:            多文件批量处理管道

  Phase 5.5 答案/内容恢复:
    - resolver.GarbageDetector:     乱码检测器
    - resolver.AnswerResolver:      答案恢复器(题库+LLM+人工兜底)

  Phase 6.1 自我验证:
    - validator.TaskValidator:      任务结果验证模块

  Phase 6.2 人工确认:
    - confirmer.HumanConfirmer:     高风险操作人工确认节点
    - confirmer.RiskLevel:          风险等级枚举

  Phase 6.3 待确认清单:
    - pending_export.PendingExporter: 待确认清单导出(xlsx/csv)

  Phase 7.1 场景:
    - scenarios.question_bank.QuestionBankScenario: 题库处理场景

  Phase 8.1 MCP:
    - mcp_server.OfficeMCPServer: MCP 协议暴露文档操作
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.tasks.confirmer import (
    ConfirmationRequest,
    HumanConfirmer,
    RiskLevel,
)
from fnixagent.tasks.dsl import (
    Intent,
    TaskRequest,
    TaskResult,
    TaskStep,
    TaskType,
)
from fnixagent.tasks.editability import EditabilityGuard, EditabilityReport
from fnixagent.tasks.pending_export import (
    PendingExporter,
    PendingItem,
)
from fnixagent.tasks.resolver import (
    AnswerResolver,
    GarbageDetector,
    GarbageReport,
    ResolveResult,
)
from fnixagent.tasks.router import TaskRouter
from fnixagent.tasks.scenarios import (
    ProcessOptions,
    QuestionBankScenario,
    QuestionInfo,
)
from fnixagent.tasks.validator import (
    CheckItem,
    TaskValidator,
    ValidationReport,
)

__all__ = [
    # Phase 5.2 任务 DSL 与路由
    "TaskType",
    "Intent",
    "TaskRequest",
    "TaskResult",
    "TaskStep",
    "TaskRouter",
    # Phase 5.5 答案恢复
    "GarbageDetector",
    "GarbageReport",
    "AnswerResolver",
    "ResolveResult",
    # Phase 6.1 验证
    "TaskValidator",
    "CheckItem",
    "ValidationReport",
    # Phase 6.2 人工确认
    "HumanConfirmer",
    "RiskLevel",
    "ConfirmationRequest",
    # Phase 6.3 待确认清单
    "PendingExporter",
    "PendingItem",
    # Phase 7.1 场景
    "QuestionBankScenario",
    "QuestionInfo",
    "ProcessOptions",
    # Phase 6.5 可编辑性
    "EditabilityGuard",
    "EditabilityReport",
]
