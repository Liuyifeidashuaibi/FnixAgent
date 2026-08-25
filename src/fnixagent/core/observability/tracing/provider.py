"""TracingProvider —— P1-1 顶层入口。

职责:
  - start_trace(name, trace_id=None, **attrs): 启动一个新 Trace,返回 TraceImpl
  - add_span_exporter(exporter):  注册 Span 级 exporter(每个 Span 结束时调用)
  - add_trace_exporter(exporter): 注册 Trace 级 exporter(整个 Trace 结束时调用)
  - get_current_trace():          获取当前上下文的 Trace(基于 contextvars)

Exporter 协议:
  - span exporter:  Callable[[Span], None]
  - trace exporter: Callable[[TraceImpl], None]

全局 Provider:
  - get_provider():    获取全局 Provider(惰性初始化)
  - set_provider(p):   替换全局 Provider(用于测试)
  - reset_provider():  重置为默认 Provider
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import contextvars
import logging
import os
import threading
import uuid
from collections.abc import Callable
from typing import Any

from fnixagent.core.observability.tracing.span import Span
from fnixagent.core.observability.tracing.trace import TraceImpl

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exporter 类型
# ---------------------------------------------------------------------------

SpanExporter = Callable[[Span], None]
TraceExporter = Callable[[TraceImpl], None]

# ---------------------------------------------------------------------------
# TracingProvider
# ---------------------------------------------------------------------------


class TracingProvider:
    """顶层 Tracing Provider。

    用法:
        provider = get_provider()
        with provider.start_trace("agent_run", user_id="u1") as trace:
            with trace.start_span("agent", AgentSpanData(agent_name="paper")):
                ...
    """

    def __init__(self) -> None:
        self._span_exporters: list[SpanExporter] = []
        self._trace_exporters: list[TraceExporter] = []
        # exporter 列表锁:允许并发注册/移除 exporter(线程安全)
        self._exporters_lock = threading.Lock()
        # 当前上下文的 Trace(基于 contextvars,每个线程/协程独立隔离)
        # 支持嵌套 Trace:外层 Trace 完成后自动恢复外层引用
        self._current_trace: contextvars.ContextVar[TraceImpl | None] = contextvars.ContextVar(
            "fnixagent_current_trace", default=None
        )

    # -- Exporter 注册 ------------------------------------------------------
    def add_span_exporter(self, exporter: SpanExporter) -> None:
        """注册 Span 级 exporter。

        每个 Span 结束时调用一次。exporter 异常会被吞掉(不影响主流程)。
        线程安全:内部加锁,允许并发注册。
        """
        with self._exporters_lock:
            self._span_exporters.append(exporter)

    def add_trace_exporter(self, exporter: TraceExporter) -> None:
        """注册 Trace 级 exporter。

        整个 Trace 结束时调用一次。exporter 异常会被吞掉。
        线程安全:内部加锁。
        """
        with self._exporters_lock:
            self._trace_exporters.append(exporter)

    def remove_span_exporter(self, exporter: SpanExporter) -> None:
        """移除已注册的 Span exporter。"""
        with self._exporters_lock:
            try:
                self._span_exporters.remove(exporter)
            except ValueError:
                pass

    def remove_trace_exporter(self, exporter: TraceExporter) -> None:
        """移除已注册的 Trace exporter。"""
        with self._exporters_lock:
            try:
                self._trace_exporters.remove(exporter)
            except ValueError:
                pass

    # -- 启动 Trace ---------------------------------------------------------
    def start_trace(
        self,
        name: str,
        trace_id: str | None = None,
        **attributes: Any,
    ) -> TraceImpl:
        """启动一个新 Trace。

        Args:
            name:        Trace 名称(如 "agent_run"、"chat_completion"),非空
            trace_id:    指定 trace_id(默认自动生成);用于关联外部系统,非空
            **attributes:Trace 属性(user_id/session_id 等)

        Returns:
            TraceImpl 实例(支持 with 语法)

        Raises:
            ValueError: name 或 trace_id 为空字符串
        """
        # 参数校验:name 必须非空
        if not name or not name.strip():
            raise ValueError("Trace name must not be empty")
        # trace_id 若显式提供则必须非空
        if trace_id is not None and not trace_id.strip():
            raise ValueError("trace_id must not be empty")

        tid = trace_id or uuid.uuid4().hex[:16]
        # 保存外层 Trace(支持嵌套 Trace;contextvars 保证线程/协程隔离)
        previous = self._current_trace.get()

        # 快照 exporter 列表,避免回调执行期间被并发修改导致迭代异常
        span_exporters_snapshot = list(self._span_exporters)
        trace_exporters_snapshot = list(self._trace_exporters)

        def _on_span_end(snapshot: Span) -> None:
            # 遍历快照,exporter 异常不影响主流程
            for exporter in span_exporters_snapshot:
                try:
                    exporter(snapshot)
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)

        def _on_trace_end(trace: TraceImpl) -> None:
            for exporter in trace_exporters_snapshot:
                try:
                    exporter(trace)
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)
            # 恢复外层 Trace(contextvars 的 set 在当前上下文生效)
            try:
                self._current_trace.set(previous)
            except Exception:
                # contextvars 异常通常不可恢复,忽略避免影响主流程
                _logger.debug('Unhandled exception', exc_info=True)

        trace = TraceImpl(
            trace_id=tid,
            name=name,
            attributes=attributes,
            on_span_end=_on_span_end,
            on_trace_end=_on_trace_end,
        )
        self._current_trace.set(trace)
        return trace

    # -- 查询 ---------------------------------------------------------------
    def get_current_trace(self) -> TraceImpl | None:
        """获取当前上下文的 Trace(若有)。"""
        return self._current_trace.get()

    @property
    def span_exporter_count(self) -> int:
        """已注册的 Span exporter 数量。"""
        with self._exporters_lock:
            return len(self._span_exporters)

    @property
    def trace_exporter_count(self) -> int:
        """已注册的 Trace exporter 数量。"""
        with self._exporters_lock:
            return len(self._trace_exporters)

    # -- Flush / Shutdown(OTLP 等批量 exporter 的收尾钩子)--------------------
    @staticmethod
    def _exporter_owner(exporter: Any) -> Any:
        """解析 exporter 的宿主对象。

        注册项可能是:实例(自带 flush/shutdown 方法)、绑定方法
        (如 otlp_exporter.export,其 __self__ 携带收尾方法)或普通函数。
        返回携带 flush/shutdown 方法的宿主;无则返回 None。
        """
        if hasattr(exporter, "flush"):
            return exporter
        owner = getattr(exporter, "__self__", None)
        return owner if hasattr(owner, "flush") else None

    def flush(self, timeout: float = 10.0) -> None:
        """通知所有支持 flush 的 exporter 刷出缓冲数据。

        供进程内主动刷盘(如测试断言前、优雅停机)调用。
        exporter 未实现 flush 或 flush 抛异常时静默忽略,不影响主流程。

        Args:
            timeout: 透传给各 exporter.flush 的超时秒数。
        """
        with self._exporters_lock:
            exporters = list(self._span_exporters) + list(self._trace_exporters)
        for exporter in exporters:
            owner = self._exporter_owner(exporter)
            flush_fn = getattr(owner, "flush", None)
            if not callable(flush_fn):
                continue
            try:
                try:
                    flush_fn(timeout=timeout)
                except TypeError:
                    flush_fn()
            except Exception:
                # 单个 exporter 失败不阻断其他 exporter 与主流程
                _logger.debug('Unhandled exception', exc_info=True)

    def shutdown(self, timeout: float = 5.0) -> None:
        """通知所有支持 shutdown 的 exporter 收尾(停线程 + flush 残留)。

        供应用退出路径调用;exporter 异常静默,保证关停流程不被阻断。

        Args:
            timeout: 透传给各 exporter.shutdown 的超时秒数。
        """
        with self._exporters_lock:
            exporters = list(self._span_exporters) + list(self._trace_exporters)
        for exporter in exporters:
            owner = self._exporter_owner(exporter)
            shutdown_fn = getattr(owner, "shutdown", None)
            if callable(shutdown_fn):
                try:
                    shutdown_fn()
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)


# ---------------------------------------------------------------------------
# 全局 Provider 管理
# ---------------------------------------------------------------------------

_global_provider: TracingProvider | None = None
# 单例初始化锁:保证多线程下 get_provider 只创建一个实例(线程安全单例)
_provider_lock = threading.Lock()

# 自动挂载的 OTLP 导出器强引用(防止被 GC 后后台线程/队列失效)
_otlp_exporter: Any | None = None


def _auto_attach_otlp_exporter(provider: TracingProvider) -> None:
    """按环境变量自动挂载 OtlpHttpExporter(provider 初始化接入点)。

    仅当 ``FNIX_OTEL_EXPORTER_OTLP_ENDPOINT`` 设置时启用;导入失败或
    构造失败均静默忽略(可观测性组件绝不影响主流程)。挂载成功后
    保留模块级强引用,供 flush/shutdown 钩子使用。
    """
    global _otlp_exporter
    if not os.getenv("FNIX_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return
    try:
        from fnixagent.core.observability.tracing.exporter import OtlpHttpExporter

        exporter = OtlpHttpExporter()
        if exporter.enabled:
            # 注册实例本身(可调用对象),flush/shutdown 钩子经 __self__ 定位
            provider.add_span_exporter(exporter)
            _otlp_exporter = exporter
            _logger.info(
                "OTLP tracing exporter enabled (endpoint=%s)",
                exporter._endpoint,
            )
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)


def get_provider() -> TracingProvider:
    """获取全局 TracingProvider(惰性初始化,线程安全)。

    首次调用时创建默认 Provider;后续调用返回同一实例。
    使用 double-checked locking 保证多线程下只创建一个实例。
    测试场景可用 set_provider() 替换。

    OTLP 自动接入:若环境变量 ``FNIX_OTEL_EXPORTER_OTLP_ENDPOINT``
    已设置,首次创建 Provider 时会自动挂载 OtlpHttpExporter
    (未设置则完全不创建,零开销)。
    """
    global _global_provider
    if _global_provider is None:
        with _provider_lock:
            if _global_provider is None:
                _global_provider = TracingProvider()
                _auto_attach_otlp_exporter(_global_provider)
    return _global_provider


def set_provider(provider: TracingProvider) -> None:
    """替换全局 TracingProvider(用于测试或自定义配置)。

    线程安全:内部加锁,保证与 get_provider 之间无竞态。
    """
    global _global_provider
    with _provider_lock:
        _global_provider = provider


def reset_provider() -> None:
    """重置全局 Provider 为 None(下次 get_provider 重新创建)。

    线程安全:内部加锁。
    """
    global _global_provider
    with _provider_lock:
        _global_provider = None
