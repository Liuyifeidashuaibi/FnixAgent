"""Span 数据模型 —— P1-1。

定义:
  - SpanStatus:        Span 生命周期状态枚举(STARTED/COMPLETED/FAILED)
  - SpanData 系列:     6 种 Span 携带的结构化数据(基类 + 5 个子类)
  - Span:              不可变快照(SpanImpl 结束时产出,供 exporter 消费)
  - SpanImpl:          可变 Span 实现,支持 with 上下文管理器

Span 树形结构说明:
  - 一个 Trace 包含多棵 Span 树,顶层 Span 的 parent_id=None。
  - 子 Span 通过 TracingScope.current_span_id() 自动获取父 ID,
    形成 parent → child 的树形关系(to_dict 导出后可重建树)。
  - Span 的 trace_id 在整个 Trace 生命周期内不变,用于关联同一 Trace
    下的所有 Span。

设计:
  - OpenAI Agents SDK: SpanData 分类型(agent/llm/tool/guardrail/handoff)
  - OpenTelemetry:     Span 的 started_at/ended_at/status/attributes 模型
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 敏感信息脱敏
# ---------------------------------------------------------------------------

# 敏感字段名匹配模式(不区分大小写):api_key / token / secret / password 等
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|credential|authorization|auth[_-]?header)",
    re.IGNORECASE,
)


def _mask_sensitive(value: Any) -> Any:
    """脱敏单个值:返回固定掩码字符串,长度信息不泄露。

    字符串值统一替换为 "***REDACTED***";非字符串原样返回
    (数字/布尔等本身不含敏感信息)。
    """
    if isinstance(value, str) and value:
        return "***REDACTED***"
    return value


def _filter_sensitive_dict(data: dict) -> dict:
    """过滤字典中的敏感字段(递归一层)。

    键名匹配敏感模式的值会被脱敏;普通字段保留原值。
    用于 Span.attributes / SpanData.arguments 等用户可写数据的导出。
    """
    if not isinstance(data, dict):
        return data
    filtered: dict = {}
    for k, v in data.items():
        key_str = str(k)
        if _SENSITIVE_KEY_PATTERN.search(key_str):
            filtered[k] = _mask_sensitive(v)
        else:
            filtered[k] = v
    return filtered


# ---------------------------------------------------------------------------
# Span 状态
# ---------------------------------------------------------------------------


class SpanStatus:
    """Span 生命周期状态。

    流转:STARTED → COMPLETED | FAILED
    """

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# SpanData 系列(结构化数据,按 Span 类型区分)
# ---------------------------------------------------------------------------


@dataclass
class SpanData:
    """Span 携带的结构化数据基类。

    子类通过 span_type 区分:agent / llm / tool / guardrail / handoff / custom。
    """

    span_type: str = "custom"


@dataclass
class AgentSpanData(SpanData):
    """Agent 层 Span 数据(顶层 Span)。

    对应一次 Agent.reply() 或一次飞轮迭代。
    """

    span_type: str = "agent"
    agent_name: str = ""
    reasoning_mode: str = ""  # react/cot/plan_execute/...
    iteration: int = 0
    thought: str = ""


@dataclass
class LLMSpanData(SpanData):
    """LLM 调用 Span 数据。"""

    span_type: str = "llm"
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False


@dataclass
class ToolSpanData(SpanData):
    """工具调用 Span 数据。"""

    span_type: str = "tool"
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)
    status: str = ""  # success/failed/timeout
    duration_ms: float = 0.0
    error: str = ""
    attempts: int = 1


@dataclass
class GuardrailSpanData(SpanData):
    """Guardrail 校验 Span 数据。"""

    span_type: str = "guardrail"
    direction: str = ""  # input/output
    passed: bool = True
    blocked_reason: str = ""
    risk_score: float = 0.0
    tripwire_triggered: bool = False


@dataclass
class HandoffSpanData(SpanData):
    """Agent 间 Handoff Span 数据(P3-1)。"""

    span_type: str = "handoff"
    from_agent: str = ""
    to_agent: str = ""
    reason: str = ""


# ---------------------------------------------------------------------------
# Span(不可变快照)
# ---------------------------------------------------------------------------


@dataclass
class Span:
    """Span 的不可变快照。

    由 SpanImpl.end() 产出,供 SpanExporter 消费。
    一旦创建不应修改(对 exporter 友好)。
    """

    span_id: str
    trace_id: str
    parent_id: str | None
    name: str
    started_at: float
    ended_at: float | None = None
    status: str = SpanStatus.STARTED
    data: SpanData | None = None
    error: str | None = None
    attributes: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        """Span 持续时间(毫秒),未结束时为 None。"""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000

    def to_dict(self) -> dict:
        """转为字典(用于 JSON 导出/日志)。

        安全:对 attributes 中的敏感字段(api_key/token/secret/password 等)
        自动脱敏,避免 exporter 持久化明文凭证。
        """
        # 导出时过滤敏感字段,防止 API Key 等凭证泄漏到日志/外部系统
        safe_attributes = _filter_sensitive_dict(self.attributes)
        # SpanData 内部可能含敏感参数(如 ToolSpanData.arguments 里的 api_key)
        safe_data = None
        if self.data is not None:
            data_dict = dict(self.data.__dict__)
            # 对 dataclass 内的 dict 类型字段单独脱敏(如 arguments)
            for k, v in data_dict.items():
                if isinstance(v, dict):
                    data_dict[k] = _filter_sensitive_dict(v)
            safe_data = data_dict
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "data": safe_data,
            "error": self.error,
            "attributes": safe_attributes,
        }


# ---------------------------------------------------------------------------
# SpanImpl(可变,context manager)
# ---------------------------------------------------------------------------

# SpanImpl 对象池:复用已结束的 SpanImpl 实例,减少 GC 压力(性能优化)
# 池中的实例在 acquire 时重置状态后供新 Span 使用,release 时归还
_SPAN_POOL: list = []
_SPAN_POOL_LOCK = None  # 延迟初始化,避免 import 时创建锁


def _get_pool_lock():
    """惰性初始化对象池锁(避免 import 时副作用)。"""
    global _SPAN_POOL_LOCK
    if _SPAN_POOL_LOCK is None:
        import threading

        _SPAN_POOL_LOCK = threading.Lock()
    return _SPAN_POOL_LOCK


class SpanImpl:
    """可变的 Span 实现,支持 with 上下文管理器。

    生命周期:
      1. __init__: 生成 span_id,记录 started_at,状态 STARTED
      2. __enter__: 推入 TracingScope(设置 parent_id),返回 self
      3. with 块内: 可调用 set_attribute / set_error
      4. __exit__: 标记 COMPLETED(无异常)或 FAILED(有异常),调用 end()
      5. end(): 产出不可变 Span,触发 exporter(幂等,重复调用不报错)

    注意:本类不直接持有 TracingScope/TraceImpl 引用,而是通过构造注入的
    回调(on_end)与 scope 交互,避免循环依赖。

    对象池:批量创建 Span 时可通过 acquire/release 复用实例,减少 GC 开销。
    """

    # 对象池容量上限(防止池无限增长反而占用内存)
    _POOL_MAX_SIZE = 256

    def __init__(
        self,
        name: str,
        trace_id: str,
        data: SpanData | None = None,
        parent_id: str | None = None,
        on_end: Any | None = None,  # Callable[[Span], None]
    ):
        # 参数校验:name / trace_id 必须非空(防止生成无效 Span)
        if not name or not name.strip():
            raise ValueError("Span name must not be empty")
        if not trace_id or not trace_id.strip():
            raise ValueError("trace_id must not be empty")
        self.span_id = uuid.uuid4().hex[:16]
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.name = name
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.status = SpanStatus.STARTED
        self.data = data
        self.error: str | None = None
        self.attributes: dict = {}
        self._on_end = on_end
        self._ended = False
        self._last_snapshot: Span | None = None

    # -- 对象池(性能优化:减少高频创建/销毁的 GC 开销)----------------------
    @classmethod
    def acquire(
        cls,
        name: str,
        trace_id: str,
        data: SpanData | None = None,
        parent_id: str | None = None,
        on_end: Any | None = None,
    ) -> SpanImpl:
        """从对象池获取实例(池空则新建)。

        复用已 release 的实例,重置状态后返回。若池为空,创建新实例。
        适合高频创建短生命周期 Span 的场景。
        """
        pool_lock = _get_pool_lock()
        instance: SpanImpl | None = None
        with pool_lock:
            if _SPAN_POOL:
                instance = _SPAN_POOL.pop()
        if instance is not None:
            # 复用实例:重新初始化状态(避免旧数据残留)
            instance._reset(
                name=name,
                trace_id=trace_id,
                data=data,
                parent_id=parent_id,
                on_end=on_end,
            )
            return instance
        return cls(
            name=name,
            trace_id=trace_id,
            data=data,
            parent_id=parent_id,
            on_end=on_end,
        )

    def release(self) -> None:
        """归还实例到对象池(仅已 end 的实例可归还)。

        未结束的实例不归还(避免状态泄漏);池满时直接丢弃交由 GC 回收。
        """
        if not self._ended:
            return  # 未结束的 Span 不复用,防止状态污染
        pool_lock = _get_pool_lock()
        with pool_lock:
            if len(_SPAN_POOL) < self._POOL_MAX_SIZE:
                # 清理引用,帮助 GC 释放快照/on_end 闭包
                self._last_snapshot = None
                self._on_end = None
                self.data = None
                self.attributes = {}
                _SPAN_POOL.append(self)

    def _reset(
        self,
        name: str,
        trace_id: str,
        data: SpanData | None = None,
        parent_id: str | None = None,
        on_end: Any | None = None,
    ) -> None:
        """重置实例状态以供复用(对象池场景)。"""
        if not name or not name.strip():
            raise ValueError("Span name must not be empty")
        if not trace_id or not trace_id.strip():
            raise ValueError("trace_id must not be empty")
        self.span_id = uuid.uuid4().hex[:16]
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.name = name
        self.started_at = time.time()
        self.ended_at = None
        self.status = SpanStatus.STARTED
        self.data = data
        self.error = None
        self.attributes = {}
        self._on_end = on_end
        self._ended = False
        self._last_snapshot = None

    # -- 上下文管理器 -------------------------------------------------------
    def __enter__(self) -> SpanImpl:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.set_error(f"{exc_type.__name__}: {exc_val}")
        self.end()

    # -- 状态变更 -----------------------------------------------------------
    def set_attribute(self, key: str, value: Any) -> None:
        """设置 Span 属性(键值对,用于附加自定义信息)。

        注意:不应将 API Key / Token 等凭证写入 attributes,
        to_dict() 会对敏感字段名(api_key/token/secret/password)自动脱敏。
        """
        self.attributes[key] = value

    def set_error(self, error: str) -> None:
        """标记 Span 失败并记录错误信息。"""
        self.error = error
        self.status = SpanStatus.FAILED

    def end(self) -> Span:
        """结束 Span,产出不可变快照并触发 exporter。

        幂等:多次调用只生效一次,重复调用返回首次产出的快照,不抛异常。
        这保证了用户重复调用 end() 或 with 块退出后再次 export() 的安全。
        """
        if self._ended:
            # 已结束:返回上次产出的快照(幂等,不重复触发 exporter)
            if self._last_snapshot is not None:
                return self._last_snapshot
            # 极端情况:_ended=True 但 _last_snapshot 为 None,返回占位快照
            return Span(
                span_id=self.span_id,
                trace_id=self.trace_id,
                parent_id=self.parent_id,
                name=self.name,
                started_at=self.started_at,
                ended_at=self.ended_at,
                status=self.status,
                data=self.data,
                error=self.error,
                attributes=dict(self.attributes),
            )
        self.ended_at = time.time()
        if self.status != SpanStatus.FAILED:
            self.status = SpanStatus.COMPLETED
        snapshot = Span(
            span_id=self.span_id,
            trace_id=self.trace_id,
            parent_id=self.parent_id,
            name=self.name,
            started_at=self.started_at,
            ended_at=self.ended_at,
            status=self.status,
            data=self.data,
            error=self.error,
            attributes=dict(self.attributes),
        )
        self._last_snapshot = snapshot
        self._ended = True
        # 触发 exporter(通过回调);exporter 异常不影响主流程
        if self._on_end is not None:
            try:
                self._on_end(snapshot)
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        return snapshot

    def export(self) -> Span:
        """显式导出(等价于 end(),幂等)。"""
        return self.end()
