"""
技能-拓扑突触协议 (STP) 绑定协议。

管理 L2 概念节点与技能(工具)的绑定关系:
    - 每个 L2 CONCEPT 节点可绑定一个技能(skill_binding 字段)
    - 一个技能可被多个 CONCEPT 节点绑定(多对一)
    - 绑定关系存储在 TopologyNode.skill_binding 字段
    - 绑定/解绑操作同步更新 ToolMetadata.topology_binding

权重→优先级换算公式(来自计划 3.2):
    技能优先级 = Σ(绑定该技能的 CONCEPT 节点权重 × 路径命中系数)
    路径命中系数:
        - 当前推理路径经过该 CONCEPT: 1.0
        - 路径未经过但同属 L2 兄弟节点: 0.3
        - 完全无关: 0.0
"""
from __future__ import annotations

from typing import Optional

from fnixagent.core.exceptions import (
    SkillBindingError,
    TopologyNodeNotFoundError,
)
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    NodeType,
    SkillLevel,
    SkillRecord,
    TopologyLayer,
    TopologyNode,
    TopologyPath,
)

# 路径命中系数(来自计划 3.2)
HIT_COEFFICIENT_ON_PATH: float = 1.0       # 路径经过该 CONCEPT
HIT_COEFFICIENT_SIBLING: float = 0.3       # 同属 L2 兄弟节点
HIT_COEFFICIENT_UNRELATED: float = 0.0     # 完全无关


class SkillBindingProtocol:
    """技能-拓扑绑定协议管理器。

    职责:
        - 绑定/解绑 L2 概念节点与技能
        - 查询绑定关系(正查/反查)
        - 根据拓扑路径换算技能优先级
    """

    def __init__(self, graph: TopologyGraph) -> None:
        """初始化绑定协议管理器。

        Args:
            graph: 拓扑图实例(绑定关系存储在节点 skill_binding 字段)
        """
        self._graph = graph

    # -----------------------------------------------------------------------
    # 绑定/解绑
    # -----------------------------------------------------------------------

    def bind(
        self,
        concept_node_id: str,
        skill_name: str,
        skill_level: SkillLevel = SkillLevel.BASIC,
    ) -> TopologyNode:
        """绑定 L2 概念节点与技能。

        Args:
            concept_node_id: L2 概念节点 ID
            skill_name: 技能名(与 ToolMetadata.name 对应)
            skill_level: 技能权限级别

        Returns:
            更新后的概念节点

        Raises:
            SkillBindingError: 节点不存在/非 L2 概念节点/已绑定其他技能/参数非法
        """
        # 参数校验:concept_node_id 与 skill_name 必须非空
        if not concept_node_id or not isinstance(concept_node_id, str):
            raise SkillBindingError("concept_node_id must be a non-empty string")
        if not skill_name or not isinstance(skill_name, str):
            raise SkillBindingError("skill_name must be a non-empty string")
        try:
            node = self._graph.get_node(concept_node_id)
        except TopologyNodeNotFoundError:
            raise SkillBindingError(f"概念节点不存在: {concept_node_id}")

        if node.layer != TopologyLayer.L2_CONCEPT or node.node_type != NodeType.CONCEPT:
            raise SkillBindingError(
                f"仅 L2 CONCEPT 节点可绑定技能,当前节点 {concept_node_id} "
                f"为 {node.layer.value}/{node.node_type.value}"
            )

        if node.skill_binding is not None and node.skill_binding != skill_name:
            raise SkillBindingError(
                f"概念节点 {concept_node_id} 已绑定技能 {node.skill_binding},"
                f"不能重复绑定到 {skill_name}"
            )

        node.skill_binding = skill_name
        # 在 metadata 中记录技能级别
        node.metadata["skill_level"] = skill_level.value
        return node

    def unbind(self, concept_node_id: str) -> TopologyNode:
        """解绑 L2 概念节点的技能。"""
        node = self._graph.get_node(concept_node_id)
        if node.skill_binding is None:
            raise SkillBindingError(f"概念节点 {concept_node_id} 未绑定任何技能")
        node.skill_binding = None
        node.metadata.pop("skill_level", None)
        return node

    # -----------------------------------------------------------------------
    # 绑定查询
    # -----------------------------------------------------------------------

    def get_bound_skill(self, concept_node_id: str) -> Optional[str]:
        """查询概念节点绑定的技能名。"""
        try:
            node = self._graph.get_node(concept_node_id)
            return node.skill_binding
        except TopologyNodeNotFoundError:
            return None

    def get_bound_concepts(self, skill_name: str) -> list[TopologyNode]:
        """反查: 绑定到指定技能的全部概念节点。"""
        concepts = self._graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
        )
        return [c for c in concepts if c.skill_binding == skill_name]

    def list_all_bindings(self) -> list[SkillRecord]:
        """列举全部技能绑定关系(返回 SkillRecord 列表)。"""
        concepts = self._graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
        )
        records = []
        for c in concepts:
            if c.skill_binding is None:
                continue
            level_str = c.metadata.get("skill_level", SkillLevel.BASIC.value)
            try:
                level = SkillLevel(level_str)
            except ValueError:
                level = SkillLevel.BASIC
            records.append(SkillRecord(
                name=c.skill_binding,
                skill_level=level,
                bound_concept_id=c.node_id,
                priority=c.weight,  # 初始优先级 = 节点权重
                success_count=c.metadata.get("success_count", 0),
                failure_count=c.metadata.get("failure_count", 0),
                last_invoked_at=c.last_used_at,
            ))
        return records

    # -----------------------------------------------------------------------
    # 优先级换算
    # -----------------------------------------------------------------------

    def compute_priority(
        self,
        skill_name: str,
        path: Optional[TopologyPath] = None,
    ) -> float:
        """根据拓扑权重换算技能调度优先级。

        公式: 优先级 = Σ(绑定该技能的 CONCEPT 节点权重 × 路径命中系数)

        Args:
            skill_name: 技能名
            path: 当前推理路径(可选,无路径时仅按权重和计算)

        Returns:
            优先级值(0~1 范围,越高越优先调度)
        """
        bound_concepts = self.get_bound_concepts(skill_name)
        if not bound_concepts:
            return 0.0

        path_node_ids = set(path.nodes) if path else set()
        path_concept_ids = {
            nid for nid in path_node_ids
            if self._graph.has_node(nid)
            and self._graph.get_node(nid).node_type == NodeType.CONCEPT
        }

        priority_sum = 0.0
        for concept in bound_concepts:
            if concept.node_id in path_concept_ids:
                coeff = HIT_COEFFICIENT_ON_PATH
            elif path is not None:
                # 路径存在但未经过此概念 → 兄弟系数
                coeff = HIT_COEFFICIENT_SIBLING
            else:
                # 无路径 → 直接用权重
                coeff = HIT_COEFFICIENT_ON_PATH
            priority_sum += concept.weight * coeff

        # 归一化到 [0, 1]
        return min(1.0, priority_sum / max(1, len(bound_concepts)))

    def compute_priorities(
        self,
        skill_names: list[str],
        path: Optional[TopologyPath] = None,
    ) -> list[tuple[str, float]]:
        """批量计算技能优先级,返回按优先级降序排列的列表。

        Returns:
            [(skill_name, priority), ...] 按优先级降序
        """
        result = [(name, self.compute_priority(name, path)) for name in skill_names]
        result.sort(key=lambda x: x[1], reverse=True)
        return result
