"""
LangGraph 编排层单元测试公共夹具。

提供以下 fixtures:
    - mock_search:           模拟 TopologySearch(返回固定路径)
    - mock_registry:         注册了测试工具的 ToolRegistry
    - mock_scheduler:        模拟 SkillScheduler(返回固定 ToolMetadata)
    - mock_binding_protocol: 模拟 SkillBindingProtocol
    - sample_path:           一条 TopologyPath
    - sample_tool_metadata:  一个 ToolMetadata
    - sample_state:          初始化的 AgentState
"""
import os
import sys

# 确保 src 在路径中(与 tests/unit/test_topology/conftest.py 一致)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest

from officeagent.core.tools.protocol import ToolMetadata
from officeagent.core.tools.registry import ToolRegistry
from officeagent.core.types import ToolPermission, TopologyPath
from officeagent.graph.state import AgentState, create_initial_state


# ---------------------------------------------------------------------------
# 模拟 TopologySearch
# ---------------------------------------------------------------------------

class FakeSearchEngine:
    """模拟 TopologySearch,记录调用并返回固定路径。"""

    def __init__(self, paths=None):
        self._paths = paths or []
        self.call_count = 0
        self.last_query = None
        self.last_keywords = None
        self.last_top_k = None

    def search(self, query, keywords=None, top_k=None):
        self.call_count += 1
        self.last_query = query
        self.last_keywords = keywords
        self.last_top_k = top_k
        return list(self._paths)


@pytest.fixture
def sample_path() -> TopologyPath:
    """一条示例 TopologyPath。"""
    return TopologyPath(
        nodes=["L2:concept1", "L3:rule1"],
        edges=["e1", "e2"],
        total_weight=0.75,
        depth=2,
    )


@pytest.fixture
def mock_search(sample_path) -> FakeSearchEngine:
    """返回模拟 TopologySearch 实例(内部持有一条固定路径)。"""
    return FakeSearchEngine(paths=[sample_path])


# ---------------------------------------------------------------------------
# 模拟 SkillScheduler
# ---------------------------------------------------------------------------

class FakeScheduler:
    """模拟 SkillScheduler,记录调用并返回固定 ToolMetadata 列表。"""

    def __init__(self, tools=None):
        self._tools = tools or []
        self.call_count = 0
        self.last_path = None
        self.last_top_k = None
        self.last_category = None
        self.last_auto_invoke_only = None

    def select_skills(
        self,
        path=None,
        top_k=5,
        category=None,
        auto_invoke_only=False,
    ):
        self.call_count += 1
        self.last_path = path
        self.last_top_k = top_k
        self.last_category = category
        self.last_auto_invoke_only = auto_invoke_only
        return list(self._tools)


@pytest.fixture
def sample_tool_metadata() -> ToolMetadata:
    """一个示例 ToolMetadata。"""
    return ToolMetadata(
        name="search_paper",
        description="搜索学术论文",
        category="search",
        permission_level=ToolPermission.LOW,
        priority=0.7,
    )


@pytest.fixture
def mock_scheduler(sample_tool_metadata) -> FakeScheduler:
    """返回模拟 SkillScheduler 实例。"""
    return FakeScheduler(tools=[sample_tool_metadata])


# ---------------------------------------------------------------------------
# 模拟 SkillBindingProtocol
# ---------------------------------------------------------------------------

class FakeBindingProtocol:
    """模拟 SkillBindingProtocol。"""

    def __init__(self, priority=0.8):
        self._priority = priority
        self.call_count = 0
        self.last_skill_name = None
        self.last_path = None

    def compute_priority(self, skill_name, path):
        self.call_count += 1
        self.last_skill_name = skill_name
        self.last_path = path
        return self._priority


@pytest.fixture
def mock_binding_protocol() -> FakeBindingProtocol:
    """返回模拟 SkillBindingProtocol 实例。"""
    return FakeBindingProtocol(priority=0.85)


# ---------------------------------------------------------------------------
# 真实 ToolRegistry(注册了测试工具)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_registry() -> ToolRegistry:
    """返回注册了测试工具的 ToolRegistry。"""
    registry = ToolRegistry()

    def search_paper(args):
        return {"papers": ["paper1", "paper2"]}

    meta = ToolMetadata(
        name="search_paper",
        description="搜索学术论文",
        category="search",
        permission_level=ToolPermission.LOW,
    )
    registry.register(meta, search_paper)
    return registry


# ---------------------------------------------------------------------------
# AgentState fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_state() -> AgentState:
    """返回初始化的 AgentState。"""
    return create_initial_state("搜索 GPT-4 论文")


@pytest.fixture
def empty_state() -> dict:
    """返回空 state dict(模拟缺失字段的场景)。"""
    return {}
