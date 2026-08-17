"""Precise 策略:精确推理(P2-6)。

特点:
  - 推理模式:Plan&Execute + Self-Reflect(先规划后执行,执行后反思)
  - 思考模式:启用(GLM-4.5 / DeepSeek-R1 思考模式)
  - 工具数:不限(可调度全部工具)
  - max_iterations:大(默认 15 步,允许重试与反思)
  - 适用:复杂任务、关键业务操作、用户要求"准确/校验/正式"

成本预估:最高(token 多 / 耗时长 / 思考模式叠加成本)

BUG 修复:
  - 原 reflect_trace.final_response 直接属性访问,但 ExecutionTrace 无此字段,
    会抛 AttributeError;改用 getattr 安全访问。
  - 原直接修改 ctx.max_iterations / ctx.extra,并发不安全;改用 override 透传。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fnixagent.core.reasoning.strategies.base import BaseStrategy, StrategyContext
from fnixagent.core.types import ExecutionTrace, ReasoningMode


class PreciseStrategy(BaseStrategy):
    """精确策略:Plan&Execute + Self-Reflect + 思考模式。"""

    # Precise 策略强制下限(原 max(ctx.max_iterations, 15))
    MIN_ITERATIONS_FLOOR: int = 15

    @property
    def name(self) -> str:
        """策略名。"""
        return "precise"

    @property
    def think_mode(self) -> bool:
        """启用思考模式(Precise 主打深度推理)。"""
        return True

    def execute(self, ctx: StrategyContext) -> ExecutionTrace:
        """执行 Precise 策略:Plan&Execute + Self-Reflect + 思考模式。

        两阶段:
          1. Plan&Execute 生成计划并执行
          2. Self-Reflect 对执行结果做反思校验,合并 trace
        """
        # 取 max(ctx.max_iterations, 15),不修改原 ctx
        floored_iter = max(ctx.max_iterations, self.MIN_ITERATIONS_FLOOR)

        # 第一阶段:Plan&Execute
        reasoning_ctx = self._build_reasoning_context(
            ctx,
            ReasoningMode.PLAN_EXECUTE,
            max_iterations_override=floored_iter,
            extra_overrides={
                "think_mode": True,
                "cost_preference": "quality",
            },
        )
        engine = self._select_engine(ReasoningMode.PLAN_EXECUTE)
        trace = engine.reason(reasoning_ctx)

        # 第二阶段:Self-Reflect(对 trace 做反思校验)
        if trace.steps:
            reflect_ctx = self._build_reasoning_context(
                ctx,
                ReasoningMode.SELF_REFLECT,
                max_iterations_override=floored_iter,
                extra_overrides={
                    "think_mode": True,
                    "cost_preference": "quality",
                },
            )
            reflect_engine = self._select_engine(ReasoningMode.SELF_REFLECT)
            reflect_trace = reflect_engine.reason(reflect_ctx)
            # 合并 trace(把反思步骤追加到原 trace)
            trace.steps.extend(reflect_trace.steps)
            # BUG 修复:ExecutionTrace 无 final_response 字段,
            # 用 getattr 安全访问,避免 AttributeError 中断执行
            reflect_final = getattr(reflect_trace, "final_response", None)
            if reflect_final:
                trace.final_response = reflect_final
        return trace

    def estimate_cost(self, ctx: StrategyContext) -> dict[str, Any]:
        """Precise 策略成本预估(最高档,比 Fast 贵 20 倍)。"""
        return {
            "input_tokens": 2000,
            "output_tokens": 800,
            "duration_s": 8.0,
            "cost_usd": 0.01,  # 比 Fast 贵 20 倍
            "tool_calls": 5,
            "iterations": 12,
        }

    def is_applicable(self, ctx: StrategyContext) -> bool:
        """Precise 适用条件:用户要求精确 / 工具数 ≥ 5 / 复杂任务关键词。"""
        # 工具数多或用户要求精确时适用
        if ctx.user_preference == "precise":
            return True
        if ctx.available_tools >= 5:
            return True
        # 复杂任务关键词(简单委托给 selector 的复杂度评分)
        complex_keywords = ["然后", "接着", "之后", "并", "多个", "批量", "依次"]
        if any(kw in ctx.goal for kw in complex_keywords):
            return True
        return False
