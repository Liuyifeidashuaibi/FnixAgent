"""
LangGraph 图装配与编译。

将节点与边组装为 StateGraph,编译为可执行的图实例:
    START → perceive → search → skill_select → execute → reflect
                                                        ↓
                                              ┌── loop_back ──┐
                                              ↓               │
                                          perceive         (循环)
                                              ↑               │
                                              └───────────────┘
                                              ↓
                                             END(to_end)

用法:
    builder = GraphBuilder(
        search_engine=search,
        scheduler=scheduler,
        registry=registry,
        binding_protocol=binding,
    )
    graph = builder.build()
    result = graph.invoke(create_initial_state("搜索论文"))

便捷函数:
    graph = build_graph(search_engine=..., scheduler=..., registry=...)
"""
from __future__ import annotations

from typing import Any

from officeagent.graph.edges import (
    EDGE_LOOP_BACK,
    EDGE_TO_END,
    EDGE_TO_EXECUTE,
    EDGE_TO_REFLECT,
    EDGE_TO_SEARCH,
    EDGE_TO_SKILL_SELECT,
    route_after_reflect,
)
from officeagent.graph.nodes import (
    NODE_EXECUTE,
    NODE_PERCEIVE,
    NODE_REFLECT,
    NODE_SEARCH,
    NODE_SKILL_SELECT,
    make_execute_node,
    make_search_node,
    make_skill_select_node,
    perceive_node,
    reflect_node,
)
from officeagent.graph.state import GraphState


