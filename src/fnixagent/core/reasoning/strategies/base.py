"""策略基类(P2-6)。

定义所有推理策略的统一接口:
  - name:           策略名(如 "fast" / "cheap" / "precise" / "compliance")
  - think_mode:     是否启用思考模式(GLM-4.5 / DeepSeek-R1,对接 P2-8)
  - execute:        执行推理,返回 ExecutionTrace(委托给具体 ReasoningEngine)
  - estimate_cost:  预估成本(token / 时间 / 钱),供调度器比较策略
  - is_applicable:  策略自评是否适用当前任务(如 Compliance 仅对敏感任务)

StrategyContext 是 ReasoningContext 的"调度视图":
  - 携带 goal / llm / tool_registry / tool_executor
  - 携带 user_id / session_id / project_id / trace_id(供审计)
  - 携带 max_iterations / sensitivity(敏感度,影响 Compliance 判定)

并发安全(BUG 修复):
  原 FastStrategy/CheapStrategy/PreciseStrategy/ComplianceStrategy 直接修改
  ctx.max_iterations 与 ctx.extra,导致同一 StrategyContext 被多次 execute 时
  状态污染(如 max_iterations 被反复 min/max 截断)。
  现统一在 _build_reasoning_context 中以 ctx 副本构造 ReasoningContext,
  StrategyContext 本身保持不可变(只读)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fnixagent.core.exceptions import ReasoningError
from fnixagent.core.types import ExecutionTrace

# ---------------------------------------------------------------------------
# 策略类型枚举
# ---------------------------------------------------------------------------


class StrategyType(str, Enum):
    """策略类型(用于注册与查找)。"""

    FAST = "fast"  # 快速(单步 ReAct,非思考)
    CHEAP = "cheap"  # 低成本(便宜模型,少工具)
    PRECISE = "precise"  # 精确(Plan&Execute + Self-Reflect + 思考)
    COMPLIANCE = "compliance"  # 合规(强审计 + 人工确认)


# ---------------------------------------------------------------------------
# StrategyContext
# ---------------------------------------------------------------------------


@dataclass
class StrategyContext:
    """策略运行时上下文(ReasoningContext 的调度视图)。

    与 ReasoningContext 的区别:
      - StrategyContext 面向"策略选择层",携带调度参数(sensitivity/preference)
      - ReasoningContext 面向"引擎执行层",携带完整执行依赖
      - Strategy.execute(ctx) 内部把 StrategyContext 转换为 ReasoningContext

    不可变性约定:
      - Strategy 不应直接修改 ctx 字段(并发安全)
      - 需要调整 max_iterations / extra 时,通过 _build_reasoning_context
        传 override 参数,在 ReasoningContext 副本上生效
    """

    goal: str = ""
    llm: Any = None  # LLMRouter
    tool_registry: Any = None  # ToolRegistry
    tool_executor: Any = None  # ToolExecutor
    history: list = field(default_factory=list)
    max_iterations: int = 10
    # 用户与租户
    user_id: str = ""
    session_id: str = ""
    project_id: str = ""
    trace_id: str = ""
    tenant_id: str = ""
    # 调度参数
    sensitivity: str = "low"  # low / medium / high(影响 Compliance 判定)
    user_preference: str | None = None  # 用户显式偏好(fast/cheap/precise/compliance)
    available_tools: int = 0  # 可用工具数(影响 is_applicable)
    # 限流与计费(P1-5 集成)
    usage: Any = None  # Usage(累积用量)
    usage_limits: Any = None  # UsageLimits
    # 元数据
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# BaseStrategy
# ---------------------------------------------------------------------------


class BaseStrategy(abc.ABC):
    """策略抽象基类。

    子类需实现:
      - name:           返回策略名(对应 StrategyType)
      - think_mode:     返回是否启用思考模式
      - execute(ctx):   执行推理,返回 ExecutionTrace
      - estimate_cost:  预估成本
      - is_applicable:  是否适用(默认 True)

    execute(ctx) 的典型实现:
      1. 由 ctx 构造 ReasoningContext(通过 _build_reasoning_context,
         传 max_iterations / extra_overrides 而非直接改 ctx)
      2. 选择合适的 ReasoningEngine(ReAct/PlanExecute/SelfReflect)
      3. 调 engine.reason(reasoning_ctx) 得到 ExecutionTrace
      4. 返回 trace
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """策略名(如 "fast" / "precise")。"""
        ...

    @property
    @abc.abstractmethod
    def think_mode(self) -> bool:
        """是否启用思考模式(GLM-4.5 / DeepSeek-R1)。"""
        ...

    @abc.abstractmethod
    def execute(self, ctx: StrategyContext) -> ExecutionTrace:
        """执行推理,返回完整执行轨迹。"""
        ...

    def estimate_cost(self, ctx: StrategyContext) -> dict[str, Any]:
        """预估成本(供调度器比较策略)。

        返回 dict,推荐字段:
          - input_tokens:  预估输入 token
          - output_tokens: 预估输出 token
          - duration_s:    预估耗时(秒)
          - cost_usd:      预估美元成本
          - tool_calls:    预估工具调用次数
        默认实现:粗略估计,子类可重写。
        """
        return {
            "input_tokens": 500,
            "output_tokens": 200,
            "duration_s": 2.0,
            "cost_usd": 0.001,
            "tool_calls": 1,
        }

    def is_applicable(self, ctx: StrategyContext) -> bool:
        """策略是否适用当前任务(默认 True)。

        子类可重写,如 ComplianceStrategy 仅对 sensitivity=high 返回 True。
        """
        return True

    # ------------------------------------------------------------------
    # 内部工具(子类共用)
    # ------------------------------------------------------------------

    def _build_reasoning_context(
        self,
        ctx: StrategyContext,
        mode: Any,
        *,
        max_iterations_override: int | None = None,
        extra_overrides: dict[str, Any] | None = None,
    ) -> Any:
        """把 StrategyContext 转换为 ReasoningContext(子类共用)。

        并发安全(BUG 修复):
          不再修改原 ctx,而是用 override 参数生成 ReasoningContext 副本。
          ctx.max_iterations 与 ctx.extra 保持不变,允许多次 execute 共用同一 ctx。

        Args:
            ctx: StrategyContext
            mode: ReasoningMode(react/plan_execute/self_reflect)
            max_iterations_override: 覆盖 max_iterations(不传则用 ctx.max_iterations)
            extra_overrides: 额外的 extra 字段(与 ctx.extra 合并,不覆盖原值)

        Returns:
            ReasoningContext 实例
        """
        from fnixagent.core.reasoning.base import ReasoningContext

        max_iter = (
            max_iterations_override if max_iterations_override is not None else ctx.max_iterations
        )
        # 合并 extra:原 ctx.extra 保留,额外字段叠加(不修改原 dict)
        merged_extra: dict[str, Any] = dict(ctx.extra)
        if extra_overrides:
            merged_extra.update(extra_overrides)

        # ReasoningContext 没有 extra 字段,merged_extra 仅在需要时通过
        # trace.metadata 或 LLMRequest.extra 透传;此处保留以便未来扩展。
        # 当前 ReasoningContext 字段集为已知集合,直接构造。
        _ = merged_extra  # 保留计算结果供未来扩展使用

        return ReasoningContext(
            goal=ctx.goal,
            llm=ctx.llm,
            tool_registry=ctx.tool_registry,
            tool_executor=ctx.tool_executor,
            history=list(ctx.history),
            max_iterations=max_iter,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            trace_id=ctx.trace_id,
            usage=ctx.usage,
            usage_limits=ctx.usage_limits,
        )

    def _select_engine(self, mode: Any) -> Any:
        """根据 ReasoningMode 返回对应的 ReasoningEngine 实例。

        异常处理:未知 mode 抛 ReasoningError(原实现 ValueError,改为内核异常
        以便上层统一捕获 fnixagentError)。
        """
        from fnixagent.core.reasoning.planner import PlanExecuteEngine
        from fnixagent.core.reasoning.react import ReActEngine
        from fnixagent.core.reasoning.reflector import SelfReflectEngine

        mode_value = getattr(mode, "value", None)
        if mode_value == "react":
            return ReActEngine()
        if mode_value == "plan_execute":
            return PlanExecuteEngine()
        if mode_value == "self_reflect":
            return SelfReflectEngine()
        raise ReasoningError(f"未知的推理模式: {mode}")
