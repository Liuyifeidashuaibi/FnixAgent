"""
知识拓扑图 (KTG) 内存数据结构单元测试。

测试模块: fnixagent.core.topology.graph.TopologyGraph
覆盖:
    - 节点操作: add_node, get_node, has_node, list_nodes, deprecate_node
    - 边操作: add_edge, get_edge, get_out_edges, get_in_edges, list_edges, deprecate_edge
    - 权重更新: reinforce_node, reinforce_edge, penalize_edge, apply_daily_decay
    - 快照与统计: snapshot, restore, stats
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest

from fnixagent.core.exceptions import (
    TopologyEdgeNotFoundError,
    TopologyLayerViolationError,
    TopologyNodeNotFoundError,
    TopologyValidationError,
)
from fnixagent.core.topology import weights as weights_mod
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    EdgeType,
    NodeType,
    TopologyLayer,
)

# ---------------------------------------------------------------------------
# 节点操作
# ---------------------------------------------------------------------------


class TestAddNode:
    """测试 add_node() 方法。"""

    def test_add_node_with_auto_id(self, empty_graph):
        """自动生成 ID 应以层级前缀开头。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
        )
        assert node.node_id.startswith("L1:")
        assert empty_graph.has_node(node.node_id)

    def test_add_node_with_custom_id(self, empty_graph):
        """使用自定义 ID 添加节点。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="概念",
            node_id="L2:custom",
        )
        assert node.node_id == "L2:custom"

    def test_add_node_duplicate_id(self, empty_graph):
        """重复 ID 应抛 TopologyValidationError。"""
        empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标1",
            node_id="L1:dup",
        )
        with pytest.raises(TopologyValidationError, match="已存在"):
            empty_graph.add_node(
                layer=TopologyLayer.L1_GOAL,
                node_type=NodeType.GOAL,
                name="目标2",
                node_id="L1:dup",
            )

    def test_add_node_initial_weight(self, empty_graph):
        """新节点初始权重应为 INITIAL_WEIGHT=0.5。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
        )
        assert node.weight == weights_mod.INITIAL_WEIGHT

    def test_add_node_initial_confidence(self, empty_graph):
        """新节点初始置信度应为 CONFIDENCE_INIT=0.3。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
        )
        assert node.confidence == weights_mod.CONFIDENCE_INIT

    def test_add_node_with_skill_binding_l2(self, empty_graph):
        """L2 CONCEPT 节点可绑定技能。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="概念",
            skill_binding="my_skill",
        )
        assert node.skill_binding == "my_skill"

    def test_add_node_skill_binding_on_non_l2(self, empty_graph):
        """非 L2 节点绑定技能应抛 TopologyValidationError。"""
        with pytest.raises(TopologyValidationError):
            empty_graph.add_node(
                layer=TopologyLayer.L1_GOAL,
                node_type=NodeType.GOAL,
                name="目标",
                skill_binding="should_fail",
            )

    def test_add_node_wrong_layer_type_combo(self, empty_graph):
        """节点类型与层级不匹配应抛 TopologyValidationError。"""
        with pytest.raises(TopologyValidationError):
            empty_graph.add_node(
                layer=TopologyLayer.L1_GOAL,
                node_type=NodeType.CONCEPT,
                name="错误",
            )

    def test_add_node_with_metadata(self, empty_graph):
        """添加节点时应存储 metadata。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            metadata={"source": "test", "priority": 1},
        )
        assert node.metadata == {"source": "test", "priority": 1}

    def test_add_node_with_content(self, empty_graph):
        """添加节点时应存储 content。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.RULE,
            name="规则",
            content="这是一条规则",
        )
        assert node.content == "这是一条规则"

    def test_add_node_initial_fields(self, empty_graph):
        """新节点的初始字段值应正确。"""
        node = empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
        )
        assert node.use_count == 0
        assert node.freshness == 1.0
        assert node.deprecated is False
        assert node.version == 1
        assert node.created_at > 0.0
        assert node.last_used_at == 0.0


class TestGetNode:
    """测试 get_node() 方法。"""

    def test_get_existing_node(self, empty_graph):
        """获取已存在的节点。"""
        empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            node_id="L1:g1",
        )
        node = empty_graph.get_node("L1:g1")
        assert node.name == "目标"

    def test_get_nonexistent_node(self, empty_graph):
        """获取不存在的节点应抛 TopologyNodeNotFoundError。"""
        with pytest.raises(TopologyNodeNotFoundError, match="节点不存在"):
            empty_graph.get_node("L1:nonexistent")


