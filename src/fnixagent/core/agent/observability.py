"""
Observability - 可观测性 (Observability)
=========================================
对齐 OpenTelemetry (OTel) + Langfuse + Phoenix 的可观测性管道。

设计要点:
  - OTel 钩子: 结构化事件 (syscall 级追踪)
  - 指标收集: 计数器/直方图/计量
  - 可插拔: 多个 sink (OTel collector / Langfuse / stdout)
  - 零依赖: 纯 Python 实现, 无需 opentelemetry-sdk
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.agent.types import utcnow_iso


@dataclass
class Span:
    """OTel Span (类比分布式追踪的 span)。

    Attributes:
        span_id: span ID
        trace_id: trace ID
        parent_span_id: 父 span ID
        name: span 名称 (如 "syscall.fs.read")
        start_time: 开始时间 (ISO)
        end_time: 结束时间 (ISO, None = 未结束)
        duration_ms: 持续时间 (毫秒)
        attributes: 属性 (key-value)
        events: 事件列表
        status: 状态 (ok/error)
        status_message: 状态消息
    """

    span_id: str = field(default_factory=lambda: format(id(object()), "016x"))
    trace_id: str = ""
    parent_span_id: str = ""
    name: str = ""
    start_time: str = field(default_factory=utcnow_iso)
    end_time: str | None = None
    duration_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "ok"  # ok/error
    status_message: str = ""

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "name": name,
                "timestamp": utcnow_iso(),
                "attributes": attributes or {},
            }
        )

    def end(self, status: str = "ok", message: str = "") -> None:
        self.end_time = utcnow_iso()
        self.status = status
        self.status_message = message
        # 计算 duration (近似)
        from datetime import datetime

        try:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            self.duration_ms = (end - start).total_seconds() * 1000
        except (ValueError, TypeError):
            pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 3),
            "attributes": dict(self.attributes),
            "events": list(self.events),
            "status": self.status,
            "status_message": self.status_message,
        }


class ObservabilityManager:
    """可观测性管理器 (对齐 OTel + Langfuse)。

    功能:
      - Span 管理 (开始/结束/属性/事件)
      - 钩子注册 (多 sink)
      - 指标收集 (计数器/直方图)
      - 审计日志 (内存环形缓冲)

    使用方式:
      1. start_span(name) → Span
      2. span.set_attribute(...) / span.add_event(...)
      3. span.end()
      4. 钩子自动触发 (可注册多个 sink)
    """

    def __init__(self, max_spans: int = 10000, max_audit: int = 10000):
        self._spans: deque[Span] = deque(maxlen=max_spans)
        self._active_spans: dict[str, Span] = {}
        self._hooks: list[Callable[[str, dict[str, Any]], None]] = []
        self._audit_log: deque[dict[str, Any]] = deque(maxlen=max_audit)
        # 指标
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._lock_calls: dict[str, int] = defaultdict(int)  # syscall 调用次数

    # --- 钩子 ---

    def add_hook(self, hook: Callable[[str, dict[str, Any]], None]) -> None:
        """注册 OTel 钩子 (多 sink 支持)。

        钩子签名: (event_name, payload) -> None
        事件类型: span_start / span_end / syscall / audit / metric
        """
        self._hooks.append(hook)

    def _fire_hooks(self, event: str, payload: dict[str, Any]) -> None:
        """触发钩子。"""
        for hook in self._hooks:
            try:
                hook(event, payload)
            except Exception:
                continue

    # --- Span 管理 ---

    def start_span(
        self,
        name: str,
        trace_id: str = "",
        parent_span_id: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """开始 span。"""
        span = Span(
            name=name,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        self._active_spans[span.span_id] = span
        self._spans.append(span)
        self._fire_hooks("span_start", span.to_dict())
        return span

    def end_span(self, span_id: str, status: str = "ok", message: str = "") -> Span | None:
        """结束 span。"""
        span = self._active_spans.pop(span_id, None)
        if span is None:
            return None
        span.end(status, message)
        self._fire_hooks("span_end", span.to_dict())
        return span

    def get_span(self, span_id: str) -> Span | None:
        """获取 span。"""
        return self._active_spans.get(span_id)

    def list_active_spans(self) -> list[Span]:
        """列出活跃 span。"""
        return list(self._active_spans.values())

    # --- Syscall 追踪 ---

    def trace_syscall(
        self, syscall_name: str, args: dict[str, Any], caller_pid: str, trace_id: str = ""
    ) -> Span:
        """创建 syscall 追踪 span。"""
        self._lock_calls[syscall_name] += 1
        span = self.start_span(
            name=f"syscall.{syscall_name}",
            trace_id=trace_id,
            attributes={
                "syscall": syscall_name,
                "caller_pid": caller_pid,
                "args": args,
            },
        )
        self._fire_hooks(
            "syscall",
            {
                "syscall": syscall_name,
                "caller_pid": caller_pid,
                "args": args,
                "trace_id": trace_id,
            },
        )
        return span

    # --- 审计日志 ---

    def audit(
        self,
        action: str,
        detail: dict[str, Any] | None = None,
        subject: str | None = None,
        trace_id: str = "",
    ) -> None:
        """记录审计事件。"""
        entry = {
            "action": action,
            "subject": subject,
            "detail": detail or {},
            "trace_id": trace_id,
            "timestamp": utcnow_iso(),
        }
        self._audit_log.append(entry)
        self._fire_hooks("audit", entry)

    def get_audit_log(self, limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
        """查询审计日志, 返回最近 limit 条 (过滤后)。"""
        filtered = [l for l in self._audit_log if not action or l.get("action") == action]
        return filtered[-limit:] if limit < len(filtered) else filtered

    # --- 指标 ---

    def increment(self, name: str, value: int = 1) -> None:
        """计数器递增。"""
        self._counters[name] += value
        self._fire_hooks("metric", {"type": "counter", "name": name, "value": self._counters[name]})

    def observe(self, name: str, value: float) -> None:
        """直方图观测。"""
        self._histograms[name].append(value)
        # 限制内存
        if len(self._histograms[name]) > 10000:
            self._histograms[name] = self._histograms[name][-5000:]
        self._fire_hooks("metric", {"type": "histogram", "name": name, "value": value})

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_histogram_stats(self, name: str) -> dict[str, float]:
        """直方图统计 (count/sum/avg/min/max/p50/p95/p99)。"""
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "count": n,
            "sum": round(sum(sorted_vals), 3),
            "avg": round(sum(sorted_vals) / n, 3),
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "p50": sorted_vals[n // 2],
            "p95": sorted_vals[int(n * 0.95)] if n > 1 else sorted_vals[0],
            "p99": sorted_vals[int(n * 0.99)] if n > 1 else sorted_vals[0],
        }

    # --- 统计 ---

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_spans": len(self._spans),
            "active_spans": len(self._active_spans),
            "audit_entries": len(self._audit_log),
            "counters": dict(self._counters),
            "histogram_count": len(self._histograms),
            "syscall_calls": dict(self._lock_calls),
            "hooks_count": len(self._hooks),
        }


__all__ = ["ObservabilityManager", "Span"]
