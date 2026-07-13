"""
技能-拓扑突触协议 (STP) 模块单元测试公共夹具。

提供以下 fixtures:
    - sample_graph:       包含 L1→L2→L3→L4 完整层级的拓扑图(L2 节点已绑定技能)
    - sample_registry:    注册了 4 个测试工具的 ToolRegistry(覆盖三种 skill_level)
    - binding_protocol:   SkillBindingProtocol 实例
    - permission_policy:  SkillPermissionPolicy 实例
    - scheduler:          SkillScheduler 实例
    - feedback_handler:   SkillFeedbackHandler 实例
    - sample_path:        一条 TopologyPath(L2→L3→L4)
"""
import os
import sys

# 确保 src 在路径中(与 tests/unit/test_topology/conftest.py 一致)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest

from officeagent.core.skills.feedback import SkillFeedbackHandler
from officeagent.core.skills.levels import SkillPermissionPolicy
from officeagent.core.skills.protocol import SkillBindingProtocol
from officeagent.core.skills.scheduler import SkillScheduler
from officeagent.core.tools.protocol import ToolMetadata
from officeagent.core.tools.registry import ToolRegistry
from officeagent.core.topology.graph import TopologyGraph
from officeagent.core.types import (
    EdgeType,
    NodeType,
    SkillLevel,
    TopologyLayer,
    TopologyPath,
    ToolPermission,
)


# ---------------------------------------------------------------------------
# 拓扑图(包含 L1→L2→L3→L4 完整层级,L2 节点已绑定技能)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_graph() -> TopologyGraph:
    """构建包含 L1→L2→L3→L4 完整层级的示例拓扑图。

    节点:
        - L1:goal1     GOAL     "撰写论文综述"
        - L2:concept1  CONCEPT  "文献检索"(绑定 search_skill)
        - L2:concept2  CONCEPT  "格式转换"(绑定 convert_skill)
        - L2:concept3  CONCEPT  "图表生成"(绑定 chart_skill,未在 registry 注册)
        - L3:rule1     RULE     "按发表年份降序排序"
        - L4:fact1     FACT     "arXiv:2401.00001 是 GPT-4 论文"

    边:
        - e1: L1:goal1    → L2:concept1  CONTAINS    (固定 1.0)
        - e2: L1:goal1    → L2:concept2  CONTAINS    (固定 1.0)
        - e3: L2:concept1 → L3:rule1     DEPENDS_ON  (0.6,可变权重)
        - e4: L3:rule1    → L4:fact1     DEPENDS_ON  (0.7,可变权重)
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
        layer=TopologyLayer.L2_CONCEPT,
        node_type=NodeType.CONCEPT,
        name="格式转换",
        content="文档格式转换的概念",
        skill_binding="convert_skill",
        node_id="L2:concept2",
    )
    graph.add_node(
        layer=TopologyLayer.L2_CONCEPT,
        node_type=NodeType.CONCEPT,
        name="图表生成",
        content="生成图表的概念",
        skill_binding="chart_skill",
        node_id="L2:concept3",
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
    graph.add_edge("L1:goal1", "L2:concept2", EdgeType.CONTAINS, edge_id="e2")
    graph.add_edge(
        "L2:concept1", "L3:rule1", EdgeType.DEPENDS_ON, weight=0.6, edge_id="e3"
    )
    graph.add_edge(
        "L3:rule1", "L4:fact1", EdgeType.DEPENDS_ON, weight=0.7, edge_id="e4"
    )
    return graph


# ---------------------------------------------------------------------------
# 工具注册中心(注册 4 个测试工具,覆盖三种 skill_level)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_registry() -> ToolRegistry:
    """注册 4 个测试工具的 ToolRegistry。

    工具列表:
        - search_skill  (basic,     category="search",  priority=0.5)
        - convert_skill (reasoning, category="convert", priority=0.5)
        - meta_skill    (meta,      category="meta",    priority=0.5)
        - unbound_skill (basic,     category="search",  priority=0.8,未绑定拓扑)
    """
    registry = ToolRegistry()

    def _noop(args: dict) -> dict:
        return {"ok": True}

    registry.register(
        ToolMetadata(
            name="search_skill",
            description="搜索学术论文",
            category="search",
            skill_level=SkillLevel.BASIC.value,
            priority=0.5,
        ),
        _noop,
    )
    registry.register(
        ToolMetadata(
            name="convert_skill",
            description="文档格式转换",
            category="convert",
            skill_level=SkillLevel.REASONING.value,
            priority=0.5,
        ),
        _noop,
    )
    registry.register(
        ToolMetadata(
            name="meta_skill",
            description="元级技能(修改拓扑)",
            category="meta",
            skill_level=SkillLevel.META.value,
            priority=0.5,
        ),
        _noop,
    )
    registry.register(
        ToolMetadata(
            name="unbound_skill",
            description="未绑定拓扑的工具",
            category="search",
            skill_level=SkillLevel.BASIC.value,
            priority=0.8,
        ),
        _noop,
    )
    return registry


# ---------------------------------------------------------------------------
# STP 组件实例
# ---------------------------------------------------------------------------

@pytest.fixture
def binding_protocol(sample_graph: TopologyGraph) -> SkillBindingProtocol:
    """返回基于 sample_graph 的 SkillBindingProtocol 实例。"""
    return SkillBindingProtocol(sample_graph)


@pytest.fixture
def permission_policy() -> SkillPermissionPolicy:
    """返回使用默认配置的 SkillPermissionPolicy 实例。"""
    return SkillPermissionPolicy()


@pytest.fixture
def scheduler(
    sample_registry: ToolRegistry,
    binding_protocol: SkillBindingProtocol,
    permission_policy: SkillPermissionPolicy,
) -> SkillScheduler:
    """返回组装好的 SkillScheduler 实例。"""
    return SkillScheduler(
        registry=sample_registry,
        binding_protocol=binding_protocol,
        permission_policy=permission_policy,
    )


@pytest.fixture
def feedback_handler(sample_graph: TopologyGraph) -> SkillFeedbackHandler:
    """返回基于 sample_graph 的 SkillFeedbackHandler 实例。"""
    return SkillFeedbackHandler(sample_graph)


# ---------------------------------------------------------------------------
# 推理路径(L2→L3→L4)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_path() -> TopologyPath:
    """返回一条 L2→L3→L4 的推理路径。

    路径节点: L2:concept1 → L3:rule1 → L4:fact1
    路径边:   e3(DEPENDS_ON, 0.6) → e4(DEPENDS_ON, 0.7)
    """
    return TopologyPath(
        nodes=["L2:concept1", "L3:rule1", "L4:fact1"],
        edges=["e3", "e4"],
        total_weight=1.3,
        depth=2,
    )
