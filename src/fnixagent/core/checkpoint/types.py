"""Checkpoint 数据结构 —— P1-2。

定义 Checkpoint 持久化所需的数据结构,与 LangGraph 兼容:
  - CheckpointMetadata: 检查点元信息
  - Checkpoint:         检查点内容(channel_values + versions)
  - CheckpointTuple:    检查点元组(config + checkpoint + metadata + parent_config)

术语对照(LangGraph 概念 → 本实现):
  - channel:        GraphState 的一个字段(如 messages/iteration/trace)
  - channel_values: 所有 channel 的当前值(等价于 GraphState 快照)
  - channel_versions: 每个 channel 的版本号(每次更新自增)
  - versions_seen:  每个节点已处理的 channel 版本(避免重复处理)
  - thread_id:       会话/线程标识(一个用户会话一个 thread_id)
  - checkpoint_id:   检查点唯一 ID(同一 thread 可有多个检查点)

Channel + Version 模型说明:
  - channel 是 GraphState 的字段名(如 "messages" / "iteration"),每个 channel
    独立版本化:channel_versions[channel] 是单调递增的整数,每次该 channel 被写入
    时版本号 +1。LangGraph 节点据此判断"哪些 channel 自上次执行后有更新"。
  - versions_seen[node_name][channel] 记录某节点上次处理该 channel 时的版本号;
    节点执行前对比 channel_versions[channel] 与 versions_seen[node][channel],
    若前者更大说明有新数据需处理,处理完后更新 versions_seen。
  - 该模型支持增量执行:只有发生变更的 channel 会触发节点重新运行,
    避免每次全量重算(对含大量历史消息的场景尤其重要)。
  - 并发安全注意:versions_seen 的更新需在 Checkpointer 锁保护下完成
    (MemoryCheckpointer 用 RLock,PostgresCheckpointer 用行锁/事务),
    否则并发节点执行会出现"丢失更新"竞态。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# 敏感字段名匹配模式(不区分大小写):序列化前据此脱敏
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|credential|authorization|"
    r"auth[_-]?header|private[_-]?key|access[_-]?token|refresh[_-]?token)",
    re.IGNORECASE,
)


def _mask_sensitive_value(value: Any) -> Any:
    """脱敏单个值:字符串替换为固定掩码,非字符串原样返回。"""
    if isinstance(value, str) and value:
        return "***REDACTED***"
    return value


def _filter_sensitive(data: dict) -> dict:
    """递归过滤字典中的敏感字段(深度优先)。

    - 键名匹配敏感模式的值替换为 "***REDACTED***"
    - 嵌套 dict 递归过滤;list 中的 dict 元素也递归
    - 用于 Checkpoint.to_serializable / CheckpointMetadata.to_dict,
      防止 api_key/token 等凭证被持久化到 Postgres JSONB
    """
    if not isinstance(data, dict):
        return data
    filtered: dict = {}
    for k, v in data.items():
        key_str = str(k)
        if _SENSITIVE_KEY_PATTERN.search(key_str):
            filtered[k] = _mask_sensitive_value(v)
        elif isinstance(v, dict):
            filtered[k] = _filter_sensitive(v)
        elif isinstance(v, list):
            filtered[k] = [
                _filter_sensitive(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            filtered[k] = v
    return filtered


@dataclass
class CheckpointMetadata:
    """检查点元信息。

    Attributes:
        source: 检查点来源
            - loop:    主循环每步自动保存
            - input:   用户输入后保存
            - update:  外部主动更新
            - interrupt: 中断时保存(等待人工审核等)
        step:   当前步数(主循环迭代次数)
        writes: 本次写入的 channel 及其新值(增量)
        score:  检查点质量评分(可选,用于选择最佳恢复点)
    """

    source: str = "loop"  # loop/input/update/interrupt
    step: int = -1
    writes: dict = field(default_factory=dict)
    score: float | None = None

    def to_dict(self) -> dict:
        """转为字典(用于持久化)。

        安全:对 writes 中的敏感字段(api_key/token 等)递归脱敏,
        防止凭证被写入 Postgres JSONB。
        """
        return {
            "source": self.source,
            "step": self.step,
            "writes": _filter_sensitive(dict(self.writes)),
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CheckpointMetadata:
        return cls(
            source=data.get("source", "loop"),
            step=data.get("step", -1),
            writes=dict(data.get("writes", {})),
            score=data.get("score"),
        )


@dataclass
class Checkpoint:
    """检查点内容。

    Attributes:
        channel_values:   所有 channel 的当前值(可序列化的 GraphState 快照)
        channel_versions: 每个 channel 的版本号(channel_name → int)
        versions_seen:    每个节点已见的 channel 版本(node_name → {channel → version})
        metadata:         检查点元信息
    """

    channel_values: dict = field(default_factory=dict)
    channel_versions: dict = field(default_factory=dict)
    versions_seen: dict = field(default_factory=dict)
    metadata: CheckpointMetadata = field(default_factory=CheckpointMetadata)

    def to_serializable(self) -> dict:
        """转为可 pickle/JSON 序列化的字典。

        安全:对 channel_values 中的敏感字段(api_key/token 等)递归脱敏,
        避免凭证被持久化到 Postgres JSONB 或日志中。
        channel_versions / versions_seen 的值是整数版本号,无需脱敏。
        """
        return {
            "channel_values": _filter_sensitive(dict(self.channel_values)),
            "channel_versions": dict(self.channel_versions),
            "versions_seen": dict(self.versions_seen),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_serializable(cls, data: dict) -> Checkpoint:
        """从序列化字典重建。"""
        return cls(
            channel_values=dict(data.get("channel_values", {})),
            channel_versions=dict(data.get("channel_versions", {})),
            versions_seen=dict(data.get("versions_seen", {})),
            metadata=CheckpointMetadata.from_dict(data.get("metadata", {})),
        )


@dataclass
class CheckpointTuple:
    """检查点元组(查询返回的完整记录)。

    Attributes:
        config:        本检查点的配置({"thread_id": ..., "checkpoint_id": ...})
        checkpoint:    检查点内容
        metadata:      检查点元信息(等价于 checkpoint.metadata,冗余便于查询)
        parent_config: 父检查点的配置(用于回溯历史)
    """

    config: dict
    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    parent_config: dict | None = None

    @property
    def thread_id(self) -> str:
        return self.config.get("thread_id", "")

    @property
    def checkpoint_id(self) -> str:
        return self.config.get("checkpoint_id", "")
