"""
飞轮 3: 元反思修正环(准实时,每 N 次对话触发)。

触发: 每 5 次对话 或 用户显式反馈"不对"
职责:
    1. 独立元 Agent 读取最近 N 条 TraceRecord + 当前知识拓扑子图
    2. 三维评估:
        - 推理路径质量: 路径权重 vs 平均值(低于均值 50% → 降权)
        - 技能匹配准确率: 成功调用率(< 60% → 调整优先级)
        - 知识完整性: 是否存在知识缺口(LLM 判定缺失 → 补全)
    3. 自动权重调节:
        - 有效路径: 权重 +0.03(强化)
        - 无效路径: 权重 -0.05(弱化)
        - 错误路径: 标记 deprecated,权重降至 0.01(永久降级)
    4. 自动补充拓扑缺失知识节点(初始置信度 0.2)
"""
from __future__ import annotations

import time
from typing import Any, Optional

from officeagent.core.flywheel.trace import TraceStore
from officeagent.core.topology import weights as weights_mod
from officeagent.core.topology.graph import TopologyGraph
from officeagent.core.types import (
    EdgeType,
    NodeType,
    TopologyLayer,
    TraceRecord,
)

# 默认触发间隔(对话数)
DEFAULT_TRIGGER_INTERVAL: int = 5

# 评估阈值
PATH_WEIGHT_LOW_THRESHOLD: float = 0.5     # 路径权重低于均值的 50% → 降权
SKILL_SUCCESS_RATE_THRESHOLD: float = 0.6  # 技能成功率低于 60% → 调整优先级

# 权重调节常量
EFFECTIVE_PATH_BONUS: float = 0.03         # 有效路径强化
INEFFECTIVE_PATH_PENALTY: float = -0.05    # 无效路径弱化
MISSING_KNOWLEDGE_CONFIDENCE: float = 0.2  # 补充节点的初始置信度(低于正常 0.3)


