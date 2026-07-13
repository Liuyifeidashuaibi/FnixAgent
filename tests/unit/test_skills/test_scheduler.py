"""
技能调度器 (SkillScheduler) 单元测试。

测试模块: fnixagent.core.skills.scheduler.SkillScheduler
覆盖:
    - __init__: 默认策略 / 自定义策略
    - select_skills: 优先级降序、top_k 限制、category 过滤、auto_invoke_only、权限过滤、disabled 跳过
    - select_by_concept: 已绑定 / 未绑定 / 技能未注册
    - select_for_path: 路径命中 / 空路径 / 无绑定
    - describe_schedule: 返回结构、top_k 限制
"""
import pytest

from fnixagent.core.skills.levels import SkillPermissionPolicy
from fnixagent.core.skills.scheduler import SkillScheduler
from fnixagent.core.tools.protocol import ToolMetadata
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.types import SkillLevel, TopologyPath


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    """测试 SkillScheduler 初始化。"""

    def test_init_with_custom_policy(
        self, sample_registry, binding_protocol, permission_policy
    ):
        """传入自定义权限策略时应直接使用。"""
        scheduler = SkillScheduler(
            registry=sample_registry,
            binding_protocol=binding_protocol,
            permission_policy=permission_policy,
        )
        assert scheduler._policy is permission_policy

    def test_init_with_default_policy(self, sample_registry, binding_protocol):
        """未传入权限策略时应自动创建默认策略。"""
        scheduler = SkillScheduler(
            registry=sample_registry,
            binding_protocol=binding_protocol,
        )
        assert isinstance(scheduler._policy, SkillPermissionPolicy)
        assert scheduler._policy.can_auto_invoke(SkillLevel.BASIC) is True


# ---------------------------------------------------------------------------
# select_skills
# ---------------------------------------------------------------------------

