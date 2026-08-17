"""
调度中枢运行时上下文 (Orchestrator Context)。

封装一次请求的全部引擎引用和运行时状态:
  - llm_router:      LLM 基础服务(多模型路由/限流/熔断/计费/缓存)
  - memory_manager:  三层记忆(短期/长期/实体)
  - tool_registry:   工具注册中心
  - tool_executor:   工具执行器(DAG编排/沙箱)
  - security_engine: 安全引擎(敏感词/注入/审核/脱敏)
  - prompt_manager:  Prompt 模板管理
  - reasoning_selector: 推理模式选择器
  - validator:       结果校验器
  - replanner:       重规划器

所有引擎通过此上下文注入,避免全局单例,便于测试和多租户隔离。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.config import CoreConfig
from fnixagent.core.llm.router import LLMRouter
from fnixagent.core.memory.manager import MemoryManager
from fnixagent.core.prompt.manager import PromptManager
from fnixagent.core.reasoning.selector import ReasoningSelector
from fnixagent.core.reflection.replanner import Replanner
from fnixagent.core.reflection.validator import ResultValidator
from fnixagent.core.security.engine import SecurityEngine
from fnixagent.core.tools.executor import ToolExecutor
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.types import Message


@dataclass
class OrchestratorContext:
    """
    调度中枢运行时上下文。

    一次请求的完整上下文,贯穿 7 步流水线。
    """

    # -- 引擎引用 ----------------------------------------------------------
    llm_router: LLMRouter
    memory_manager: MemoryManager
    tool_registry: ToolRegistry
    tool_executor: ToolExecutor
    security_engine: SecurityEngine
    prompt_manager: PromptManager
    reasoning_selector: ReasoningSelector
    validator: ResultValidator
    replanner: Replanner
    config: CoreConfig

    # -- 请求信息 ----------------------------------------------------------
    user_id: str = ""
    session_id: str = ""
    tenant_id: str = "default"
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])

    # -- 运行时状态 --------------------------------------------------------
    current_goal: str = ""
    messages: list[Message] = field(default_factory=list)
    reasoning_mode: Any = None  # 选定的推理模式
    execution_trace: Any = None  # 执行轨迹
    final_response: str = ""  # 最终回复
    blocked: bool = False  # 是否被安全拦截
    blocked_reason: str = ""

    # -- 记忆上下文 --------------------------------------------------------
    short_term_history: list[Message] = field(default_factory=list)
    long_term_memories: list[Any] = field(default_factory=list)
    user_profile: Any | None = None

    @property
    def has_security_engine(self) -> bool:
        """是否注入了安全引擎。"""
        return self.security_engine is not None

    def to_dict(self) -> dict:
        """转为字典(用于日志/调试)。

        Returns:
            含请求标识 / 目标 / 推理模式 / 拦截状态 / 工具数 / 记忆数等摘要字段的字典
        """
        # tool_registry.count 用 getattr 兜底,防止注入了非标准 registry 时 AttributeError
        tool_count = getattr(self.tool_registry, "count", 0) if self.tool_registry else 0
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "goal": self.current_goal[:100],
            "reasoning_mode": (self.reasoning_mode.value if self.reasoning_mode else None),
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "tool_count": tool_count,
            "short_term_messages": len(self.short_term_history),
            "long_term_memories": len(self.long_term_memories),
        }
