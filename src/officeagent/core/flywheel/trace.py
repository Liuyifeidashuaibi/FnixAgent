"""
轨迹记录格式与存储。

管理飞轮 ① 产出的 TraceRecord 的持久化:
    - 追加写: traces.jsonl(每行一条 TraceRecord)
    - 查询: 按时间范围/任务 ID/成功失败状态查询
    - 统计: 成功率/平均耗时/平均 token 消耗

存储格式: JSONL(纯文本,跨平台可迁移,不依赖任何框架)
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from officeagent.core.flywheel.stage1_perception import trace_from_dict, trace_to_dict
from officeagent.core.types import TraceRecord


class TraceStore:
    """轨迹记录存储管理器。

    文件布局:
        <base_dir>/traces.jsonl   追加写,每行一条 TraceRecord

    用法:
        store = TraceStore("assets/traces")
        store.append(trace)
        recent = store.load_recent(limit=10)
    """

    def __init__(self, base_dir: str) -> None:
        """初始化轨迹存储。

        Args:
            base_dir: 存储根目录(自动创建)
        """
        self._base_dir = base_dir
        self._file_path = os.path.join(base_dir, "traces.jsonl")
        os.makedirs(base_dir, exist_ok=True)

    def append(self, trace: TraceRecord) -> None:
        """追加写入一条轨迹(只增不删)。"""
        record = trace_to_dict(trace)
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            raise IOError(f"写入轨迹失败: {e}") from e

    def load_all(self) -> list[TraceRecord]:
        """加载全部轨迹。"""
        if not os.path.exists(self._file_path):
            return []
        traces = []
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        traces.append(trace_from_dict(d))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return traces

    def load_recent(self, limit: int = 10) -> list[TraceRecord]:
        """加载最近 N 条轨迹(按创建时间降序)。"""
        all_traces = self.load_all()
        all_traces.sort(key=lambda t: t.created_at, reverse=True)
        return all_traces[:limit]

    def load_by_time_range(
        self,
        start_time: float,
        end_time: float,
    ) -> list[TraceRecord]:
        """按时间范围加载轨迹。"""
        all_traces = self.load_all()
        return [
            t for t in all_traces
            if start_time <= t.created_at <= end_time
        ]

    def load_by_success(self, success: bool = True) -> list[TraceRecord]:
        """按成功/失败状态加载轨迹。"""
        all_traces = self.load_all()
        return [t for t in all_traces if t.success == success]

    def count(self) -> int:
        """返回轨迹总数。"""
        return len(self.load_all())

    def stats(self) -> dict:
        """返回轨迹统计信息。

        Returns:
            {
                "total": int,               总轨迹数
                "success_count": int,       成功数
                "failure_count": int,       失败数
                "success_rate": float,      成功率
                "avg_duration_ms": float,   平均耗时
                "avg_tokens": int,          平均 token 消耗
                "avg_reflection_score": float,  平均反思得分
            }
        """
        traces = self.load_all()
        if not traces:
            return {
                "total": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_tokens": 0,
                "avg_reflection_score": 0.0,
            }
        success_count = sum(1 for t in traces if t.success)
        total = len(traces)
        return {
            "total": total,
            "success_count": success_count,
            "failure_count": total - success_count,
            "success_rate": success_count / total,
            "avg_duration_ms": sum(t.duration_ms for t in traces) / total,
            "avg_tokens": sum(t.usage_tokens for t in traces) // total,
            "avg_reflection_score": sum(t.reflection_score for t in traces) / total,
        }

    def clear(self) -> int:
        """清空全部轨迹(仅开发/测试用)。

        Returns:
            清空的轨迹数
        """
        count = self.count()
        try:
            if os.path.exists(self._file_path):
                os.remove(self._file_path)
        except OSError as e:
            raise IOError(f"清空轨迹失败: {e}") from e
        return count