class TestSelectSkills:
    """测试 select_skills() 方法。"""

    def test_select_returns_sorted_by_priority(self, scheduler, sample_path):
        """返回结果应按优先级降序排列。"""
        # search_skill 绑定 concept1(在路径上,优先级 0.5)
        # convert_skill 绑定 concept2(兄弟,优先级 0.15)
        # chart_skill 绑定 concept3(兄弟,优先级 0.15)
        # unbound_skill 无绑定,但自身 priority=0.8 → max(0.0, 0.8)=0.8
        result = scheduler.select_skills(path=sample_path, top_k=10)
        # unbound_skill(0.8) > search_skill(0.5) > convert_skill(0.5, 自身优先级)
        #   > chart_skill(0.5, 自身优先级)
        # 注意: convert_skill 和 chart_skill 的 binding 优先级 0.15,
        # 但 max(0.15, 0.5)=0.5,所以与 search_skill 同为 0.5
        assert len(result) >= 1
        # unbound_skill 应排首位(最高优先级 0.8)
        assert result[0].name == "unbound_skill"

    def test_select_top_k_limit(self, scheduler, sample_path):
        """top_k 应限制返回数量。"""
        result = scheduler.select_skills(path=sample_path, top_k=2)
        assert len(result) == 2

    def test_select_top_k_one(self, scheduler, sample_path):
        """top_k=1 应只返回 1 个技能。"""
        result = scheduler.select_skills(path=sample_path, top_k=1)
        assert len(result) == 1
        assert result[0].name == "unbound_skill"

    def test_select_category_filter(self, scheduler, sample_path):
        """category 过滤应仅返回该分类的工具。"""
        result = scheduler.select_skills(
            path=sample_path, top_k=10, category="search"
        )
        names = {t.name for t in result}
        # search 分类包含 search_skill 和 unbound_skill
        assert names == {"search_skill", "unbound_skill"}

    def test_select_category_no_match(self, scheduler, sample_path):
        """不存在的分类应返回空列表。"""
        result = scheduler.select_skills(
            path=sample_path, top_k=10, category="nonexistent"
        )
        assert result == []

    def test_select_auto_invoke_only(self, scheduler, sample_path):
        """auto_invoke_only=True 应仅返回可自动调用的技能(BASIC 级)。"""
        result = scheduler.select_skills(
            path=sample_path, top_k=10, auto_invoke_only=True
        )
        names = {t.name for t in result}
        # BASIC 级: search_skill, unbound_skill
        # REASONING 级 convert_skill 被排除(需确认)
        # META 级 meta_skill 被排除(禁用)
        assert "search_skill" in names
        assert "unbound_skill" in names
        assert "convert_skill" not in names
        assert "meta_skill" not in names

    def test_select_excludes_forbidden(self, scheduler, sample_path):
        """META 级(forbidden)技能应始终被排除,即使 auto_invoke_only=False。"""
        result = scheduler.select_skills(path=sample_path, top_k=10)
        names = {t.name for t in result}
        # meta_skill 是 META 级 → forbidden → 始终排除
        assert "meta_skill" not in names
        # convert_skill 是 REASONING 级 → needs_confirmation → 保留(auto_invoke_only=False)
        assert "convert_skill" in names

    def test_select_includes_needs_confirmation(self, scheduler, sample_path):
        """REASONING 级技能(需确认)在 auto_invoke_only=False 时应被保留。"""
        result = scheduler.select_skills(path=sample_path, top_k=10)
        names = {t.name for t in result}
        assert "convert_skill" in names

    def test_select_disabled_tool_skipped(
        self, scheduler, sample_registry, sample_path
    ):
        """enabled=False 的工具应被跳过。"""
        # 禁用 unbound_skill(优先级最高的工具)
        tool = sample_registry.get("unbound_skill")
        tool.metadata.enabled = False
        result = scheduler.select_skills(path=sample_path, top_k=10)
        names = {t.name for t in result}
        assert "unbound_skill" not in names

    def test_select_empty_registry(self, binding_protocol):
        """空注册中心应返回空列表。"""
        empty_registry = ToolRegistry()
        scheduler = SkillScheduler(empty_registry, binding_protocol)
        result = scheduler.select_skills(top_k=5)
        assert result == []

    def test_select_no_path(self, scheduler):
        """无路径时应使用工具自身优先级与绑定权重(系数 1.0)。"""
        result = scheduler.select_skills(path=None, top_k=10)
        # 无路径时绑定技能优先级 = 节点权重(0.5),unbound_skill 自身优先级 0.8
        assert len(result) >= 1
        assert result[0].name == "unbound_skill"

    def test_select_authorized_meta_skill(
        self, scheduler, permission_policy, sample_path
    ):
        """显式授权的 META 级技能应被包含在结果中。"""
        permission_policy.authorize("meta_skill")
        result = scheduler.select_skills(path=sample_path, top_k=10)
        names = {t.name for t in result}
        assert "meta_skill" in names


# ---------------------------------------------------------------------------
# select_by_concept
# ---------------------------------------------------------------------------

class TestSelectByConcept:
    """测试 select_by_concept() 方法。"""

    def test_select_by_concept_bound(self, scheduler):
        """已绑定技能的概念节点应返回对应工具元数据。"""
        result = scheduler.select_by_concept("L2:concept1")
        assert len(result) == 1
        assert result[0].name == "search_skill"

    def test_select_by_concept_unbound(self, scheduler):
        """未绑定技能的概念节点应返回空列表。"""
        # concept1 绑定了 search_skill,先解绑
        scheduler._binding.unbind("L2:concept1")
        result = scheduler.select_by_concept("L2:concept1")
        assert result == []

    def test_select_by_concept_nonexistent(self, scheduler):
        """不存在的概念节点应返回空列表。"""
        result = scheduler.select_by_concept("L2:nonexistent")
        assert result == []

    def test_select_by_concept_skill_not_in_registry(
        self, scheduler, binding_protocol
    ):
        """绑定的技能未在 registry 注册时应返回空列表。"""
        # chart_skill 绑定在 concept3 上,但未在 registry 注册
        result = scheduler.select_by_concept("L2:concept3")
        assert result == []


