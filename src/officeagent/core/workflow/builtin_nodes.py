"""工作流默认节点实现。

提供 analyze/plan/think/execute_tools/reflect 五个节点的默认实现,
上层可按需覆盖(通过 engine.register 注册替换)。

默认实现策略:
  - analyze:        调用 MoE 路由器快速分类(零 LLM 调用,失败降级)
  - plan:           透传 analyze 结果(复杂规划由上层注入)
  - think:          占位(实际推理由 Agent.think 注入),累加 round_idx
  - execute_tools:  占位(实际执行由 ToolExecutor 注入)
  - reflect:        调用多评估器反思系统评估最终答案(失败降级为仅置 status)

依赖说明:
  - 默认节点通过惰性 import 调用 moe_router / reflection_manager
  - 若被调用模块不可用,节点降级为占位行为,不阻断工作流
  - 工作流引擎本身不依赖这些模块(标准库 only)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from officeagent.core.workflow.engine import NodeResult
from officeagent.core.workflow.state import WorkflowContext, WorkflowState

if TYPE_CHECKING:
    from officeagent.core.workflow.engine import WorkflowEngine

logger = logging.getLogger(__name__)


async def default_analyze(ctx: WorkflowContext) -> NodeResult:
    """默认分析节点 - 用 MoE 路由器快速分类(零 LLM 调用)。

    调用 officeagent.core.multiagent.moe_router.get_router() 对 goal
    做关键词路由,输出"任务类型: {expert}"文本,并将 expert_key 存入 extra。
    路由失败时降级为默认专家 "generate",不阻断工作流。
    """
    try:
        from officeagent.core.multiagent.moe_router import get_router

        router = get_router()
        expert = router.route_by_user_input(ctx.goal)
    except Exception as exc:
        logger.warning(
            "default_analyze: MoE 路由失败,降级为默认专家 'generate': %s: %s",
            type(exc).__name__, exc,
        )
        expert = "generate"

    ctx.analyze_text = f"任务类型: {expert}"
    ctx.extra["expert_key"] = expert
    logger.debug("default_analyze: expert=%s", expert)
    return NodeResult.SUCCESS


async def default_plan(ctx: WorkflowContext) -> NodeResult:
    """默认规划节点 - 透传 analyze 结果(复杂规划由上层注入)。

    默认不拆分子任务,直接将 analyze_text 作为 plan_text。
    上层可通过 engine.register(WorkflowState.PLAN, custom_plan) 注入
    复杂的 LLM 规划逻辑(如 Plan&Execute 拆分)。
    """
    ctx.plan_text = ctx.analyze_text
    return NodeResult.SUCCESS


async def default_think(ctx: WorkflowContext) -> NodeResult:
    """默认思考节点 - 占位(实际由 Agent.think 注入)。

    仅累加 round_idx(供路由判断是否达 max_total_steps)。
    实际的 LLM 推理与 tool_calls 决策由上层注入:
        engine.register(WorkflowState.THINK, agent.think_node)
    """
    ctx.round_idx += 1
    return NodeResult.SUCCESS


async def default_execute_tools(ctx: WorkflowContext) -> NodeResult:
    """默认工具执行节点 - 占位。

    实际的工具执行由上层注入:
        engine.register(WorkflowState.EXECUTE_TOOLS, tool_executor_node)
    默认实现清空 ctx.tool_calls(表示本轮工具已处理),避免路由回 THINK
    时因 tool_calls 非空再次进入 EXECUTE_TOOLS 形成死循环。
    """
    # 清空已处理的工具调用,防止 _route 误判为"仍有工具需执行"
    # 而在 THINK ↔ EXECUTE_TOOLS 间死循环
    if ctx.tool_calls:
        ctx.tool_calls = []
    return NodeResult.SUCCESS


async def default_reflect(ctx: WorkflowContext) -> NodeResult:
    """默认反思节点 - 调用多评估器反思系统评估最终答案。

    对 final_answer(或 think_text 兜底)调用 ReflectionManager.evaluate,
    将反馈消息写入 reflect_text,子分数与是否需反思写入 extra。
    评估失败时降级为仅置 status=success,不阻断工作流结束。
    """
    content = ctx.final_answer or ctx.think_text or ""
    if content:
        try:
            from officeagent.core.reflection.manager import (
                get_reflection_manager,
            )

            manager = get_reflection_manager()
            result = await manager.evaluate(
                content,
                context={"goal": ctx.goal, "keywords": []},
            )
            ctx.reflect_text = result.feedback_message
            ctx.extra["reflection_score"] = result.score
            ctx.extra["reflection_should_reflect"] = result.should_reflect
            logger.debug(
                "default_reflect: score=%.2f, should_reflect=%s",
                result.score,
                result.should_reflect,
            )
        except Exception as exc:
            logger.warning(
                "default_reflect: 反思评估失败,跳过评估: %s: %s",
                type(exc).__name__, exc,
            )
            ctx.reflect_text = ""

    ctx.status = "success"
    return NodeResult.SUCCESS


def register_default_nodes(engine: "WorkflowEngine") -> None:
    """将 5 个默认节点注册到引擎。

    覆盖 analyze/plan/think/execute_tools/reflect 五个节点。
    可安全重复调用(后注册覆盖先注册)。

    Args:
        engine: WorkflowEngine 实例
    """
    engine.register(WorkflowState.ANALYZE, default_analyze)
    engine.register(WorkflowState.PLAN, default_plan)
    engine.register(WorkflowState.THINK, default_think)
    engine.register(WorkflowState.EXECUTE_TOOLS, default_execute_tools)
    engine.register(WorkflowState.REFLECT, default_reflect)
    logger.debug("已注册 5 个默认工作流节点")


__all__ = [
    "default_analyze",
    "default_plan",
    "default_think",
    "default_execute_tools",
    "default_reflect",
    "register_default_nodes",
]
