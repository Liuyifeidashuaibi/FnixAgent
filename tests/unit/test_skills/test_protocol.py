"""
技能-拓扑绑定协议 (SkillBindingProtocol) 单元测试。

测试模块: fnixagent.core.skills.protocol.SkillBindingProtocol
覆盖:
    - 常量校验: HIT_COEFFICIENT_ON_PATH / SIBLING / UNRELATED
    - bind: 正常绑定、幂等绑定、异常路径(节点不存在/非 L2/已绑不同技能)
    - unbind: 正常解绑、异常路径(未绑定/节点不存在)
    - get_bound_skill: 已绑定/未绑定/节点不存在
    - get_bound_concepts: 有匹配/无匹配
    - list_all_bindings: 空图/有绑定/skill_level 容错
    - compute_priority: 路径命中/兄弟/无路径/无绑定/多概念
    - compute_priorities: 批量计算与降序排列
"""
import pytest

from fnixagent.core.exceptions import SkillBindingError
from fnixagent.core.skills.protocol import (
    HIT_COEFFICIENT_ON_PATH,
    HIT_COEFFICIENT_SIBLING,
    HIT_COEFFICIENT_UNRELATED,
    SkillBindingProtocol,
)
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    NodeType,
    SkillLevel,
    SkillRecord,
    TopologyLayer,
    TopologyPath,
)


# ---------------------------------------------------------------------------
# 常量校验
# ---------------------------------------------------------------------------

class TestConstants:
    """测试路径命中系数常量。"""

    def test_hit_coefficient_values(self):
        """路径命中系数应符合计划 3.2 的固化值。"""
        assert HIT_COEFFICIENT_ON_PATH == 1.0
        assert HIT_COEFFICIENT_SIBLING == 0.3
        assert HIT_COEFFICIENT_UNRELATED == 0.0


# ---------------------------------------------------------------------------
# bind
# ---------------------------------------------------------------------------

class TestBind:
    """测试 bind() 方法。"""

    def test_bind_normal(self, binding_protocol, sample_graph):
        """正常绑定 L2 概念节点与技能应成功并返回更新后的节点。"""
        # 先解绑 concept3 原有的 chart_skill
        binding_protocol.unbind("L2:concept3")
        node = binding_protocol.bind(
            "L2:concept3", "new_skill", SkillLevel.REASONING
        )
        assert node.skill_binding == "new_skill"
        assert node.metadata["skill_level"] == SkillLevel.REASONING.value
        # 图中节点应同步更新
        assert sample_graph.get_node("L2:concept3").skill_binding == "new_skill"

    def test_bind_default_level(self, binding_protocol):
        """未指定 skill_level 时默认使用 BASIC。"""
        binding_protocol.unbind("L2:concept3")
        node = binding_protocol.bind("L2:concept3", "new_skill")
        assert node.metadata["skill_level"] == SkillLevel.BASIC.value

    def test_bind_idempotent_same_skill(self, binding_protocol):
        """对同一技能重复绑定应为幂等操作,不抛异常。"""
        node = binding_protocol.bind("L2:concept1", "search_skill")
        assert node.skill_binding == "search_skill"

    def test_bind_nonexistent_node(self, binding_protocol):
        """绑定不存在的节点应抛 SkillBindingError。"""
        with pytest.raises(SkillBindingError, match="概念节点不存在"):
            binding_protocol.bind("L2:nonexistent", "some_skill")

    def test_bind_non_l2_node(self, binding_protocol):
        """绑定非 L2 CONCEPT 节点应抛 SkillBindingError。"""
        with pytest.raises(SkillBindingError, match="仅 L2 CONCEPT"):
            binding_protocol.bind("L1:goal1", "some_skill")

    def test_bind_l3_node(self, binding_protocol):
        """绑定 L3 RULE 节点应抛 SkillBindingError。"""
        with pytest.raises(SkillBindingError, match="仅 L2 CONCEPT"):
            binding_protocol.bind("L3:rule1", "some_skill")

    def test_bind_already_bound_different_skill(self, binding_protocol):
        """已绑定其他技能的节点再次绑定不同技能应抛 SkillBindingError。"""
        with pytest.raises(SkillBindingError, match="已绑定技能"):
            binding_protocol.bind("L2:concept1", "other_skill")


# ---------------------------------------------------------------------------
# unbind
# ---------------------------------------------------------------------------