# ---------------------------------------------------------------------------
# select_for_path
# ---------------------------------------------------------------------------

class TestSelectForPath:
    """测试 select_for_path() 方法。"""

    def test_select_for_path_with_bindings(self, scheduler, sample_path):
        """路径上概念节点绑定的技能应被收集并按优先级降序返回。"""
        # sample_path 节点: L2:concept1 → L3:rule1 → L4:fact1
        # 仅 L2:concept1 绑定了 search_skill(在 registry 中)
        result = scheduler.select_for_path(sample_path, top_k=5)
        assert len(result) == 1
        assert result[0].name == "search_skill"

    def test_select_for_path_top_k(self, scheduler, sample_path):
        """top_k 应限制返回数量。"""
        result = scheduler.select_for_path(sample_path, top_k=0)
        # top_k=0 → 取 0 个
        assert len(result) == 0

    def test_select_for_path_no_bindings(self, scheduler):
        """路径上无概念节点绑定技能时应返回空列表。"""
        path = TopologyPath(
            nodes=["L3:rule1", "L4:fact1"],
            edges=["e4"],
        )
        result = scheduler.select_for_path(path, top_k=5)
        assert result == []

    def test_select_for_path_empty_path(self, scheduler):
        """空路径应返回空列表。"""
        empty_path = TopologyPath()
        result = scheduler.select_for_path(empty_path, top_k=5)
        assert result == []

    def test_select_for_path_multiple_skills(
        self, scheduler, binding_protocol, sample_registry, sample_path
    ):
        """路径上多个概念节点绑定不同技能时应全部返回。"""
        # 让 L3:rule1 不参与(它是 RULE 不是 CONCEPT,get_bound_skill 返回 None)
        # 需要在路径中加入另一个绑定了技能的 CONCEPT 节点
        # concept2 绑定了 convert_skill,加入路径
        path = TopologyPath(
            nodes=["L2:concept1", "L2:concept2", "L3:rule1"],
            edges=["e3"],
        )
        result = scheduler.select_for_path(path, top_k=5)
        names = {t.name for t in result}
        assert "search_skill" in names
        assert "convert_skill" in names


# ---------------------------------------------------------------------------
# describe_schedule
# ---------------------------------------------------------------------------

class TestDescribeSchedule:
    """测试 describe_schedule() 方法。"""

    def test_describe_returns_list_of_dicts(self, scheduler, sample_path):
        """应返回 dict 列表,每项包含调度详情字段。"""
        info = scheduler.describe_schedule(path=sample_path, top_k=5)
        assert isinstance(info, list)
        assert len(info) <= 5
        for item in info:
            assert isinstance(item, dict)
            assert "name" in item
            assert "skill_level" in item
            assert "priority" in item
            assert "allowed" in item
            assert "reason" in item
            assert "bound_concepts" in item

    def test_describe_top_k_limit(self, scheduler, sample_path):
        """top_k 应限制返回数量。"""
        info = scheduler.describe_schedule(path=sample_path, top_k=2)
        assert len(info) <= 2

    def test_describe_sorted_by_priority(self, scheduler, sample_path):
        """返回结果应按优先级降序排列。"""
        info = scheduler.describe_schedule(path=sample_path, top_k=10)
        priorities = [item["priority"] for item in info]
        assert priorities == sorted(priorities, reverse=True)

    def test_describe_includes_bound_concepts(self, scheduler, sample_path):
        """bound_concepts 字段应正确反映技能绑定的概念节点。"""
        info = scheduler.describe_schedule(path=sample_path, top_k=10)
        search_info = next(item for item in info if item["name"] == "search_skill")
        assert "L2:concept1" in search_info["bound_concepts"]

    def test_describe_no_path(self, scheduler):
        """无路径时应仍返回调度详情。"""
        info = scheduler.describe_schedule(path=None, top_k=5)
        assert isinstance(info, list)
        assert len(info) <= 5
