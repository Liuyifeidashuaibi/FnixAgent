"""Fast 策略:快速响应(P2-6)。

特点:
  - 推理模式:ReAct(单步思考-行动,无规划阶段)
  - 思考模式:关闭(非 GLM-4.5 思考模式,直接生成答案)
  - 工具数:少(建议 ≤ 3 个,避免 LLM 选工具耗时)
  - max_iterations:小(默认 3 步,失败即返回)
  - 适用:简单查询、单工具调用、闲聊

成本预估:最低(token 少 / 耗时短)

并发安全(BUG 修复):
  原实现直接修改 ctx.max_iterations,导致同一 ctx 被多次 execute 时迭代数
  被反复截断。现通过 max_iterations_override 在 ReasoningContext 副本上生效。
"""
from __future__ import annotations

from typing import Any

from fnixagent.core.reasoning.strategies.base import BaseStrategy, StrategyContext
from fnixagent.core.types import ExecutionTrace, ReasoningMode


class FastStrategy(BaseStrategy):
    """快速策略:ReAct + 非思考模式 + 少迭代。"""

    # Fast 策略强制上限(原 min(ctx.max_iterations, 3))
    MAX_ITERATIONS_CAP: int = 3

    @property
    def name(self) -> str:
        """策略名。"""
        return "fast"

    @property
    def think_mode(self) -> bool:
        """不启用思考模式(Fast 主打快速响应)。"""
        return False

    def execute(self, ctx: StrategyContext) -> ExecutionTrace:
        """执行 Fast 策略:ReAct + 限制迭代数。

        不修改 ctx,通过 override 在 ReasoningContext 副本上设置 max_iterations。
        """
        # 取 min(ctx.max_iterations, 3),不修改原 ctx
        capped_iter = min(ctx.max_iterations, self.MAX_ITERATIONS_CAP)
        # max_iterations 必须 ≥1,避免 ReAct 循环 0 次
        capped_iter = max(capped_iter, 1)
        reasoning_ctx = self._build_reasoning_context(
            ctx,
            ReasoningMode.REACT,
            max_iterations_override=capped_iter,
        )
        engine = self._select_engine(ReasoningMode.REACT)
        return engine.reason(reasoning_ctx)

    def estimate_cost(self, ctx: StrategyContext) -> dict[str, Any]:
        """Fast 策略成本预估(最低档)。"""
        return {
            "input_tokens": 300,
            "output_tokens": 150,
            "duration_s": 1.0,
            "cost_usd": 0.0005,
            "tool_calls": 1,
            "iterations": 2,
        }

    def is_applicable(self, ctx: StrategyContext) -> bool:
        """Fast 适用条件:非敏感任务且工具数 ≤ 8。"""
        # 敏感任务不适用 Fast(让位给 Compliance)
        if ctx.sensitivity == "high":
            return False
        # 工具数过多不适用 Fast(让位给 Precise)
        if ctx.available_tools > 8:
            return False
        return True
