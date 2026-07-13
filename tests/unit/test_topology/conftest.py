"""
知识拓扑图 (KTG) 模块单元测试公共夹具。

提供以下 fixtures:
    - empty_graph:    空拓扑图
    - sample_graph:   包含 L1→L2→L3→L4 完整层级的示例图
    - sample_node:    一个 L2 CONCEPT 节点(独立对象,未加入图)
    - sample_edge:    一条 CONTAINS 边(独立对象,未加入图)
"""
import os
import sys

# 确保 src 在路径中(与 tests/unit/test_api/conftest.py 一致)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest

from officeagent.core.topology.graph import TopologyGraph
from officeagent.core.types import (
    EdgeType,
    NodeType,
    TopologyEdge,
    TopologyLayer,
    TopologyNode,
)


# ---------------------------------------------------------------------------
# 空拓扑图
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_graph() -> TopologyGraph:
    """返回一个空的拓扑图实例。"""
    return TopologyGraph()


# ---------------------------------------------------------------------------
# 包含 L1→L2→L3→L4 完整层级的示例图
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_graph() -> TopologyGraph:
    """构建包含 L1→L2→L3→L4 完整层级的示例拓扑图。

    节点:
        - L1:goal1   GOAL       "撰写论文综述"
        - L2:concept1 CONCEPT    "文献检索"  (绑定 skill: search_skill)
        - L3:rule1    RULE       "按发表年份降序排序"
        - L4:fact1    FACT       "arXiv:2401.00001 是 GPT-4 论文"

    边:
        - e1: L1→L2 CONTAINS (固定权重 1.0)
        - e2: L2→L3 CONTAINS (固定权重 1.0)
        - e3: L3→L4 CONTAINS (固定权重 1.0)
        - e4: L2→L3 DEPENDS_ON (可变权重 0.6)
        - e5: L3→L4 DEPENDS_ON (可变权重 0.7)
    """
    graph = TopologyGraph()
    graph.add_node(
        layer=TopologyLayer.L1_GOAL,
        node_type=NodeType.GOAL,
        name="撰写论文综述",
        content="用户想撰写一篇论文综述",
        node_id="L1:goal1",
    )
    graph.add_node(
        layer=TopologyLayer.L2_CONCEPT,
        node_type=NodeType.CONCEPT,
        name="文献检索",
        content="检索相关文献的概念",
        skill_binding="search_skill",
        node_id="L2:concept1",
    )
    graph.add_node(
        layer=TopologyLayer.L3_RULE,
        node_type=NodeType.RULE,
        name="按发表年份降序排序",
        content="检索结果按发表年份降序排列",
        node_id="L3:rule1",
    )
    graph.add_node(
        layer=TopologyLayer.L4_FACT,
        node_type=NodeType.FACT,
        name="arXiv:2401.00001 是 GPT-4 论文",
        content="GPT-4 技术报告发表于 arXiv",
        node_id="L4:fact1",
    )

    graph.add_edge("L1:goal1", "L2:concept1", EdgeType.CONTAINS, edge_id="e1")
    graph.add_edge("L2:concept1", "L3:rule1", EdgeType.CONTAINS, edge_id="e2")
    graph.add_edge("L3:rule1", "L4:fact1", EdgeType.CONTAINS, edge_id="e3")
    graph.add_edge(
        "L2:concept1", "L3:rule1", EdgeType.DEPENDS_ON, weight=0.6, edge_id="e4"
    )
    graph.add_edge(
        "L3:rule1", "L4:fact1", EdgeType.DEPENDS_ON, weight=0.7, edge_id="e5"
    )
    return graph


# ---------------------------------------------------------------------------
# 独立的 L2 CONCEPT 节点(未加入图)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_node() -> TopologyNode:
    """返回一个独立的 L2 CONCEPT 节点(未加入任何图)。"""
    return TopologyNode(
        node_id="L2:test_concept",
        layer=TopologyLayer.L2_CONCEPT,
        node_type=NodeType.CONCEPT,
        name="测试概念",
        content="用于单元测试的概念节点",
        weight=0.5,
        confidence=0.3,
        use_count=0,
        freshness=1.0,
        deprecated=False,
        version=1,
        metadata={},
        skill_binding="test_skill",
    )


# ---------------------------------------------------------------------------
# 独立的 CONTAINS 边(未加入图)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_edge() -> TopologyEdge:
    """返回一条独立的 CONTAINS 边(未加入任何图)。"""
    return TopologyEdge(
        edge_id="e:test_contains",
        source_id="L1:test_goal",
        target_id="L2:test_concept",
        edge_type=EdgeType.CONTAINS,
        weight=1.0,
        version=1,
        deprecated=False,
        metadata={},
    )
