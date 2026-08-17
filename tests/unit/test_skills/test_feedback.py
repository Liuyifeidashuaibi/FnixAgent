"""
技能反馈处理器 (SkillFeedbackHandler) 单元测试。

测试模块: fnixagent.core.skills.feedback.SkillFeedbackHandler
覆盖:
    - on_skill_success: 节点权重增加 SUCCESS_BONUS、置信度增加、边强化、统计返回
    - on_skill_failure: 节点权重减少 FAILURE_PENALTY、边惩罚、废弃标记、统计返回
    - process_tool_result: SUCCESS/FAILED/TIMEOUT 自动分发
    - get_success_rate: 空历史/混合/全成功/全失败
    - get_feedback_history: 空历史/有记录
    - get_all_success_rates: 空集合/多技能
    - 滑动窗口大小限制
    - 权重数值精确验证
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest

from fnixagent.core.skills.feedback import SkillFeedbackHandler
from fnixagent.core.topology import weights as weights_mod
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    ToolExecutionStatus,
    ToolResult,
)

# ---------------------------------------------------------------------------
# on_skill_success
# ---------------------------------------------------------------------------


class TestOnSkillSuccess:
    """测试 on_skill_success() 方法。"""

    def test_success_increases_node_weight_by_success_bonus(self, feedback_handler, sample_graph):
        """成功反馈后绑定概念节点权重应增加 SUCCESS_BONUS(+0.05)。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        feedback_handler.on_skill_success("search_skill")
        new_weight = sample_graph.get_node("L2:concept1").weight
        assert new_weight == pytest.approx(initial_weight + weights_mod.SUCCESS_BONUS)

    def test_success_increases_confidence(self, feedback_handler, sample_graph):
        """成功反馈后概念节点置信度应增加 CONFIDENCE_INCREMENT(+0.02)。"""
        initial_confidence = sample_graph.get_node("L2:concept1").confidence
        feedback_handler.on_skill_success("search_skill")
        new_confidence = sample_graph.get_node("L2:concept1").confidence
        assert new_confidence == pytest.approx(
            initial_confidence + weights_mod.CONFIDENCE_INCREMENT
        )

    def test_success_confidence_capped(self, feedback_handler, sample_graph):
        """置信度不应超过 CONFIDENCE_MAX(1.0)。"""
        node = sample_graph.get_node("L2:concept1")
        node.confidence = 0.99
        feedback_handler.on_skill_success("search_skill")
        assert node.confidence == pytest.approx(weights_mod.CONFIDENCE_MAX)

    def test_success_records_success_count(self, feedback_handler, sample_graph):
        """成功反馈应在 metadata 中累计 success_count。"""
        feedback_handler.on_skill_success("search_skill")
        feedback_handler.on_skill_success("search_skill")
        node = sample_graph.get_node("L2:concept1")
        assert node.metadata["success_count"] == 2

    def test_success_reinforces_path_edges(self, feedback_handler, sample_graph, sample_path):
        """成功反馈后路径上的边权重应增加 SINGLE_INCREMENT(+0.02)。"""
        initial_e3 = sample_graph.get_edge("e3").weight
        initial_e4 = sample_graph.get_edge("e4").weight
        feedback_handler.on_skill_success("search_skill", path=sample_path)
        new_e3 = sample_graph.get_edge("e3").weight
        new_e4 = sample_graph.get_edge("e4").weight
        assert new_e3 == pytest.approx(initial_e3 + weights_mod.SINGLE_INCREMENT)
        assert new_e4 == pytest.approx(initial_e4 + weights_mod.SINGLE_INCREMENT)

    def test_success_returns_stats(self, feedback_handler, sample_path):
        """成功反馈应返回包含 concepts_reinforced 和 edges_reinforced 的统计。"""
        stats = feedback_handler.on_skill_success("search_skill", path=sample_path)
        assert stats["concepts_reinforced"] == 1
        assert stats["edges_reinforced"] == 2

    def test_success_with_explicit_concept_node(self, feedback_handler, sample_graph):
        """指定 concept_node_id 时应仅强化该节点。"""
        # search_skill 绑定 concept1,但显式指定 concept2
        initial_c1 = sample_graph.get_node("L2:concept1").weight
        initial_c2 = sample_graph.get_node("L2:concept2").weight
        feedback_handler.on_skill_success("search_skill", concept_node_id="L2:concept2")
        # concept1 不变,concept2 强化
        assert sample_graph.get_node("L2:concept1").weight == pytest.approx(initial_c1)
        assert sample_graph.get_node("L2:concept2").weight == pytest.approx(
            initial_c2 + weights_mod.SUCCESS_BONUS
        )

    def test_success_no_bound_concept(self, feedback_handler):
        """技能未绑定任何概念节点时 stats 中 concepts_reinforced 应为 0。"""
        stats = feedback_handler.on_skill_success("nonexistent_skill")
        assert stats["concepts_reinforced"] == 0
        assert stats["edges_reinforced"] == 0


