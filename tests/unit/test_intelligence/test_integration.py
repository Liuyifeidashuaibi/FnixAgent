"""集成协调层 (IntelligenceIntegrator) 单元测试。

用 tmp_path 隔离 state_dir 和 workspace, 不污染真实环境。
无 LLM/网络依赖 (GeneticEvolver 真实进化被跳过)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.intelligence.integration import IntelligenceIntegrator


def _make_integrator(tmp_path) -> IntelligenceIntegrator:
    """构造一个隔离的 IntelligenceIntegrator (workspace + state_dir 都在 tmp_path 下)。"""
    ws = str(tmp_path / "workspace")
    state = str(tmp_path / "intel_state")
    return IntelligenceIntegrator(workspace=ws, state_dir=state)


class TestIntelligenceIntegrator:
    """IntelligenceIntegrator 核心功能测试。"""

    def test_integrator_init(self, tmp_path):
        """初始化应成功创建所有子模块。"""
        integrator = _make_integrator(tmp_path)
        assert integrator.workspace  # workspace 非空
        # 七层子模块都应实例化
        assert integrator.memory is not None  # L5
        assert integrator.loop_executor is not None  # L1
        assert integrator.nudge_engine is not None  # L1
        assert integrator.guard is not None  # L3
        assert integrator.judge is not None  # L7
        assert integrator.evolver is not None  # L2
        assert integrator.skill_market is not None  # L6

    def test_pre_task_nudge_returns_string(self, tmp_path):
        """pre_task_nudge 应返回字符串 (可能为空)。"""
        integrator = _make_integrator(tmp_path)
        nudge = integrator.pre_task_nudge(
            "帮我重构认证模块",
            {
                "workspace_kind": "code",
                "reasoning_mode": "react",
            },
        )
        assert isinstance(nudge, str)
        # 空记忆库时可能返回空, 但类型必须是 str
        # 写入记忆后再调用, 应返回非空 nudge
        integrator.memory.add_memory(
            "重构认证模块", "上次重构认证模块用了策略A", memory_type="episodic"
        )
        nudge2 = integrator.pre_task_nudge(
            "重构认证模块",
            {
                "workspace_kind": "code",
            },
        )
        assert isinstance(nudge2, str)
        assert len(nudge2) > 0  # 有记忆时应注入 nudge

    def test_pre_task_nudge_empty_input(self, tmp_path):
        """空 user_input 应返回空字符串。"""
        integrator = _make_integrator(tmp_path)
        assert integrator.pre_task_nudge("", {}) == ""

    def test_post_evolution_returns_dict(self, tmp_path):
        """post_evolution 应返回包含必要字段的 dict。"""
        integrator = _make_integrator(tmp_path)
        result = integrator.post_evolution(
            trace_record={
                "user_input": "实现一个登录接口",
                "tool_calls": [
                    {"name": "read_file", "success": True},
                    {"name": "edit_file", "success": True},
                ],
                "success": True,
                "duration_ms": 1500,
                "workspace_kind": "code",
            },
            mfp_result={"solidified": True, "reflected": None, "climbed": False},
        )
        assert isinstance(result, dict)
        # 必要字段
        assert "guard_level" in result
        assert "judge_verdict" in result
        assert "evolved" in result
        assert "skill_created" in result
        assert "memory_saved" in result
        assert "degraded" in result
        # 成功任务应创建技能并保存记忆
        assert result["skill_created"] is True
        assert result["memory_saved"] is True

    def test_post_evolution_failed_task(self, tmp_path):
        """失败任务的 post_evolution 不应创建技能, 但仍返回 dict。"""
        integrator = _make_integrator(tmp_path)
        result = integrator.post_evolution(
            trace_record={
                "user_input": "失败的任务",
                "tool_calls": [{"name": "tool_x", "success": False}],
                "success": False,
                "duration_ms": 3000,
                "workspace_kind": "general",
            },
            mfp_result={},
        )
        assert isinstance(result, dict)
        assert result["skill_created"] is False  # 失败不创建技能

    def test_post_evolution_does_not_raise_on_failure(self, tmp_path):
        """post_evolution 在异常输入下也不应抛出 (失败不阻塞)。"""
        integrator = _make_integrator(tmp_path)
        # 各种异常输入
        assert isinstance(integrator.post_evolution({}, {}), dict)
        assert isinstance(
            integrator.post_evolution(
                {"user_input": "x", "tool_calls": None, "success": "maybe"}, None
            ),
            dict,
        )
        assert isinstance(
            integrator.post_evolution(
                {"user_input": None, "tool_calls": [], "success": True, "duration_ms": "abc"},
                {"bad": "mfp"},
            ),
            dict,
        )

    def test_get_intelligence_report(self, tmp_path):
        """get_intelligence_report 应返回汇总报告。"""
        integrator = _make_integrator(tmp_path)
        report = integrator.get_intelligence_report()
        assert isinstance(report, dict)
        assert "workspace" in report
        assert "total_cycles" in report
        assert "memory_stats" in report
        assert "guard_health" in report
        assert "judge_report" in report
        assert "skill_stats" in report
        assert "recent_cycles" in report
        assert report["total_cycles"] == 0  # 初始无周期

        # 跑一次 post_evolution 后, 周期数应增加
        integrator.post_evolution(
            trace_record={
                "user_input": "test",
                "tool_calls": [],
                "success": True,
                "duration_ms": 100,
            },
            mfp_result={},
        )
        report2 = integrator.get_intelligence_report()
        assert report2["total_cycles"] >= 1
        assert len(report2["recent_cycles"]) >= 1

    def test_post_evolution_memory_persisted(self, tmp_path):
        """post_evolution 后记忆应被持久化 (可通过 memory.recall 召回)。"""
        integrator = _make_integrator(tmp_path)
        integrator.post_evolution(
            trace_record={
                "user_input": "持久化测试任务",
                "tool_calls": [{"name": "t1", "success": True}],
                "success": True,
                "duration_ms": 500,
            },
            mfp_result={},
        )
        # 应能召回
        results = integrator.memory.recall("持久化测试任务", top_k=5)
        assert len(results) >= 1
        assert any("持久化测试任务" in r.get("content", "") for r in results)

    def test_init_with_default_state_dir(self, tmp_path):
        """用默认 state_dir (data/intelligence) 初始化不抛异常。"""
        ws = str(tmp_path / "ws_default")
        # 默认 state_dir="data/intelligence" 会在 cwd 下创建, 测试时切到 tmp
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            integrator = IntelligenceIntegrator(workspace=ws)
            assert integrator.guard is not None
        finally:
            os.chdir(old_cwd)