class TestHasNode:
    """测试 has_node() 方法。"""

    def test_has_existing_node(self, empty_graph):
        """已存在的节点应返回 True。"""
        empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            node_id="L1:g1",
        )
        assert empty_graph.has_node("L1:g1") is True

    def test_has_nonexistent_node(self, empty_graph):
        """不存在的节点应返回 False。"""
        assert empty_graph.has_node("L1:nonexistent") is False


class TestListNodes:
    """测试 list_nodes() 方法。"""

    def test_list_all_nodes(self, sample_graph):
        """列举全部节点(不含废弃)。"""
        nodes = sample_graph.list_nodes()
        assert len(nodes) == 4

    def test_list_by_layer(self, sample_graph):
        """按层级列举节点。"""
        l1_nodes = sample_graph.list_nodes(layer=TopologyLayer.L1_GOAL)
        assert len(l1_nodes) == 1
        assert l1_nodes[0].node_type == NodeType.GOAL

        l3_nodes = sample_graph.list_nodes(layer=TopologyLayer.L3_RULE)
        assert len(l3_nodes) == 1

    def test_list_by_type(self, sample_graph):
        """按节点类型列举。"""
        concepts = sample_graph.list_nodes(node_type=NodeType.CONCEPT)
        assert len(concepts) == 1
        assert concepts[0].layer == TopologyLayer.L2_CONCEPT

    def test_list_by_layer_and_type(self, sample_graph):
        """同时按层级和类型列举。"""
        nodes = sample_graph.list_nodes(layer=TopologyLayer.L4_FACT, node_type=NodeType.FACT)
        assert len(nodes) == 1

    def test_list_exclude_deprecated(self, sample_graph):
        """默认不包含废弃节点。"""
        sample_graph.deprecate_node("L4:fact1")
        nodes = sample_graph.list_nodes()
        assert len(nodes) == 3
        assert all(not n.deprecated for n in nodes)

    def test_list_include_deprecated(self, sample_graph):
        """include_deprecated=True 应包含废弃节点。"""
        sample_graph.deprecate_node("L4:fact1")
        nodes = sample_graph.list_nodes(include_deprecated=True)
        assert len(nodes) == 4

    def test_list_empty_graph(self, empty_graph):
        """空图列举应返回空列表。"""
        assert empty_graph.list_nodes() == []


class TestDeprecateNode:
    """测试 deprecate_node() 方法。"""

    def test_deprecate_sets_flag(self, sample_graph):
        """废弃节点应设置 deprecated=True。"""
        node = sample_graph.deprecate_node("L1:goal1")
        assert node.deprecated is True

    def test_deprecate_sets_weight(self, sample_graph):
        """废弃节点权重应降至 DEPRECATED_WEIGHT。"""
        sample_graph.deprecate_node("L1:goal1")
        node = sample_graph.get_node("L1:goal1")
        assert node.weight == weights_mod.DEPRECATED_WEIGHT

    def test_deprecate_nonexistent(self, empty_graph):
        """废弃不存在的节点应抛 TopologyNodeNotFoundError。"""
        with pytest.raises(TopologyNodeNotFoundError):
            empty_graph.deprecate_node("L1:nonexistent")


# ---------------------------------------------------------------------------
# 边操作
# ---------------------------------------------------------------------------


