"""
飞轮模块单元测试公共夹具。

提供以下 fixtures:
    - sample_graph:        包含 L1→L2→L3→L4 完整层级的拓扑图
    - sample_trace:        一条成功的 TraceRecord(含工具调用)
    - failed_trace:        一条失败的 TraceRecord
    - junk_trace:          一条临时话术的 TraceRecord
    - no_tool_trace:       一条无工具调用的 TraceRecord(用于过滤测试)
    - mock_search:         TopologySearch 实例
    - mock_registry:       注册了测试工具的 ToolRegistry
    - mock_binding_protocol: SkillBindingProtocol 实例
    - mock_scheduler:      SkillScheduler 实例
    - trace_store:         TraceStore 实例(基于 tmp_path)
    - fake_graph:          模拟编译后的 LangGraph(供飞轮①测试)
    - fake_snapshot_manager: 模拟快照管理器
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import os
import sys
import time

# 确保 src 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest

from fnixagent.core.flywheel.trace import TraceStore
from fnixagent.core.skills.protocol import SkillBindingProtocol
from fnixagent.core.skills.scheduler import SkillScheduler
from fnixagent.core.tools.protocol import ToolMetadata
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.topology.search import TopologySearch
from fnixagent.core.types import (
    EdgeType,
    NodeType,
    ReasoningMode,
    ToolPermission,
    TopologyLayer,
    TraceRecord,
)

# ---------------------------------------------------------------------------
# 拓扑图(包含 L1→L2→L3→L4 完整层级 + 额外节点)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_graph() -> TopologyGraph:
    """构建包含 L1→L2→L3→L4 完整层级的示例拓扑图。

    节点:
        - L1:goal1     GOAL     "撰写论文综述"
        - L2:concept1  CONCEPT  "文献检索"  (绑定 skill: search_paper)
        - L2:concept2  CONCEPT  "数据分析"  (绑定 skill: analyze_data)
        - L3:rule1     RULE     "按发表年份降序排序"
        - L4:fact1     FACT     "arXiv:2401.00001 是 GPT-4 论文"

    边:
        - e1: L1→L2 CONTAINS
        - e2: L2→L3 CONTAINS
        - e3: L3→L4 CONTAINS
        - e4: L2:concept1→L3:rule1 DEPENDS_ON (weight=0.6)
        - e5: L3:rule1→L4:fact1 DEPENDS_ON (weight=0.7)
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
        skill_binding="search_paper",
        node_id="L2:concept1",
    )
    graph.add_node(
        layer=TopologyLayer.L2_CONCEPT,
        node_type=NodeType.CONCEPT,
        name="数据分析",
        content="对检索结果进行数据分析",
        skill_binding="analyze_data",
        node_id="L2:concept2",
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
    graph.add_edge("L2:concept1", "L3:rule1", EdgeType.DEPENDS_ON, weight=0.6, edge_id="e4")
    graph.add_edge("L3:rule1", "L4:fact1", EdgeType.DEPENDS_ON, weight=0.7, edge_id="e5")
    return graph


# ---------------------------------------------------------------------------
# TraceRecord fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_trace() -> TraceRecord:
    """一条成功的 TraceRecord(含 2 次工具调用)。"""
    return TraceRecord(
        trace_id="trace-success-001",
        task_id="task-001",
        goal="撰写论文综述",
        mode=ReasoningMode.REACT,
        concept_path=["L2:concept1"],
        tool_calls=[
            {"name": "search_paper", "args": {"query": "GPT-4"}, "status": "success"},
            {"name": "analyze_data", "args": {"data": "results"}, "status": "success"},
        ],
        success=True,
        duration_ms=1500.0,
        usage_tokens=500,
        reflection_score=0.0,
        created_at=time.time(),
    )


@pytest.fixture
def failed_trace() -> TraceRecord:
    """一条失败的 TraceRecord。"""
    return TraceRecord(
        trace_id="trace-fail-001",
        task_id="task-002",
        goal="执行失败的任务",
        mode=ReasoningMode.REACT,
        concept_path=["L2:concept1"],
        tool_calls=[
            {"name": "search_paper", "args": {}, "status": "failed", "error": "timeout"},
        ],
        success=False,
        duration_ms=3000.0,
        usage_tokens=200,
        reflection_score=0.0,
        created_at=time.time(),
    )


@pytest.fixture
def junk_trace() -> TraceRecord:
    """一条临时话术的 TraceRecord(成功但无实质内容)。"""
    return TraceRecord(
        trace_id="trace-junk-001",
        task_id="task-003",
        goal="你好",
        mode=ReasoningMode.REACT,
        concept_path=[],
        tool_calls=[],
        success=True,
        duration_ms=100.0,
        usage_tokens=10,
        reflection_score=0.0,
        created_at=time.time(),
    )


@pytest.fixture
def no_tool_trace() -> TraceRecord:
    """一条成功但无工具调用的 TraceRecord(用于无实质推理过滤测试)。"""
    return TraceRecord(
        trace_id="trace-notool-001",
        task_id="task-004",
        goal="分析数据报告",
        mode=ReasoningMode.REACT,
        concept_path=[],
        tool_calls=[],
        success=True,
        duration_ms=50.0,
        usage_tokens=5,
        reflection_score=0.0,
        created_at=time.time(),
    )


# ---------------------------------------------------------------------------
# 拓扑搜索 / 工具注册 / 调度器
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_search(sample_graph) -> TopologySearch:
    """返回基于 sample_graph 的 TopologySearch 实例。"""
    return TopologySearch(sample_graph, top_k=3, max_depth=6)


@pytest.fixture
def mock_registry() -> ToolRegistry:
    """返回注册了测试工具的 ToolRegistry。"""
    registry = ToolRegistry()

    def search_paper(args):
        return {"papers": ["paper1", "paper2"]}

    def analyze_data(args):
        return {"analysis": "complete"}

    registry.register(
        ToolMetadata(
            name="search_paper",
            description="搜索学术论文",
            category="search",
            permission_level=ToolPermission.LOW,
            skill_level="basic",
        ),
        search_paper,
    )
    registry.register(
        ToolMetadata(
            name="analyze_data",
            description="数据分析",
            category="analysis",
            permission_level=ToolPermission.LOW,
            skill_level="basic",
        ),
        analyze_data,
    )
    return registry


@pytest.fixture
def mock_binding_protocol(sample_graph) -> SkillBindingProtocol:
    """返回基于 sample_graph 的 SkillBindingProtocol 实例。"""
    return SkillBindingProtocol(sample_graph)


@pytest.fixture
def mock_scheduler(mock_registry, mock_binding_protocol) -> SkillScheduler:
    """返回 SkillScheduler 实例。"""
    return SkillScheduler(mock_registry, mock_binding_protocol)


# ---------------------------------------------------------------------------
# TraceStore(基于 tmp_path,每个测试独立隔离)
# ---------------------------------------------------------------------------


@pytest.fixture
def trace_store(tmp_path) -> TraceStore:
    """返回基于 tmp_path 的 TraceStore 实例。"""
    return TraceStore(str(tmp_path / "traces"))


# ---------------------------------------------------------------------------
# 模拟编译后的 LangGraph(供飞轮①测试)
# ---------------------------------------------------------------------------


class FakeGraph:
    """模拟编译后的 LangGraph,记录 invoke/stream 调用。"""

    def __init__(self, final_state=None, events=None, raise_exc=None):
        self._final_state = final_state or {}
        self._events = events or []
        self._raise = raise_exc
        self.invoke_count = 0
        self.last_config = None
        self.last_state = None

    def invoke(self, state, config=None):
        self.invoke_count += 1
        self.last_state = state
        self.last_config = config
        if self._raise is not None:
            raise self._raise
        return dict(self._final_state)

    def stream(self, state, config=None):
        for event in self._events:
            yield event


@pytest.fixture
def fake_graph():
    """返回模拟编译后的 LangGraph(成功执行)。"""
    return FakeGraph(
        final_state={
            "trace": {
                "trace_id": "trace-001",
                "task_id": "task-001",
                "success": True,
                "tool_calls": [{"name": "search_paper", "args": {}, "status": "success"}],
            },
            "concept_path": ["L2:concept1"],
            "error": None,
        }
    )


@pytest.fixture
def fake_graph_failure():
    """返回模拟编译后的 LangGraph(执行抛异常)。"""
    return FakeGraph(raise_exc=RuntimeError("graph execution failed"))


# ---------------------------------------------------------------------------
# 模拟快照管理器(供飞轮④测试)
# ---------------------------------------------------------------------------


class FakeSnapshotManager:
    """模拟快照管理器。"""

    def __init__(self):
        self.snapshots = {}
        self.create_count = 0
        self.restore_count = 0

    def create_snapshot(self, name):
        self.create_count += 1
        self.snapshots[name] = {"name": name, "data": "snapshot_data"}
        return name

    def restore_snapshot(self, name):
        self.restore_count += 1
        return self.snapshots.get(name, {})


@pytest.fixture
def fake_snapshot_manager() -> FakeSnapshotManager:
    """返回模拟快照管理器。"""
    return FakeSnapshotManager()
