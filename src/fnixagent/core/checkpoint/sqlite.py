"""SqliteCheckpointer —— H3-4 SQLite 持久化 Checkpointer。,
并融合 OpenAI Agents SDK SQLiteSession 的双表 schema(message 独立通道)。

LICENSE 兼容性:
  - LangGraph (langchain-ai/langgraph) —— MIT License
  - OpenAI Agents SDK (openai/openai-agents-python) —— MIT License
  本文件 copy-adapt 自上述两个项目,保留 MIT 许可证兼容性。

设计要点:
  1. 单文件 SQLite + WAL 模式 + check_same_thread=False
     → 跨线程读写不阻塞,无需额外同步原语
  2. 双表 schema:
     - checkpoints(thread_id, checkpoint_id, parent_id, channel_values, channel_versions, versions_seen, metadata, created_at)
     - writes(thread_id, checkpoint_id, task_id, idx, channel, value, created_at)
     → messages 通过 writes 表实现 append-only,不全量重写
  3. setup() 双检锁延迟建表,首次 cursor() 调用时执行
  4. threading.Lock 串行所有 cursor 操作
  5. 标准库 sqlite3,零外部依赖,standalone 友好
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fnixagent.core.checkpoint.base import BaseCheckpointer
from fnixagent.core.checkpoint.types import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

logger = logging.getLogger(__name__)

# ============================================================================
# SQL Schema
# ============================================================================
# 设计要点:
#   - WAL 模式:写入不阻塞读,崩溃恢复性强
#   - checkpoints 表:整快照存储(channel_values + versions + metadata)
#   - writes 表:append-only 中间写,崩溃窗口收窄到单条 write
#   - parent_checkpoint_id:支持回溯历史链(对应 LangGraph 的回溯语义)
# ============================================================================

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id            TEXT NOT NULL,
    checkpoint_id        TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    channel_values       TEXT NOT NULL DEFAULT '{}',
    channel_versions     TEXT NOT NULL DEFAULT '{}',
    versions_seen        TEXT NOT NULL DEFAULT '{}',
    metadata             TEXT NOT NULL DEFAULT '{}',
    created_at           REAL NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
    ON checkpoints(thread_id, created_at DESC);

CREATE TABLE IF NOT EXISTS writes (
    thread_id     TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    task_id       TEXT NOT NULL,
    idx           INTEGER NOT NULL,
    channel       TEXT NOT NULL,
    value         TEXT NOT NULL,
    created_at    REAL NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_id, task_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_writes_thread_cp
    ON writes(thread_id, checkpoint_id, task_id, idx);
"""