# ---------------------------------------------------------------------------
# on_skill_failure
# ---------------------------------------------------------------------------


class TestOnSkillFailure:
    """测试 on_skill_failure() 方法。"""

    def test_failure_decreases_node_weight_by_failure_penalty(self, feedback_handler, sample_graph):
        """失败反馈后绑定概念节点权重应减少 FAILURE_PENALTY(-0.08)。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        feedback_handler.on_skill_failure("search_skill")
        new_weight = sample_graph.get_node("L2:concept1").weight
        # FAILURE_PENALTY = -0.08
        assert new_weight == pytest.approx(initial_weight + weights_mod.FAILURE_PENALTY)

    def test_failure_records_failure_count(self, feedback_handler, sample_graph):
        """失败反馈应在 metadata 中累计 failure_count。"""
        feedback_handler.on_skill_failure("search_skill")
        feedback_handler.on_skill_failure("search_skill")
        node = sample_graph.get_node("L2:concept1")
        assert node.metadata["failure_count"] == 2

    def test_failure_records_error_message(self, feedback_handler, sample_graph):
        """传入 error 时应在 metadata 中记录 last_error。"""
        feedback_handler.on_skill_failure("search_skill", error="connection timeout")
        node = sample_graph.get_node("L2:concept1")
        assert node.metadata["last_error"] == "connection timeout"

    def test_failure_penalizes_path_edges(self, feedback_handler, sample_graph, sample_path):
        """失败反馈后路径上的边权重应减少 0.03。"""
        initial_e3 = sample_graph.get_edge("e3").weight
        feedback_handler.on_skill_failure("search_skill", path=sample_path)
        new_e3 = sample_graph.get_edge("e3").weight
        assert new_e3 == pytest.approx(initial_e3 - 0.03)

    def test_failure_returns_stats(self, feedback_handler, sample_path):
        """失败反馈应返回包含 concepts_penalized/edges_penalized/deprecated 的统计。"""
        stats = feedback_handler.on_skill_failure("search_skill", path=sample_path)
        assert stats["concepts_penalized"] == 1
        assert stats["edges_penalized"] == 2
        assert stats["deprecated"] == 0

    def test_failure_deprecation(self, feedback_handler, sample_graph):
        """连续失败导致权重低于 DEPRECATE_THRESHOLD 时应标记 deprecated。"""
        node = sample_graph.get_node("L2:concept1")
        # 初始权重 0.5,每次失败 -0.08
        # 0.5 → 0.42 → 0.34 → 0.26 → 0.18 → 0.10 → 0.02(< 0.05,废弃)
        for _ in range(6):
            feedback_handler.on_skill_failure("search_skill")
        assert node.deprecated is True
        assert node.weight == pytest.approx(weights_mod.DEPRECATED_WEIGHT)

    def test_failure_deprecation_stats(self, feedback_handler, sample_path):
        """废弃标记应在 stats['deprecated'] 中计数。"""
        # 连续失败 6 次,第 6 次触发废弃
        for i in range(6):
            stats = feedback_handler.on_skill_failure("search_skill", path=sample_path)
        # 最后一次应有 deprecated 计数(节点 1 + 可能的边)
        assert stats["deprecated"] >= 1


# ---------------------------------------------------------------------------
# process_tool_result
# ---------------------------------------------------------------------------


class TestProcessToolResult:
    """测试 process_tool_result() 方法。"""

    def test_process_success_result(self, feedback_handler, sample_graph, sample_path):
        """SUCCESS 状态的 ToolResult 应触发成功反馈。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        result = ToolResult(
            call_id="call-1",
            name="search_skill",
            status=ToolExecutionStatus.SUCCESS,
            output={"data": "ok"},
        )
        stats = feedback_handler.process_tool_result("search_skill", result, path=sample_path)
        # 应触发成功反馈
        assert stats["concepts_reinforced"] == 1
        new_weight = sample_graph.get_node("L2:concept1").weight
        assert new_weight == pytest.approx(initial_weight + weights_mod.SUCCESS_BONUS)

    def test_process_failed_result(self, feedback_handler, sample_graph, sample_path):
        """FAILED 状态的 ToolResult 应触发失败反馈。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        result = ToolResult(
            call_id="call-2",
            name="search_skill",
            status=ToolExecutionStatus.FAILED,
            error="something went wrong",
        )
        stats = feedback_handler.process_tool_result("search_skill", result, path=sample_path)
        assert stats["concepts_penalized"] == 1
        new_weight = sample_graph.get_node("L2:concept1").weight
        assert new_weight == pytest.approx(initial_weight + weights_mod.FAILURE_PENALTY)

    def test_process_timeout_result(self, feedback_handler, sample_graph, sample_path):
        """TIMEOUT 状态应按失败处理。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        result = ToolResult(
            call_id="call-3",
            name="search_skill",
            status=ToolExecutionStatus.TIMEOUT,
            error="execution timed out",
        )
        stats = feedback_handler.process_tool_result("search_skill", result, path=sample_path)
        assert stats["concepts_penalized"] == 1
        new_weight = sample_graph.get_node("L2:concept1").weight
        assert new_weight == pytest.approx(initial_weight + weights_mod.FAILURE_PENALTY)

    def test_process_failed_records_error(self, feedback_handler, sample_graph):
        """FAILED 状态的 ToolResult 应将 error 记录到节点 metadata。"""
        result = ToolResult(
            call_id="call-4",
            name="search_skill",
            status=ToolExecutionStatus.FAILED,
            error="network error",
        )
        feedback_handler.process_tool_result("search_skill", result)
        node = sample_graph.get_node("L2:concept1")
        assert node.metadata["last_error"] == "network error"


