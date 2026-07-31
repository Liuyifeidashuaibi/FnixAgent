"""DAAO Router 单元测试。

覆盖:
- estimate_difficulty 难度估算
- route 基础路由 (ask/plan/code/research/通用)
- route 反馈回路 (HERA 高/低命中率, 失败率)
- compute_hera_hit_rate
- compute_recent_failure_rate (含失败技能入库后的真实场景)
- RouteDecision 字段契约 (无 tool_subset)

设计原则: 纯本地逻辑, 零 LLM 依赖。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fnixagent.core.flywheel.daao_router import (
    compute_hera_hit_rate,
    compute_recent_failure_rate,
    estimate_difficulty,
    route,
)
from fnixagent.core.skills.library import SkillLibrary


class TestEstimateDifficulty:
    def test_ask_mode_base(self):
        d = estimate_difficulty("你好", "general", "ask")
        assert 0.0 <= d <= 1.0
        assert d < 0.3  # ask 基础 0.1

    def test_plan_mode_base(self):
        d = estimate_difficulty("规划任务", "general", "plan")
        assert d >= 0.5  # plan 基础 0.5

    def test_high_complexity_keyword_bonus(self):
        d1 = estimate_difficulty("做个简单功能", "general", "craft")
        d2 = estimate_difficulty("重构整个系统", "general", "craft")
        assert d2 > d1, "高复杂度关键词应加分"

    def test_medium_complexity_keyword_bonus(self):
        d1 = estimate_difficulty("随便看看", "general", "craft")
        d2 = estimate_difficulty("实现一个功能", "general", "craft")
        assert d2 > d1, "中复杂度关键词应加分"

    def test_code_workspace_bonus(self):
        d1 = estimate_difficulty("test", "general", "craft")
        d2 = estimate_difficulty("test", "code", "craft")
        assert d2 > d1, "code workspace 应 +0.1"

    def test_research_workspace_penalty(self):
        d1 = estimate_difficulty("test", "general", "craft")
        d2 = estimate_difficulty("test", "research", "craft")
        assert d2 < d1, "research workspace 应 -0.1"

    def test_length_bonus(self):
        d1 = estimate_difficulty("短", "general", "craft")
        d2 = estimate_difficulty("x" * 500, "general", "craft")
        assert d2 > d1, "长输入应加分"

    def test_clamped_to_01(self):
        d = estimate_difficulty("x" * 10000, "code", "plan")
        assert d <= 1.0
        d = estimate_difficulty("", "general", "ask")
        assert d >= 0.0


class TestRouteBasic:
    def test_ask_mode(self):
        d = route(user_input="你好", workspace_kind="general", work_mode="ask")
        assert d.reasoning_mode == "react"
        assert d.max_steps == 5
        assert d.max_reflect_rounds == 0
        assert "Ask" in d.route_reason

    def test_plan_mode(self):
        d = route(user_input="规划", workspace_kind="general", work_mode="plan", hera_hit_rate=0.6)
        assert d.reasoning_mode == "plan_execute"
        assert d.max_steps == 25
        # hera_hit_rate=0.6 触发高命中率减反思, 2→1
        assert d.max_reflect_rounds == 1

    def test_code_workspace(self):
        d = route(user_input="写代码", workspace_kind="code", work_mode="craft")
        assert d.reasoning_mode == "react"
        assert d.max_steps == 16
        assert d.max_reflect_rounds == 2

    def test_research_workspace(self):
        d = route(user_input="调研", workspace_kind="research", work_mode="craft")
        assert d.reasoning_mode == "react"
        assert d.max_steps == 12
        assert d.max_reflect_rounds == 1

    def test_high_difficulty_uses_plan_execute(self):
        """通用 craft 高难度 (diff>=0.7) 应走 plan_execute。

        注意: workspace_kind="code" 会走 code 分支(react), 不进入通用 craft 分支。
        要触发通用 craft 高难度分支, 需用 general workspace + 高复杂度关键词 + 长输入,
        且难度需达 0.7。general 基础 0.3 + 关键词 0.2 + 长度上限 0.2 = 0.7 刚好达标。
        """
        d = route(
            user_input="重构整个系统从零开始完整实现端到端多文件微服务" + "x" * 800,
            workspace_kind="general",  # 避免 code 分支
            work_mode="craft",
            hera_hit_rate=0.6,  # 避免 HERA 低命中率回路干扰
        )
        assert d.reasoning_mode == "plan_execute"
        assert d.max_steps == 25
        assert d.difficulty_score >= 0.7

    def test_low_difficulty_uses_react(self):
        d = route(user_input="test", workspace_kind="general", work_mode="craft")
        assert d.reasoning_mode == "react"
        assert d.max_steps == 12


class TestRouteFeedbackLoop:
    def test_hera_high_hit_rate_reduces_reflect(self):
        """HERA 命中率 ≥ 0.5 → 减少反思轮数。"""
        d_low = route(
            user_input="写代码",
            workspace_kind="code",
            work_mode="craft",
            hera_hit_rate=0.0,
        )
        d_high = route(
            user_input="写代码",
            workspace_kind="code",
            work_mode="craft",
            hera_hit_rate=0.8,
        )
        assert d_high.max_reflect_rounds < d_low.max_reflect_rounds
        assert "HERA" in d_high.route_reason

    def test_hera_low_hit_rate_increases_reflect(self):
        """HERA 命中率 < 0.2 + 高难度 → 增加反思轮数。"""
        d = route(
            user_input="重构整个系统从零开始",
            workspace_kind="general",
            work_mode="craft",
            hera_hit_rate=0.1,
        )
        assert d.max_reflect_rounds >= 2
        assert "HERA" in d.route_reason

    def test_high_failure_rate_switches_to_plan_execute(self):
        """失败率 ≥ 0.5 → 切换到 plan_execute。"""
        d = route(
            user_input="写代码",
            workspace_kind="code",
            work_mode="craft",
            recent_failure_rate=0.7,
        )
        assert d.reasoning_mode == "plan_execute"
        assert "失败率" in d.route_reason

    def test_confidence_based_on_hera(self):
        d_no_hera = route(user_input="test", workspace_kind="general", work_mode="craft")
        d_with_hera = route(
            user_input="test",
            workspace_kind="general",
            work_mode="craft",
            hera_hit_rate=0.5,
        )
        assert d_with_hera.confidence == 1.0
        assert d_no_hera.confidence == 0.7


class TestRouteDecisionContract:
    def test_no_tool_subset_field(self):
        """修复后: RouteDecision 不应再有 tool_subset 字段 (诚实降级)。"""
        d = route(user_input="test", workspace_kind="general", work_mode="craft")
        assert not hasattr(d, "tool_subset"), "tool_subset 字段应已移除"

    def test_required_fields(self):
        d = route(user_input="test", workspace_kind="general", work_mode="craft")
        assert hasattr(d, "reasoning_mode")
        assert hasattr(d, "max_steps")
        assert hasattr(d, "max_reflect_rounds")
        assert hasattr(d, "route_reason")
        assert hasattr(d, "difficulty_score")
        assert hasattr(d, "hera_hit_rate")
        assert hasattr(d, "recent_failure_rate")
        assert hasattr(d, "confidence")


class TestComputeHeraHitRate:
    def test_normal_case(self):
        assert compute_hera_hit_rate(retrieved_count=2, requested_top_k=3) == 2 / 3

    def test_full_hit(self):
        assert compute_hera_hit_rate(retrieved_count=3, requested_top_k=3) == 1.0

    def test_no_hit(self):
        assert compute_hera_hit_rate(retrieved_count=0, requested_top_k=3) == 0.0

    def test_clamped_to_1(self):
        """召回数超过 top_k 时应 clamp 到 1.0。"""
        assert compute_hera_hit_rate(retrieved_count=5, requested_top_k=3) == 1.0

    def test_zero_top_k(self):
        assert compute_hera_hit_rate(retrieved_count=1, requested_top_k=0) == 0.0


class TestComputeRecentFailureRate:
    def test_no_library(self):
        assert compute_recent_failure_rate(workspace_kind="code", library=None) == 0.0

    def test_empty_library(self, tmp_path: Path):
        lib = SkillLibrary(str(tmp_path))
        assert compute_recent_failure_rate(workspace_kind="code", library=lib) == 0.0

    def test_all_success(self, tmp_path: Path):
        lib = SkillLibrary(str(tmp_path))
        for i in range(5):
            lib.add_new_skill(
                user_input=f"成功任务 {i}",
                response="r",
                tool_calls=[],
                workspace_kind="code",
                success=True,
            )
        rate = compute_recent_failure_rate(workspace_kind="code", library=lib)
        assert rate == 0.0

    def test_all_failed_after_fix(self, tmp_path: Path):
        """修复后: 失败技能能入库, 失败率应真实反映。"""
        lib = SkillLibrary(str(tmp_path))
        for i in range(5):
            lib.add_new_skill(
                user_input=f"失败任务 {i}",
                response="r",
                tool_calls=[],
                workspace_kind="code",
                success=False,
            )
        rate = compute_recent_failure_rate(workspace_kind="code", library=lib)
        assert rate == 1.0, "全部失败应得 1.0 (修复后失败技能入库)"

    def test_mixed(self, tmp_path: Path):
        lib = SkillLibrary(str(tmp_path))
        for i in range(3):
            lib.add_new_skill(
                user_input=f"成功 {i}",
                response="r",
                tool_calls=[],
                workspace_kind="code",
                success=True,
            )
        for i in range(2):
            lib.add_new_skill(
                user_input=f"失败 {i}",
                response="r",
                tool_calls=[],
                workspace_kind="code",
                success=False,
            )
        rate = compute_recent_failure_rate(workspace_kind="code", library=lib)
        assert rate == 0.4, "2/5 失败应得 0.4"

    def test_workspace_kind_filter(self, tmp_path: Path):
        """只统计同 workspace_kind 的技能。"""
        lib = SkillLibrary(str(tmp_path))
        lib.add_new_skill(
            user_input="code 任务",
            response="r",
            tool_calls=[],
            workspace_kind="code",
            success=False,
        )
        lib.add_new_skill(
            user_input="general 任务",
            response="r",
            tool_calls=[],
            workspace_kind="general",
            success=True,
        )
        rate_code = compute_recent_failure_rate(workspace_kind="code", library=lib)
        rate_general = compute_recent_failure_rate(workspace_kind="general", library=lib)
        assert rate_code == 1.0
        assert rate_general == 0.0

    def test_library_exception_returns_zero(self):
        """library 异常时应返回 0.0 不抛出。"""
        mock_lib = MagicMock()
        mock_lib.skills = "not a list"  # 故意制造异常
        rate = compute_recent_failure_rate(workspace_kind="code", library=mock_lib)
        assert rate == 0.0
