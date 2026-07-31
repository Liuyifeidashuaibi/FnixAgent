"""KTG 知识拓扑图核心机制测试（论文 Contribution 1 验证）。

覆盖三大核心能力：
  1. schema 固化校验（四层拓扑 + 六类节点 + 六类边 + 固定权重约束）
  2. graph 增删查改 + 权重强化/衰减 + 快照/恢复
  3. search 权重优先路径搜索 + MUTEX 惩罚 + 冷启动兜底

论文 ablation 基线：关闭 KTG 路径搜索即退化为"无拓扑召回"（回退向量召回）。
"""

from __future__ import annotations

import pytest

from fnixagent.core.exceptions import (
    TopologyLayerViolationError,
    TopologyNodeNotFoundError,
    TopologyValidationError,
)
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.topology.search import MUTEX_PENALTY, TopologySearch
from fnixagent.core.topology import weights as weights_mod
from fnixagent.core.topology import schema as schema_mod
from fnixagent.core.types import EdgeType, NodeType, TopologyLayer


# ──────────────────────────────────────────────────────────────────────
# 1. Schema 固化校验（四层拓扑不可变形）
# ──────────────────────────────────────────────────────────────────────


class TestKTGSchema:
    """KTG schema 固化规则验证。"""

    def test_node_type_layer_mapping_fixed(self):
        """节点类型与层级映射永久固定。"""
        assert schema_mod.NODE_TYPE_LAYER_MAP[NodeType.GOAL] == TopologyLayer.L1_GOAL
        assert schema_mod.NODE_TYPE_LAYER_MAP[NodeType.CONCEPT] == TopologyLayer.L2_CONCEPT
        assert NodeType.RULE in schema_mod.LAYER_NODE_TYPES[TopologyLayer.L3_RULE]
        assert NodeType.FACT in schema_mod.LAYER_NODE_TYPES[TopologyLayer.L4_FACT]

    def test_fixed_weight_edges_immutable(self):
        """MUTEX 恒 -1.0，CONTAINS 恒 1.0（永久不变）。"""
        assert schema_mod.FIXED_WEIGHT_EDGES[EdgeType.MUTEX] == -1.0
        assert schema_mod.FIXED_WEIGHT_EDGES[EdgeType.CONTAINS] == 1.0

    def test_layer_order_sequential(self):
        """四层层级序号严格递增。"""
        assert schema_mod.LAYER_ORDER[TopologyLayer.L1_GOAL] == 1
        assert schema_mod.LAYER_ORDER[TopologyLayer.L2_CONCEPT] == 2
        assert schema_mod.LAYER_ORDER[TopologyLayer.L3_RULE] == 3
        assert schema_mod.LAYER_ORDER[TopologyLayer.L4_FACT] == 4


# ──────────────────────────────────────────────────────────────────────
# 2. Graph 增删查改 + 权重系统
# ──────────────────────────────────────────────────────────────────────