# ---------------------------------------------------------------------------
# get_success_rate / get_feedback_history / get_all_success_rates
# ---------------------------------------------------------------------------


class TestFeedbackWindow:
    """测试反馈窗口查询方法。"""

    def test_get_success_rate_empty(self, feedback_handler):
        """无历史记录时成功率应为 0.0。"""
        assert feedback_handler.get_success_rate("search_skill") == 0.0

    def test_get_feedback_history_empty(self, feedback_handler):
        """无历史记录时反馈历史应为空列表。"""
        assert feedback_handler.get_feedback_history("search_skill") == []

    def test_get_all_success_rates_empty(self, feedback_handler):
        """无任何反馈记录时 get_all_success_rates 应返回空 dict。"""
        assert feedback_handler.get_all_success_rates() == {}

    def test_success_rate_mixed(self, feedback_handler):
        """混合成功/失败的成功率应正确计算。"""
        feedback_handler.on_skill_success("search_skill")
        feedback_handler.on_skill_failure("search_skill")
        feedback_handler.on_skill_success("search_skill")
        # 2 成功 / 3 总数 = 0.666...
        rate = feedback_handler.get_success_rate("search_skill")
        assert rate == pytest.approx(2 / 3)

    def test_success_rate_all_success(self, feedback_handler):
        """全部成功时成功率应为 1.0。"""
        for _ in range(5):
            feedback_handler.on_skill_success("search_skill")
        assert feedback_handler.get_success_rate("search_skill") == 1.0

    def test_success_rate_all_failure(self, feedback_handler):
        """全部失败时成功率应为 0.0。"""
        for _ in range(3):
            feedback_handler.on_skill_failure("search_skill")
        assert feedback_handler.get_success_rate("search_skill") == 0.0

    def test_feedback_history_records(self, feedback_handler):
        """反馈历史应按顺序记录每次结果(True=成功, False=失败)。"""
        feedback_handler.on_skill_success("search_skill")
        feedback_handler.on_skill_failure("search_skill")
        feedback_handler.on_skill_success("search_skill")
        history = feedback_handler.get_feedback_history("search_skill")
        assert history == [True, False, True]

    def test_feedback_history_returns_copy(self, feedback_handler):
        """get_feedback_history 应返回副本,修改不影响内部状态。"""
        feedback_handler.on_skill_success("search_skill")
        history = feedback_handler.get_feedback_history("search_skill")
        history.append(False)
        # 内部状态不应改变
        assert feedback_handler.get_feedback_history("search_skill") == [True]

    def test_get_all_success_rates_multiple(self, feedback_handler):
        """多个技能的反馈记录应全部出现在 get_all_success_rates 中。"""
        feedback_handler.on_skill_success("search_skill")
        feedback_handler.on_skill_failure("convert_skill")
        rates = feedback_handler.get_all_success_rates()
        assert "search_skill" in rates
        assert "convert_skill" in rates
        assert rates["search_skill"] == 1.0
        assert rates["convert_skill"] == 0.0

    def test_window_size_limit(self, feedback_handler):
        """反馈窗口应限制在 50 条记录以内(先进先出)。"""
        # 记录 60 次成功
        for _ in range(60):
            feedback_handler.on_skill_success("search_skill")
        history = feedback_handler.get_feedback_history("search_skill")
        assert len(history) == 50
        # 成功率仍应为 1.0(全部成功)
        assert feedback_handler.get_success_rate("search_skill") == 1.0

    def test_window_size_mixed_eviction(self, feedback_handler):
        """窗口满后旧记录应被淘汰,成功率反映最近窗口。"""
        # 30 次成功 + 30 次失败 = 60 次,窗口保留最后 50 次(20 成功 + 30 失败)
        for _ in range(30):
            feedback_handler.on_skill_success("search_skill")
        for _ in range(30):
            feedback_handler.on_skill_failure("search_skill")
        history = feedback_handler.get_feedback_history("search_skill")
        assert len(history) == 50
        # 最近 50 次: 20 成功 + 30 失败
        assert sum(history) == 20
        rate = feedback_handler.get_success_rate("search_skill")
        assert rate == pytest.approx(20 / 50)


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """测试边界条件。"""

    def test_success_with_empty_graph(self):
        """空图上调用成功反馈不应抛异常,stats 全为 0。"""
        handler = SkillFeedbackHandler(TopologyGraph())
        stats = handler.on_skill_success("any_skill")
        assert stats["concepts_reinforced"] == 0
        assert stats["edges_reinforced"] == 0

    def test_failure_with_empty_graph(self):
        """空图上调用失败反馈不应抛异常,stats 全为 0。"""
        handler = SkillFeedbackHandler(TopologyGraph())
        stats = handler.on_skill_failure("any_skill")
        assert stats["concepts_penalized"] == 0
        assert stats["edges_penalized"] == 0
        assert stats["deprecated"] == 0

    def test_success_no_path(self, feedback_handler, sample_graph):
        """无路径时成功反馈应仅强化节点,不强化边。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        stats = feedback_handler.on_skill_success("search_skill", path=None)
        assert stats["concepts_reinforced"] == 1
        assert stats["edges_reinforced"] == 0
        new_weight = sample_graph.get_node("L2:concept1").weight
        assert new_weight == pytest.approx(initial_weight + weights_mod.SUCCESS_BONUS)

    def test_failure_no_path(self, feedback_handler, sample_graph):
        """无路径时失败反馈应仅惩罚节点,不惩罚边。"""
        initial_weight = sample_graph.get_node("L2:concept1").weight
        stats = feedback_handler.on_skill_failure("search_skill", path=None)
        assert stats["concepts_penalized"] == 1
        assert stats["edges_penalized"] == 0
        new_weight = sample_graph.get_node("L2:concept1").weight
        assert new_weight == pytest.approx(initial_weight + weights_mod.FAILURE_PENALTY)

    def test_weight_clamped_to_min(self, feedback_handler, sample_graph):
        """节点权重不应低于 MIN_WEIGHT(0.0)。"""
        node = sample_graph.get_node("L2:concept1")
        node.weight = 0.01  # 接近下限
        # 失败一次: 0.01 - 0.08 = -0.07 → clamp 到 0.0
        # 但 0.0 < 0.05 → deprecated, weight = 0.01
        feedback_handler.on_skill_failure("search_skill")
        # 废弃后权重应为 DEPRECATED_WEIGHT=0.01
        assert node.deprecated is True
        assert node.weight == pytest.approx(weights_mod.DEPRECATED_WEIGHT)
