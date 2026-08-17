"""
知识拓扑图 (KTG) 权重体系单元测试。

测试模块: fnixagent.core.topology.weights
覆盖:
    - 固化常量值校验
    - 纯函数: clamp_weight, reinforce, penalize, decay, should_deprecate
    - 节点操作: node_on_hit, node_daily_decay, node_on_skill_success, node_on_skill_failure
    - 边操作: edge_on_path_hit, edge_on_failure, edge_daily_decay
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest

from fnixagent.core.topology import weights
from fnixagent.core.types import (
    EdgeType,
    TopologyEdge,
)

# ---------------------------------------------------------------------------
# 固化常量
# ---------------------------------------------------------------------------


class TestConstants:
    """测试权重体系固化常量。"""

    def test_initial_weight(self):
        """INITIAL_WEIGHT 应为 0.5。"""
        assert weights.INITIAL_WEIGHT == 0.5

    def test_success_bonus(self):
        """SUCCESS_BONUS 应为 0.05。"""
        assert weights.SUCCESS_BONUS == 0.05

    def test_failure_penalty(self):
        """FAILURE_PENALTY 应为 -0.08。"""
        assert weights.FAILURE_PENALTY == -0.08

    def test_daily_decay(self):
        """DAILY_DECAY 应为 0.999。"""
        assert weights.DAILY_DECAY == 0.999

    def test_deprecate_threshold(self):
        """DEPRECATE_THRESHOLD 应为 0.05。"""
        assert weights.DEPRECATE_THRESHOLD == 0.05

    def test_confidence_init(self):
        """CONFIDENCE_INIT 应为 0.3。"""
        assert weights.CONFIDENCE_INIT == 0.3

    def test_max_weight(self):
        """MAX_WEIGHT 应为 1.0。"""
        assert weights.MAX_WEIGHT == 1.0

    def test_min_weight(self):
        """MIN_WEIGHT 应为 0.0。"""
        assert weights.MIN_WEIGHT == 0.0

    def test_deprecated_weight(self):
        """DEPRECATED_WEIGHT 应为 0.01。"""
        assert weights.DEPRECATED_WEIGHT == 0.01


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


class TestClampWeight:
    """测试 clamp_weight() 函数。"""

    def test_within_range(self):
        """范围内的值应不变。"""
        assert weights.clamp_weight(0.5) == 0.5

    def test_above_max(self):
        """超过上限应钳制为 MAX_WEIGHT。"""
        assert weights.clamp_weight(1.5) == 1.0

    def test_below_min(self):
        """低于下限应钳制为 MIN_WEIGHT。"""
        assert weights.clamp_weight(-0.5) == 0.0

    def test_at_max_boundary(self):
        """边界值 1.0 应不变。"""
        assert weights.clamp_weight(1.0) == 1.0

    def test_at_min_boundary(self):
        """边界值 0.0 应不变。"""
        assert weights.clamp_weight(0.0) == 0.0


class TestReinforce:
    """测试 reinforce() 函数。"""

    def test_default_increment(self):
        """默认增量 SINGLE_INCREMENT=0.02。"""
        assert weights.reinforce(0.5) == pytest.approx(0.52)

    def test_custom_increment(self):
        """自定义增量。"""
        assert weights.reinforce(0.5, 0.1) == pytest.approx(0.6)

    def test_clamp_at_max(self):
        """强化后超过上限应钳制为 1.0。"""
        assert weights.reinforce(0.99, 0.1) == 1.0

    def test_negative_weight_reinforced(self):
        """负权重强化后被钳制为 0.0(MIN_WEIGHT)。"""
        assert weights.reinforce(-0.5) == 0.0


class TestPenalize:
    """测试 penalize() 函数。"""

    def test_default_penalty(self):
        """默认惩罚 FAILURE_PENALTY=-0.08。"""
        assert weights.penalize(0.5) == pytest.approx(0.42)

    def test_custom_penalty(self):
        """自定义惩罚值。"""
        assert weights.penalize(0.5, -0.1) == pytest.approx(0.4)

    def test_clamp_at_min(self):
        """惩罚后低于下限应钳制为 0.0。"""
        assert weights.penalize(0.05) == 0.0


class TestDecay:
    """测试 decay() 函数。"""

    def test_default_factor(self):
        """默认衰减系数 DAILY_DECAY=0.999。"""
        assert weights.decay(0.5) == pytest.approx(0.5 * 0.999)

    def test_custom_factor(self):
        """自定义衰减系数。"""
        assert weights.decay(1.0, 0.5) == pytest.approx(0.5)

    def test_decay_stays_non_negative(self):
        """衰减后权重不低于 MIN_WEIGHT(非负)。"""
        # 0.0 衰减后仍为 0.0
        assert weights.decay(0.0, 0.1) == 0.0
        # 正数衰减后为更小的正数(在 [0,1] 范围内不触发钳制)
        result = weights.decay(0.001, 0.1)
        assert result >= weights.MIN_WEIGHT


class TestShouldDeprecate:
    """测试 should_deprecate() 函数。"""

    def test_below_threshold(self):
        """权重低于阈值应返回 True。"""
        assert weights.should_deprecate(0.04) is True

    def test_at_threshold(self):
        """权重等于阈值应返回 False(严格小于)。"""
        assert weights.should_deprecate(0.05) is False

    def test_above_threshold(self):
        """权重高于阈值应返回 False。"""
        assert weights.should_deprecate(0.5) is False

    def test_zero_weight(self):
        """权重为 0 应返回 True。"""
        assert weights.should_deprecate(0.0) is True


# ---------------------------------------------------------------------------
# 节点权重操作
# ---------------------------------------------------------------------------


class TestNodeOnHit:
    """测试 node_on_hit() 函数。"""

    def test_weight_increases(self, sample_node):
        """命中后权重应增加 SINGLE_INCREMENT。"""
        original_weight = sample_node.weight
        weights.node_on_hit(sample_node)
        assert sample_node.weight == pytest.approx(original_weight + weights.SINGLE_INCREMENT)

    def test_confidence_increases(self, sample_node):
        """命中后置信度应增加 CONFIDENCE_INCREMENT。"""
        original_conf = sample_node.confidence
        weights.node_on_hit(sample_node)
        assert sample_node.confidence == pytest.approx(original_conf + weights.CONFIDENCE_INCREMENT)

    def test_use_count_increments(self, sample_node):
        """命中后 use_count 应 +1。"""
        original_count = sample_node.use_count
        weights.node_on_hit(sample_node)
        assert sample_node.use_count == original_count + 1

    def test_freshness_reset(self, sample_node):
        """命中后 freshness 应重置为 1.0。"""
        sample_node.freshness = 0.5
        weights.node_on_hit(sample_node)
        assert sample_node.freshness == 1.0

    def test_last_used_at_updated(self, sample_node):
        """命中后 last_used_at 应更新为当前时间。"""
        sample_node.last_used_at = 0.0
        weights.node_on_hit(sample_node)
        assert sample_node.last_used_at > 0.0

    def test_confidence_clamped_at_max(self, sample_node):
        """置信度达到上限后不再增加。"""
        sample_node.confidence = 0.99
        weights.node_on_hit(sample_node)
        assert sample_node.confidence == weights.CONFIDENCE_MAX

    def test_weight_clamped_at_max(self, sample_node):
        """权重达到上限后不再增加。"""
        sample_node.weight = 0.99
        weights.node_on_hit(sample_node)
        assert sample_node.weight == weights.MAX_WEIGHT

    def test_returns_same_node(self, sample_node):
        """函数应返回被修改的同一节点对象。"""
        result = weights.node_on_hit(sample_node)
        assert result is sample_node


class TestNodeDailyDecay:
    """测试 node_daily_decay() 函数。"""

    def test_freshness_decays(self, sample_node):
        """每日衰减后 freshness 应乘以 DAILY_DECAY。"""
        sample_node.freshness = 1.0
        weights.node_daily_decay(sample_node)
        assert sample_node.freshness == pytest.approx(1.0 * weights.DAILY_DECAY)

    def test_no_stale_penalty_when_fresh(self, sample_node):
        """freshness 较高时不触发 stale 惩罚。"""
        sample_node.freshness = 1.0
        sample_node.use_count = 0
        sample_node.weight = 0.5
        weights.node_daily_decay(sample_node)
        # freshness=0.999 > STALE_FRESHNESS=0.3,无 stale 惩罚
        assert sample_node.weight == 0.5

    def test_stale_penalty_applied(self, sample_node):
        """freshness 低且 use_count 低时应触发 stale 惩罚。"""
        sample_node.freshness = 0.2  # < STALE_FRESHNESS=0.3
        sample_node.use_count = 0  # < STALE_USE_COUNT=5
        sample_node.weight = 0.5
        weights.node_daily_decay(sample_node)
        # freshness 先 *= 0.999 → 0.1998(仍 < 0.3)
        # stale 惩罚: weight *= 0.95 → 0.475
        assert sample_node.weight == pytest.approx(0.5 * weights.STALE_PENALTY_FACTOR)

    def test_no_stale_penalty_when_use_count_high(self, sample_node):
        """use_count 较高时不触发 stale 惩罚。"""
        sample_node.freshness = 0.2
        sample_node.use_count = 10  # >= STALE_USE_COUNT=5
        sample_node.weight = 0.5
        weights.node_daily_decay(sample_node)
        assert sample_node.weight == 0.5  # 无 stale 惩罚

    def test_deprecate_when_weight_below_threshold(self, sample_node):
        """权重低于废弃阈值时应标记 deprecated。"""
        sample_node.weight = 0.04  # < DEPRECATE_THRESHOLD=0.05
        sample_node.freshness = 1.0
        sample_node.use_count = 10
        sample_node.deprecated = False
        weights.node_daily_decay(sample_node)
        assert sample_node.deprecated is True
        assert sample_node.weight == weights.DEPRECATED_WEIGHT

    def test_no_deprecate_when_weight_above_threshold(self, sample_node):
        """权重高于废弃阈值时不应标记 deprecated。"""
        sample_node.weight = 0.5
        sample_node.freshness = 1.0
        sample_node.use_count = 10
        sample_node.deprecated = False
        weights.node_daily_decay(sample_node)
        assert sample_node.deprecated is False


class TestNodeOnSkillSuccess:
    """测试 node_on_skill_success() 函数。"""

    def test_weight_increases_by_bonus(self, sample_node):
        """技能成功后权重应增加 SUCCESS_BONUS。"""
        sample_node.weight = 0.5
        weights.node_on_skill_success(sample_node)
        assert sample_node.weight == pytest.approx(0.5 + weights.SUCCESS_BONUS)

    def test_weight_clamped_at_max(self, sample_node):
        """权重达到上限后不再增加。"""
        sample_node.weight = 0.99
        weights.node_on_skill_success(sample_node)
        assert sample_node.weight == weights.MAX_WEIGHT

    def test_returns_same_node(self, sample_node):
        """函数应返回同一节点对象。"""
        result = weights.node_on_skill_success(sample_node)
        assert result is sample_node


class TestNodeOnSkillFailure:
    """测试 node_on_skill_failure() 函数。"""

    def test_weight_decreases_by_penalty(self, sample_node):
        """技能失败后权重应减少 |FAILURE_PENALTY|。"""
        sample_node.weight = 0.5
        sample_node.deprecated = False
        weights.node_on_skill_failure(sample_node)
        assert sample_node.weight == pytest.approx(0.5 + weights.FAILURE_PENALTY)

    def test_weight_clamped_at_min(self, sample_node):
        """权重降至 0.0 后触发废弃,权重设为 DEPRECATED_WEIGHT。"""
        sample_node.weight = 0.01
        sample_node.deprecated = False
        weights.node_on_skill_failure(sample_node)
        # 0.01 + (-0.08) = -0.07 → clamp 到 0.0 → should_deprecate → DEPRECATED_WEIGHT
        assert sample_node.deprecated is True
        assert sample_node.weight == weights.DEPRECATED_WEIGHT

    def test_deprecate_when_below_threshold(self, sample_node):
        """惩罚后权重低于阈值应标记废弃。"""
        sample_node.weight = 0.04
        sample_node.deprecated = False
        weights.node_on_skill_failure(sample_node)
        assert sample_node.deprecated is True
        assert sample_node.weight == weights.DEPRECATED_WEIGHT

    def test_no_deprecate_when_above_threshold(self, sample_node):
        """惩罚后权重仍高于阈值不应标记废弃。"""
        sample_node.weight = 0.5
        sample_node.deprecated = False
        weights.node_on_skill_failure(sample_node)
        assert sample_node.deprecated is False


# ---------------------------------------------------------------------------
# 边权重操作
# ---------------------------------------------------------------------------


class TestEdgeOnPathHit:
    """测试 edge_on_path_hit() 函数。"""

    def test_normal_edge_reinforced(self):
        """普通边(CAUSAL)命中后权重应增加。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        weights.edge_on_path_hit(edge)
        assert edge.weight == pytest.approx(0.5 + weights.SINGLE_INCREMENT)

    def test_depends_on_edge_reinforced(self):
        """DEPENDS_ON 边命中后权重应增加。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.DEPENDS_ON,
            weight=0.5,
        )
        weights.edge_on_path_hit(edge)
        assert edge.weight == pytest.approx(0.5 + weights.SINGLE_INCREMENT)

    def test_contains_edge_not_reinforced(self):
        """CONTAINS 边(权重固定 1.0)命中后权重不变。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        weights.edge_on_path_hit(edge)
        assert edge.weight == 1.0

    def test_weight_clamped_at_max(self):
        """普通边权重达到上限后不再增加。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.99,
        )
        weights.edge_on_path_hit(edge)
        assert edge.weight == weights.MAX_WEIGHT

    def test_returns_same_edge(self):
        """函数应返回同一边对象。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        result = weights.edge_on_path_hit(edge)
        assert result is edge