class TestAddEdge:
    """测试 add_edge() 方法。"""

    def test_add_edge_with_auto_id(self, empty_graph):
        """自动生成边 ID 应以 'e:' 开头。"""
        empty_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="g",
            node_id="L1:g1",
        )
        empty_graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="c",
            node_id="L2:c1",
        )
        edge = empty_graph.add_edge("L1:g1", "L2:c1", EdgeType.CAUSAL)
        assert edge.edge_id.startswith("e:")

    def test_add_edge_with_custom_id(self, sample_graph):
        """使用自定义 ID 添加边。"""
        edge = sample_graph.add_edge(
            "L1:goal1", "L2:concept1", EdgeType.DERIVES, edge_id="e:custom"
        )
        assert edge.edge_id == "e:custom"

    def test_add_edge_default_weight_variable(self, sample_graph):
        """可变权重边默认权重为 INITIAL_WEIGHT=0.5。"""
        edge = sample_graph.add_edge("L1:goal1", "L2:concept1", EdgeType.CAUSAL, edge_id="e:def")
        assert edge.weight == weights_mod.INITIAL_WEIGHT

    def test_add_edge_custom_weight_variable(self, sample_graph):
        """可变权重边可指定自定义权重(会被钳制)。"""
        edge = sample_graph.add_edge(
            "L1:goal1", "L2:concept1", EdgeType.CAUSAL, weight=0.8, edge_id="e:cw"
        )
        assert edge.weight == 0.8

    def test_add_edge_weight_clamped(self, sample_graph):
        """可变权重边权重超出范围应被钳制。"""
        edge = sample_graph.add_edge(
            "L1:goal1", "L2:concept1", EdgeType.CAUSAL, weight=1.5, edge_id="e:cl"
        )
        assert edge.weight == 1.0

    def test_add_mutex_edge_fixed_weight(self, sample_graph):
        """MUTEX 边权重固定为 -1.0。"""
        edge = sample_graph.add_edge("L3:rule1", "L3:rule1", EdgeType.MUTEX, edge_id="e:mx")
        # 注意: 自环也允许(MUTEX 不要求相邻层)
        assert edge.weight == -1.0

    def test_add_contains_edge_fixed_weight(self, sample_graph):
        """CONTAINS 边权重固定为 1.0。"""
        edge = sample_graph.get_edge("e1")  # sample_graph 中的 e1 是 CONTAINS
        assert edge.weight == 1.0

    def test_add_edge_source_not_found(self, empty_graph):
        """源节点不存在应抛 TopologyNodeNotFoundError。"""
        with pytest.raises(TopologyNodeNotFoundError):
            empty_graph.add_edge("L1:none", "L2:none", EdgeType.CAUSAL)

    def test_add_edge_target_not_found(self, sample_graph):
        """目标节点不存在应抛 TopologyNodeNotFoundError。"""
        with pytest.raises(TopologyNodeNotFoundError):
            sample_graph.add_edge("L1:goal1", "L4:nonexistent", EdgeType.CAUSAL)

    def test_add_contains_non_adjacent(self, sample_graph):
        """CONTAINS 边跨非相邻层应抛 TopologyLayerViolationError。"""
        with pytest.raises(TopologyLayerViolationError):
            sample_graph.add_edge("L1:goal1", "L3:rule1", EdgeType.CONTAINS, edge_id="e:bad")

    def test_add_parallel_edges(self, sample_graph):
        """同源同目标可新增平行边(不同 edge_id)。"""
        initial_count = len(sample_graph.list_edges())
        sample_graph.add_edge("L1:goal1", "L2:concept1", EdgeType.CAUSAL, edge_id="e:parallel1")
        sample_graph.add_edge("L1:goal1", "L2:concept1", EdgeType.CAUSAL, edge_id="e:parallel2")
        assert len(sample_graph.list_edges()) == initial_count + 2

    def test_add_edge_with_metadata(self, sample_graph):
        """添加边时应存储 metadata。"""
        edge = sample_graph.add_edge(
            "L1:goal1",
            "L2:concept1",
            EdgeType.CAUSAL,
            metadata={"reason": "test"},
            edge_id="e:meta",
        )
        assert edge.metadata == {"reason": "test"}


class TestGetEdge:
    """测试 get_edge() 方法。"""

    def test_get_existing_edge(self, sample_graph):
        """获取已存在的边。"""
        edge = sample_graph.get_edge("e1")
        assert edge.edge_type == EdgeType.CONTAINS

    def test_get_nonexistent_edge(self, empty_graph):
        """获取不存在的边应抛 TopologyEdgeNotFoundError。"""
        with pytest.raises(TopologyEdgeNotFoundError, match="边不存在"):
            empty_graph.get_edge("e:nonexistent")


