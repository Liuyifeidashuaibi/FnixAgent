"""
版本快照管理测试。

覆盖:
    - 创建快照(create_snapshot)
    - 恢复快照(restore_snapshot)
    - 列举快照(list_snapshots)
    - 删除快照(delete_snapshot)
    - 清理过期快照(cleanup_old_snapshots)
    - 不可变性(同名快照不能覆盖)
"""
import json
import os
import time

import pytest

from fnixagent.assets.snapshot import SnapshotManager
from fnixagent.core.exceptions import SnapshotError


# ---------------------------------------------------------------------------
# 创建快照
# ---------------------------------------------------------------------------

class TestCreateSnapshot:
    """create_snapshot 测试。"""

    def test_create_with_explicit_name(self, tmp_path):
        """使用显式名称创建快照。"""
        mgr = SnapshotManager(str(tmp_path))
        name = mgr.create_snapshot(
            name="my_snap",
            payload={"nodes": [], "edges": []},
            node_count=0,
            edge_count=0,
        )
        assert name == "my_snap"
        # 文件存在
        assert os.path.exists(os.path.join(str(tmp_path), "snapshots", "my_snap.json"))

    def test_create_with_auto_name(self, tmp_path):
        """不传名称时自动生成(snap_ 前缀)。"""
        mgr = SnapshotManager(str(tmp_path))
        name = mgr.create_snapshot(payload={"k": "v"})
        assert name.startswith("snap_")
        # 文件存在
        assert os.path.exists(os.path.join(str(tmp_path), "snapshots", f"{name}.json"))

    def test_create_writes_correct_format(self, tmp_path):
        """快照文件格式包含 timestamp/node_count/edge_count/payload。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(
            name="fmt_snap",
            payload={"nodes": [1, 2]},
            node_count=2,
            edge_count=1,
        )
        path = os.path.join(str(tmp_path), "snapshots", "fmt_snap.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["name"] == "fmt_snap"
        assert "timestamp" in data
        assert data["node_count"] == 2
        assert data["edge_count"] == 1
        assert data["payload"] == {"nodes": [1, 2]}

    def test_create_duplicate_raises(self, tmp_path):
        """同名快照已存在时报错(不可变)。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(name="dup", payload={})
        with pytest.raises(SnapshotError):
            mgr.create_snapshot(name="dup", payload={"new": "data"})

    def test_create_snapshot_dir_auto_created(self, tmp_path):
        """base_dir 不存在时自动创建 snapshots 子目录。"""
        base = tmp_path / "deep" / "path"
        mgr = SnapshotManager(str(base))
        mgr.create_snapshot(name="s1", payload={})
        assert (base / "snapshots" / "s1.json").exists()


# ---------------------------------------------------------------------------
# 恢复快照
# ---------------------------------------------------------------------------

class TestRestoreSnapshot:
    """restore_snapshot 测试。"""

    def test_restore_returns_full_dict(self, tmp_path):
        """恢复快照返回完整 dict(含 payload)。"""
        mgr = SnapshotManager(str(tmp_path))
        payload = {"nodes": [{"id": "n1"}], "edges": []}
        mgr.create_snapshot(
            name="r1",
            payload=payload,
            node_count=1,
            edge_count=0,
        )
        restored = mgr.restore_snapshot("r1")
        assert restored["name"] == "r1"
        assert restored["payload"] == payload
        assert restored["node_count"] == 1

    def test_restore_nonexistent_raises(self, tmp_path):
        """恢复不存在的快照抛出 SnapshotError。"""
        mgr = SnapshotManager(str(tmp_path))
        with pytest.raises(SnapshotError):
            mgr.restore_snapshot("no_such_snap")

    def test_restore_does_not_modify_source(self, tmp_path):
        """恢复不修改源快照文件(不可变)。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(name="imm", payload={"v": 1})
        path = os.path.join(str(tmp_path), "snapshots", "imm.json")
        mtime_before = os.path.getmtime(path)
        # 恢复
        restored = mgr.restore_snapshot("imm")
        assert restored["payload"] == {"v": 1}
        # 文件未被修改
        mtime_after = os.path.getmtime(path)
        assert mtime_before == mtime_after


# ---------------------------------------------------------------------------
# 列举快照
# ---------------------------------------------------------------------------

class TestListSnapshots:
    """list_snapshots 测试。"""

    def test_list_empty(self, tmp_path):
        """空目录列举返回空列表。"""
        mgr = SnapshotManager(str(tmp_path))
        assert mgr.list_snapshots() == []

    def test_list_returns_metadata(self, tmp_path):
        """列举返回 name/timestamp/node_count/edge_count。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(name="a", payload={}, node_count=3, edge_count=5)
        # 确保时间戳不同
        time.sleep(0.01)
        mgr.create_snapshot(name="b", payload={}, node_count=7, edge_count=2)
        snaps = mgr.list_snapshots()
        assert len(snaps) == 2
        names = [s["name"] for s in snaps]
        assert "a" in names and "b" in names
        # 每条含完整元信息
        for s in snaps:
            assert "timestamp" in s
            assert "node_count" in s
            assert "edge_count" in s

    def test_list_sorted_by_timestamp(self, tmp_path):
        """列举按时间戳升序排列。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(name="second", payload={})
        time.sleep(0.01)
        mgr.create_snapshot(name="first_after", payload={})
        snaps = mgr.list_snapshots()
        timestamps = [s["timestamp"] for s in snaps]
        assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# 删除快照
# ---------------------------------------------------------------------------

class TestDeleteSnapshot:
    """delete_snapshot 测试。"""

    def test_delete_existing(self, tmp_path):
        """删除已存在的快照返回 True。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(name="del", payload={})
        assert mgr.delete_snapshot("del") is True
        assert mgr.list_snapshots() == []

    def test_delete_nonexistent_returns_false(self, tmp_path):
        """删除不存在的快照返回 False(不抛异常)。"""
        mgr = SnapshotManager(str(tmp_path))
        assert mgr.delete_snapshot("ghost") is False

    def test_delete_then_recreate_allowed(self, tmp_path):
        """删除后可重新创建同名快照。"""
        mgr = SnapshotManager(str(tmp_path))
        mgr.create_snapshot(name="rec", payload={"v": 1})
        mgr.delete_snapshot("rec")
        # 重新创建不报错
        mgr.create_snapshot(name="rec", payload={"v": 2})
        restored = mgr.restore_snapshot("rec")
        assert restored["payload"] == {"v": 2}


