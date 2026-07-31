"""
知识拓扑图 (KTG) 内存数据结构。

基于邻接表实现的拓扑图,支持:
    - 节点/边的增删查改(删除为软删除,标记 deprecated)
    - 按层级/类型查询节点
    - 邻接边查询(出边/入边)
    - 快照导出(用于持久化与回滚)

设计原则:
    - 节点与边分离存储(避免循环引用)
    - 邻接表维护正向/反向索引,支持高效查询
    - 所有写操作通过 schema 校验,确保不违反固化规则
    - 软删除:deprecated 节点/边不物理移除,权重降至 0.01
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict

from fnixagent.core.exceptions import (
    TopologyEdgeNotFoundError,
    TopologyNodeNotFoundError,
    TopologyValidationError,
)
from fnixagent.core.topology import schema as schema_mod
from fnixagent.core.topology import weights as weights_mod
from fnixagent.core.types import EdgeType, NodeType, TopologyEdge, TopologyLayer, TopologyNode


class TopologyGraph:
    """知识拓扑图内存结构。

    内部维护:
        _nodes: dict[node_id, TopologyNode]       节点表
        _edges: dict[edge_id, TopologyEdge]       边表
        _out_edges: dict[node_id, list[edge_id]]  正向邻接(出边)
        _in_edges: dict[node_id, list[edge_id]]   反向邻接(入边)
    """

    def __init__(self) -> None:
        """初始化空拓扑图。"""
        self._nodes: dict[str, TopologyNode] = {}
        self._edges: dict[str, TopologyEdge] = {}
        self._out_edges: defaultdict[str, list[str]] = defaultdict(list)
        self._in_edges: defaultdict[str, list[str]] = defaultdict(list)

    # -----------------------------------------------------------------------
    # 节点操作
    # -----------------------------------------------------------------------

    def add_node(
        self,
        layer: TopologyLayer,
        node_type: NodeType,
        name: str,
        content: str = "",
        skill_binding: str | None = None,
        metadata: dict | None = None,
        node_id: str | None = None,
    ) -> TopologyNode:
        """新增节点(永远 INSERT,不 UPDATE 已有节点)。

        若 node_id 已存在,抛出 TopologyValidationError(避免覆盖)。
        新节点初始权重 INITIAL_WEIGHT=0.5,置信度 CONFIDENCE_INIT=0.3。
        """
        if node_id is None:
            # 自动生成 ID: 层级前缀 + 短 UUID
            node_id = f"{layer.value}:{uuid.uuid4().hex[:12]}"
        if node_id in self._nodes:
            raise TopologyValidationError(f"节点 {node_id} 已存在(只增不删不覆盖,请使用新 ID)")
        node = TopologyNode(
            node_id=node_id,
            layer=layer,
            node_type=node_type,
            name=name,
            content=content,
            weight=weights_mod.INITIAL_WEIGHT,
            confidence=weights_mod.CONFIDENCE_INIT,
            use_count=0,
            freshness=1.0,
            deprecated=False,
            version=1,
            metadata=metadata or {},
            skill_binding=skill_binding,
            created_at=time.time(),
            last_used_at=0.0,
        )
        schema_mod.validate_node(node)
        self._nodes[node_id] = node
        return node

    def get_node(self, node_id: str) -> TopologyNode:
        """获取节点(不存在则抛 TopologyNodeNotFoundError)。"""
        node = self._nodes.get(node_id)
        if node is None:
            raise TopologyNodeNotFoundError(f"节点不存在: {node_id}")
        return node

    def has_node(self, node_id: str) -> bool:
        """判断节点是否存在。"""
        return node_id in self._nodes

    def list_nodes(
        self,
        layer: TopologyLayer | None = None,
        node_type: NodeType | None = None,
        include_deprecated: bool = False,
    ) -> list[TopologyNode]:
        """按层级/类型列举节点。"""
        result = []
        for node in self._nodes.values():
            if not include_deprecated and node.deprecated:
                continue
            if layer is not None and node.layer != layer:
                continue
            if node_type is not None and node.node_type != node_type:
                continue
            result.append(node)
        return result

    def deprecate_node(self, node_id: str) -> TopologyNode:
        """软删除节点(标记 deprecated,权重降至 DEPRECATED_WEIGHT)。"""
        node = self.get_node(node_id)
        node.deprecated = True
        node.weight = weights_mod.DEPRECATED_WEIGHT
        return node

    # -----------------------------------------------------------------------
    # 边操作
    # -----------------------------------------------------------------------

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        weight: float | None = None,
        metadata: dict | None = None,
        edge_id: str | None = None,
    ) -> TopologyEdge:
        """新增边(永远 INSERT,同源同目标可新增平行边,不覆盖旧边)。

        新边默认权重:
            - MUTEX: -1.0(固定)
            - CONTAINS: 1.0(固定)
            - 其他: INITIAL_WEIGHT=0.5
        """
        source = self.get_node(source_id)  # 自动校验存在性
        target = self.get_node(target_id)

        if edge_id is None:
            edge_id = f"e:{uuid.uuid4().hex[:12]}"

        # 确定权重
        if edge_type in schema_mod.FIXED_WEIGHT_EDGES:
            weight = schema_mod.FIXED_WEIGHT_EDGES[edge_type]
        elif weight is None:
            weight = weights_mod.INITIAL_WEIGHT
        else:
            weight = weights_mod.clamp_weight(weight)

        edge = TopologyEdge(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            version=1,
            deprecated=False,
            metadata=metadata or {},
            created_at=time.time(),
        )
        schema_mod.validate_edge(edge, source, target)
        self._edges[edge_id] = edge
        self._out_edges[source_id].append(edge_id)
        self._in_edges[target_id].append(edge_id)
        return edge

    def get_edge(self, edge_id: str) -> TopologyEdge:
        """获取边。"""
        edge = self._edges.get(edge_id)
        if edge is None:
            raise TopologyEdgeNotFoundError(f"边不存在: {edge_id}")
        return edge

    def get_out_edges(self, node_id: str, edge_type: EdgeType | None = None) -> list[TopologyEdge]:
        """获取节点的出边(可选按类型过滤)。"""
        edge_ids = self._out_edges.get(node_id, [])
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]
        if edge_type is not None:
            edges = [e for e in edges if e.edge_type == edge_type]
        return edges

    def get_in_edges(self, node_id: str, edge_type: EdgeType | None = None) -> list[TopologyEdge]:
        """获取节点的入边。"""
        edge_ids = self._in_edges.get(node_id, [])
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]
        if edge_type is not None:
            edges = [e for e in edges if e.edge_type == edge_type]
        return edges

    def list_edges(
        self,
        edge_type: EdgeType | None = None,
        include_deprecated: bool = False,
    ) -> list[TopologyEdge]:
        """列举边。"""
        result = []
        for edge in self._edges.values():
            if not include_deprecated and edge.deprecated:
                continue
            if edge_type is not None and edge.edge_type != edge_type:
                continue
            result.append(edge)
        return result

    def deprecate_edge(self, edge_id: str) -> TopologyEdge:
        """软删除边。"""
        edge = self.get_edge(edge_id)
        edge.deprecated = True
        return edge

    # -----------------------------------------------------------------------
    # 权重更新(由飞轮/STP 反馈触发)
    # -----------------------------------------------------------------------

    def reinforce_node(self, node_id: str) -> TopologyNode:
        """节点命中强化(飞轮 ② 调用)。"""
        node = self.get_node(node_id)
        return weights_mod.node_on_hit(node)

    def reinforce_edge(self, edge_id: str) -> TopologyEdge:
        """边命中强化。"""
        edge = self.get_edge(edge_id)
        return weights_mod.edge_on_path_hit(edge)

    def penalize_edge(self, edge_id: str) -> TopologyEdge:
        """边失败惩罚。"""
        edge = self.get_edge(edge_id)
        return weights_mod.edge_on_failure(edge)

    def apply_daily_decay(self) -> int:
        """全局每日衰减(飞轮 ④ 调用)。

        Returns:
            被标记废弃的节点/边总数
        """
        deprecated_count = 0
        for node in self._nodes.values():
            weights_mod.node_daily_decay(node)
            if node.deprecated:
                deprecated_count += 1
        for edge in self._edges.values():
            weights_mod.edge_daily_decay(edge)
            if edge.deprecated:
                deprecated_count += 1
        return deprecated_count

    # -----------------------------------------------------------------------
    # 快照与统计
    # -----------------------------------------------------------------------

    def snapshot(self) -> dict:
        """导出完整快照(用于持久化与回滚)。"""
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "layer": n.layer.value,
                    "node_type": n.node_type.value,
                    "name": n.name,
                    "content": n.content,
                    "weight": n.weight,
                    "confidence": n.confidence,
                    "use_count": n.use_count,
                    "freshness": n.freshness,
                    "deprecated": n.deprecated,
                    "version": n.version,
                    "metadata": n.metadata,
                    "skill_binding": n.skill_binding,
                    "created_at": n.created_at,
                    "last_used_at": n.last_used_at,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "edge_id": e.edge_id,
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type.value,
                    "weight": e.weight,
                    "version": e.version,
                    "deprecated": e.deprecated,
                    "metadata": e.metadata,
                    "created_at": e.created_at,
                }
                for e in self._edges.values()
            ],
        }

    def restore(self, snapshot: dict) -> None:
        """从快照恢复(清空当前图,加载快照数据)。"""
        self._nodes.clear()
        self._edges.clear()
        self._out_edges.clear()
        self._in_edges.clear()
        for n_data in snapshot.get("nodes", []):
            node = TopologyNode(
                node_id=n_data["node_id"],
                layer=TopologyLayer(n_data["layer"]),
                node_type=NodeType(n_data["node_type"]),
                name=n_data["name"],
                content=n_data.get("content", ""),
                weight=n_data["weight"],
                confidence=n_data["confidence"],
                use_count=n_data["use_count"],
                freshness=n_data["freshness"],
                deprecated=n_data["deprecated"],
                version=n_data["version"],
                metadata=n_data.get("metadata", {}),
                skill_binding=n_data.get("skill_binding"),
                created_at=n_data.get("created_at", 0.0),
                last_used_at=n_data.get("last_used_at", 0.0),
            )
            self._nodes[node.node_id] = node
        for e_data in snapshot.get("edges", []):
            edge = TopologyEdge(
                edge_id=e_data["edge_id"],
                source_id=e_data["source_id"],
                target_id=e_data["target_id"],
                edge_type=EdgeType(e_data["edge_type"]),
                weight=e_data["weight"],
                version=e_data["version"],
                deprecated=e_data["deprecated"],
                metadata=e_data.get("metadata", {}),
                created_at=e_data.get("created_at", 0.0),
            )
            self._edges[edge.edge_id] = edge
            self._out_edges[edge.source_id].append(edge.edge_id)
            self._in_edges[edge.target_id].append(edge.edge_id)

    def stats(self) -> dict:
        """返回图统计信息。"""
        active_nodes = sum(1 for n in self._nodes.values() if not n.deprecated)
        active_edges = sum(1 for e in self._edges.values() if not e.deprecated)
        return {
            "total_nodes": len(self._nodes),
            "active_nodes": active_nodes,
            "deprecated_nodes": len(self._nodes) - active_nodes,
            "total_edges": len(self._edges),
            "active_edges": active_edges,
            "deprecated_edges": len(self._edges) - active_edges,
        }
