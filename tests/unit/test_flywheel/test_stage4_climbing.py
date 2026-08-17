"""
飞轮 ④ 爬坡进化环单元测试。

测试模块: fnixagent.core.flywheel.stage4_climbing
覆盖:
    - should_trigger(): 进化间隔判断
    - 范式检测: 高频任务范式
    - 常用推理链路: Top-N 路径
    - 高频技能组合检测
    - 薄弱链路修复
    - 技能优先级调整
    - 范式固化
    - 全局旧知识衰减
    - run() 完整流程与快照
    - get_evolution_history()
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import time

import pytest

from fnixagent.core.flywheel.stage4_climbing import (
    DEFAULT_EVOLUTION_INTERVAL,
    HillClimbingFlywheel,
)
from fnixagent.core.types import (
    FlywheelStage,
    NodeType,
    ReasoningMode,
    TopologyLayer,
    TraceRecord,
)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_trace(goal, success=True, tool_calls=None, concept_path=None):
    """快速构造 TraceRecord。"""
    return TraceRecord(
        trace_id=f"trace-{goal[:10]}-{time.time()}",
        task_id="task-x",
        goal=goal,
        mode=ReasoningMode.REACT,
        concept_path=concept_path or [],
        tool_calls=tool_calls or [],
        success=success,
        duration_ms=100.0,
        usage_tokens=50,
        reflection_score=0.0,
        created_at=time.time(),
    )


# ---------------------------------------------------------------------------
# should_trigger
# ---------------------------------------------------------------------------


class TestStage4ShouldTrigger:
    """测试 should_trigger() 方法。"""

    def test_triggers_at_interval(self, sample_graph):
        """达到进化间隔时应返回 True。"""
        fw = HillClimbingFlywheel(sample_graph, evolution_interval=3)
        assert fw.should_trigger() is False
        assert fw.should_trigger() is False
        assert fw.should_trigger() is True

    def test_default_interval(self, sample_graph):
        """默认进化间隔应为 100。"""
        assert DEFAULT_EVOLUTION_INTERVAL == 100
        fw = HillClimbingFlywheel(sample_graph)
        for _ in range(99):
            assert fw.should_trigger() is False
        assert fw.should_trigger() is True

    def test_increments_task_count(self, sample_graph):
        """should_trigger 应递增内部计数器。"""
        fw = HillClimbingFlywheel(sample_graph, evolution_interval=10)
        fw.should_trigger()
        fw.should_trigger()
        assert fw._task_count == 2


# ---------------------------------------------------------------------------
# 范式检测
# ---------------------------------------------------------------------------


class TestStage4DetectPatterns:
    """测试高频任务范式检测。"""

    def test_detects_frequent_patterns(self, sample_graph):
        """出现>=3 次的相似目标应被检测为范式。"""
        fw = HillClimbingFlywheel(sample_graph)
        traces = [
            _make_trace("撰写论文综述详细版本"),
            _make_trace("撰写论文综述详细版本"),
            _make_trace("撰写论文综述详细版本"),
        ]
        patterns = fw._detect_patterns(traces)
        assert len(patterns) == 1
        assert patterns[0]["count"] == 3

    def test_ignores_infrequent_goals(self, sample_graph):
        """出现<3 次的目标不应被检测为范式。"""
        fw = HillClimbingFlywheel(sample_graph)
        traces = [
            _make_trace("撰写论文综述"),
            _make_trace("撰写论文综述"),
            _make_trace("完全不同的任务"),
        ]
        patterns = fw._detect_patterns(traces)
        # "撰写论文综述" 仅出现 2 次 < 3
        assert len(patterns) == 0

    def test_empty_traces_returns_empty(self, sample_graph):
        """空轨迹列表应返回空范式。"""
        fw = HillClimbingFlywheel(sample_graph)
        assert fw._detect_patterns([]) == []

    def test_pattern_contains_success_rate(self, sample_graph):
        """范式应包含 success_rate 字段。"""
        fw = HillClimbingFlywheel(sample_graph)
        traces = [
            _make_trace("分析数据报告", success=True),
            _make_trace("分析数据报告", success=True),
            _make_trace("分析数据报告", success=False),
        ]
        patterns = fw._detect_patterns(traces)
        assert len(patterns) == 1
        assert patterns[0]["success_rate"] == pytest.approx(2 / 3, rel=1e-2)


# ---------------------------------------------------------------------------
# 技能组合检测
# ---------------------------------------------------------------------------


class TestStage4DetectSkillCombos:
    """测试高频技能组合检测。"""

    def test_detects_frequent_combos(self, sample_graph):
        """出现>=3 次的技能组合应被检测。"""
        fw = HillClimbingFlywheel(sample_graph)
        tool_calls = [
            {"name": "search_paper", "args": {}, "status": "success"},
            {"name": "analyze_data", "args": {}, "status": "success"},
        ]
        traces = [_make_trace("g", tool_calls=tool_calls) for _ in range(3)]
        combos = fw._detect_skill_combos(traces)
        assert len(combos) == 1
        assert set(combos[0]["skills"]) == {"search_paper", "analyze_data"}
        assert combos[0]["count"] == 3

    def test_ignores_single_skill(self, sample_graph):
        """单个技能(无组合)不应被检测。"""
        fw = HillClimbingFlywheel(sample_graph)
        traces = [
            _make_trace("g", tool_calls=[{"name": "search_paper", "args": {}, "status": "success"}])
            for _ in range(5)
        ]
        combos = fw._detect_skill_combos(traces)
        assert len(combos) == 0

    def test_empty_traces_returns_empty(self, sample_graph):
        """空轨迹列表应返回空组合。"""
        fw = HillClimbingFlywheel(sample_graph)
        assert fw._detect_skill_combos([]) == []


# ---------------------------------------------------------------------------
# 常用推理链路
# ---------------------------------------------------------------------------


class TestStage4FindTopPaths:
    """测试常用推理链路查找。"""

    def test_returns_list(self, sample_graph):
        """_find_top_paths 应返回列表。"""
        fw = HillClimbingFlywheel(sample_graph)
        paths = fw._find_top_paths()
        assert isinstance(paths, list)

    def test_includes_concept_out_edges(self, sample_graph):
        """应包含 L2 概念节点的出边信息。"""
        fw = HillClimbingFlywheel(sample_graph)
        paths = fw._find_top_paths()
        # sample_graph 中 L2:concept1 有 2 条出边(CONTAINS + DEPENDS_ON)
        # L2:concept2 无出边
        assert len(paths) >= 1
        concept_names = [p["concept"] for p in paths]
        assert "文献检索" in concept_names

    def test_paths_sorted_by_concept_weight(self, sample_graph):
        """路径应按概念节点权重降序排列。"""
        # 调整权重使排序可验证
        c1 = sample_graph.get_node("L2:concept1")
        c2 = sample_graph.get_node("L2:concept2")
        c1.weight = 0.9
        c2.weight = 0.1
        fw = HillClimbingFlywheel(sample_graph)
        paths = fw._find_top_paths()
        if len(paths) >= 2:
            assert paths[0]["concept_weight"] >= paths[1]["concept_weight"]


# ---------------------------------------------------------------------------
# 薄弱链路修复
# ---------------------------------------------------------------------------


class TestStage4FixWeakLinks:
    """测试薄弱链路修复。"""

    def test_fixes_low_weight_high_usage_nodes(self, sample_graph):
        """低权重但高频使用的节点应被提升。"""
        node = sample_graph.get_node("L2:concept2")
        node.weight = 0.2  # 低于 0.3
        fw = HillClimbingFlywheel(sample_graph)
        traces = [_make_trace("g", concept_path=["L2:concept2"]) for _ in range(3)]
        fixed = fw._fix_weak_links(traces)
        assert fixed >= 1
        assert node.weight > 0.2

    def test_skips_high_weight_nodes(self, sample_graph):
        """高权重节点不应被修复(即使高频使用)。"""
        node = sample_graph.get_node("L2:concept1")
        node.weight = 0.8  # 高于 0.3
        original = node.weight
        fw = HillClimbingFlywheel(sample_graph)
        traces = [_make_trace("g", concept_path=["L2:concept1"]) for _ in range(5)]
        fixed = fw._fix_weak_links(traces)
        assert fixed == 0

    def test_skips_low_usage_nodes(self, sample_graph):
        """低使用频次的节点不应被修复(即使低权重)。"""
        node = sample_graph.get_node("L2:concept2")
        node.weight = 0.1
        fw = HillClimbingFlywheel(sample_graph)
        traces = [_make_trace("g", concept_path=["L2:concept2"])]  # 仅 1 次
        fixed = fw._fix_weak_links(traces)
        assert fixed == 0


# ---------------------------------------------------------------------------
# 技能优先级调整
# ---------------------------------------------------------------------------


class TestStage4AdjustSkillPriorities:
    """测试技能优先级调整。"""

    def test_adjusts_high_success_rate_skills(self, sample_graph):
        """高成功率的技能绑定的概念节点应被强化。"""
        fw = HillClimbingFlywheel(sample_graph)
        tool_calls = [
            {"name": "search_paper", "args": {}, "status": "success"},
        ]
        traces = [_make_trace("g", tool_calls=tool_calls, success=True) for _ in range(4)]
        node = sample_graph.get_node("L2:concept1")  # 绑定 search_paper
        original_weight = node.weight
        adjusted = fw._adjust_skill_priorities(traces)
        assert adjusted >= 1
        assert node.weight > original_weight

    def test_skips_low_success_rate_skills(self, sample_graph):
        """低成功率的技能不应被调整。"""
        fw = HillClimbingFlywheel(sample_graph)
        traces = [
            _make_trace(
                "g",
                tool_calls=[{"name": "search_paper", "args": {}, "status": "failed"}],
                success=False,
            )
            for _ in range(4)
        ]
        node = sample_graph.get_node("L2:concept1")
        original_weight = node.weight
        adjusted = fw._adjust_skill_priorities(traces)
        assert adjusted == 0
        assert node.weight == original_weight

    def test_empty_traces_returns_zero(self, sample_graph):
        """空轨迹列表应返回 0。"""
        fw = HillClimbingFlywheel(sample_graph)
        assert fw._adjust_skill_priorities([]) == 0


# ---------------------------------------------------------------------------
# 范式固化
# ---------------------------------------------------------------------------


class TestStage4SolidifyPatterns:
    """测试范式固化为 L3 规则节点。"""

    def test_solidifies_high_success_pattern(self, sample_graph):
        """高成功率的范式应被固化为 L3 RULE 节点。"""
        fw = HillClimbingFlywheel(sample_graph)
        patterns = [
            {
                "signature": "撰写论文综述",
                "count": 5,
                "representative_goal": "撰写论文综述详细版",
                "success_rate": 0.8,
            }
        ]
        solidified = fw._solidify_patterns(patterns)
        assert solidified >= 1
        rules = sample_graph.list_nodes(layer=TopologyLayer.L3_RULE, node_type=NodeType.RULE)
        names = [r.name for r in rules]
        assert any("pattern:" in n for n in names)

    def test_skips_low_success_pattern(self, sample_graph):
        """低成功率(< 0.5)的范式不应被固化。"""
        fw = HillClimbingFlywheel(sample_graph)
        patterns = [
            {
                "signature": "失败任务",
                "count": 5,
                "representative_goal": "失败任务详细",
                "success_rate": 0.3,
            }
        ]
        solidified = fw._solidify_patterns(patterns)
        assert solidified == 0

    def test_does_not_duplicate(self, sample_graph):
        """已固化的范式不应重复添加。"""
        fw = HillClimbingFlywheel(sample_graph)
        patterns = [
            {
                "signature": "撰写论文综述",
                "count": 5,
                "representative_goal": "撰写论文综述",
                "success_rate": 0.9,
            }
        ]
        fw._solidify_patterns(patterns)
        solidified = fw._solidify_patterns(patterns)
        assert solidified == 0


# ---------------------------------------------------------------------------
# 全局衰减
# ---------------------------------------------------------------------------


class TestStage4GlobalDecay:
    """测试全局旧知识衰减。"""

    def test_decays_all_nodes(self, sample_graph):
        """全局衰减应处理全部节点(freshness 降低)。"""
        node = sample_graph.get_node("L1:goal1")
        original_freshness = node.freshness
        fw = HillClimbingFlywheel(sample_graph)
        decayed, stale = fw._apply_global_decay()
        assert decayed >= 1
        assert node.freshness < original_freshness

    def test_marks_stale_for_old_unused_nodes(self, sample_graph):
        """30天未使用且 use_count=0 的节点应标记 stale。"""
        node = sample_graph.get_node("L4:fact1")
        node.created_at = time.time() - 31 * 86400  # 31天前创建
        node.use_count = 0
        node.last_used_at = 0.0
        fw = HillClimbingFlywheel(sample_graph)
        decayed, stale = fw._apply_global_decay()
        assert stale >= 1
        assert node.metadata.get("stale") is True

    def test_returns_tuple_of_ints(self, sample_graph):
        """应返回 (衰减数, stale数) 整数元组。"""
        fw = HillClimbingFlywheel(sample_graph)
        decayed, stale = fw._apply_global_decay()
        assert isinstance(decayed, int)
        assert isinstance(stale, int)


# ---------------------------------------------------------------------------
# run() 完整流程
# ---------------------------------------------------------------------------


class TestStage4Run:
    """测试 run() 完整流程。"""

    def test_run_returns_expected_keys(self, sample_graph, sample_trace, fake_snapshot_manager):
        """run() 返回的 dict 应包含全部预期键。"""
        fw = HillClimbingFlywheel(
            sample_graph, snapshot_manager=fake_snapshot_manager, evolution_interval=1
        )
        result = fw.run([sample_trace])
        expected_keys = {
            "analyzed_traces",
            "patterns_detected",
            "top_paths",
            "skill_combos",
            "weak_links_fixed",
            "skills_adjusted",
            "patterns_solidified",
            "decayed_nodes",
            "stale_nodes",
            "snapshot_created",
            "rolled_back",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_run_analyzes_traces_count(self, sample_graph, sample_trace):
        """run() 应正确统计分析的轨迹数。"""
        fw = HillClimbingFlywheel(sample_graph)
        result = fw.run([sample_trace])
        assert result["analyzed_traces"] == 1

    def test_run_creates_snapshots(self, sample_graph, sample_trace, fake_snapshot_manager):
        """有 snapshot_manager 时应创建快照。"""
        fw = HillClimbingFlywheel(sample_graph, snapshot_manager=fake_snapshot_manager)
        result = fw.run([sample_trace])
        assert result["snapshot_created"] is True
        # 应创建 pre 和 post 两个快照
        assert fake_snapshot_manager.create_count >= 2

    def test_run_without_snapshot_manager(self, sample_graph, sample_trace):
        """无 snapshot_manager 时应正常执行。"""
        fw = HillClimbingFlywheel(sample_graph)
        result = fw.run([sample_trace])
        assert result["snapshot_created"] is False
        assert result["rolled_back"] is False

    def test_run_resets_task_count(self, sample_graph, sample_trace):
        """run() 后应重置 task_count。"""
        fw = HillClimbingFlywheel(sample_graph)
        fw._task_count = 50
        fw.run([sample_trace])
        assert fw._task_count == 0

    def test_run_empty_traces(self, sample_graph):
        """空轨迹列表时 run() 应正常返回。"""
        fw = HillClimbingFlywheel(sample_graph)
        result = fw.run([])
        assert result["analyzed_traces"] == 0
        assert result["patterns_detected"] == 0

    def test_run_no_rollback_on_first_run(self, sample_graph, sample_trace):
        """首次 run 不应触发回滚。"""
        fw = HillClimbingFlywheel(sample_graph)
        result = fw.run([sample_trace])
        assert result["rolled_back"] is False

    def test_run_detects_patterns(self, sample_graph):
        """run() 应检测到高频范式。"""
        fw = HillClimbingFlywheel(sample_graph)
        traces = [_make_trace("撰写论文综述版本", success=True) for _ in range(3)]
        result = fw.run(traces)
        assert result["patterns_detected"] >= 1


# ---------------------------------------------------------------------------
# get_evolution_history
# ---------------------------------------------------------------------------


class TestStage4EvolutionHistory:
    """测试 get_evolution_history() 方法。"""

    def test_initial_history_empty(self, sample_graph):
        """初始进化历史应为空。"""
        fw = HillClimbingFlywheel(sample_graph)
        assert fw.get_evolution_history() == []

    def test_history_populated_after_run(self, sample_graph, sample_trace):
        """run() 后进化历史应包含快照。"""
        fw = HillClimbingFlywheel(sample_graph)
        fw.run([sample_trace])
        history = fw.get_evolution_history()
        assert len(history) == 1

    def test_history_snapshot_has_hill_climbing_stage(self, sample_graph, sample_trace):
        """进化快照的 stage 应为 HILL_CLIMBING。"""
        fw = HillClimbingFlywheel(sample_graph)
        fw.run([sample_trace])
        snapshot = fw.get_evolution_history()[0]
        assert snapshot.stage == FlywheelStage.HILL_CLIMBING

    def test_history_snapshot_has_metrics(self, sample_graph, sample_trace):
        """进化快照应包含性能指标。"""
        fw = HillClimbingFlywheel(sample_graph)
        fw.run([sample_trace])
        snapshot = fw.get_evolution_history()[0]
        assert snapshot.node_count > 0
        assert snapshot.avg_success_rate >= 0.0

    def test_history_returns_copy(self, sample_graph, sample_trace):
        """get_evolution_history 应返回副本(修改不影响内部状态)。"""
        fw = HillClimbingFlywheel(sample_graph)
        fw.run([sample_trace])
        history = fw.get_evolution_history()
        history.clear()
        assert len(fw.get_evolution_history()) == 1

    def test_multiple_runs_accumulate_history(self, sample_graph, sample_trace):
        """多次 run 应累积进化历史。"""
        fw = HillClimbingFlywheel(sample_graph)
        fw.run([sample_trace])
        fw.run([sample_trace])
        assert len(fw.get_evolution_history()) == 2
