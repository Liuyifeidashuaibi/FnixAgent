"""Checkpoint 持久化模块 —— P1-2。,提供 Agent 状态的持久化与恢复能力。

模块组成:
  - types:    Checkpoint / CheckpointMetadata / CheckpointTuple 数据结构
  - base:     BaseCheckpointer 抽象基类(同步 + 异步接口)
  - memory:   MemoryCheckpointer(内存版,测试用)
  - postgres: PostgresCheckpointer(生产用,需 psycopg)
  - manager:  CheckpointManager(P2-04,工作流状态持久化与恢复,)

设计要点:
  - channel_values:     当前所有 channel 的值(对应 GraphState 各字段)
  - channel_versions:   每个 channel 的版本号(用于增量更新检测)
  - versions_seen:      每个节点已见的 channel 版本(避免重复处理)
  - metadata:           检查点元信息(source/step/writes/score)

典型流程:
    # P1-2: LangGraph 风格 Checkpointer(细粒度 channel 版本化)
    checkpointer = MemoryCheckpointer()
    # 保存
    config = checkpointer.put(thread_id, channel_values, metadata)
    # 恢复
    tuple = checkpointer.get_tuple(config)
    # 列出历史
    tuples = checkpointer.list(thread_id)

    # P2-04: CheckpointManager(工作流每步检查点 + 崩溃恢复)
    mgr = get_checkpoint_manager()
    mgr.save(task_id, node="think", state=ctx.to_dict())
    entry = mgr.load(task_id)
    if entry and entry.status == "active":
        ctx = WorkflowContext.from_dict(entry.state)
        await engine.run(ctx)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.checkpoint.base import BaseCheckpointer
from fnixagent.core.checkpoint.manager import (
    CheckpointEntry,
    CheckpointManager,
    get_checkpoint_manager,
    reset_checkpoint_manager,
)
from fnixagent.core.checkpoint.memory import MemoryCheckpointer
from fnixagent.core.checkpoint.types import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

__all__ = [
    # types
    "Checkpoint",
    "CheckpointMetadata",
    "CheckpointTuple",
    # base
    "BaseCheckpointer",
    # implementations
    "MemoryCheckpointer",
    # P2-04: 检查点管理器(工作流状态持久化与恢复)
    "CheckpointEntry",
    "CheckpointManager",
    "get_checkpoint_manager",
    "reset_checkpoint_manager",
]

# PostgresCheckpointer 按需导入(psycopg 可能未安装)
try:
    from fnixagent.core.checkpoint.postgres import PostgresCheckpointer  # noqa: F401

    __all__.append("PostgresCheckpointer")
except ImportError:
    pass

# SqliteCheckpointer 按需导入(sqlite3 是标准库,通常可用;此 try 仅为防御性)
try:
    from fnixagent.core.checkpoint.sqlite import SqliteCheckpointer  # noqa: F401

    __all__.append("SqliteCheckpointer")
except ImportError:
    pass
