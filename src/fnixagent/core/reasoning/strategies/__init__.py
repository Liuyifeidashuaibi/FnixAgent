"""推理策略可插拔(P2-6)。

把"推理模式"和"质量/速度/成本偏好"解耦为独立的 Strategy 类:
  - BaseStrategy:    抽象基类,定义 execute / estimate_cost / is_applicable / think_mode
  - FastStrategy:    快速(单步 ReAct,非思考模式,适合简单任务)
  - CheapStrategy:   低成本(便宜模型,少工具,适合大规模批处理)
  - PreciseStrategy: 精确(Plan&Execute + Self-Reflect + 思考模式,适合关键任务)
  - ComplianceStrategy: 合规(强审计 + 人工确认 + 完整 trace,适合敏感操作)

设计要点:
  - Strategy 与 ReasoningEngine 正交:Strategy 描述"如何选模式 + 配置",
    ReasoningEngine(ReAct/PlanExecute/SelfReflect)是底层执行器
  - think_mode 字段对接 P2-8 思考/非思考模式(GLM-4.5 / DeepSeek-R1 等)
  - estimate_cost 返回 token / 时间 / 钱的预估,供调度器决策
  - is_applicable 让策略自评是否适用(如 ComplianceStrategy 仅对敏感任务返回 True)

ReasoningSelector 改造为策略模式:
  - 旧版 select(goal, tools) → ReasoningMode(保留向后兼容)
  - 新版 select_strategy(...) → BaseStrategy
"""
from fnixagent.core.reasoning.strategies.base import (
    BaseStrategy,
    StrategyContext,
    StrategyType,
)
from fnixagent.core.reasoning.strategies.fast import FastStrategy
from fnixagent.core.reasoning.strategies.cheap import CheapStrategy
from fnixagent.core.reasoning.strategies.precise import PreciseStrategy
from fnixagent.core.reasoning.strategies.compliance import ComplianceStrategy

__all__ = [
    "BaseStrategy",
    "StrategyContext",
    "StrategyType",
    "FastStrategy",
    "CheapStrategy",
    "PreciseStrategy",
    "ComplianceStrategy",
]