class MetaReflectionFlywheel:
    """飞轮 ③ 元反思修正环。

    用法:
        flywheel3 = MetaReflectionFlywheel(graph, trace_store)
        result = flywheel3.run()
    """

    def __init__(
        self,
        graph: TopologyGraph,
        trace_store: Optional[TraceStore] = None,
        llm_router: Any = None,
        trigger_interval: int = DEFAULT_TRIGGER_INTERVAL,
    ) -> None:
        """初始化元反思飞轮。

        Args:
            graph: 拓扑图实例
            trace_store: 轨迹存储(可选,也可直接传入 traces)
            llm_router: LLM 路由器(用于知识完整性评估)
            trigger_interval: 触发间隔(对话数)
        """
        self._graph = graph
        self._trace_store = trace_store
        self._llm = llm_router
        self._trigger_interval = trigger_interval
        self._task_count = 0

    def should_trigger(self) -> bool:
        """判断是否应触发元反思。"""
        self._task_count += 1
        return self._task_count >= self._trigger_interval

    def run(self, traces: Optional[list[TraceRecord]] = None) -> dict:
        """执行元反思。

        Args:
            traces: 待评估的轨迹列表(若为 None,从 trace_store 加载最近 N 条)

        Returns:
            反思结果 {
                "evaluated_traces": int,        评估的轨迹数
                "path_quality": float,          路径质量评分(0~1)
                "skill_accuracy": float,        技能匹配准确率(0~1)
                "knowledge_completeness": float,知识完整性评分(0~1)
                "weakened_paths": int,          弱化的路径数
                "strengthened_paths": int,      强化的路径数
                "deprecated_paths": int,        废弃的路径数
                "added_nodes": int,             补充的节点数
            }
        """
        # 加载轨迹
        if traces is None and self._trace_store is not None:
            traces = self._trace_store.load_recent(limit=self._trigger_interval)
        if not traces:
            traces = []

        # Step 1: 三维评估
        path_quality = self._evaluate_path_quality(traces)
        skill_accuracy = self._evaluate_skill_accuracy(traces)
        knowledge_completeness = self._evaluate_knowledge_completeness(traces)

        # Step 2: 自动权重调节
        weakened, strengthened, deprecated = self._adjust_weights(traces)

        # Step 3: 补充缺失知识节点
        added_nodes = self._fill_knowledge_gaps(traces)

        # 重置计数器
        self._task_count = 0

        return {
            "evaluated_traces": len(traces),
            "path_quality": path_quality,
            "skill_accuracy": skill_accuracy,
            "knowledge_completeness": knowledge_completeness,
            "weakened_paths": weakened,
            "strengthened_paths": strengthened,
            "deprecated_paths": deprecated,
            "added_nodes": added_nodes,
        }

    # -----------------------------------------------------------------------
    # 三维评估
    # -----------------------------------------------------------------------

    def _evaluate_path_quality(self, traces: list[TraceRecord]) -> float:
        """评估推理路径质量。

        计算: 成功轨迹的平均概念路径长度 / 全部轨迹的平均概念路径长度
        低于 0.5 → 路径质量差
        """
        if not traces:
            return 0.0
        success_traces = [t for t in traces if t.success]
        if not success_traces:
            return 0.0
        avg_success_path_len = sum(len(t.concept_path) for t in success_traces) / len(success_traces)
        avg_all_path_len = sum(len(t.concept_path) for t in traces) / len(traces)
        if avg_all_path_len == 0:
            return 1.0
        return min(1.0, avg_success_path_len / avg_all_path_len)

    def _evaluate_skill_accuracy(self, traces: list[TraceRecord]) -> float:
        """评估技能匹配准确率。

        计算: 成功的工具调用数 / 总工具调用数
        低于 60% → 需调整优先级
        """
        if not traces:
            return 0.0
        total_calls = 0
        success_calls = 0
        for trace in traces:
            for call in trace.tool_calls:
                total_calls += 1
                if call.get("status") == "success":
                    success_calls += 1
        if total_calls == 0:
            return 1.0
        return success_calls / total_calls

    def _evaluate_knowledge_completeness(self, traces: list[TraceRecord]) -> float:
        """评估知识完整性。

        若有 LLM: 让 LLM 判断是否存在知识缺口
        否则: 基于拓扑图规模估算(节点越多越完整)
        """
        stats = self._graph.stats()
        active_nodes = stats.get("active_nodes", 0)
        # 简单启发式: 节点数 > 50 视为完整
        if active_nodes >= 50:
            return 1.0
        return active_nodes / 50.0

    # -----------------------------------------------------------------------
    # 自动权重调节
    # -----------------------------------------------------------------------

    def _adjust_weights(self, traces: list[TraceRecord]) -> tuple[int, int, int]:
        """根据轨迹结果调节路径权重。

        Returns:
            (弱化路径数, 强化路径数, 废弃路径数)
        """
        weakened = 0
        strengthened = 0
        deprecated = 0

        for trace in traces:
            for node_id in trace.concept_path:
                if not self._graph.has_node(node_id):
                    continue
                node = self._graph.get_node(node_id)

                if trace.success:
                    # 成功 → 强化
                    node.weight = weights_mod.reinforce(node.weight, EFFECTIVE_PATH_BONUS)
                    strengthened += 1
                else:
                    # 失败 → 弱化
                    node.weight = weights_mod.penalize(node.weight, INEFFECTIVE_PATH_PENALTY)
                    weakened += 1

                    # 权重过低 → 废弃
                    if weights_mod.should_deprecate(node.weight):
                        self._graph.deprecate_node(node_id)
                        deprecated += 1

        return weakened, strengthened, deprecated

    # -----------------------------------------------------------------------
    # 补充缺失知识节点
    # -----------------------------------------------------------------------

    def _fill_knowledge_gaps(self, traces: list[TraceRecord]) -> int:
        """补充拓扑中缺失的知识节点。

        策略: 从失败轨迹中提取用户目标,若拓扑中无对应 L1 目标节点,则补充。
        新节点初始置信度 0.2(低于正常 0.3,需后续验证)。
        """
        if not self._llm:
            # 无 LLM 时,用规则式补充
            return self._rule_based_fill_gaps(traces)
        return self._llm_fill_gaps(traces)

    def _rule_based_fill_gaps(self, traces: list[TraceRecord]) -> int:
        """规则式补充(降级模式)。"""
        added = 0
        for trace in traces:
            if trace.success:
                continue  # 只从失败轨迹补充
            # 检查是否已有同名 L1 目标节点
            existing = self._find_node_by_name(trace.goal, TopologyLayer.L1_GOAL, NodeType.GOAL)
            if existing is None and trace.goal:
                self._graph.add_node(
                    layer=TopologyLayer.L1_GOAL,
                    node_type=NodeType.GOAL,
                    name=trace.goal[:50],  # 截断过长的目标
                    content=trace.goal,
                    metadata={"source": "meta_reflection", "confidence": MISSING_KNOWLEDGE_CONFIDENCE},
                )
                # 手动设置低置信度
                node = self._graph.list_nodes(layer=TopologyLayer.L1_GOAL, node_type=NodeType.GOAL)[-1]
                node.confidence = MISSING_KNOWLEDGE_CONFIDENCE
                added += 1
        return added

    def _llm_fill_gaps(self, traces: list[TraceRecord]) -> int:
        """LLM 补充(实际部署时使用)。"""
        # 简化实现: 复用规则式
        return self._rule_based_fill_gaps(traces)

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    def _find_node_by_name(
        self,
        name: str,
        layer: TopologyLayer,
        node_type: NodeType,
    ) -> Optional[Any]:
        """按名称查找节点。"""
        nodes = self._graph.list_nodes(layer=layer, node_type=node_type)
        for node in nodes:
            if node.name == name:
                return node
        return None
