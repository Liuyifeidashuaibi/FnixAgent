"""Trace 实现 —— P1-1。

一个 Trace 对应一次完整的请求处理(如一次 Agent.reply() 或一次 API 调用),
包含多个 Span 构成的树形结构。

Span 树形结构:
  - 一个 Trace 维护一个 Span 列表(_spans),按 end 顺序追加。
  - 每个 Span 持有 parent_id,据此可重建树:遍历 spans,
    按 parent_id 分组即得到 children 映射;parent_id=None 的是根 Span。
  - 顶层 Span 的 parent_id 在 start_span 时由 TracingScope.current_span_id()
    返回 None(栈空),因此每个 Trace 可含多棵独立子树。

职责:
  - start_span(name, data): 创建子 Span(自动从 TracingScope 读 parent_id)
  - end(status):             结束整个 Trace,触发 trace exporter
  - export():                导出全部 Span 快照

与 SpanImpl 的协作:
  - start_span 创建 SpanImpl 并 push 到 TracingScope
  - SpanImpl.__exit__ 自动 end()(产出 Span 快照)并 pop scope
  - Trace 收集所有 Span 快照,结束时一次性交给 trace exporter
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from fnixagent.core.observability.tracing.scope import TracingScope
from fnixagent.core.observability.tracing.span import (
    Span,
    SpanData,
    SpanImpl,
    SpanStatus,
)


class TraceImpl:
    """一个 Trace 的运行时实现。

    由 TracingProvider.start_trace() 创建,不支持直接实例化(需经 Provider)。

    内存与并发:
      - _spans 上限为 MAX_SPANS,超出后丢弃最早 Span(防内存泄漏)。
      - _spans_lock 保证多线程并发 append 安全(子 Span 可能跨线程 end)。
      - Trace 结束后清理 _spans 引用,帮助 GC 释放。
    """

    # 单个 Trace 的 Span 数量上限(防泄漏:异常场景下无限创建 Span 会被截断)
    MAX_SPANS = 10000

    def __init__(
        self,
        trace_id: str,
        name: str,
        attributes: dict | None = None,
        on_span_end: Callable[[Span], None] | None = None,
        on_trace_end: Callable[[TraceImpl], None] | None = None,
    ):
        self.trace_id = trace_id
        self.name = name
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.status = SpanStatus.STARTED
        self.attributes: dict = dict(attributes or {})
        # _spans 收集所有已 end 的 Span 快照;加锁保护并发 append
        self._spans: list[Span] = []
        self._spans_lock = threading.Lock()
        self._on_span_end = on_span_end
        self._on_trace_end = on_trace_end
        self._ended = False
        self._scope = TracingScope()

    # -- Span 管理 ----------------------------------------------------------
    def start_span(
        self,
        name: str,
        data: SpanData | None = None,
        **attributes: Any,
    ) -> SpanImpl:
        """创建并启动一个子 Span。

        自动从 TracingScope 读取 parent_id(栈顶 Span 的 ID)。
        返回的 SpanImpl 可用 with 语法:
            with trace.start_span("llm", LLMSpanData(...)) as span:
                ...

        Args:
            name:        Span 名称(如 "llm_call"、"tool_search"),非空
            data:        SpanData 实例(携带结构化数据)
            **attributes:Span 属性(键值对)

        Raises:
            ValueError: name 为空
        """
        # 参数校验:name 非空(SpanImpl.__init__ 也会校验,提前抛出更清晰)
        if not name or not name.strip():
            raise ValueError("Span name must not be empty")

        parent_id = self._scope.current_span_id()

        def _on_end(snapshot: Span) -> None:
            # 收集到本 Trace(加锁,因 Span 可能跨线程 end)
            with self._spans_lock:
                # 容量上限保护:超出 MAX_SPANS 时丢弃最早 Span(防泄漏)
                if len(self._spans) >= self.MAX_SPANS:
                    # 丢弃最早的 Span,保留近期数据(FIFO 淘汰)
                    self._spans.pop(0)
                self._spans.append(snapshot)
            # 触发 span exporter(异常不影响主流程)
            if self._on_span_end is not None:
                try:
                    self._on_span_end(snapshot)
                except Exception:
                    pass

        span = SpanImpl(
            name=name,
            trace_id=self.trace_id,
            data=data,
            parent_id=parent_id,
            on_end=_on_end,
        )
        for k, v in attributes.items():
            span.set_attribute(k, v)
        # push 到 scope(成为后续子 Span 的 parent)
        # contextvars 保证跨线程/协程隔离,此处 push 仅影响当前上下文
        self._scope.push(span)

        # 包装 __exit__ 以确保 pop(即使 SpanImpl.__exit__ 已 end,也需 pop scope)
        # 传入 expected=span 校验栈顶身份,避免异常场景下 pop 错误的 Span
        original_exit = span.__exit__

        def _wrapped_exit(exc_type, exc_val, exc_tb):
            try:
                return original_exit(exc_type, exc_val, exc_tb)
            finally:
                # pop 时校验栈顶是否为当前 span,防止嵌套异常导致栈错乱
                self._scope.pop(expected=span)

        span.__exit__ = _wrapped_exit  # type: ignore[method-assign]
        return span

    # -- Trace 结束 ---------------------------------------------------------
    def end(self, status: str = SpanStatus.COMPLETED, error: str | None = None) -> None:
        """结束整个 Trace。

        幂等:多次调用只生效一次。结束后清理 Span 引用帮助 GC。

        Args:
            status: Trace 最终状态(COMPLETED/FAILED)
            error:  失败时的错误信息
        """
        if self._ended:
            return
        self.ended_at = time.time()
        self.status = status
        if error:
            self.attributes["error"] = error
        self._ended = True
        # 触发 trace exporter
        if self._on_trace_end is not None:
            try:
                self._on_trace_end(self)
            except Exception:
                pass
        # 内存优化:Trace 完成后释放 Span 引用(exporter 已拿到快照)
        # 注意:仅在 exporter 执行完毕后清理,保证 exporter 能通过 self.spans 访问
        # 这里不立即清空 _spans,因为 export() 和 spans 属性可能在外部被读取;
        # 真正的释放由调用方在确认不再需要后调用 release_spans() 完成。

    def release_spans(self) -> None:
        """显式释放 Span 引用(内存优化)。

        Trace 结束且 exporter 处理完毕后调用,清空 _spans 列表帮助 GC。
        调用后 spans / span_count / export 将返回空数据,慎用。
        """
        with self._spans_lock:
            self._spans.clear()

    # -- 上下文管理器 -------------------------------------------------------
    def __enter__(self) -> TraceImpl:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.end(
                status=SpanStatus.FAILED,
                error=f"{exc_type.__name__}: {exc_val}",
            )
        else:
            self.end()

    # -- 导出 ---------------------------------------------------------------
    def export(self) -> dict:
        """导出 Trace 的完整数据(全部 Span + 元信息)。

        用于 trace exporter 持久化或转发到外部系统。
        Span.to_dict() 已对敏感字段脱敏。
        """
        with self._spans_lock:
            spans_copy = list(self._spans)
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": ((self.ended_at - self.started_at) * 1000 if self.ended_at else None),
            "status": self.status,
            "attributes": dict(self.attributes),
            "span_count": len(spans_copy),
            "spans": [s.to_dict() for s in spans_copy],
        }

    @property
    def spans(self) -> list[Span]:
        """本 Trace 收集的全部 Span 快照(只读副本)。"""
        with self._spans_lock:
            return list(self._spans)

    @property
    def span_count(self) -> int:
        """已收集的 Span 数量。"""
        with self._spans_lock:
            return len(self._spans)
