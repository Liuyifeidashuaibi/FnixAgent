"""
版本快照管理 (Snapshot Manager)。

为自进化 Agent 的飞轮 ④(爬山进化)提供不可变快照:
    - create_snapshot:  创建快照(写入 JSON 文件,永不覆盖)
    - restore_snapshot: 恢复快照(返回快照数据,不修改原文件,由调用方另存为新分支)
    - list_snapshots:   列举全部快照(含元信息)
    - delete_snapshot:  删除指定快照
    - cleanup_old_snapshots: 清理过期快照(保留最近 N 天每日 + 全部周快照)

快照格式(JSON):
    {
        "name":        "snap_20260704_120000",
        "timestamp":   1783148400.0,
        "node_count":  42,
        "edge_count":  87,
        "payload":     { ... 完整拓扑与技能权重 ... }
    }

设计原则:
    - 快照文件不可变: create 时若同名已存在则报错,restore 不修改源文件
    - 恢复创建新分支: restore 仅返回数据,调用方负责"另存为新快照"实现分支
    - 清理策略: 保留最近 max_daily 天内的每日最新快照 + 最近 max_weekly 周的每周最新快照
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from typing import Any, Optional

from fnixagent.core.exceptions import SnapshotError


class SnapshotManager:
    """版本快照管理器。

    Args:
        base_dir:   快照存储根目录(其下创建 snapshots/ 子目录)
        max_daily:  保留最近 N 天的每日快照(每天保留最新一个)
        max_weekly: 保留最近 N 周的每周快照(每周保留最新一个)
    """

    def __init__(
        self,
        base_dir: str,
        max_daily: int = 30,
        max_weekly: int = 12,
    ) -> None:
        self._base_dir = base_dir
        self._snapshot_dir = os.path.join(base_dir, "snapshots")
        self._max_daily = max_daily
        self._max_weekly = max_weekly
        os.makedirs(self._snapshot_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 创建快照
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        name: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        node_count: int = 0,
        edge_count: int = 0,
    ) -> str:
        """创建快照并落盘(不可变,同名已存在则报错)。

        Args:
            name:       快照名(为空则按时间戳生成)
            payload:    快照载荷(完整拓扑与技能权重)
            node_count: 节点数
            edge_count: 边数

        Returns:
            快照名

        Raises:
            SnapshotError: 同名快照已存在或写入失败
        """
        timestamp = time.time()
        if name is None:
            name = "snap_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(timestamp))

        path = os.path.join(self._snapshot_dir, f"{name}.json")
        if os.path.exists(path):
            raise SnapshotError(f"快照已存在(不可变): {name}")

        record = {
            "name": name,
            "timestamp": timestamp,
            "node_count": node_count,
            "edge_count": edge_count,
            "payload": payload or {},
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except OSError as e:
            raise SnapshotError(f"快照写入失败: {e}") from e
        return name

    # ------------------------------------------------------------------
    # 恢复快照
    # ------------------------------------------------------------------

    def restore_snapshot(self, name: str) -> dict[str, Any]:
        """恢复快照:返回快照数据(不修改源文件,调用方另存为新分支)。

        Args:
            name: 快照名

        Returns:
            快照完整 dict(name, timestamp, node_count, edge_count, payload)

        Raises:
            SnapshotError: 快照不存在或损坏
        """
        path = os.path.join(self._snapshot_dir, f"{name}.json")
        if not os.path.exists(path):
            raise SnapshotError(f"快照不存在: {name}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise SnapshotError(f"快照加载失败: {e}") from e

    # ------------------------------------------------------------------
    # 列举快照
    # ------------------------------------------------------------------

    def list_snapshots(self) -> list[dict[str, Any]]:
        """列举全部快照(含元信息,按时间戳升序)。

        Returns:
            [{"name", "timestamp", "node_count", "edge_count"}, ...]
        """
        snapshots: list[dict[str, Any]] = []
        if not os.path.isdir(self._snapshot_dir):
            return snapshots
        for fname in os.listdir(self._snapshot_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(self._snapshot_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            snapshots.append({
                "name": data.get("name", fname[:-5]),
                "timestamp": data.get("timestamp", 0.0),
                "node_count": data.get("node_count", 0),
                "edge_count": data.get("edge_count", 0),
            })
        snapshots.sort(key=lambda x: x["timestamp"])
        return snapshots

    # ------------------------------------------------------------------
    # 删除快照
    # ------------------------------------------------------------------

    def delete_snapshot(self, name: str) -> bool:
        """删除指定快照。

        Args:
            name: 快照名

        Returns:
            True 表示已删除,False 表示快照不存在
        """
        path = os.path.join(self._snapshot_dir, f"{name}.json")
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True

    # ------------------------------------------------------------------
    # 清理过期快照
    # ------------------------------------------------------------------

    def cleanup_old_snapshots(self) -> int:
        """清理过期快照。

        保留策略:
            - 最近 max_daily 天:每天保留最新一个快照
            - 最近 max_weekly 周(超出 max_daily 天的部分):每周保留最新一个
            - 其余快照删除

        Returns:
            被删除的快照数量
        """
        snapshots = self.list_snapshots()
        if not snapshots:
            return 0

        now = time.time()
        daily_cutoff = now - self._max_daily * 86400
        weekly_cutoff = now - self._max_weekly * 7 * 86400

        # 按天分组(最近 max_daily 天内),每天保留最新一个
        keep_names: set[str] = set()
        daily_buckets: dict[str, dict[str, Any]] = {}
        weekly_buckets: dict[str, dict[str, Any]] = {}

        for snap in snapshots:
            ts = snap["timestamp"]
            snap_name = snap["name"]
            dt = _dt.datetime.fromtimestamp(ts)
            day_key = dt.strftime("%Y-%m-%d")
            iso_year, iso_week, _ = dt.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"

            if ts >= daily_cutoff:
                # 最近 max_daily 天内:按天保留最新
                if day_key not in daily_buckets or ts > daily_buckets[day_key]["timestamp"]:
                    daily_buckets[day_key] = snap
            elif ts >= weekly_cutoff:
                # 超出 max_daily 天但在 max_weekly 周内:按周保留最新
                if week_key not in weekly_buckets or ts > weekly_buckets[week_key]["timestamp"]:
                    weekly_buckets[week_key] = snap

        for snap in daily_buckets.values():
            keep_names.add(snap["name"])
        for snap in weekly_buckets.values():
            keep_names.add(snap["name"])

        # 删除未保留的快照
        deleted = 0
        for snap in snapshots:
            if snap["name"] not in keep_names:
                if self.delete_snapshot(snap["name"]):
                    deleted += 1
        return deleted