class TestEdgeOnFailure:
    """测试 edge_on_failure() 函数。"""

    def test_normal_edge_penalized(self):
        """普通边(CAUSAL)失败后权重应减少 0.03。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        weights.edge_on_failure(edge)
        assert edge.weight == pytest.approx(0.5 - 0.03)

    def test_contains_edge_not_penalized(self):
        """CONTAINS 边(权重固定 1.0)失败后权重不变。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        weights.edge_on_failure(edge)
        assert edge.weight == 1.0

    def test_weight_clamped_at_min(self):
        """普通边权重达到下限后不再减少。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.01,
        )
        weights.edge_on_failure(edge)
        assert edge.weight == weights.MIN_WEIGHT

    def test_returns_same_edge(self):
        """函数应返回同一边对象。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        result = weights.edge_on_failure(edge)
        assert result is edge


class TestEdgeDailyDecay:
    """测试 edge_daily_decay() 函数。"""

    def test_normal_edge_decayed(self):
        """普通边(CAUSAL)每日衰减后权重应乘以 DAILY_DECAY。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        weights.edge_daily_decay(edge)
        assert edge.weight == pytest.approx(0.5 * weights.DAILY_DECAY)

    def test_contains_edge_not_decayed(self):
        """CONTAINS 边(权重固定 1.0)每日衰减后权重不变。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        weights.edge_daily_decay(edge)
        assert edge.weight == 1.0

    def test_deprecate_when_below_threshold(self):
        """衰减后权重低于阈值应标记 deprecated。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.04,
        )
        edge.deprecated = False
        weights.edge_daily_decay(edge)
        assert edge.deprecated is True

    def test_no_deprecate_when_above_threshold(self):
        """衰减后权重高于阈值不应标记 deprecated。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        edge.deprecated = False
        weights.edge_daily_decay(edge)
        assert edge.deprecated is False

    def test_returns_same_edge(self):
        """函数应返回同一边对象。"""
        edge = TopologyEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        result = weights.edge_daily_decay(edge)
        assert result is edge
