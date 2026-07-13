"""Cheap 策略:低成本批处理(P2-6)。

特点:
  - 推理模式:ReAct(单步)
  - 思考模式:关闭
  - 模型选择:便宜模型(由 LLMRouter 根据 cost_score 路由到低成本 provider)
  - 工具数:少(强制 top_k=3,过滤贵工具)
  - 适用:大规模批处理、低价值任务、内部定时任务

与 Fast 的区别:
  - Fast 强调"响应快"(可能用贵模型快速出结果)
  - Cheap 强调"成本低"(用便宜模型,牺牲质量)

并发安全(BUG 修复):
  不再修改 ctx.max_iterations / ctx.extra,通过 override 透传给
  ReasoningContext 副本(同一 ctx 可被多次 execute)。
"""
from __future__ import annotations

from typing import Any

from officeagent.core.reasoning.strategies.base import BaseStrategy, StrategyContext
from officeagent.core.types import ExecutionTrace, ReasoningMode


class CheapStrategy(BaseStrategy):
    """低成本策略:ReAct + 便宜模型 + 严格工具过滤。"""

    # Cheap 策略强制上限(原 min(ctx.max_iterations, 2))
    MAX_ITERATIONS_CAP: int = 2

    @property
    def name(self) -> str:
        """策略名。"""
        return "cheap"

    @property
    def think_mode(self) -> bool:
        """不启用思考模式(Cheap 主打低成本)。"""
        return False

    def execute(self, ctx: StrategyContext) -> ExecutionTrace:
        """执行 Cheap 策略:ReAct + 便宜模型 + 严格迭代上限。

        通过 extra_overrides 标记 LLM 路由偏好(LLMRouter 在 chat() 时
        检查 ctx.extra['cost_preference'])。
        """
        # 取 min(ctx.max_iterations, 2),不修改原 ctx
        capped_iter = min(ctx.max_iterations, self.MAX_ITERATIONS_CAP)
        capped_iter = max(capped_iter, 1)
        # 标记 LLM 路由偏好:便宜模型(透传到 extra,不改原 ctx)
        reasoning_ctx = self._build_reasoning_context(
            ctx,
            ReasoningMode.REACT,
            max_iterations_override=capped_iter,
            extra_overrides={"cost_preference": "cheap"},
        )
        engine = self._select_engine(ReasoningMode.REACT)
        return engine.reason(reasoning_ctx)

    def estimate_cost(self, ctx: StrategyContext) -> dict[str, Any]:
        """Cheap 策略成本预估(比 Fast 便宜 5 倍)。"""
        return {
            "input_tokens": 200,
            "output_tokens": 100,
            "duration_s": 1.5,
            "cost_usd": 0.0001,  # 比 Fast 便宜 5 倍
            "tool_calls": 1,
            "iterations": 1,
        }

    def is_applicable(self, ctx: StrategyContext) -> bool:
        """Cheap 适用条件:非敏感任务且用户未显式要求精确。"""
        # 敏感任务不适用
        if ctx.sensitivity in ("medium", "high"):
            return False
        # 用户显式要求精确,不适用 Cheap
        if ctx.user_preference == "precise":
            return False
        return True
