"""BaseCheckpointer 抽象基类 —— P1-2。

定义所有 Checkpointer 实现的统一接口(同步 + 异步)。。

核心方法:
  - put / aput:           保存检查点
  - get / aget:           获取检查点内容(返回 dict)
  - get_tuple / aget_tuple: 获取检查点元组(含 config + metadata)
  - list / alist:         列出某 thread 的历史检查点
  - get_state / aget_state: 获取当前状态(channel_values)
  - update_state / aupdate_state: 增量更新状态

config 格式:{"thread_id": str, "checkpoint_id": Optional[str]}
  - thread_id 必填
  - checkpoint_id 可选(为 None 时表示最新检查点)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
from collections.abc import Iterator

from fnixagent.core.checkpoint.types import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

class BaseCheckpointer(abc.ABC):
    """Checkpointer 抽象基类。

    子类必须实现同步方法;异步方法默认委托给同步方法(子类可覆盖以优化)。
    """

    # ------------------------------------------------------------------
    # 同步接口(子类必须实现)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def put(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        """保存检查点。

        Args:
            config:       {"thread_id": str, "checkpoint_id": Optional[str]}
                          (checkpoint_id 为父检查点 ID,可为 None)
            checkpoint:   检查点内容
            metadata:     检查点元信息
            new_versions: 本次新增的 channel 版本(channel → version)

        Returns:
            新检查点的 config({"thread_id": ..., "checkpoint_id": <new_id>})
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_tuple(self, config: dict) -> CheckpointTuple | None:
        """获取检查点元组。

        Args:
            config: {"thread_id": str, "checkpoint_id": Optional[str]}
                    checkpoint_id 为 None 时返回最新检查点

        Returns:
            CheckpointTuple 或 None(不存在时)
        """
        raise NotImplementedError

    @abc.abstractmethod
    def list(
        self,
        config: dict | None,
        *,
        filter: dict | None = None,
        before: dict | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """列出检查点历史。

        Args:
            config: {"thread_id": str}(必填);其他字段可选
            filter: 元数据过滤(如 {"source": "loop"})
            before: 只返回此 config 之前的检查点
            limit:  最多返回数量

        Yields:
            CheckpointTuple(按时间倒序)
        """
        raise NotImplementedError

    # -- 派生方法(基于 get_tuple,子类通常无需覆盖)-------------------------

    def get(self, config: dict) -> dict | None:
        """获取检查点的 channel_values(快捷方式)。"""
        tuple = self.get_tuple(config)
        if tuple is None:
            return None
        return tuple.checkpoint.channel_values

    def get_state(self, config: dict) -> dict | None:
        """获取当前状态(channel_values)。等价于 get()。"""
        return self.get(config)

    def update_state(
        self,
        config: dict,
        values: dict,
        metadata: dict | None = None,
    ) -> dict:
        """增量更新状态(创建新检查点)。

        基于"读-改-写"模式:先读取当前检查点的 channel_values 与
        channel_versions,合并新值后版本号 +1,再 put 新检查点。
        注意:本方法非原子操作,并发调用同一 thread 可能产生"丢失更新"。
        如需严格并发安全,子类应重写为基于事务/行锁的实现
        (PostgresCheckpointer 可用 SELECT ... FOR UPDATE)。

        Args:
            config:   当前配置(必须含 thread_id,非空)
            values:   要更新的 channel_values
            metadata: 额外元信息

        Returns:
            新检查点的 config

        Raises:
            ValueError: thread_id 为空
        """
        # 参数校验:thread_id 必须非空
        thread_id = config.get("thread_id", "") if config else ""
        if not thread_id:
            raise ValueError("thread_id must not be empty")

        tuple = self.get_tuple(config)
        if tuple is None:
            # 创建全新检查点
            old_values: dict = {}
            old_versions: dict = {}
            step = 0
        else:
            old_values = dict(tuple.checkpoint.channel_values)
            old_versions = dict(tuple.checkpoint.channel_versions)
            step = tuple.metadata.step + 1

        # 合并新值(后者覆盖前者)
        new_values = {**old_values, **values}
        # 更新版本号(变更的 channel 版本 +1)
        # 注意:版本号自增需在子类的锁/事务保护下完成,避免并发竞态
        new_versions = dict(old_versions)
        for channel in values:
            new_versions[channel] = new_versions.get(channel, 0) + 1

        checkpoint = Checkpoint(
            channel_values=new_values,
            channel_versions=new_versions,
            versions_seen={},
            metadata=CheckpointMetadata(
                source="update",
                step=step,
                writes=dict(values),
            ),
        )
        if metadata:
            checkpoint.metadata.writes.update(metadata)

        return self.put(
            config={"thread_id": thread_id, "checkpoint_id": None},
            checkpoint=checkpoint,
            metadata=checkpoint.metadata,
            new_versions={k: new_versions[k] for k in values if k in new_versions},
        )

    # ------------------------------------------------------------------
    # 异步接口(默认委托给同步,子类可覆盖)
    # ------------------------------------------------------------------

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        """异步保存检查点(默认委托给同步)。"""
        return self.put(config, checkpoint, metadata, new_versions)

    async def aget_tuple(self, config: dict) -> CheckpointTuple | None:
        """异步获取检查点元组。"""
        return self.get_tuple(config)

    async def alist(
        self,
        config: dict | None,
        *,
        filter: dict | None = None,
        before: dict | None = None,
        limit: int | None = None,
    ):
        """异步列出检查点。"""
        for tuple in self.list(config, filter=filter, before=before, limit=limit):
            yield tuple

    async def aget(self, config: dict) -> dict | None:
        """异步获取 channel_values。"""
        return self.get(config)

    async def aget_state(self, config: dict) -> dict | None:
        """异步获取当前状态。"""
        return self.get_state(config)

    async def aupdate_state(
        self,
        config: dict,
        values: dict,
        metadata: dict | None = None,
    ) -> dict:
        """异步增量更新状态。"""
        return self.update_state(config, values, metadata)