class TestUnbind:
    """测试 unbind() 方法。"""

    def test_unbind_normal(self, binding_protocol, sample_graph):
        """正常解绑应清除 skill_binding 与 metadata 中的 skill_level。"""
        node = binding_protocol.unbind("L2:concept1")
        assert node.skill_binding is None
        assert "skill_level" not in node.metadata
        assert sample_graph.get_node("L2:concept1").skill_binding is None

    def test_unbind_unbound_node(self, binding_protocol):
        """解绑未绑定技能的节点应抛 SkillBindingError。"""
        binding_protocol.unbind("L2:concept1")
        with pytest.raises(SkillBindingError, match="未绑定任何技能"):
            binding_protocol.unbind("L2:concept1")


# ---------------------------------------------------------------------------
# get_bound_skill
# ---------------------------------------------------------------------------

class TestGetBoundSkill:
    """测试 get_bound_skill() 方法。"""

    def test_get_bound_skill_present(self, binding_protocol):
        """已绑定的节点应返回技能名。"""
        assert binding_protocol.get_bound_skill("L2:concept1") == "search_skill"

    def test_get_bound_skill_absent(self, binding_protocol):
        """未绑定的节点应返回 None。"""
        binding_protocol.unbind("L2:concept1")
        assert binding_protocol.get_bound_skill("L2:concept1") is None

    def test_get_bound_skill_nonexistent_node(self, binding_protocol):
        """不存在的节点应返回 None(不抛异常)。"""
        assert binding_protocol.get_bound_skill("L2:nonexistent") is None


# ---------------------------------------------------------------------------
# get_bound_concepts
# ---------------------------------------------------------------------------

class TestGetBoundConcepts:
    """测试 get_bound_concepts() 反查方法。"""

    def test_get_bound_concepts_with_match(self, binding_protocol):
        """反查绑定到指定技能的概念节点应返回正确列表。"""
        concepts = binding_protocol.get_bound_concepts("search_skill")
        assert len(concepts) == 1
        assert concepts[0].node_id == "L2:concept1"

    def test_get_bound_concepts_multiple(self, binding_protocol, sample_graph):
        """一个技能被多个概念节点绑定时应全部返回。"""
        # 让 concept3 也绑定 search_skill
        binding_protocol.unbind("L2:concept3")
        binding_protocol.bind("L2:concept3", "search_skill")
        concepts = binding_protocol.get_bound_concepts("search_skill")
        assert len(concepts) == 2
        node_ids = {c.node_id for c in concepts}
        assert node_ids == {"L2:concept1", "L2:concept3"}

    def test_get_bound_concepts_no_match(self, binding_protocol):
        """无概念节点绑定该技能时应返回空列表。"""
        assert binding_protocol.get_bound_concepts("nonexistent_skill") == []


# ---------------------------------------------------------------------------
# list_all_bindings
# ---------------------------------------------------------------------------

class TestListAllBindings:
    """测试 list_all_bindings() 方法。"""

    def test_list_all_bindings_returns_records(self, binding_protocol):
        """应返回全部已绑定技能的 SkillRecord 列表。"""
        records = binding_protocol.list_all_bindings()
        assert len(records) == 3  # concept1, concept2, concept3
        names = {r.name for r in records}
        assert names == {"search_skill", "convert_skill", "chart_skill"}

    def test_list_all_bindings_record_fields(self, binding_protocol):
        """SkillRecord 字段应正确映射节点属性。"""
        records = binding_protocol.list_all_bindings()
        search_record = next(r for r in records if r.name == "search_skill")
        assert isinstance(search_record, SkillRecord)
        assert search_record.bound_concept_id == "L2:concept1"
        assert search_record.skill_level == SkillLevel.BASIC
        # 初始优先级 = 节点权重
        assert search_record.priority == 0.5

    def test_list_all_bindings_empty_graph(self):
        """空图的绑定列表应为空。"""
        protocol = SkillBindingProtocol(TopologyGraph())
        assert protocol.list_all_bindings() == []

    def test_list_all_bindings_skips_unbound(self, binding_protocol):
        """未绑定技能的 L2 节点不应出现在结果中。"""
        binding_protocol.unbind("L2:concept3")
        records = binding_protocol.list_all_bindings()
        assert len(records) == 2
        assert all(r.name != "chart_skill" for r in records)


# ---------------------------------------------------------------------------
# compute_priority
# ---------------------------------------------------------------------------

