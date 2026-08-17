"""
飞轮 ③ 元反思修正环单元测试。

测试模块: fnixagent.core.flywheel.stage3_reflection
覆盖:
    - should_trigger(): 触发间隔判断
    - 三维评估: 路径质量/技能准确率/知识完整性
    - 自动权重调节: 强化/弱化/废弃
    - 知识补充: 从失败轨迹补充 L1 目标节点
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest

from fnixagent.core.flywheel.stage3_reflection import (
    MISSING_KNOWLEDGE_CONFIDENCE,
    MetaReflectionFlywheel,
)
from fnixagent.core.types import NodeType, ReasoningMode, TopologyLayer, TraceRecord


class TestStage3ShouldTrigger:
    """测试 should_trigger() 方法。"""

    def test_triggers_at_interval(self, sample_graph):
        """达到触发间隔时应返回 True。"""
        fw = MetaReflectionFlywheel(sample_graph, trigger_interval=3)
        assert fw.should_trigger() is False  # count=1
        assert fw.should_trigger() is False  # count=2
        assert fw.should_trigger() is True  # count=3

    def test_not_triggered_before_interval(self, sample_graph):
        """未达触发间隔时应返回 False。"""
        fw = MetaReflectionFlywheel(sample_graph, trigger_interval=5)
        for _ in range(4):
            assert fw.should_trigger() is False

    def test_default_interval(self, sample_graph):
        """默认触发间隔应为 5。"""
        fw = MetaReflectionFlywheel(sample_graph)
        for _ in range(4):
            assert fw.should_trigger() is False
        assert fw.should_trigger() is True

    def test_increments_task_count(self, sample_graph):
        """should_trigger 应递增内部计数器。"""
        fw = MetaReflectionFlywheel(sample_graph, trigger_interval=10)
        fw.should_trigger()
        fw.should_trigger()
        assert fw._task_count == 2


class TestStage3EvaluatePathQuality:
    """测试路径质量评估。"""

    def test_empty_traces_returns_zero(self, sample_graph):
        """空轨迹列表应返回 0.0。"""
        fw = MetaReflectionFlywheel(sample_graph)
        assert fw._evaluate_path_quality([]) == 0.0

    def test_all_success_traces(self, sample_graph, sample_trace):
        """全部成功轨迹时路径质量应为 1.0。"""
        fw = MetaReflectionFlywheel(sample_graph)
        quality = fw._evaluate_path_quality([sample_trace])
        assert quality == 1.0

    def test_mixed_traces(self, sample_graph, sample_trace, failed_trace):
        """混合成功/失败轨迹时路径质量应介于 0~1。"""
        fw = MetaReflectionFlywheel(sample_graph)
        # sample_trace: concept_path len=1, success
        # failed_trace: concept_path len=1, fail
        # avg_success_path_len = 1, avg_all_path_len = 1 → 1.0
        quality = fw._evaluate_path_quality([sample_trace, failed_trace])
        assert 0.0 <= quality <= 1.0

    def test_no_success_traces_returns_zero(self, sample_graph, failed_trace):
        """无成功轨迹时应返回 0.0。"""
        fw = MetaReflectionFlywheel(sample_graph)
        assert fw._evaluate_path_quality([failed_trace]) == 0.0


class TestStage3EvaluateSkillAccuracy:
    """测试技能匹配准确率评估。"""

    def test_empty_traces_returns_zero(self, sample_graph):
        """空轨迹列表应返回 0.0。"""
        fw = MetaReflectionFlywheel(sample_graph)
        assert fw._evaluate_skill_accuracy([]) == 0.0

    def test_all_successful_calls(self, sample_graph, sample_trace):
        """全部工具调用成功时准确率应为 1.0。"""
        fw = MetaReflectionFlywheel(sample_graph)
        accuracy = fw._evaluate_skill_accuracy([sample_trace])
        assert accuracy == 1.0

    def test_mixed_calls(self, sample_graph, sample_trace, failed_trace):
        """混合成功/失败调用时准确率应介于 0~1。"""
        fw = MetaReflectionFlywheel(sample_graph)
        accuracy = fw._evaluate_skill_accuracy([sample_trace, failed_trace])
        # sample_trace: 2 success, failed_trace: 1 failed → 2/3
        assert accuracy == pytest.approx(2 / 3, rel=1e-2)

    def test_no_tool_calls_returns_one(self, sample_graph):
        """无工具调用时应返回 1.0(无失败)。"""
        fw = MetaReflectionFlywheel(sample_graph)
        trace = TraceRecord(
            trace_id="t1",
            task_id="tk1",
            goal="test",
            mode=ReasoningMode.REACT,
            tool_calls=[],
            success=True,
        )
        assert fw._evaluate_skill_accuracy([trace]) == 1.0


class TestStage3EvaluateKnowledgeCompleteness:
    """测试知识完整性评估。"""

    def test_small_graph_returns_ratio(self, sample_graph):
        """小规模图(节点<50)应返回 active_nodes/50。"""
        fw = MetaReflectionFlywheel(sample_graph)
        completeness = fw._evaluate_knowledge_completeness([])
        stats = sample_graph.stats()
        assert completeness == pytest.approx(stats["active_nodes"] / 50.0)

    def test_completeness_between_zero_and_one(self, sample_graph, sample_trace):
        """完整性评分应介于 0~1。"""
        fw = MetaReflectionFlywheel(sample_graph)
        completeness = fw._evaluate_knowledge_completeness([sample_trace])
        assert 0.0 <= completeness <= 1.0


class TestStage3AdjustWeights:
    """测试自动权重调节。"""

    def test_success_reinforces_path_nodes(self, sample_graph, sample_trace):
        """成功轨迹应强化 concept_path 上的节点。"""
        fw = MetaReflectionFlywheel(sample_graph)
        node = sample_graph.get_node("L2:concept1")
        original_weight = node.weight
        weakened, strengthened, deprecated = fw._adjust_weights([sample_trace])
        assert strengthened >= 1
        assert node.weight > original_weight

    def test_failure_weakens_path_nodes(self, sample_graph, failed_trace):
        """失败轨迹应弱化 concept_path 上的节点。"""
        fw = MetaReflectionFlywheel(sample_graph)
        node = sample_graph.get_node("L2:concept1")
        original_weight = node.weight
        weakened, strengthened, deprecated = fw._adjust_weights([failed_trace])
        assert weakened >= 1
        assert node.weight < original_weight

    def test_low_weight_deprecated(self, sample_graph, failed_trace):
        """权重低于废弃阈值时应标记 deprecated。"""
        fw = MetaReflectionFlywheel(sample_graph)
        node = sample_graph.get_node("L2:concept1")
        # 设为极低权重,一次惩罚后应低于 DEPRECATE_THRESHOLD
        node.weight = 0.01
        weakened, strengthened, deprecated = fw._adjust_weights([failed_trace])
        assert deprecated >= 1
        assert node.deprecated is True

    def test_nonexistent_node_skipped(self, sample_graph):
        """concept_path 中不存在的节点应被跳过。"""
        fw = MetaReflectionFlywheel(sample_graph)
        trace = TraceRecord(
            trace_id="t1",
            task_id="tk1",
            goal="test",
            mode=ReasoningMode.REACT,
            concept_path=["L2:nonexistent"],
            tool_calls=[{"name": "x", "args": {}, "status": "success"}],
            success=True,
        )
        weakened, strengthened, deprecated = fw._adjust_weights([trace])
        assert weakened == 0
        assert strengthened == 0
        assert deprecated == 0


class TestStage3FillKnowledgeGaps:
    """测试知识补充。"""

    def test_adds_l1_goal_for_failed_trace(self, sample_graph, failed_trace):
        """失败轨迹的 goal 若无对应 L1 节点应补充。"""
        fw = MetaReflectionFlywheel(sample_graph)
        added = fw._fill_knowledge_gaps([failed_trace])
        assert added >= 1
        # 验证新增了 L1 GOAL 节点
        l1_nodes = sample_graph.list_nodes(layer=TopologyLayer.L1_GOAL, node_type=NodeType.GOAL)
        goals = [n.name for n in l1_nodes]
        assert any("执行失败" in g for g in goals)

    def test_skips_successful_traces(self, sample_graph, sample_trace):
        """成功轨迹不应触发知识补充。"""
        fw = MetaReflectionFlywheel(sample_graph)
        added = fw._fill_knowledge_gaps([sample_trace])
        assert added == 0

    def test_new_node_has_low_confidence(self, sample_graph, failed_trace):
        """补充的节点应具有低置信度(0.2)。"""
        fw = MetaReflectionFlywheel(sample_graph)
        fw._fill_knowledge_gaps([failed_trace])
        l1_nodes = sample_graph.list_nodes(layer=TopologyLayer.L1_GOAL, node_type=NodeType.GOAL)
        new_node = [n for n in l1_nodes if "执行失败" in n.name][0]
        assert new_node.confidence == MISSING_KNOWLEDGE_CONFIDENCE

    def test_existing_goal_not_duplicated(self, sample_graph):
        """已有同名 L1 目标节点时不应重复添加。"""
        fw = MetaReflectionFlywheel(sample_graph)
        trace = TraceRecord(
            trace_id="t1",
            task_id="tk1",
            goal="撰写论文综述",
            mode=ReasoningMode.REACT,
            concept_path=[],
            tool_calls=[{"name": "x", "args": {}, "status": "failed"}],
            success=False,
        )
        # sample_graph 已有 L1:goal1 name="撰写论文综述"
        added = fw._fill_knowledge_gaps([trace])
        assert added == 0


class TestStage3Run:
    """测试 run() 方法。"""

    def test_run_returns_expected_keys(self, sample_graph, sample_trace, failed_trace):
        """run() 返回的 dict 应包含全部预期键。"""
        fw = MetaReflectionFlywheel(sample_graph)
        result = fw.run([sample_trace, failed_trace])
        expected_keys = {
            "evaluated_traces",
            "path_quality",
            "skill_accuracy",
            "knowledge_completeness",
            "weakened_paths",
            "strengthened_paths",
            "deprecated_paths",
            "added_nodes",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_run_evaluates_traces_count(self, sample_graph, sample_trace, failed_trace):
        """run() 应正确统计评估的轨迹数。"""
        fw = MetaReflectionFlywheel(sample_graph)
        result = fw.run([sample_trace, failed_trace])
        assert result["evaluated_traces"] == 2

    def test_run_resets_task_count(self, sample_graph, sample_trace):
        """run() 后应重置 task_count。"""
        fw = MetaReflectionFlywheel(sample_graph)
        fw._task_count = 5
        fw.run([sample_trace])
        assert fw._task_count == 0

    def test_run_with_empty_traces(self, sample_graph):
        """空轨迹列表时 run() 应正常返回。"""
        fw = MetaReflectionFlywheel(sample_graph)
        result = fw.run([])
        assert result["evaluated_traces"] == 0
        assert result["path_quality"] == 0.0
        assert result["skill_accuracy"] == 0.0