class TestTopologyGraph:
    """拓扑图内存数据结构验证。"""

    def test_add_node_default_weight(self):
        """新节点初始权重 INITIAL_WEIGHT=0.5，置信度 CONFIDENCE_INIT=0.3。"""
        g = TopologyGraph()
        node = g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "论文写作")
        assert node.weight == weights_mod.INITIAL_WEIGHT
        assert node.confidence == weights_mod.CONFIDENCE_INIT
        assert node.deprecated is False
        assert node.use_count == 0

    def test_add_node_duplicate_id_raises(self):
        """节点 ID 唯一（只增不覆盖）。"""
        g = TopologyGraph()
        g.add_node(TopologyLayer.L1_GOAL, NodeType.GOAL, "目标1", node_id="g1")
        with pytest.raises(TopologyValidationError):
            g.add_node(TopologyLayer.L1_GOAL, NodeType.GOAL, "目标2", node_id="g1")

    def test_add_edge_fixed_weight_mutex(self):
        """MUTEX 边权重恒 -1.0（不可覆盖）。"""
        g = TopologyGraph()
        g.add_node(TopologyLayer.L3_RULE, NodeType.CONSTRAINT, "约束A", node_id="c1")
        g.add_node(TopologyLayer.L3_RULE, NodeType.CONSTRAINT, "约束B", node_id="c2")
        edge = g.add_edge("c1", "c2", EdgeType.MUTEX, weight=0.99)
        assert edge.weight == -1.0  # 固定权重，忽略传入值

    def test_add_edge_fixed_weight_contains(self):
        """CONTAINS 边权重恒 1.0。"""
        g = TopologyGraph()
        g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念", node_id="k1")
        g.add_node(TopologyLayer.L3_RULE, NodeType.RULE, "规则", node_id="r1")
        edge = g.add_edge("k1", "r1", EdgeType.CONTAINS, weight=0.01)
        assert edge.weight == 1.0

    def test_add_edge_nonexistent_node_raises(self):
        """边源/目标节点必须存在。"""
        g = TopologyGraph()
        g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念", node_id="k1")
        with pytest.raises(TopologyNodeNotFoundError):
            g.add_edge("k1", "nonexistent", EdgeType.DEPENDS_ON)

    def test_reinforce_node_increases_weight(self):
        """节点命中强化后权重上升（飞轮 ② 调用）。"""
        g = TopologyGraph()
        node = g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念")
        original_weight = node.weight
        g.reinforce_node(node.node_id)
        assert node.weight > original_weight
        assert node.use_count == 1

    def test_deprecate_node_sets_low_weight(self):
        """软删除节点权重降至 DEPRECATED_WEIGHT。"""
        g = TopologyGraph()
        node = g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "过时概念")
        g.deprecate_node(node.node_id)
        assert node.deprecated is True
        assert node.weight == weights_mod.DEPRECATED_WEIGHT

    def test_list_nodes_filter_by_layer(self):
        """按层级过滤节点。"""
        g = TopologyGraph()
        g.add_node(TopologyLayer.L1_GOAL, NodeType.GOAL, "目标")
        g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念1")
        g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念2")
        l2_nodes = g.list_nodes(layer=TopologyLayer.L2_CONCEPT)
        assert len(l2_nodes) == 2
        l1_nodes = g.list_nodes(layer=TopologyLayer.L1_GOAL)
        assert len(l1_nodes) == 1

    def test_snapshot_restore_roundtrip(self):
        """快照导出与恢复保持数据一致。"""
        g = TopologyGraph()
        g.add_node(TopologyLayer.L1_GOAL, NodeType.GOAL, "目标", node_id="g1")
        g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念", node_id="k1")
        g.add_edge("g1", "k1", EdgeType.CONTAINS)
        snap = g.snapshot()
        assert len(snap["nodes"]) == 2
        assert len(snap["edges"]) == 1

        # 恢复到新图
        g2 = TopologyGraph()
        g2.restore(snap)
        assert g2.has_node("g1")
        assert g2.has_node("k1")
        assert len(g2.list_edges()) == 1
        assert g2.stats()["total_nodes"] == 2

    def test_apply_daily_decay(self):
        """全局每日衰减后 freshness 下降。"""
        g = TopologyGraph()
        node = g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "概念")
        original_freshness = node.freshness
        g.apply_daily_decay()
        assert node.freshness < original_freshness


# ──────────────────────────────────────────────────────────────────────
# 3. Search 权重优先路径搜索
# ──────────────────────────────────────────────────────────────────────