class TestGetOutEdges:
    """测试 get_out_edges() 方法。"""

    def test_get_all_out_edges(self, sample_graph):
        """获取节点的全部出边。"""
        out_edges = sample_graph.get_out_edges("L2:concept1")
        # e2 (CONTAINS) + e4 (DEPENDS_ON) = 2
        assert len(out_edges) == 2

    def test_get_out_edges_by_type(self, sample_graph):
        """按类型过滤出边。"""
        contains_edges = sample_graph.get_out_edges("L2:concept1", edge_type=EdgeType.CONTAINS)
        assert len(contains_edges) == 1
        assert contains_edges[0].edge_type == EdgeType.CONTAINS

    def test_get_out_edges_no_edges(self, sample_graph):
        """无出边的节点应返回空列表。"""
        out_edges = sample_graph.get_out_edges("L4:fact1")
        assert out_edges == []

    def test_get_out_edges_nonexistent_node(self, sample_graph):
        """不存在节点的出边应返回空列表。"""
        assert sample_graph.get_out_edges("L1:nonexistent") == []


class TestGetInEdges:
    """测试 get_in_edges() 方法。"""

    def test_get_all_in_edges(self, sample_graph):
        """获取节点的全部入边。"""
        in_edges = sample_graph.get_in_edges("L3:rule1")
        # e2 (CONTAINS from L2) + e4 (DEPENDS_ON from L2) = 2
        assert len(in_edges) == 2

    def test_get_in_edges_by_type(self, sample_graph):
        """按类型过滤入边。"""
        contains_edges = sample_graph.get_in_edges("L3:rule1", edge_type=EdgeType.CONTAINS)
        assert len(contains_edges) == 1

    def test_get_in_edges_no_edges(self, sample_graph):
        """无入边的节点应返回空列表。"""
        assert sample_graph.get_in_edges("L1:goal1") == []


class TestListEdges:
    """测试 list_edges() 方法。"""

    def test_list_all_edges(self, sample_graph):
        """列举全部边。"""
        edges = sample_graph.list_edges()
        assert len(edges) == 5  # e1~e5

    def test_list_by_type(self, sample_graph):
        """按类型列举边。"""
        contains_edges = sample_graph.list_edges(edge_type=EdgeType.CONTAINS)
        assert len(contains_edges) == 3  # e1, e2, e3

    def test_list_exclude_deprecated(self, sample_graph):
        """默认不包含废弃边。"""
        sample_graph.deprecate_edge("e1")
        edges = sample_graph.list_edges()
        assert len(edges) == 4

    def test_list_include_deprecated(self, sample_graph):
        """include_deprecated=True 应包含废弃边。"""
        sample_graph.deprecate_edge("e1")
        edges = sample_graph.list_edges(include_deprecated=True)
        assert len(edges) == 5

    def test_list_empty_graph(self, empty_graph):
        """空图列举应返回空列表。"""
        assert empty_graph.list_edges() == []


class TestDeprecateEdge:
    """测试 deprecate_edge() 方法。"""

    def test_deprecate_sets_flag(self, sample_graph):
        """废弃边应设置 deprecated=True。"""
        edge = sample_graph.deprecate_edge("e1")
        assert edge.deprecated is True

    def test_deprecate_nonexistent(self, empty_graph):
        """废弃不存在的边应抛 TopologyEdgeNotFoundError。"""
        with pytest.raises(TopologyEdgeNotFoundError):
            empty_graph.deprecate_edge("e:nonexistent")


# ---------------------------------------------------------------------------
# 权重更新
# ---------------------------------------------------------------------------


class TestReinforceNode:
    """测试 reinforce_node() 方法。"""

    def test_weight_increases(self, sample_graph):
        """强化节点后权重应增加。"""
        node = sample_graph.reinforce_node("L1:goal1")
        original = weights_mod.INITIAL_WEIGHT
        assert node.weight == pytest.approx(original + weights_mod.SINGLE_INCREMENT)

    def test_use_count_increases(self, sample_graph):
        """强化节点后 use_count 应 +1。"""
        sample_graph.reinforce_node("L1:goal1")
        node = sample_graph.get_node("L1:goal1")
        assert node.use_count == 1

    def test_nonexistent_node(self, empty_graph):
        """强化不存在的节点应抛 TopologyNodeNotFoundError。"""
        with pytest.raises(TopologyNodeNotFoundError):
            empty_graph.reinforce_node("L1:none")


