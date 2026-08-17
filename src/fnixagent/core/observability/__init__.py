"""fnixagent 可观测性模块 — Phase 2.10。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.observability.metrics import (
    is_enabled,
    record_audit_log,
    record_chat_message,
    record_document_operation,
    record_flywheel_trigger,
    record_injection_blocked,
    record_langgraph_node,
    record_llm_call,
    record_llm_error,
    record_llm_tokens,
    record_login,
    record_mfa_challenge,
    record_permission_denied,
    record_rate_limit_triggered,
    record_sensitive_hit,
    record_task_created,
    record_tool_error,
    record_tool_execution,
    record_user_active,
    record_user_registration,
    setup_metrics,
    update_topology_stats,
)
from fnixagent.core.observability.stats import (
    StatsAggregator,
    StatsProvider,
    get_stats_aggregator,
    register_default_providers,
    reset_stats_aggregator,
)

__all__ = [
    "setup_metrics",
    "is_enabled",
    "record_login",
    "record_user_active",
    "record_user_registration",
    "record_chat_message",
    "record_document_operation",
    "record_task_created",
    "record_langgraph_node",
    "record_flywheel_trigger",
    "update_topology_stats",
    "record_tool_execution",
    "record_tool_error",
    "record_permission_denied",
    "record_rate_limit_triggered",
    "record_injection_blocked",
    "record_sensitive_hit",
    "record_mfa_challenge",
    "record_audit_log",
    "record_llm_call",
    "record_llm_tokens",
    "record_llm_error",
    # P2-02: 统一指标聚合
    "StatsAggregator",
    "StatsProvider",
    "get_stats_aggregator",
    "register_default_providers",
    "reset_stats_aggregator",
]