class SqliteCheckpointer(BaseCheckpointer):
    """SQLite Checkpointer。

    特性:
      - WAL 模式:读写不互斥,跨线程安全
      - 双表 schema:checkpoints(快照) + writes(append-only 中间写)
      - 标准库 sqlite3,零外部依赖
      - 原子事务:put / put_writes 全部走 BEGIN/COMMIT
      - 跨进程:多进程可同时读同一 SQLite 文件(WAL 模式)

    用法::

        cp = SqliteCheckpointer(db_path="~/.fnix/checkpoints.db")
        config = cp.put({"thread_id": "t1"}, checkpoint, metadata, new_versions)
        tuple = cp.get_tuple(config)
        for t in cp.list({"thread_id": "t1"}, limit=10):
            print(t.metadata.step)
        # 追加中间写(每条 message 一次)
        cp.put_writes(config, [("messages", {"role":"user","content":"hi"})], "task-1")
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        serde: Any = None,
    ) -> None:
        """初始化 SQLite Checkpointer。

        Args:
            db_path: SQLite 数据库路径。":memory:" = 内存数据库(进程内可见)。
                文件路径建议带 .db 后缀。父目录不存在时自动创建。
            serde: 序列化器(暂未使用,保留接口以便扩展)。
        """
        self._db_path: str = str(db_path)
        self._is_memory: bool = self._db_path == ":memory:"
        self._serde = serde

        # 文件模式:确保父目录存在
        if not self._is_memory:
            parent = Path(self._db_path).expanduser().parent
            try:
                parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning("创建 SQLite 父目录失败 %s: %s", parent, e)

        # 单连接 + check_same_thread=False(配合 self._lock 串行化)
        self._conn: sqlite3.Connection = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # 手动事务控制
        )
        self._conn.row_factory = sqlite3.Row
        self._is_setup: bool = False
        # RLock(可重入):允许 _cursor 持锁时调用 setup() 等内部方法
        self._lock: threading.RLock = threading.RLock()

    # ------------------------------------------------------------------
    # 内部:连接管理
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """初始化数据库 schema(幂等,首次调用时执行)。"""
        if self._is_setup:
            return
        with self._lock:
            if self._is_setup:
                return
            try:
                self._conn.executescript(_SCHEMA_SQL)
                self._is_setup = True
            except sqlite3.Error as e:
                logger.error("SQLite schema 初始化失败: %s", e)
                raise

    @contextmanager
    def _cursor(self, *, transaction: bool = True):
        """获取 cursor(线程安全,可选事务)。

        Args:
            transaction: True=BEGIN/COMMIT 包裹,False=无事务(读操作)。
        """
        with self._lock:
            self.setup()
            cur = self._conn.cursor()
            try:
                if transaction:
                    cur.execute("BEGIN")
                yield cur
                if transaction:
                    cur.execute("COMMIT")
            except Exception:
                if transaction:
                    try:
                        cur.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                raise
            finally:
                cur.close()

    # ------------------------------------------------------------------
    # 同步接口实现
    # ------------------------------------------------------------------

    def put(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        """保存检查点(整快照,事务原子)。"""
        thread_id = config.get("thread_id", "") if config else ""
        if not thread_id:
            raise ValueError("thread_id must not be empty")
        parent_checkpoint_id = config.get("checkpoint_id") if config.get("checkpoint_id") else None
        checkpoint_id = uuid.uuid4().hex[:16]
        now = time.time()

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO checkpoints
                    (thread_id, checkpoint_id, parent_checkpoint_id,
                     channel_values, channel_versions, versions_seen,
                     metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    checkpoint_id,
                    parent_checkpoint_id,
                    json.dumps(checkpoint.channel_values, ensure_ascii=False, default=str),
                    json.dumps(checkpoint.channel_versions, ensure_ascii=False, default=str),
                    json.dumps(checkpoint.versions_seen, ensure_ascii=False, default=str),
                    json.dumps(metadata.to_dict(), ensure_ascii=False, default=str),
                    now,
                ),
            )

        return {"thread_id": thread_id, "checkpoint_id": checkpoint_id}

    def put_writes(
        self,
        config: dict,
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """追加中间写(append-only,每条 write 一行)。(节点子任务)执行后立即调用,
        崩溃后可从 last write 恢复,无需重放整个节点。

        Args:
            config:  {"thread_id": str, "checkpoint_id": str}
            writes:  [(channel, value), ...] —— 每个元组是一条 write
            task_id: 当前 task 的 ID
        """
        thread_id = config.get("thread_id", "") if config else ""
        checkpoint_id = config.get("checkpoint_id", "")
        if not thread_id or not checkpoint_id:
            raise ValueError("thread_id 和 checkpoint_id 必须非空")
        if not writes:
            return
        now = time.time()
        with self._cursor() as cur:
            for idx, (channel, value) in enumerate(writes):
                cur.execute(
                    """
                    INSERT OR REPLACE INTO writes
                        (thread_id, checkpoint_id, task_id, idx,
                         channel, value, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        thread_id,
                        checkpoint_id,
                        task_id,
                        idx,
                        channel,
                        json.dumps(value, ensure_ascii=False, default=str),
                        now,
                    ),
                )

    def get_tuple(self, config: dict) -> CheckpointTuple | None:
        """获取检查点元组。checkpoint_id 为 None 时返回最新。"""
        thread_id = config.get("thread_id", "") if config else ""
        if not thread_id:
            return None
        checkpoint_id = config.get("checkpoint_id")

        with self._cursor(transaction=False) as cur:
            if checkpoint_id:
                cur.execute(
                    """
                    SELECT * FROM checkpoints
                    WHERE thread_id=? AND checkpoint_id=?
                    """,
                    (thread_id, checkpoint_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM checkpoints
                    WHERE thread_id=?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (thread_id,),
                )
            row = cur.fetchone()
            if row is None:
                return None

            try:
                channel_values = json.loads(row["channel_values"])
                channel_versions = json.loads(row["channel_versions"])
                versions_seen = json.loads(row["versions_seen"])
                metadata = CheckpointMetadata.from_dict(json.loads(row["metadata"]))
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning("SQLite 检查点反序列化失败: %s", e)
                return None

            checkpoint = Checkpoint(
                channel_values=channel_values,
                channel_versions=channel_versions,
                versions_seen=versions_seen,
                metadata=metadata,
            )
            parent_config = (
                {
                    "thread_id": thread_id,
                    "checkpoint_id": row["parent_checkpoint_id"],
                }
                if row["parent_checkpoint_id"]
                else None
            )
            return CheckpointTuple(
                config={
                    "thread_id": thread_id,
                    "checkpoint_id": row["checkpoint_id"],
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )

    def list(
        self,
        config: dict | None,
        *,
        filter: dict | None = None,
        before: dict | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """列出检查点历史(按时间倒序)。"""
        if config is None:
            return
        thread_id = config.get("thread_id", "")
        if not thread_id:
            return
        before_id = before.get("checkpoint_id") if before else None

        with self._cursor(transaction=False) as cur:
            if before_id:
                cur.execute(
                    """
                    SELECT * FROM checkpoints
                    WHERE thread_id=? AND created_at < (
                        SELECT created_at FROM checkpoints
                        WHERE thread_id=? AND checkpoint_id=?
                    )
                    ORDER BY created_at DESC
                    """,
                    (thread_id, thread_id, before_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM checkpoints
                    WHERE thread_id=?
                    ORDER BY created_at DESC
                    """,
                    (thread_id,),
                )
            rows = cur.fetchall()

        for row in rows:
            try:
                channel_values = json.loads(row["channel_values"])
                channel_versions = json.loads(row["channel_versions"])
                versions_seen = json.loads(row["versions_seen"])
                metadata = CheckpointMetadata.from_dict(json.loads(row["metadata"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            # metadata filter
            if filter:
                match = True
                for k, v in filter.items():
                    if getattr(metadata, k, None) != v:
                        match = False
                        break
                if not match:
                    continue

            checkpoint = Checkpoint(
                channel_values=channel_values,
                channel_versions=channel_versions,
                versions_seen=versions_seen,
                metadata=metadata,
            )
            parent_config = (
                {
                    "thread_id": thread_id,
                    "checkpoint_id": row["parent_checkpoint_id"],
                }
                if row["parent_checkpoint_id"]
                else None
            )
            yield CheckpointTuple(
                config={
                    "thread_id": thread_id,
                    "checkpoint_id": row["checkpoint_id"],
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )
            if limit is not None:
                limit -= 1
                if limit <= 0:
                    break

    # ------------------------------------------------------------------
    # 便捷方法:get_writes(获取某 checkpoint 的中间写)
    # ------------------------------------------------------------------

    def get_writes(
        self,
        config: dict,
        task_id: str | None = None,
    ) -> list[tuple[str, str, Any]]:
        """获取某 checkpoint 下的 writes(中间写)。

        Args:
            config:  {"thread_id": str, "checkpoint_id": str}
            task_id: 过滤指定 task。None=返回所有 task 的 writes。

        Returns:
            [(task_id, channel, value), ...] 按 idx 正序
        """
        thread_id = config.get("thread_id", "") if config else ""
        checkpoint_id = config.get("checkpoint_id", "")
        if not thread_id or not checkpoint_id:
            return []
        with self._cursor(transaction=False) as cur:
            if task_id:
                cur.execute(
                    """
                    SELECT task_id, channel, value FROM writes
                    WHERE thread_id=? AND checkpoint_id=? AND task_id=?
                    ORDER BY idx ASC
                    """,
                    (thread_id, checkpoint_id, task_id),
                )
            else:
                cur.execute(
                    """
                    SELECT task_id, channel, value FROM writes
                    WHERE thread_id=? AND checkpoint_id=?
                    ORDER BY task_id ASC, idx ASC
                    """,
                    (thread_id, checkpoint_id),
                )
            rows = cur.fetchall()
        out: list[tuple[str, str, Any]] = []
        for row in rows:
            try:
                value = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                value = row["value"]
            out.append((row["task_id"], row["channel"], value))
        return out

    def clear_thread(self, thread_id: str) -> int:
        """清空指定 thread 的所有 checkpoints + writes。

        Returns:
            删除的 checkpoint 数量。
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM checkpoints WHERE thread_id=?",
                (thread_id,),
            )
            count = cur.fetchone()[0]
            cur.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
            cur.execute("DELETE FROM writes WHERE thread_id=?", (thread_id,))
        return count

    def close(self) -> None:
        """关闭数据库连接。"""
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except sqlite3.Error:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
