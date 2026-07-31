"""L3 安全认知层 (EvolutionGuard) 单元测试。

用 tmp_path 隔离 state_dir, 无 LLM/网络依赖。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fnixagent.core.intelligence.evolution_guard import (
    BenchmarkSnapshot,
    DegradationDetector,
    EvolutionGuard,
    GuardLevel,
)


def _make_snapshot(
    *,
    task_completion_rate: float = 0.9,
    error_rate: float = 0.05,
    response_quality: float = 0.85,
    hallucination_rate: float = 0.03,
) -> BenchmarkSnapshot:
    """构造一个 BenchmarkSnapshot 用于测试。"""
    return BenchmarkSnapshot(
        snapshot_id="test_snap",
        version="test",
        created_at=datetime.now(UTC).isoformat(),
        metrics={
            "task_completion_rate": task_completion_rate,
            "error_rate": error_rate,
            "response_quality": response_quality,
            "hallucination_rate": hallucination_rate,
        },
    )


class TestEvolutionGuard:
    """EvolutionGuard 核心功能测试。"""

    def test_init(self, tmp_path):
        """初始化应自动创建 state_dir 及子模块。"""
        guard = EvolutionGuard(state_dir=str(tmp_path / "guard_state"))
        assert guard.boundary is not None
        assert guard.detector is not None
        assert guard.sandbox is not None
        assert guard.rollback is not None
        # state_dir 应被创建
        assert (tmp_path / "guard_state").exists()

    def test_init_creates_state_dir(self, tmp_path):
        """state_dir 不存在时应自动 mkdir。"""
        state = tmp_path / "nested" / "deep" / "guard"
        assert not state.exists()
        EvolutionGuard(state_dir=str(state))
        assert state.exists()

    def test_set_baseline(self, tmp_path):
        """set_baseline 应把快照设为基准。"""
        guard = EvolutionGuard(state_dir=str(tmp_path / "g"))
        snap = _make_snapshot()
        guard.set_baseline(snap)
        assert guard.detector.baseline is snap

    def test_get_health_report(self, tmp_path):
        """get_health_report 应返回 dict 含 boundary/degradation/overall_health。"""
        guard = EvolutionGuard(state_dir=str(tmp_path / "g"))
        report = guard.get_health_report()
        assert isinstance(report, dict)
        assert "boundary" in report
        assert "degradation" in report
        assert "rollback_count" in report
        assert "overall_health" in report
        # 初始无退化, 应为 healthy
        assert report["overall_health"] == "healthy"

    def test_detect_circular_evolution_no_history(self):
        """DegradationDetector 历史不足时应返回 False。"""
        detector = DegradationDetector()
        assert detector.detect_circular_evolution() is False

    def test_detect_circular_evolution_with_history(self):
        """DegradationDetector 历史充足时检测循环进化 (A→B→A)。"""
        detector = DegradationDetector()
        # 构造 A → B → A 的 metrics 模式 (B 需方向不同, 余弦相似度才低)
        snap_a = BenchmarkSnapshot(
            snapshot_id="a",
            version="v",
            created_at="t1",
            metrics={"quality": 0.9, "speed": 0.1},
        )
        snap_b = BenchmarkSnapshot(
            snapshot_id="b",
            version="v",
            created_at="t2",
            metrics={"quality": 0.1, "speed": 0.9},  # 方向相反
        )
        snap_a2 = BenchmarkSnapshot(
            snapshot_id="a2",
            version="v",
            created_at="t3",
            metrics={"quality": 0.9, "speed": 0.1},  # 回到 A
        )
        detector._history = [snap_a, snap_b, snap_a2]
        # v0 ≈ v2 (余弦相似度高) 且 v1 方向不同 (余弦相似度低) → 循环进化
        assert detector.detect_circular_evolution() is True

    def test_detect_circular_evolution_no_loop(self):
        """DegradationDetector 持续进化 (无循环) 应返回 False。"""
        detector = DegradationDetector()
        snap1 = BenchmarkSnapshot(
            snapshot_id="s1",
            version="v",
            created_at="t1",
            metrics={"quality": 0.6, "speed": 0.5},
        )
        snap2 = BenchmarkSnapshot(
            snapshot_id="s2",
            version="v",
            created_at="t2",
            metrics={"quality": 0.7, "speed": 0.6},
        )
        snap3 = BenchmarkSnapshot(
            snapshot_id="s3",
            version="v",
            created_at="t3",
            metrics={"quality": 0.8, "speed": 0.7},  # 持续上升, 无循环
        )
        detector._history = [snap1, snap2, snap3]
        assert detector.detect_circular_evolution() is False

    def test_check_snapshot_no_baseline(self, tmp_path):
        """无基准时 check_snapshot 应返回 SAFE。"""
        guard = EvolutionGuard(state_dir=str(tmp_path / "g"))
        # 不设 baseline, 直接 check
        result = guard.detector.check_snapshot(_make_snapshot())
        assert isinstance(result, dict)
        assert "guard_level" in result
        assert result["guard_level"] == GuardLevel.SAFE

    def test_check_snapshot_detects_degradation(self, tmp_path):
        """指标显著下降时应检测到退化信号。"""
        guard = EvolutionGuard(state_dir=str(tmp_path / "g"))
        # 基准: 高质量
        guard.set_baseline(
            _make_snapshot(
                task_completion_rate=0.9,
                error_rate=0.05,
                response_quality=0.85,
                hallucination_rate=0.03,
            )
        )
        # 当前: 大幅下降
        degraded_snap = BenchmarkSnapshot(
            snapshot_id="deg",
            version="v",
            created_at=datetime.now(UTC).isoformat(),
            metrics={
                "task_completion_rate": 0.5,  # 下降 44% → 性能退化
                "error_rate": 0.2,  # 上升 300% → 错误率退化
                "response_quality": 0.5,  # 下降 41% → 质量退化
                "hallucination_rate": 0.15,  # 上升 → 幻觉退化
            },
        )
        result = guard.detector.check_snapshot(degraded_snap)
        assert isinstance(result, dict)
        assert len(result["signals"]) >= 1
        # 多信号时应至少 WARNING
        assert result["guard_level"] in (
            GuardLevel.WARNING,
            GuardLevel.CRITICAL,
            GuardLevel.ROLLBACK_REQUIRED,
        )

    def test_get_degradation_report(self, tmp_path):
        """get_degradation_report 应返回 dict。"""
        guard = EvolutionGuard(state_dir=str(tmp_path / "g"))
        report = guard.detector.get_degradation_report()
        assert isinstance(report, dict)
        assert "total_checks" in report
        assert "degradation_events" in report
        assert "current_level" in report