class TestReinforceEdge:
    """测试 reinforce_edge() 方法。"""

    def test_weight_increases(self, sample_graph):
        """强化边后权重应增加(可变权重边)。"""
        original = sample_graph.get_edge("e4").weight  # DEPENDS_ON, 0.6
        sample_graph.reinforce_edge("e4")
        edge = sample_graph.get_edge("e4")
        assert edge.weight == pytest.approx(original + weights_mod.SINGLE_INCREMENT)

    def test_contains_not_reinforced(self, sample_graph):
        """CONTAINS 边强化后权重不变。"""
        sample_graph.reinforce_edge("e1")  # CONTAINS
        assert sample_graph.get_edge("e1").weight == 1.0

    def test_nonexistent_edge(self, empty_graph):
        """强化不存在的边应抛 TopologyEdgeNotFoundError。"""
        with pytest.raises(TopologyEdgeNotFoundError):
            empty_graph.reinforce_edge("e:none")


class TestPenalizeEdge:
    """测试 penalize_edge() 方法。"""

    def test_weight_decreases(self, sample_graph):
        """惩罚边后权重应减少(可变权重边)。"""
        original = sample_graph.get_edge("e4").weight  # 0.6
        sample_graph.penalize_edge("e4")
        edge = sample_graph.get_edge("e4")
        assert edge.weight == pytest.approx(original - 0.03)

    def test_contains_not_penalized(self, sample_graph):
        """CONTAINS 边惩罚后权重不变。"""
        sample_graph.penalize_edge("e1")
        assert sample_graph.get_edge("e1").weight == 1.0

    def test_nonexistent_edge(self, empty_graph):
        """惩罚不存在的边应抛 TopologyEdgeNotFoundError。"""
        with pytest.raises(TopologyEdgeNotFoundError):
            empty_graph.penalize_edge("e:none")


class TestApplyDailyDecay:
    """测试 apply_daily_decay() 方法。"""

    def test_returns_deprecated_count(self, sample_graph):
        """apply_daily_decay 应返回被标记废弃的节点/边总数。"""
        count = sample_graph.apply_daily_decay()
        # 权重 0.5 衰减后仍 > 0.05,不应有废弃
        assert isinstance(count, int)

    def test_freshness_decays(self, sample_graph):
        """每日衰减后节点 freshness 应降低。"""
        node = sample_graph.get_node("L1:goal1")
        original_freshness = node.freshness
        sample_graph.apply_daily_decay()
        assert node.freshness < original_freshness

    def test_edge_weight_decays(self, sample_graph):
        """每日衰减后可变权重边权重应降低。"""
        original = sample_graph.get_edge("e4").weight  # 0.6
        sample_graph.apply_daily_decay()
        edge = sample_graph.get_edge("e4")
        assert edge.weight < original

    def test_low_weight_node_deprecated(self, sample_graph):
        """权重低于阈值的节点在衰减后应被标记废弃。"""
        node = sample_graph.get_node("L1:goal1")
        node.weight = 0.04  # 低于 DEPRECATE_THRESHOLD
        node.freshness = 1.0
        node.use_count = 10
        sample_graph.apply_daily_decay()
        assert node.deprecated is True
        assert node.weight == weights_mod.DEPRECATED_WEIGHT

    def test_contains_edge_not_decayed(self, sample_graph):
        """CONTAINS 边在每日衰减后权重不变。"""
        sample_graph.apply_daily_decay()
        assert sample_graph.get_edge("e1").weight == 1.0


# ---------------------------------------------------------------------------
# 快照与统计
# ---------------------------------------------------------------------------


class TestSnapshot:
    """测试 snapshot() 方法。"""

    def test_snapshot_structure(self, sample_graph):
        """快照应包含 nodes 和 edges 两个列表。"""
        snap = sample_graph.snapshot()
        assert "nodes" in snap
        assert "edges" in snap
        assert isinstance(snap["nodes"], list)
        assert isinstance(snap["edges"], list)

    def test_snapshot_node_count(self, sample_graph):
        """快照节点数应与图中一致。"""
        snap = sample_graph.snapshot()
        assert len(snap["nodes"]) == 4

    def test_snapshot_edge_count(self, sample_graph):
        """快照边数应与图中一致。"""
        snap = sample_graph.snapshot()
        assert len(snap["edges"]) == 5

    def test_snapshot_node_fields(self, sample_graph):
        """快照节点应包含完整字段。"""
        snap = sample_graph.snapshot()
        node_data = snap["nodes"][0]
        required_fields = {
            "node_id",
            "layer",
            "node_type",
            "name",
            "content",
            "weight",
            "confidence",
            "use_count",
            "freshness",
            "deprecated",
            "version",
            "metadata",
            "skill_binding",
            "created_at",
            "last_used_at",
        }
        assert required_fields.issubset(set(node_data.keys()))

    def test_snapshot_edge_fields(self, sample_graph):
        """快照边应包含完整字段。"""
        snap = sample_graph.snapshot()
        edge_data = snap["edges"][0]
        required_fields = {
            "edge_id",
            "source_id",
            "target_id",
            "edge_type",
            "weight",
            "version",
            "deprecated",
            "metadata",
            "created_at",
        }
        assert required_fields.issubset(set(edge_data.keys()))