class TestComputePriority:
    """测试 compute_priority() 方法。"""

    def test_priority_no_binding(self, binding_protocol):
        """未绑定任何概念节点的技能优先级应为 0.0。"""
        assert binding_protocol.compute_priority("nonexistent_skill") == 0.0

    def test_priority_on_path(self, binding_protocol, sample_path):
        """路径经过绑定概念时,命中系数为 1.0,优先级 = 节点权重。"""
        # concept1 weight=0.5, 在路径上, coeff=1.0
        # priority = 0.5 * 1.0 / 1 = 0.5
        priority = binding_protocol.compute_priority("search_skill", sample_path)
        assert priority == pytest.approx(0.5)

    def test_priority_sibling(self, binding_protocol, sample_path):
        """路径存在但未经过绑定的概念时,命中系数为 0.3(兄弟节点)。"""
        # concept2 weight=0.5, 不在路径上但路径存在 → 兄弟系数 0.3
        # priority = 0.5 * 0.3 / 1 = 0.15
        priority = binding_protocol.compute_priority("convert_skill", sample_path)
        assert priority == pytest.approx(0.15)

    def test_priority_no_path(self, binding_protocol):
        """无路径时,命中系数按 1.0 计算(直接用权重)。"""
        # concept1 weight=0.5, 无路径 → coeff=1.0
        # priority = 0.5 * 1.0 / 1 = 0.5
        priority = binding_protocol.compute_priority("search_skill", path=None)
        assert priority == pytest.approx(0.5)

    def test_priority_clamped_to_one(self, binding_protocol, sample_path):
        """优先级归一化后不应超过 1.0。"""
        # 手动把 concept1 权重拉高
        node = binding_protocol._graph.get_node("L2:concept1")
        node.weight = 2.0  # 超过 1.0
        priority = binding_protocol.compute_priority("search_skill", sample_path)
        # priority = min(1.0, 2.0 * 1.0 / 1) = 1.0
        assert priority == 1.0

    def test_priority_multiple_concepts_mixed(self, binding_protocol, sample_path, sample_graph):
        """多概念绑定: 部分在路径上、部分不在,优先级为加权平均。"""
        # 让 concept3 也绑定 search_skill
        binding_protocol.unbind("L2:concept3")
        binding_protocol.bind("L2:concept3", "search_skill")
        # concept1 (0.5, 在路径, coeff=1.0) + concept3 (0.5, 不在路径, coeff=0.3)
        # priority = (0.5*1.0 + 0.5*0.3) / 2 = 0.325
        priority = binding_protocol.compute_priority("search_skill", sample_path)
        assert priority == pytest.approx(0.325)


# ---------------------------------------------------------------------------
# compute_priorities
# ---------------------------------------------------------------------------

class TestComputePriorities:
    """测试 compute_priorities() 批量方法。"""

    def test_batch_priorities_sorted_desc(self, binding_protocol, sample_path):
        """批量计算应按优先级降序排列。"""
        result = binding_protocol.compute_priorities(
            ["search_skill", "convert_skill", "chart_skill"], sample_path
        )
        # search_skill(0.5) > chart_skill(0.15) > convert_skill(0.15)
        # chart_skill 和 convert_skill 优先级相同(都是 0.15),顺序由 sort 稳定性决定
        assert len(result) == 3
        # 验证降序
        priorities = [p for _, p in result]
        assert priorities == sorted(priorities, reverse=True)
        # search_skill 应排首位(最高优先级)
        assert result[0][0] == "search_skill"
        assert result[0][1] == pytest.approx(0.5)

    def test_batch_priorities_empty_list(self, binding_protocol, sample_path):
        """空技能列表应返回空结果。"""
        assert binding_protocol.compute_priorities([], sample_path) == []

    def test_batch_priorities_no_path(self, binding_protocol):
        """无路径时批量计算应全部使用权重(系数 1.0)。"""
        result = binding_protocol.compute_priorities(
            ["search_skill", "convert_skill"], path=None
        )
        # 两者权重均为 0.5,无路径 → 0.5 * 1.0 / 1 = 0.5
        assert len(result) == 2
        for _, priority in result:
            assert priority == pytest.approx(0.5)

    def test_batch_priorities_unbound_skill(self, binding_protocol, sample_path):
        """未绑定的技能优先级应为 0.0。"""
        result = binding_protocol.compute_priorities(
            ["unbound_skill"], sample_path
        )
        assert result == [("unbound_skill", 0.0)]