# ---------------------------------------------------------------------------
# 清理过期快照
# ---------------------------------------------------------------------------

class TestCleanupOldSnapshots:
    """cleanup_old_snapshots 测试。"""

    def test_cleanup_no_snapshots(self, tmp_path):
        """无快照时清理返回 0。"""
        mgr = SnapshotManager(str(tmp_path))
        assert mgr.cleanup_old_snapshots() == 0

    def test_cleanup_keeps_recent_snapshots(self, tmp_path):
        """清理保留最近 max_daily 天内的快照。"""
        mgr = SnapshotManager(str(tmp_path), max_daily=30, max_weekly=12)
        # 创建一个"近期"快照(手动构造时间戳为 1 天前)
        now = time.time()
        self._create_snapshot_with_ts(tmp_path, "recent", now - 86400)
        deleted = mgr.cleanup_old_snapshots()
        assert deleted == 0
        snaps = mgr.list_snapshots()
        assert len(snaps) == 1
        assert snaps[0]["name"] == "recent"

    def test_cleanup_removes_old_beyond_weekly(self, tmp_path):
        """超出 max_weekly 周的快照被删除。"""
        mgr = SnapshotManager(str(tmp_path), max_daily=2, max_weekly=1)
        now = time.time()
        # 100 天前(超出 max_daily=2 天且超出 max_weekly=1 周)
        self._create_snapshot_with_ts(tmp_path, "old_100d", now - 100 * 86400)
        deleted = mgr.cleanup_old_snapshots()
        assert deleted == 1
        assert mgr.list_snapshots() == []

    def test_cleanup_keeps_weekly_for_intermediate_age(self, tmp_path):
        """超出 daily 但在 weekly 范围内,保留每周最新一个。"""
        mgr = SnapshotManager(str(tmp_path), max_daily=3, max_weekly=4)
        now = time.time()
        # 同一周内两个快照(10 天前和 8 天前,都在第 2 周内)
        # 注意: 10 天前 = 864000 秒前
        self._create_snapshot_with_ts(tmp_path, "w2_a", now - 10 * 86400)
        self._create_snapshot_with_ts(tmp_path, "w2_b", now - 8 * 86400)
        deleted = mgr.cleanup_old_snapshots()
        # 应保留较新的 w2_b,删除 w2_a
        assert deleted == 1
        snaps = mgr.list_snapshots()
        names = [s["name"] for s in snaps]
        assert "w2_b" in names
        assert "w2_a" not in names

    def test_cleanup_daily_keeps_one_per_day(self, tmp_path):
        """daily 范围内每天保留最新一个。"""
        mgr = SnapshotManager(str(tmp_path), max_daily=5, max_weekly=12)
        now = time.time()
        # 同一天两个快照
        self._create_snapshot_with_ts(tmp_path, "d1_morning", now - 3600)
        self._create_snapshot_with_ts(tmp_path, "d1_evening", now - 1800)
        deleted = mgr.cleanup_old_snapshots()
        # 同一天保留最新一个
        assert deleted == 1
        snaps = mgr.list_snapshots()
        names = [s["name"] for s in snaps]
        assert "d1_evening" in names
        assert "d1_morning" not in names

    @staticmethod
    def _create_snapshot_with_ts(tmp_path, name: str, ts: float) -> None:
        """直接写入带指定时间戳的快照文件(绕过 create_snapshot 的 now())。"""
        snap_dir = tmp_path / "snapshots"
        snap_dir.mkdir(exist_ok=True)
        path = snap_dir / f"{name}.json"
        record = {
            "name": name,
            "timestamp": ts,
            "node_count": 0,
            "edge_count": 0,
            "payload": {},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