class TestRestore:
    """测试 restore() 方法。"""

    def test_restore_round_trip(self, sample_graph):
        """快照恢复后图应与原有一致。"""
        snap = sample_graph.snapshot()
        new_graph = TopologyGraph()
        new_graph.restore(snap)
        assert len(new_graph.list_nodes(include_deprecated=True)) == 4
        assert len(new_graph.list_edges(include_deprecated=True)) == 5

    def test_restore_preserves_node_ids(self, sample_graph):
        """恢复后节点 ID 应保持一致。"""
        snap = sample_graph.snapshot()
        new_graph = TopologyGraph()
        new_graph.restore(snap)
        assert new_graph.has_node("L1:goal1")
        assert new_graph.has_node("L2:concept1")
        assert new_graph.has_node("L3:rule1")
        assert new_graph.has_node("L4:fact1")

    def test_restore_preserves_edge_weights(self, sample_graph):
        """恢复后边权重应保持一致。"""
        snap = sample_graph.snapshot()
        new_graph = TopologyGraph()
        new_graph.restore(snap)
        assert new_graph.get_edge("e4").weight == 0.6
        assert new_graph.get_edge("e1").weight == 1.0

    def test_restore_clears_existing(self, sample_graph):
        """恢复应先清空当前图。"""
        snap = sample_graph.snapshot()
        new_graph = TopologyGraph()
        new_graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="临时",
            node_id="L1:temp",
        )
        new_graph.restore(snap)
        assert not new_graph.has_node("L1:temp")

    def test_restore_preserves_adjacency(self, sample_graph):
        """恢复后邻接关系应保持一致。"""
        snap = sample_graph.snapshot()
        new_graph = TopologyGraph()
        new_graph.restore(snap)
        out_edges = new_graph.get_out_edges("L2:concept1")
        assert len(out_edges) == 2

    def test_restore_empty_snapshot(self, empty_graph):
        """恢复空快照应清空图。"""
        empty_graph.restore({"nodes": [], "edges": []})
        assert empty_graph.list_nodes(include_deprecated=True) == []
        assert empty_graph.list_edges(include_deprecated=True) == []


class TestStats:
    """测试 stats() 方法。"""

    def test_stats_initial(self, empty_graph):
        """空图统计应全为 0。"""
        stats = empty_graph.stats()
        assert stats["total_nodes"] == 0
        assert stats["active_nodes"] == 0
        assert stats["deprecated_nodes"] == 0
        assert stats["total_edges"] == 0
        assert stats["active_edges"] == 0
        assert stats["deprecated_edges"] == 0

    def test_stats_sample_graph(self, sample_graph):
        """示例图统计应正确。"""
        stats = sample_graph.stats()
        assert stats["total_nodes"] == 4
        assert stats["active_nodes"] == 4
        assert stats["deprecated_nodes"] == 0
        assert stats["total_edges"] == 5
        assert stats["active_edges"] == 5
        assert stats["deprecated_edges"] == 0

    def test_stats_with_deprecated(self, sample_graph):
        """废弃节点/边后统计应正确。"""
        sample_graph.deprecate_node("L1:goal1")
        sample_graph.deprecate_edge("e1")
        stats = sample_graph.stats()
        assert stats["deprecated_nodes"] == 1
        assert stats["active_nodes"] == 3
        assert stats["deprecated_edges"] == 1
        assert stats["active_edges"] == 4

    def test_stats_keys(self, sample_graph):
        """stats 应包含全部 6 个统计键。"""
        stats = sample_graph.stats()
        expected_keys = {
            "total_nodes",
            "active_nodes",
            "deprecated_nodes",
            "total_edges",
            "active_edges",
            "deprecated_edges",
        }
        assert expected_keys.issubset(set(stats.keys()))
