"""
轨迹存储(TraceStore)单元测试。

测试模块: officeagent.core.flywheel.trace
覆盖:
    - append(): 追加写入
    - load_all(): 全量加载
    - load_recent(): 按时间倒序加载
    - load_by_time_range(): 时间范围查询
    - load_by_success(): 按成功/失败状态查询
    - count(): 计数
    - stats(): 统计
    - clear(): 清空
"""
import time

import pytest

from officeagent.core.flywheel.stage1_perception import trace_from_dict, trace_to_dict
from officeagent.core.flywheel.trace import TraceStore
from officeagent.core.types import ReasoningMode, TraceRecord


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_trace(trace_id, goal="test", success=True, created_at=None, tokens=100, duration=500.0):
    """快速构造 TraceRecord。"""
    return TraceRecord(
        trace_id=trace_id,
        task_id=f"task-{trace_id}",
        goal=goal,
        mode=ReasoningMode.REACT,
        concept_path=["L2:c1"],
        tool_calls=[{"name": "tool1", "args": {}, "status": "success" if success else "failed"}],
        success=success,
        duration_ms=duration,
        usage_tokens=tokens,
        reflection_score=0.5,
        created_at=created_at if created_at is not None else time.time(),
    )


# ---------------------------------------------------------------------------
# append + load_all
# ---------------------------------------------------------------------------

class TestAppendAndLoadAll:
    """测试 append() 与 load_all()。"""

    def test_append_creates_file(self, tmp_path):
        """append 后应创建 traces.jsonl 文件。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        assert (tmp_path / "traces" / "traces.jsonl").exists()

    def test_load_all_empty_store(self, tmp_path):
        """空存储 load_all 应返回空列表。"""
        store = TraceStore(str(tmp_path / "traces"))
        assert store.load_all() == []

    def test_load_all_returns_traces(self, tmp_path):
        """load_all 应返回全部追加的轨迹。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        store.append(_make_trace("t2"))
        traces = store.load_all()
        assert len(traces) == 2
        ids = {t.trace_id for t in traces}
        assert ids == {"t1", "t2"}

    def test_round_trip_preserves_fields(self, tmp_path):
        """追加后加载的字段应保持一致。"""
        store = TraceStore(str(tmp_path / "traces"))
        original = _make_trace("t1", goal="搜索论文", success=True, tokens=300)
        store.append(original)
        loaded = store.load_all()[0]
        assert loaded.trace_id == "t1"
        assert loaded.goal == "搜索论文"
        assert loaded.success is True
        assert loaded.usage_tokens == 300

    def test_append_multiple_writes_lines(self, tmp_path):
        """多次 append 应写入多行(JSONL)。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        store.append(_make_trace("t2"))
        store.append(_make_trace("t3"))
        file_path = tmp_path / "traces" / "traces.jsonl"
        line_count = sum(1 for line in file_path.open(encoding="utf-8") if line.strip())
        assert line_count == 3


# ---------------------------------------------------------------------------
# load_recent
# ---------------------------------------------------------------------------

class TestLoadRecent:
    """测试 load_recent()。"""

    def test_load_recent_returns_limited(self, tmp_path):
        """load_recent 应限制返回数量。"""
        store = TraceStore(str(tmp_path / "traces"))
        base_time = time.time()
        for i in range(5):
            store.append(_make_trace(f"t{i}", created_at=base_time + i))
        recent = store.load_recent(limit=3)
        assert len(recent) == 3

    def test_load_recent_sorted_by_time_desc(self, tmp_path):
        """load_recent 应按 created_at 降序排列。"""
        store = TraceStore(str(tmp_path / "traces"))
        base_time = 1000.0
        for i in range(5):
            store.append(_make_trace(f"t{i}", created_at=base_time + i))
        recent = store.load_recent(limit=10)
        assert recent[0].created_at > recent[1].created_at
        assert recent[0].trace_id == "t4"
        assert recent[1].trace_id == "t3"

    def test_load_recent_empty_store(self, tmp_path):
        """空存储 load_recent 应返回空列表。"""
        store = TraceStore(str(tmp_path / "traces"))
        assert store.load_recent(limit=5) == []

    def test_load_recent_limit_larger_than_count(self, tmp_path):
        """limit 大于总数时应返回全部轨迹。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        recent = store.load_recent(limit=10)
        assert len(recent) == 1


# ---------------------------------------------------------------------------
# load_by_time_range
# ---------------------------------------------------------------------------

