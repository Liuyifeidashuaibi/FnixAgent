"""
Durable Execution - 持久化执行 (Durable Execution)
===================================================
对标 Restate / DBOS / Temporal 的 Durable Execution 模型。

设计要点:
  - 检查点 JSON 序列化 (修复原版 str(dict) bug)
  - 可恢复: 进程崩溃后可从检查点恢复
  - 可重放: 记录操作日志, 支持重放
  - 可插拔存储: StorageBackend (Postgres/Redis/本地 FS)

核心概念:
  - Checkpoint: 进程快照 (状态 + 资源使用 + 能力)
  - Journal: 操作日志 (syscall 调用记录)
  - Recovery: 崩溃后从 checkpoint + journal 恢复
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.agent.types import StorageBackend, utcnow_iso


@dataclass
class JournalEntry:
    """操作日志条目 (类比 WAL)。

    记录每次 syscall 调用, 用于崩溃后重放。

    Attributes:
        entry_id: 条目 ID
        pid: 进程 ID
        syscall: syscall 名称
        args: 调用参数
        result: 调用结果 (None = 未完成)
        success: 是否成功
        timestamp: 时间戳
        sequence: 序列号 (单调递增, 用于重放顺序)
    """
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pid: str = ""
    syscall: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    success: bool = False
    timestamp: str = field(default_factory=utcnow_iso)
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "pid": self.pid,
            "syscall": self.syscall,
            "args": dict(self.args),
            "result": self.result,
            "success": self.success,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }


class DurableExecutionManager:
    """Durable Execution 管理器 (对标 Restate)。

    功能:
      - 保存/恢复进程检查点
      - 记录操作日志 (journal)
      - 重放操作日志 (崩溃恢复)
      - 可插拔存储后端

    使用方式:
      1. 进程开始前 save_checkpoint
      2. 每次 syscall 后 append_journal
      3. 崩溃后 recover: 加载 checkpoint + 重放 journal
    """

    def __init__(self, storage: StorageBackend | None = None):
        self._storage = storage
        # 内存缓存 (无 storage 时降级)
        self._checkpoints: dict[str, str] = {}  # pid → JSON
        self._journals: dict[str, list[JournalEntry]] = {}  # pid → entries
        self._sequences: dict[str, int] = {}  # pid → next sequence

    # --- 检查点 ---

    async def save_checkpoint(self, pid: str, checkpoint: dict[str, Any]) -> str:
        """保存检查点 (JSON 序列化)。"""
        cp_json = json.dumps(checkpoint, ensure_ascii=False)
        self._checkpoints[pid] = cp_json
        if self._storage:
            await self._storage.set(f"checkpoint:{pid}", cp_json)
        return cp_json

    async def load_checkpoint(self, pid: str) -> dict[str, Any] | None:
        """加载检查点。"""
        if self._storage:
            cp_str = await self._storage.get(f"checkpoint:{pid}")
        else:
            cp_str = self._checkpoints.get(pid)
        if cp_str is None:
            return None
        try:
            return json.loads(cp_str)
        except json.JSONDecodeError:
            return None

    async def delete_checkpoint(self, pid: str) -> bool:
        """删除检查点。"""
        existed = pid in self._checkpoints
        self._checkpoints.pop(pid, None)
        if self._storage:
            return await self._storage.delete(f"checkpoint:{pid}")
        return existed

    # --- 操作日志 ---

    async def append_journal(self, entry: JournalEntry) -> None:
        """追加操作日志。"""
        entry.sequence = self._sequences.get(entry.pid, 0) + 1
        self._sequences[entry.pid] = entry.sequence
        self._journals.setdefault(entry.pid, []).append(entry)
        if self._storage:
            await self._storage.set(
                f"journal:{entry.pid}:{entry.sequence}",
                json.dumps(entry.to_dict(), ensure_ascii=False),
            )

    async def get_journal(self, pid: str,
                          since_sequence: int = 0) -> list[JournalEntry]:
        """获取操作日志 (从指定序列号开始)。"""
        if self._storage:
            keys = await self._storage.list_prefix(f"journal:{pid}:")
            entries: list[JournalEntry] = []
            for key in keys:
                entry_str = await self._storage.get(key)
                if entry_str:
                    try:
                        entry_dict = json.loads(entry_str)
                        if entry_dict.get("sequence", 0) > since_sequence:
                            entries.append(JournalEntry(**entry_dict))
                    except (json.JSONDecodeError, TypeError):
                        continue
            entries.sort(key=lambda e: e.sequence)
            return entries
        # 内存模式
        entries = self._journals.get(pid, [])
        return [e for e in entries if e.sequence > since_sequence]

    async def clear_journal(self, pid: str) -> int:
        """清空操作日志。"""
        count = len(self._journals.get(pid, []))
        self._journals.pop(pid, None)
        self._sequences.pop(pid, None)
        if self._storage:
            keys = await self._storage.list_prefix(f"journal:{pid}:")
            for key in keys:
                await self._storage.delete(key)
        return count

    # --- 恢复 ---

    async def recover(self, pid: str) -> dict[str, Any] | None:
        """崩溃恢复: 加载检查点 + 操作日志。

        Returns:
            {"checkpoint": dict, "journal": list[dict], "replayable": bool}
        """
        checkpoint = await self.load_checkpoint(pid)
        if checkpoint is None:
            return None
        journal = await self.get_journal(pid)
        return {
            "checkpoint": checkpoint,
            "journal": [e.to_dict() for e in journal],
            "journal_length": len(journal),
            "replayable": True,
            "recovered_at": utcnow_iso(),
        }

    # --- 统计 ---

    def get_stats(self) -> dict[str, Any]:
        return {
            "cached_checkpoints": len(self._checkpoints),
            "cached_journals": len(self._journals),
            "total_journal_entries": sum(len(v) for v in self._journals.values()),
            "has_storage": self._storage is not None,
        }


__all__ = ["DurableExecutionManager", "JournalEntry"]
