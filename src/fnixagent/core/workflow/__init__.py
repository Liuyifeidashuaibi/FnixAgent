"""工作流引擎包 (Workflow Engine) —— P1-04。

借鉴 kaoyan-ai-platform 的 routing.py:用显式状态机替代硬编码编排流程,
使路由逻辑可见、可调试、可检查点持久化。

工作流节点:
  analyze → plan → think → execute_tools → reflect → end

设计动机:
  - 原 Agent.reply() 的 4 步 ReAct 循环(prepare→think→act→reflect)硬编码
    在模板方法中,路由逻辑不可见、不可调试、不可中断恢复
  - 本包将路由逻辑提取为独立的 WorkflowEngine,条件路由集中化在 _route
  - 节点为 async 函数,可按需注册/替换(策略模式)
  - WorkflowContext 可序列化,支持 Checkpoint 持久化与恢复
  - max_total_steps / max_tool_rounds 双重上限保护(借鉴 kaoyan)

核心导出:
  - WorkflowState:        工作流节点状态枚举
  - WorkflowContext:      工作流上下文(可序列化,节点间传递)
  - WorkflowEngine:       工作流引擎(驱动节点间条件路由)
  - NodeResult:           节点执行结果枚举(SUCCESS/CONTINUE/SKIP/FAIL)
  - WorkflowNode:         节点函数类型别名
  - get_workflow_engine:  获取全局引擎单例

用法:
    from fnixagent.core.workflow import (
        WorkflowContext, WorkflowState, get_workflow_engine,
    )
    from fnixagent.core.workflow.nodes import register_default_nodes

    engine = get_workflow_engine()
    register_default_nodes(engine)

    ctx = WorkflowContext(goal="帮我检索 arxiv 上的 LLM 综述")
    result = await engine.run(ctx)
    # result.status == "success"

自定义节点(替换默认 think):
    async def my_think(ctx: WorkflowContext) -> NodeResult:
        ctx.think_text = await llm.chat(ctx.goal)
        ctx.round_idx += 1
        return NodeResult.SUCCESS

    engine.register(WorkflowState.THINK, my_think)
"""
from __future__ import annotations

from fnixagent.core.workflow.engine import (
    NodeFunc,
    NodeResult,
    WorkflowEngine,
    WorkflowNode,
    get_workflow_engine,
    reset_workflow_engine,
)
from fnixagent.core.workflow.state import WorkflowContext, WorkflowState

__all__ = [
    # 状态与上下文
    "WorkflowState",
    "WorkflowContext",
    # 引擎与节点
    "WorkflowEngine",
    "NodeResult",
    "NodeFunc",
    "WorkflowNode",
    # 单例
    "get_workflow_engine",
    "reset_workflow_engine",
]
