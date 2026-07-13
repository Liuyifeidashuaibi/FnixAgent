"""
LangGraph 条件边定义。

条件边决定图的流转方向:
    - perceive → search: 无条件(感知后必检索)
    - search → skill_select: 无条件(检索后必选技能)
    - skill_select → execute: 无条件(选技能后必执行)
    - execute → reflect: 无条件(执行后必反思)
    - reflect → perceive | END: 条件边(should_continue 决定)

条件路由函数返回下一节点名称,LangGraph 据此选择边。

P1-3 扩展:
    - RouteRegistry:    路由函数注册表(支持运行时动态注册)
    - route_after_reflect_v2: 增强版反思路由(含 human_review/replan 分支)
    - route_after_execute:    执行后路由(含 fallback 分支)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from fnixagent.graph.nodes import NODE_PERCEIVE
from fnixagent.graph.state import GraphState

# 边名称常量(对应 LangGraph add_conditional_edges 的字典 key)
EDGE_TO_SEARCH = "to_search"              # perceive → search(无条件, 仅命名)
EDGE_TO_SKILL_SELECT = "to_skill_select"  # search → skill_select(无条件)
EDGE_TO_EXECUTE = "to_execute"            # skill_select → execute(无条件)
EDGE_TO_REFLECT = "to_reflect"            # execute → reflect(无条件)
EDGE_LOOP_BACK = "loop_back"              # reflect → perceive(循环)
EDGE_TO_END = "to_end"                    # reflect → END(结束)
# P1-3 新增边(增强路由分支)
EDGE_TO_HUMAN_REVIEW = "to_human_review"  # 人工审核分支
EDGE_TO_REPLAN = "to_replan"              # 重规划分支
EDGE_TO_FALLBACK = "to_fallback"          # 降级处理分支


def route_after_reflect(state: GraphState) -> str:
    """反思后的条件路由: 决定循环回感知还是结束。

    Returns:
        "loop_back": 继续循环(回到 perceive 节点)
        "to_end": 结束(进入 END)
    """
    should_continue = state.get("should_continue", False)
    if should_continue:
        return EDGE_LOOP_BACK
    return EDGE_TO_END


def should_stop_on_error(state: GraphState) -> str:
    """错误检查路由: 若有致命错误则直接结束。

    Returns:
        "to_end": 结束
        "continue": 继续
    """
    error = state.get("error")
    if error and error == "max_iterations_exceeded":
        return EDGE_TO_END
    return "continue"


# ---------------------------------------------------------------------------
# P1-3: Conditional Edge 动态路由扩展
# ---------------------------------------------------------------------------


# 路由函数类型:接收 GraphState,返回边名称
RouteFn = Callable[[GraphState], str]


@dataclass
class RouteDecision:
    """路由决策结果。

    Attributes:
        edge:   边名称(对应 EDGE_* 常量)
        reason: 决策原因(用于日志/追踪,可选)
    """

    edge: str
    reason: str = ""

    def __str__(self) -> str:
        return self.edge


class RouteRegistry:
    """路由函数注册表(P1-3)。

    支持运行时动态注册路由函数,实现条件边的灵活扩展:
      - register(node_name, route_fn, targets): 注册节点后的路由函数
      - get(node_name): 获取节点的路由函数
      - route(node_name, state): 执行路由,返回边名称

    用法:
        registry = RouteRegistry()
        registry.register("reflect", route_after_reflect_v2,
                          targets=["loop_back", "to_end", "to_human_review"])
        edge = registry.route("reflect", state)
    """

    def __init__(self) -> None:
        self._routes: dict[str, tuple[RouteFn, list[str]]] = {}

    def register(
        self,
        node_name: str,
        route_fn: RouteFn,
        targets: Optional[list[str]] = None,
    ) -> None:
        """注册节点的路由函数。

        Args:
            node_name: 节点名称(如 "reflect")
            route_fn:  路由函数 (state) -> edge_name
            targets:   可能的目标边列表(用于 LangGraph add_conditional_edges)
        """
        self._routes[node_name] = (route_fn, targets or [])

    def unregister(self, node_name: str) -> None:
        """移除节点的路由函数。"""
        self._routes.pop(node_name, None)

    def get(self, node_name: str) -> Optional[RouteFn]:
        """获取节点的路由函数(无则返回 None)。"""
        entry = self._routes.get(node_name)
        return entry[0] if entry else None

    def get_targets(self, node_name: str) -> list[str]:
        """获取节点路由的可能目标边列表。"""
        entry = self._routes.get(node_name)
        return entry[1] if entry else []

    def route(self, node_name: str, state: GraphState) -> str:
        """执行路由,返回边名称。

        Args:
            node_name: 节点名称
            state:     当前状态

        Returns:
            边名称(若无注册路由,返回 EDGE_TO_END 作为默认)
        """
        route_fn = self.get(node_name)
        if route_fn is None:
            return EDGE_TO_END
        return route_fn(state)

    @property
    def registered_nodes(self) -> list[str]:
        """已注册路由的节点列表。"""
        return list(self._routes.keys())

    def is_registered(self, node_name: str) -> bool:
        """检查节点是否已注册路由。"""
        return node_name in self._routes


# 全局默认注册表(单例)
_default_registry: Optional[RouteRegistry] = None


def get_default_registry() -> RouteRegistry:
    """获取全局默认 RouteRegistry(惰性初始化)。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = RouteRegistry()
        # 注册默认路由
        _default_registry.register(
            "reflect", route_after_reflect,
            targets=[EDGE_LOOP_BACK, EDGE_TO_END],
        )
        _default_registry.register(
            "error_check", should_stop_on_error,
            targets=[EDGE_TO_END, "continue"],
        )
    return _default_registry