class GraphBuilder:
    """LangGraph 图装配器。

    依赖注入:
        - search_engine: TopologySearch 实例(KTG 路径搜索)
        - scheduler: SkillScheduler 实例(STP 技能调度)
        - registry: ToolRegistry 实例(工具注册表)
        - binding_protocol: SkillBindingProtocol 实例(技能-拓扑绑定)
        - executor: 可选的 ToolExecutor 实例(并行工具执行)
    """

    def __init__(
        self,
        search_engine: Any,
        scheduler: Any,
        registry: Any,
        binding_protocol: Any = None,
        executor: Any = None,
    ) -> None:
        """初始化图装配器。

        Args:
            search_engine:   TopologySearch 实例(必填)
            scheduler:       SkillScheduler 实例(必填)
            registry:        ToolRegistry 实例(必填)
            binding_protocol: SkillBindingProtocol 实例(可选)
            executor:        ToolExecutor 实例(可选, 用于并行工具执行)
        """
        self._search_engine = search_engine
        self._scheduler = scheduler
        self._registry = registry
        self._binding_protocol = binding_protocol
        self._executor = executor

    def _add_nodes_and_edges(self, graph: Any, start: Any, end: Any) -> None:
        """向 StateGraph 添加节点与边(供 build/build_with_checkpointer 复用)。

        流程:
            1. 添加 5 个节点(perceive/search/skill_select/execute/reflect)
            2. 添加无条件线性边(START → perceive → search → skill_select → execute → reflect)
            3. 添加条件边(reflect → loop_back|to_end, 由 route_after_reflect 决定)

        Args:
            graph: StateGraph 实例
            start: langgraph.graph.START 常量
            end:   langgraph.graph.END 常量
        """
        # === 1. 添加节点 ===
        graph.add_node(NODE_PERCEIVE, perceive_node)
        graph.add_node(NODE_SEARCH, make_search_node(self._search_engine))
        graph.add_node(
            NODE_SKILL_SELECT,
            make_skill_select_node(self._scheduler, self._binding_protocol),
        )
        graph.add_node(
            NODE_EXECUTE,
            make_execute_node(self._registry, self._executor),
        )
        graph.add_node(NODE_REFLECT, reflect_node)

        # === 2. 添加无条件边(线性流转) ===
        graph.add_edge(start, NODE_PERCEIVE)
        graph.add_edge(NODE_PERCEIVE, NODE_SEARCH)
        graph.add_edge(NODE_SEARCH, NODE_SKILL_SELECT)
        graph.add_edge(NODE_SKILL_SELECT, NODE_EXECUTE)
        graph.add_edge(NODE_EXECUTE, NODE_REFLECT)

        # === 3. 添加条件边(反思后决定循环或结束) ===
        graph.add_conditional_edges(
            NODE_REFLECT,
            route_after_reflect,
            {
                EDGE_LOOP_BACK: NODE_PERCEIVE,  # 继续循环 → 回到感知
                EDGE_TO_END: end,                # 结束 → END
            },
        )

    def build(self) -> Any:
        """装配并编译 LangGraph 图。

        编译流程:
            1. 延迟导入 langgraph(避免强制依赖)
            2. 创建 StateGraph(GraphState)
            3. 添加节点与边(委托 _add_nodes_and_edges)
            4. graph.compile() 编译为可执行图

        Returns:
            编译后的 CompiledGraph 实例(graph.invoke(state) 可执行)

        Raises:
            ImportError:  LangGraph 未安装
            RuntimeError: 图编译失败(节点/边配置错误)
        """
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as e:
            raise ImportError(
                "LangGraph 未安装,请运行: pip install langgraph>=0.2.0"
            ) from e

        # 创建状态图(以 GraphState 为状态 schema)
        graph = StateGraph(GraphState)
        # 添加节点与边
        self._add_nodes_and_edges(graph, START, END)

        # 编译图(捕获编译期异常, 提供清晰错误信息)
        try:
            compiled = graph.compile()
        except Exception as e:
            raise RuntimeError(
                f"LangGraph 图编译失败: {type(e).__name__}: {e}"
            ) from e
        return compiled

    def build_with_checkpointer(
        self, checkpointer: Any = None
    ) -> Any:
        """装配带检查点的图(支持中断恢复)。

        Args:
            checkpointer: LangGraph 检查器(如 MemorySaver); None 时使用默认内存检查点

        Returns:
            编译后的图(支持 graph.invoke(state, config={"configurable": {"thread_id": ...}}))

        Raises:
            ImportError:  LangGraph 未安装
            RuntimeError: 图编译失败
        """
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as e:
            raise ImportError(
                "LangGraph 未安装,请运行: pip install langgraph>=0.2.0"
            ) from e

        graph = StateGraph(GraphState)
        # 添加节点与边(同 build)
        self._add_nodes_and_edges(graph, START, END)

        # 带检查点编译
        if checkpointer is None:
            # 默认使用内存检查点
            try:
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
            except ImportError:
                pass  # 无检查点也可工作

        try:
            if checkpointer is not None:
                compiled = graph.compile(checkpointer=checkpointer)
            else:
                compiled = graph.compile()
        except Exception as e:
            raise RuntimeError(
                f"LangGraph 图编译失败(带检查点): {type(e).__name__}: {e}"
            ) from e
        return compiled


# ---------------------------------------------------------------------------
# 便捷函数: 一行构建图(隐藏 GraphBuilder 细节)
# ---------------------------------------------------------------------------

def build_graph(
    search_engine: Any,
    scheduler: Any,
    registry: Any,
    binding_protocol: Any = None,
    executor: Any = None,
    checkpointer: Any = None,
) -> Any:
    """便捷函数: 装配并编译 LangGraph 图。

    等价于:
        builder = GraphBuilder(search_engine, scheduler, registry,
                               binding_protocol, executor)
        graph = builder.build()

    Args:
        search_engine:    TopologySearch 实例
        scheduler:        SkillScheduler 实例
        registry:         ToolRegistry 实例
        binding_protocol: 可选, SkillBindingProtocol 实例
        executor:         可选, ToolExecutor 实例
        checkpointer:     可选, 检查器; 非空则使用 build_with_checkpointer

    Returns:
        编译后的图实例

    Raises:
        ImportError:  LangGraph 未安装
        RuntimeError: 图编译失败
    """
    builder = GraphBuilder(
        search_engine=search_engine,
        scheduler=scheduler,
        registry=registry,
        binding_protocol=binding_protocol,
        executor=executor,
    )
    if checkpointer is not None:
        return builder.build_with_checkpointer(checkpointer)
    return builder.build()
