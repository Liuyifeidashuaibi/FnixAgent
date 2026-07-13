"""
规划与推理引擎 (Reasoning Engine)。

支持三种主流推理模式按需切换:
  1. ReAct:          思考-行动-观察循环(简单通用任务)
  2. Plan&Execute:   先拆分多步骤子任务,分步执行(复杂长流程)
  3. Self-Reflect:   执行后自动复盘校验(叠加在上述模式之上)

selector 根据任务复杂度自动选择模式。

P2-6 新增:策略可插拔(strategies/),4 个策略 + BaseStrategy 基类。
"""
from officeagent.core.reasoning.base import ReasoningEngine, ReasoningContext
from officeagent.core.reasoning.react import ReActEngine
from officeagent.core.reasoning.plan_execute import PlanExecuteEngine
from officeagent.core.reasoning.self_reflect import SelfReflectEngine
from officeagent.core.reasoning.selector import ReasoningSelector
from officeagent.core.reasoning.strategies import (
    BaseStrategy,
    CheapStrategy,
    ComplianceStrategy,
    FastStrategy,
    PreciseStrategy,
    StrategyContext,
    StrategyType,
)

__all__ = [
    "ReasoningEngine",
    "ReasoningContext",
    "ReActEngine",
    "PlanExecuteEngine",
    "SelfReflectEngine",
    "ReasoningSelector",
    # P2-6: 策略可插拔
    "BaseStrategy",
    "StrategyContext",
    "StrategyType",
    "FastStrategy",
    "CheapStrategy",
    "PreciseStrategy",
    "ComplianceStrategy",
]