# ---------------------------------------------------------------------------
# P1-3: 增强版路由函数
# ---------------------------------------------------------------------------


def route_after_reflect_v2(state: GraphState) -> str:
    """反思后的增强版条件路由(P1-3)。

    决策逻辑(优先级从高到低):
      1. 致命错误 → to_end
      2. 需要人工审核 → to_human_review(state.needs_human_review)
      3. 需要重规划 → to_replan(state.replan_required)
      4. 应继续循环 → loop_back
      5. 否则 → to_end

    Returns:
        边名称(EDGE_TO_END / EDGE_TO_HUMAN_REVIEW / EDGE_TO_REPLAN /
               EDGE_LOOP_BACK)
    """
    # 致命错误
    error = state.get("error")
    if error and error in (
        "max_iterations_exceeded",
        "circuit_open",
        "guardrail_blocked",
    ):
        return EDGE_TO_END

    # 需要人工审核(trace 中标记)
    trace = state.get("trace", {})
    if isinstance(trace, dict) and trace.get("needs_human_review"):
        return EDGE_TO_HUMAN_REVIEW

    # 需要重规划
    if isinstance(trace, dict) and trace.get("replan_required"):
        return EDGE_TO_REPLAN

    # 应继续循环
    should_continue = state.get("should_continue", False)
    if should_continue:
        return EDGE_LOOP_BACK

    return EDGE_TO_END


def route_after_execute(state: GraphState) -> str:
    """执行后的条件路由(P1-3)。

    决策逻辑:
      1. 全部工具失败 → to_fallback(降级处理)
      2. 部分失败但可继续 → to_reflect(正常反思)
      3. 全部成功 → to_reflect

    Returns:
        EDGE_TO_FALLBACK 或 EDGE_TO_REFLECT
    """
    tool_results = state.get("tool_results", [])
    if not tool_results:
        return EDGE_TO_REFLECT

    # 检查失败比例
    failed_count = sum(
        1 for r in tool_results
        if isinstance(r, dict) and r.get("status") == "failed"
    )
    total = len(tool_results)

    # 全部失败 → 降级
    if total > 0 and failed_count == total:
        return EDGE_TO_FALLBACK

    return EDGE_TO_REFLECT