class TestLoadByTimeRange:
    """测试 load_by_time_range()。"""

    def test_filters_by_time_range(self, tmp_path):
        """应只返回时间范围内的轨迹。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", created_at=1000.0))
        store.append(_make_trace("t2", created_at=2000.0))
        store.append(_make_trace("t3", created_at=3000.0))
        result = store.load_by_time_range(1500.0, 2500.0)
        assert len(result) == 1
        assert result[0].trace_id == "t2"

    def test_inclusive_boundaries(self, tmp_path):
        """时间范围边界应包含(<=, >=)。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", created_at=1000.0))
        store.append(_make_trace("t2", created_at=2000.0))
        result = store.load_by_time_range(1000.0, 2000.0)
        assert len(result) == 2

    def test_empty_range(self, tmp_path):
        """无匹配时间范围时应返回空列表。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", created_at=1000.0))
        result = store.load_by_time_range(5000.0, 6000.0)
        assert result == []


# ---------------------------------------------------------------------------
# load_by_success
# ---------------------------------------------------------------------------

class TestLoadBySuccess:
    """测试 load_by_success()。"""

    def test_filters_successful(self, tmp_path):
        """应只返回成功的轨迹。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", success=True))
        store.append(_make_trace("t2", success=False))
        store.append(_make_trace("t3", success=True))
        result = store.load_by_success(success=True)
        assert len(result) == 2
        assert all(t.success for t in result)

    def test_filters_failed(self, tmp_path):
        """应只返回失败的轨迹。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", success=True))
        store.append(_make_trace("t2", success=False))
        result = store.load_by_success(success=False)
        assert len(result) == 1
        assert all(not t.success for t in result)

    def test_empty_store(self, tmp_path):
        """空存储应返回空列表。"""
        store = TraceStore(str(tmp_path / "traces"))
        assert store.load_by_success(True) == []


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------

class TestCount:
    """测试 count() 方法。"""

    def test_empty_store_returns_zero(self, tmp_path):
        """空存储 count 应返回 0。"""
        store = TraceStore(str(tmp_path / "traces"))
        assert store.count() == 0

    def test_count_after_appends(self, tmp_path):
        """追加后 count 应正确。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        store.append(_make_trace("t2"))
        store.append(_make_trace("t3"))
        assert store.count() == 3


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

class TestStats:
    """测试 stats() 方法。"""

    def test_empty_store_stats(self, tmp_path):
        """空存储 stats 应返回全零统计。"""
        store = TraceStore(str(tmp_path / "traces"))
        stats = store.stats()
        assert stats["total"] == 0
        assert stats["success_count"] == 0
        assert stats["failure_count"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_duration_ms"] == 0.0
        assert stats["avg_tokens"] == 0
        assert stats["avg_reflection_score"] == 0.0

    def test_stats_expected_keys(self, tmp_path):
        """stats 应包含全部预期键。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        stats = store.stats()
        expected_keys = {
            "total", "success_count", "failure_count", "success_rate",
            "avg_duration_ms", "avg_tokens", "avg_reflection_score",
        }
        assert expected_keys.issubset(set(stats.keys()))

    def test_stats_success_rate(self, tmp_path):
        """stats 应正确计算成功率。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", success=True))
        store.append(_make_trace("t2", success=True))
        store.append(_make_trace("t3", success=False))
        stats = store.stats()
        assert stats["total"] == 3
        assert stats["success_count"] == 2
        assert stats["failure_count"] == 1
        assert stats["success_rate"] == pytest.approx(2 / 3, rel=1e-2)

    def test_stats_avg_duration(self, tmp_path):
        """stats 应正确计算平均耗时。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", duration=100.0))
        store.append(_make_trace("t2", duration=300.0))
        stats = store.stats()
        assert stats["avg_duration_ms"] == pytest.approx(200.0)

    def test_stats_avg_tokens(self, tmp_path):
        """stats 应正确计算平均 token。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1", tokens=100))
        store.append(_make_trace("t2", tokens=300))
        stats = store.stats()
        assert stats["avg_tokens"] == 200


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

class TestClear:
    """测试 clear() 方法。"""

    def test_clear_removes_all_traces(self, tmp_path):
        """clear 应清空全部轨迹。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        store.append(_make_trace("t2"))
        cleared = store.clear()
        assert cleared == 2
        assert store.count() == 0

    def test_clear_empty_store_returns_zero(self, tmp_path):
        """空存储 clear 应返回 0。"""
        store = TraceStore(str(tmp_path / "traces"))
        cleared = store.clear()
        assert cleared == 0

    def test_clear_removes_file(self, tmp_path):
        """clear 后文件应被删除。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        file_path = tmp_path / "traces" / "traces.jsonl"
        assert file_path.exists()
        store.clear()
        assert not file_path.exists()

    def test_can_append_after_clear(self, tmp_path):
        """clear 后应仍能继续追加。"""
        store = TraceStore(str(tmp_path / "traces"))
        store.append(_make_trace("t1"))
        store.clear()
        store.append(_make_trace("t2"))
        assert store.count() == 1
        assert store.load_all()[0].trace_id == "t2"


# ---------------------------------------------------------------------------
# 持久化隔离
# ---------------------------------------------------------------------------

class TestPersistence:
    """测试持久化行为(多实例共享同一文件)。"""

    def test_new_instance_reads_existing_file(self, tmp_path):
        """新 TraceStore 实例应能读取已有文件。"""
        base_dir = str(tmp_path / "traces")
        store1 = TraceStore(base_dir)
        store1.append(_make_trace("t1"))
        # 新实例指向同一目录
        store2 = TraceStore(base_dir)
        traces = store2.load_all()
        assert len(traces) == 1
        assert traces[0].trace_id == "t1"

    def test_auto_creates_directory(self, tmp_path):
        """应自动创建不存在的目录。"""
        base_dir = str(tmp_path / "nested" / "deep" / "traces")
        store = TraceStore(base_dir)
        store.append(_make_trace("t1"))
        import os
        assert os.path.exists(base_dir)