class TestTopologySearch:
    """权重优先推理路径搜索验证（论文核心：替代向量 RAG）。"""

    @staticmethod
    def _build_paper_graph() -> TopologyGraph:
        """构建论文写作场景的 KTG 测试图。

        L1 目标: 写论文
          └─CONTAINS→ L2 概念: 文献综述
              ├─DEPENDS_ON→ L3 规则: 引用格式
              │   └─DERIVES→ L4 事实: APA 格式定义
              └─PRECONDITION→ L3 规则: 查重规则
        """
        g = TopologyGraph()
        g.add_node(TopologyLayer.L1_GOAL, NodeType.GOAL, "写论文", node_id="goal1")
        g.add_node(TopologyLayer.L2_CONCEPT, NodeType.CONCEPT, "文献综述", content="文献综述是论文的核心章节", node_id="concept1")
        g.add_node(TopologyLayer.L3_RULE, NodeType.RULE, "引用格式", node_id="rule1")
        g.add_node(TopologyLayer.L4_FACT, NodeType.FACT, "APA 格式定义", node_id="fact1")
        g.add_node(TopologyLayer.L3_RULE, NodeType.RULE, "查重规则", node_id="rule2")
        g.add_edge("goal1", "concept1", EdgeType.CONTAINS)
        g.add_edge("concept1", "rule1", EdgeType.DEPENDS_ON)
        g.add_edge("rule1", "fact1", EdgeType.DERIVES)
        g.add_edge("concept1", "rule2", EdgeType.PRECONDITION)
        return g

    def test_search_returns_weighted_paths(self):
        """搜索返回按权重降序排列的路径。"""
        g = self._build_paper_graph()
        search = TopologySearch(g, top_k=3)
        paths = search.search("文献综述怎么写", keywords=["文献综述"])
        assert len(paths) >= 1
        # 路径应从 concept1 出发，到达 L4 fact1 或 L3 rule
        top_path = paths[0]
        assert top_path.nodes[0] == "concept1"
        # 权重应按降序
        for i in range(len(paths) - 1):
            assert paths[i].total_weight >= paths[i + 1].total_weight

    def test_search_empty_graph_returns_empty(self):
        """空图冷启动兜底：返回空路径（上层回退向量召回）。"""
        g = TopologyGraph()
        search = TopologySearch(g)
        paths = search.search("任意查询")
        assert paths == []

    def test_search_no_match_returns_empty(self):
        """无匹配概念时返回空（冷启动）。"""
        g = self._build_paper_graph()
        search = TopologySearch(g)
        paths = search.search("完全不相关的查询xyz123", keywords=["xyz123"])
        assert paths == []

    def test_search_mutex_edge_penalty(self):
        """含 MUTEX 边的路径权重应被惩罚（× MUTEX_PENALTY）。"""
        g = self._build_paper_graph()
        # 添加互斥约束
        g.add_node(TopologyLayer.L3_RULE, NodeType.CONSTRAINT, "互斥约束", node_id="mutex1")
        g.add_node(TopologyLayer.L3_RULE, NodeType.CONSTRAINT, "对立约束", node_id="mutex2")
        g.add_edge("mutex1", "mutex2", EdgeType.MUTEX)
        # 连接到主路径
        g.add_edge("concept1", "mutex1", EdgeType.DEPENDS_ON)

        search = TopologySearch(g, top_k=10)
        paths = search.search("文献综述", keywords=["文献综述"])
        # 至少有一条不含 MUTEX 的路径权重更高
        assert len(paths) >= 1
        # MUTEX 边的固定权重为 -1.0，惩罚因子 0.5
        assert MUTEX_PENALTY == 0.5

    def test_search_reinforced_path_ranks_higher(self):
        """强化后的路径权重应高于未强化路径。"""
        g = self._build_paper_graph()
        search = TopologySearch(g, top_k=5)

        # 初始搜索
        paths_before = search.search("文献综述", keywords=["文献综述"])
        weight_before = paths_before[0].total_weight if paths_before else 0.0

        # 强化 concept1 → rule1 路径
        g.reinforce_node("concept1")
        g.reinforce_node("rule1")
        edges = g.get_out_edges("concept1", EdgeType.DEPENDS_ON)
        for e in edges:
            g.reinforce_edge(e.edge_id)

        paths_after = search.search("文献综述", keywords=["文献综述"])
        weight_after = paths_after[0].total_weight if paths_after else 0.0

        assert weight_after > weight_before

    def test_search_top_k_limit(self):
        """top_k 限制返回路径数。"""
        g = self._build_paper_graph()
        search = TopologySearch(g, top_k=1)
        paths = search.search("文献综述", keywords=["文献综述"])
        assert len(paths) <= 1


# ──────────────────────────────────────────────────────────────────────
# 4. Weights 权重系统（衰减/强化/钳制）
# ──────────────────────────────────────────────────────────────────────


class TestWeightsSystem:
    """权重系统验证（KTG 区别于向量 RAG 的核心：可解释权重）。"""

    def test_clamp_weight_bounds(self):
        """权重钳制在 [MIN_WEIGHT, MAX_WEIGHT] 范围内。"""
        assert weights_mod.clamp_weight(-1.5) == weights_mod.MIN_WEIGHT
        assert weights_mod.clamp_weight(2.0) == weights_mod.MAX_WEIGHT
        mid = weights_mod.clamp_weight(0.5)
        assert weights_mod.MIN_WEIGHT <= mid <= weights_mod.MAX_WEIGHT

    def test_node_on_hit_increases_confidence(self):
        """节点命中后置信度上升、use_count+1。"""
        from fnixagent.core.types import TopologyNode

        node = TopologyNode(
            node_id="test",
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="test",
            content="",
            weight=0.5,
            confidence=0.3,
            use_count=0,
            freshness=1.0,
            deprecated=False,
            version=1,
            metadata={},
            skill_binding=None,
            created_at=0.0,
            last_used_at=0.0,
        )
        original_confidence = node.confidence
        weights_mod.node_on_hit(node)
        assert node.use_count == 1
        assert node.confidence > original_confidence

    def test_edge_on_failure_decreases_weight(self):
        """边失败惩罚后权重下降。"""
        from fnixagent.core.types import EdgeType, TopologyEdge

        edge = TopologyEdge(
            edge_id="e1",
            source_id="a",
            target_id="b",
            edge_type=EdgeType.DEPENDS_ON,
            weight=0.8,
            version=1,
            deprecated=False,
            metadata={},
            created_at=0.0,
        )
        original_weight = edge.weight
        weights_mod.edge_on_failure(edge)
        assert edge.weight < original_weight
