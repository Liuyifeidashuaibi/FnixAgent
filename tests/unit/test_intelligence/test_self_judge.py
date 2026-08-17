"""L7 自我审判层 (SelfJudge) 单元测试。

无 LLM/网络依赖, 纯本地评分逻辑。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.intelligence.self_judge import (
    JudgeVerdict,
    SelfJudge,
)


class TestSelfJudge:
    """SelfJudge 核心功能测试。"""

    def test_evaluate_returns_verdict(self):
        """evaluate 应返回 JudgeVerdict 对象。"""
        judge = SelfJudge()
        verdict = judge.evaluate(
            {
                "correctness": 0.9,
                "completeness": 0.85,
                "efficiency": 0.8,
                "safety": 0.95,
                "innovation": 0.7,
                "robustness": 0.8,
                "consistency": 0.85,
            }
        )
        assert isinstance(verdict, JudgeVerdict)
        assert isinstance(verdict.overall_score, float)
        assert 0.0 <= verdict.overall_score <= 1.0
        assert isinstance(verdict.verdict_id, str)
        assert isinstance(verdict.scores, dict)
        assert len(verdict.scores) > 0
        # 应记录到历史
        assert len(judge._verdicts) == 1

    def test_evaluate_multiple_times(self):
        """多次 evaluate 应累积历史。"""
        judge = SelfJudge()
        for i in range(3):
            judge.evaluate({"correctness": 0.8 + i * 0.05, "completeness": 0.7})
        assert len(judge._verdicts) == 3

    def test_evolve_returns_dict(self):
        """evolve 应返回 dict, 含 threshold_changes 和 weight_adjustments。"""
        judge = SelfJudge()
        # 先评估几次 (evolve 依赖历史)
        for _ in range(6):
            judge.evaluate({"correctness": 0.92, "completeness": 0.9})
        result = judge.evolve()
        assert isinstance(result, dict)
        assert "threshold_changes" in result
        assert "weight_adjustments" in result

    def test_get_report(self):
        """get_report 应返回汇总报告 dict。"""
        judge = SelfJudge()
        # 空状态
        report = judge.get_report()
        assert isinstance(report, dict)
        assert "total_verdicts" in report
        assert "latest_verdict" in report
        assert "average_score" in report
        assert "criteria_report" in report
        assert "regression_events" in report
        assert report["total_verdicts"] == 0
        # 评估后
        judge.evaluate({"correctness": 0.85, "completeness": 0.8})
        report2 = judge.get_report()
        assert report2["total_verdicts"] == 1
        assert report2["latest_verdict"] is not None
        assert report2["average_score"] > 0.0

    def test_set_baseline_and_compare(self):
        """set_baseline + compare_with_baseline 应正常工作。"""
        judge = SelfJudge()
        judge.set_baseline({"correctness": 0.7, "completeness": 0.7})
        judge.evaluate({"correctness": 0.9, "completeness": 0.85})
        comparison = judge.compare_with_baseline()
        assert isinstance(comparison, dict)

    def test_judge_evolution_cycle(self):
        """judge_evolution_cycle 应返回 JudgeVerdict。"""
        judge = SelfJudge()
        before_stats = {"success": True, "tool_calls": 3, "duration_ms": 1000}
        after_evolutions = [
            {"success": True, "estimated_token_saving": 200},
        ]
        verdict = judge.judge_evolution_cycle(before_stats, after_evolutions)
        assert isinstance(verdict, JudgeVerdict)
        assert hasattr(verdict, "improvement_detected")
        assert hasattr(verdict, "passed")
        assert hasattr(verdict, "verdict")

    def test_get_improvement_suggestions(self):
        """get_improvement_suggestions 应返回 list。"""
        judge = SelfJudge()
        # 空历史
        assert isinstance(judge.get_improvement_suggestions(), list)
        # 有历史后
        for _ in range(3):
            judge.evaluate({"correctness": 0.3, "completeness": 0.3})
        suggestions = judge.get_improvement_suggestions()
        assert isinstance(suggestions, list)
