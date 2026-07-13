"""工作流引擎 - 驱动节点间的条件路由(借鉴 kaoyan routing.py)。

将原 Agent 的 4 步 ReAct 硬编码循环(prepare→think→act→reflect)显式化为
可见、可调试、可检查点持久化的状态机:

  analyze → plan → think → execute_tools → reflect → end

核心概念:
  - WorkflowState:  节点状态枚举(state.py)
  - WorkflowContext: 节点间传递的可序列化上下文(state.py)
  - NodeResult:     节点执行结果(SUCCESS/CONTINUE/SKIP/FAIL)
  - NodeFunc:        节点函数类型(async (ctx) -> NodeResult)
  - WorkflowEngine:  引擎,负责注册节点 + 条件路由 + 主循环

条件路由(集中化在 _route 方法):
  - analyze → plan (始终)
  - plan → think (始终)
  - think → execute_tools (有 tool_calls 且未达 max_total_steps)
  - think → reflect (无 tool_calls 或已达上限)
  - execute_tools → think (未达 max_tool_rounds,继续循环)
  - execute_tools → reflect (达 max_tool_rounds)
  - reflect → end (始终)

线程安全:
  - register / unregister / has_node 使用 threading.Lock 保护 _nodes 字典
  - run 异步执行,读取节点函数时加锁快照,避免运行期被替换导致不一致

标准库 only:asyncio / dataclasses / enum / threading / logging。

用法:
    from fnixagent.core.workflow import (
        WorkflowContext, WorkflowState, get_workflow_engine,
    )
    from fnixagent.core.workflow.nodes import register_default_nodes

    engine = get_workflow_engine()
    register_default_nodes(engine)

    ctx = WorkflowContext(goal="帮我检索 arxiv 上的 LLM 综述")
    result = await engine.run(ctx)
"""
from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

from fnixagent.core.workflow.state import WorkflowContext, WorkflowState

logger = logging.getLogger(__name__)


class NodeResult(str, Enum):
    """节点执行结果。

    继承 str+Enum,可直接与字符串比较。

    Attributes:
        SUCCESS:  成功,正常路由到下一节点
        CONTINUE: 继续(语义同 SUCCESS,供节点表达"需继续循环")
        SKIP:     跳过(正常路由,但提示本节点未实际执行)
        FAIL:     失败,直接路由到 END(终止工作流)
    """

    SUCCESS = "success"
    CONTINUE = "continue"
    SKIP = "skip"
    FAIL = "fail"


# 节点函数类型别名:接收 WorkflowContext,返回 NodeResult
NodeFunc = Callable[[WorkflowContext], Awaitable[NodeResult]]

# 公共别名(供 __init__ 导出,语义更清晰)
WorkflowNode = NodeFunc


