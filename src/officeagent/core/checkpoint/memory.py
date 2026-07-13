"""MemoryCheckpointer —— P1-2 内存版 Checkpointer。

用于测试和开发环境,数据存储在内存 dict 中(线程安全)。
不持久化,进程退出即丢失。

数据结构:
    self._storage: dict[thread_id, list[CheckpointTuple]]
    每个 thread 维护一个按 checkpoint_id 顺序的列表(最新在尾部)。

容量管理:
    单 thread 的检查点数量上限为 max_checkpoints_per_thread(默认 1000),
    超出后淘汰最早的检查点(LRU,FIFO 淘汰)。
    跨 thread 的总 thread 数上限为 max_threads(默认 10000),
    超出后淘汰最近未访问的 thread(基于 OrderedDict 的 LRU)。
    这两个上限防止异常场景下内存无限增长导致 OOM。
"""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from typing import Iterator, Optional

from officeagent.core.checkpoint.base import BaseCheckpointer
from officeagent.core.checkpoint.types import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)


class MemoryCheckpointer(BaseCheckpointer):
    """内存版 Checkpointer(线程安全,测试用)。

    用法:
        cp = MemoryCheckpointer()
        config = cp.put({"thread_id": "t1"}, checkpoint, metadata, new_versions)
        tuple = cp.get_tuple(config)
        for t in cp.list({"thread_id": "t1"}, limit=10):
            print(t.metadata.step)

    容量与淘汰:
        - max_checkpoints_per_thread:单 thread 检查点上限,超出 FIFO 淘汰
        - max_threads:总 thread 数上限,超出 LRU 淘汰最久未访问的 thread
    """

    def __init__(
        self,
        max_checkpoints_per_thread: int = 1000,
        max_threads: int = 10000,
    ) -> None:
        """初始化。

        Args:
            max_checkpoints_per_thread: 单 thread 检查点数量上限(LRU 淘汰)
            max_threads: 总 thread 数量上限(LRU 淘汰)
        """
        # OrderedDict 实现 thread 级 LRU:访问时 move_to_end,淘汰时 popitem(last=False)
        self._storage: "OrderedDict[str, list[CheckpointTuple]]" = OrderedDict()
        self._lock = threading.RLock()
        self._max_checkpoints_per_thread = max_checkpoints_per_thread
        self._max_threads = max_threads

    def put(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        """保存检查点(追加到 thread 的列表尾部)。

        Args:
            config: 必须含 thread_id(非空)
            checkpoint: 检查点内容
            metadata: 元信息
            new_versions: 新增的 channel 版本

        Raises:
            ValueError: thread_id 为空
        """
        thread_id = config.get("thread_id", "")
        # 参数校验:thread_id 非空
        if not thread_id:
            raise ValueError("thread_id must not be empty")

        parent_config = (
            {"thread_id": thread_id, "checkpoint_id": config.get("checkpoint_id")}
            if config.get("checkpoint_id")
            else None
        )
        checkpoint_id = uuid.uuid4().hex[:16]
        new_config = {"thread_id": thread_id, "checkpoint_id": checkpoint_id}

        tuple = CheckpointTuple(
            config=new_config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
        )

        with self._lock:
            # thread 级 LRU:已存在则移到末尾(最近访问)
            if thread_id in self._storage:
                self._storage.move_to_end(thread_id)
            else:
                self._storage[thread_id] = []
                # thread 数量上限:超出则淘汰最久未访问的 thread
                if len(self._storage) > self._max_threads:
                    self._storage.popitem(last=False)  # FIFO 淘汰最早访问的
            self._storage[thread_id].append(tuple)
            # 检查点数量上限:超出则 FIFO 淘汰最早的检查点
            if len(self._storage[thread_id]) > self._max_checkpoints_per_thread:
                self._storage[thread_id].pop(0)

        return new_config

    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """获取检查点元组。

        checkpoint_id 为 None 时返回最新;否则返回指定 ID。
        访问时更新 thread 的 LRU 位置。
        """
        thread_id = config.get("thread_id", "")
        checkpoint_id = config.get("checkpoint_id")

        with self._lock:
            tuples = self._storage.get(thread_id)
            if not tuples:
                return None
            # thread 级 LRU:访问时移到末尾
            self._storage.move_to_end(thread_id)
            if checkpoint_id is None:
                return tuples[-1]
            for t in tuples:
                if t.checkpoint_id == checkpoint_id:
                    return t
            return None

    def list(
        self,
        config: Optional[dict],
        *,
        filter: Optional[dict] = None,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """列出检查点历史(按时间倒序)。"""
        if config is None:
            return
        thread_id = config.get("thread_id", "")
        before_id = before.get("checkpoint_id") if before else None

        with self._lock:
            tuples = list(self._storage.get(thread_id, []))

        # 倒序
        tuples.reverse()

        # before 过滤
        if before_id is not None:
            filtered = []
            for t in tuples:
                if t.checkpoint_id == before_id:
                    break
                filtered.append(t)
            tuples = filtered

        # metadata 过滤
        if filter:
            filtered = []
            for t in tuples:
                match = True
                for k, v in filter.items():
                    if getattr(t.metadata, k, None) != v:
                        match = False
                        break
                if match:
                    filtered.append(t)
            tuples = filtered

        # limit
        if limit is not None:
            tuples = tuples[:limit]

        for t in tuples:
            yield t

    def clear(self) -> None:
        """清空全部存储(测试辅助)。"""
        with self._lock:
            self._storage.clear()

    def clear_thread(self, thread_id: str) -> None:
        """清空指定 thread 的检查点。"""
        with self._lock:
            self._storage.pop(thread_id, None)

    @property
    def thread_count(self) -> int:
        """当前存储的 thread 数量。"""
        with self._lock:
            return len(self._storage)

    def checkpoint_count(self, thread_id: str) -> int:
        """指定 thread 的检查点数量。"""
        with self._lock:
            return len(self._storage.get(thread_id, []))