class WorkflowEngine:
    """工作流引擎 - 驱动节点间的条件路由。

    节点注册:
        engine = WorkflowEngine()
        engine.register(WorkflowState.ANALYZE, analyze_node)
        engine.register(WorkflowState.THINK, think_node)
        ...

    运行:
        ctx = WorkflowContext(goal="...", ...)
        result = await engine.run(ctx)

    条件路由(借鉴 kaoyan routing.py,集中化在 _route):
        analyze → plan
        plan → think
        think → execute_tools (有 tool_calls 且未达上限)
        think → reflect (无 tool_calls 或已达上限)
        execute_tools → think (继续)
        execute_tools → reflect (达上限)
        reflect → end

    线程安全:
      - register/unregister/has_node 加锁保护 _nodes
      - run 在执行节点前快照节点函数引用,避免运行期被替换
    """

    # 工作流图(节点 → 可到达的下一节点列表)
    # 用于 get_graph() 可视化,不参与路由决策(路由在 _route)
    _GRAPH: dict[WorkflowState, list[WorkflowState]] = {
        WorkflowState.ANALYZE: [WorkflowState.PLAN],
        WorkflowState.PLAN: [WorkflowState.THINK],
        WorkflowState.THINK: [WorkflowState.EXECUTE_TOOLS, WorkflowState.REFLECT],
        WorkflowState.EXECUTE_TOOLS: [WorkflowState.THINK, WorkflowState.REFLECT],
        WorkflowState.REFLECT: [WorkflowState.END],
        WorkflowState.END: [],
    }

    def __init__(self) -> None:
        """初始化工作流引擎(无注册节点)。"""
        self._nodes: dict[WorkflowState, NodeFunc] = {}
        # RLock 允许同线程嵌套(has_node → 持锁内调其他持锁方法)
        self._lock = threading.RLock()

    # -- 节点注册 ----------------------------------------------------------

    def register(self, node: WorkflowState, func: NodeFunc) -> None:
        """注册节点函数(覆盖同名节点)。

        Args:
            node: 工作流节点状态
            func: 节点函数(async (ctx) -> NodeResult)

        Raises:
            TypeError: node 不是 WorkflowState,或 func 不可调用
        """
        if not isinstance(node, WorkflowState):
            raise TypeError(
                f"node must be WorkflowState, got {type(node).__name__}"
            )
        if not callable(func):
            raise TypeError(
                f"func must be callable, got {type(func).__name__}"
            )
        with self._lock:
            self._nodes[node] = func
        logger.debug("工作流节点已注册: %s", node.value)

    def unregister(self, node: WorkflowState) -> bool:
        """注销节点。

        Args:
            node: 工作流节点状态

        Returns:
            True 表示节点存在并已移除;False 表示节点未注册
        """
        with self._lock:
            existed = node in self._nodes
            self._nodes.pop(node, None)
        if existed:
            logger.debug("工作流节点已注销: %s", node.value)
        return existed

    def has_node(self, node: WorkflowState) -> bool:
        """检查节点是否已注册。"""
        with self._lock:
            return node in self._nodes

    def registered_nodes(self) -> list[WorkflowState]:
        """返回已注册的节点列表(拷贝)。"""
        with self._lock:
            return list(self._nodes.keys())

    # -- 主循环 ------------------------------------------------------------

    async def run(self, ctx: WorkflowContext) -> WorkflowContext:
        """运行工作流,直到 END 或失败。

        主循环:
          1. 取当前节点对应的函数(快照,加锁)
          2. 未注册 → 标记 failed 并退出
          3. 执行节点函数 → NodeResult
          4. 异常 → 标记 failed 并退出(记录 traceback)
          5. _route 决定下一节点,更新 ctx.current_node
          6. 回到步骤 1,直到 current_node == END

        Args:
            ctx: 工作流上下文(会被原地修改)

        Returns:
            同一份 ctx(便于链式取结果)
        """
        while ctx.current_node != WorkflowState.END:
            # 快照节点函数,避免运行期被 unregister 导致 KeyError
            with self._lock:
                node_func = self._nodes.get(ctx.current_node)

            if node_func is None:
                ctx.status = "failed"
                ctx.error = f"工作流节点未注册: {ctx.current_node.value}"
                logger.error(
                    "工作流节点未注册: %s (已注册: %s)",
                    ctx.current_node.value,
                    [n.value for n in self.registered_nodes()],
                )
                break

            logger.debug(
                "工作流执行节点: %s (round=%d, tool_round=%d)",
                ctx.current_node.value,
                ctx.round_idx,
                ctx.tool_round_idx,
            )

            try:
                result = await node_func(ctx)
            except Exception as exc:
                ctx.status = "failed"
                ctx.error = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "工作流节点 %s 执行异常: %s: %s",
                    ctx.current_node.value,
                    type(exc).__name__,
                    exc,
                )
                break

            # 校验节点返回值(防御:非 NodeResult 视为 SUCCESS)
            if not isinstance(result, NodeResult):
                logger.warning(
                    "工作流节点 %s 返回非 NodeResult(%s),按 SUCCESS 处理",
                    ctx.current_node.value,
                    type(result).__name__,
                )
                result = NodeResult.SUCCESS

            next_node = self._route(ctx, result)
            ctx.current_node = next_node

        return ctx

    # -- 条件路由 ----------------------------------------------------------

    def _route(
        self,
        ctx: WorkflowContext,
        node_result: NodeResult,
    ) -> WorkflowState:
        """条件路由:根据当前节点和结果决定下一节点。

        借鉴 kaoyan routing.py 的集中化路由设计。

        路由规则:
          - FAIL 或 ctx.status == "failed" → END(立即终止)
          - ANALYZE → PLAN
          - PLAN → THINK
          - THINK:
              * round_idx >= max_total_steps → REFLECT(达上限)
              * 无 tool_calls → REFLECT(已是最终答案)
              * 否则 → EXECUTE_TOOLS
          - EXECUTE_TOOLS:
              * tool_round_idx += 1(累计工具轮次)
              * tool_round_idx >= max_tool_rounds → REFLECT(达上限)
              * 否则 → THINK(继续循环)
          - REFLECT → END

        注意:EXECUTE_TOOLS 分支会修改 ctx.tool_round_idx(副作用),
        这是 kaoyan 原设计,保留以与上限判断一致。

        Args:
            ctx:          工作流上下文(可能被修改 tool_round_idx)
            node_result:  当前节点的执行结果

        Returns:
            下一节点状态
        """
        current = ctx.current_node

        # 失败短路:FAIL 或已标记 failed → END
        if node_result == NodeResult.FAIL or ctx.status == "failed":
            return WorkflowState.END

        if current == WorkflowState.ANALYZE:
            return WorkflowState.PLAN

        if current == WorkflowState.PLAN:
            return WorkflowState.THINK

        if current == WorkflowState.THINK:
            # 达到 think 循环上限 → 进入反思
            if ctx.round_idx >= ctx.max_total_steps:
                return WorkflowState.REFLECT
            # 无工具调用 → 已是最终答案,进入反思
            if not ctx.tool_calls:
                return WorkflowState.REFLECT
            return WorkflowState.EXECUTE_TOOLS

        if current == WorkflowState.EXECUTE_TOOLS:
            # 累计工具轮次(副作用,保留 kaoyan 原设计)
            ctx.tool_round_idx += 1
            # 达到工具执行上限 → 进入反思
            if ctx.tool_round_idx >= ctx.max_tool_rounds:
                return WorkflowState.REFLECT
            return WorkflowState.THINK

        if current == WorkflowState.REFLECT:
            return WorkflowState.END

        # 兜底:未知节点 → END
        return WorkflowState.END

    # -- 可视化 ------------------------------------------------------------

    def get_graph(self) -> dict[str, list[str]]:
        """返回工作流图(节点 → 可到达的下一节点列表)。

        用于调试/可视化/文档生成,不参与运行期路由决策。

        Returns:
            {node_value: [next_node_value, ...]}
        """
        return {
            node.value: [n.value for n in nexts]
            for node, nexts in self._GRAPH.items()
        }

    def get_stats(self) -> dict[str, Any]:
        """返回工作流引擎运行时统计(线程安全快照)。

        供 fnixagent.core.observability.stats 聚合器采集,
        不修改任何内部状态。

        Returns:
            包含已注册节点数、节点列表与工作流图的字典。
        """
        with self._lock:
            registered = list(self._nodes.keys())
        return {
            "registered_node_count": len(registered),
            "registered_nodes": [n.value for n in registered],
            "graph": self.get_graph(),
        }


# ---------------------------------------------------------------------------
# 模块级单例(双重检查锁)
# ---------------------------------------------------------------------------

_engine_singleton: Optional[WorkflowEngine] = None
_engine_lock = threading.Lock()


def get_workflow_engine() -> WorkflowEngine:
    """获取全局 WorkflowEngine 单例(双重检查锁)。

    首次调用返回一个裸引擎(无注册节点)。
    如需默认节点,请调用 fnixagent.core.workflow.nodes.register_default_nodes。

    Returns:
        全局唯一的 WorkflowEngine 实例
    """
    global _engine_singleton
    if _engine_singleton is None:
        with _engine_lock:
            if _engine_singleton is None:
                _engine_singleton = WorkflowEngine()
    return _engine_singleton


def reset_workflow_engine() -> None:
    """重置全局单例(主要供测试使用)。

    重置后,下次 get_workflow_engine() 会重新创建实例。
    """
    global _engine_singleton
    with _engine_lock:
        _engine_singleton = None


__all__ = [
    "NodeResult",
    "NodeFunc",
    "WorkflowNode",
    "WorkflowEngine",
    "get_workflow_engine",
    "reset_workflow_engine",
]
