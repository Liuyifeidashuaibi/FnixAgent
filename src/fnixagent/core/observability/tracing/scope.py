"""基于 contextvars 的 Span 栈 —— P1-1。

TracingScope 维护当前线程/协程的 Span 栈,支持嵌套 with 语义:
  - 进入 with span: push(span)
  - 退出 with span: pop(expected=span)
  - 创建子 Span 时,自动从栈顶读取 parent_id

设计:
  - OpenTelemetry: ContextVar 存储 active span
  - OpenAI Agents SDK: scope 栈式管理

并发安全说明(contextvars 栈管理):
  - contextvars 天然按"上下文"隔离:每个 Thread / asyncio.Task 有独立
    的 ContextVar 副本,因此不同线程/协程的栈互不干扰(线程安全)。
  - 同一上下文内,Span 严格遵循 LIFO(后进先出):push 与 pop 必须配对,
    否则栈中残留的 Span 会导致后续新建 Span 的 parent_id 错误。
  - pop(expected) 接受预期 span 参数:若栈顶不是 expected,说明 with 块
    顺序错乱(异常场景),此时不移除任何元素并返回 None,避免破坏栈结构。
  - 跨线程传递 parent_id:子线程启动时应通过 contextvars 复制父上下文
    (copy_context().run(...)),否则子线程的栈为空,parent_id 为 None。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import contextvars
import logging

from fnixagent.core.observability.tracing.span import SpanImpl

_logger = logging.getLogger(__name__)


# 全局 contextvar:存储当前协程/线程的 Span 栈(列表)
# default=None 表示未初始化,避免使用可变默认值(列表共享导致跨上下文污染)
_current_stack: contextvars.ContextVar[list] = contextvars.ContextVar(
    "fnixagent_tracing_span_stack",
    default=None,
)


def _get_stack() -> list:
    """获取当前上下文的栈(惰性初始化,O(1) 取值)。

    每个线程/协程首次调用时创建独立的空列表并绑定到当前 ContextVar,
    后续直接 get() 返回同一引用,无需重复创建。
    """
    stack = _current_stack.get()
    if stack is None:
        stack = []
        _current_stack.set(stack)
    return stack


class TracingScope:
    """Span 栈管理器(基于 contextvars,线程/协程隔离)。

    用法(通常由 TraceImpl.start_span 内部调用,不需手动操作):
        scope = TracingScope()
        scope.push(span_impl)
        try:
            ...
        finally:
            scope.pop(expected=span_impl)
    """

    def push(self, span: SpanImpl) -> None:
        """将 Span 推入栈顶。

        异常安全:contextvars 操作失败时静默忽略,避免影响主业务流程。
        """
        try:
            stack = _get_stack()
            stack.append(span)
        except Exception:
            # contextvars 栈操作异常(LookupError 等)不应中断业务
            _logger.debug('Unhandled exception', exc_info=True)

    def pop(self, expected: SpanImpl | None = None) -> SpanImpl | None:
        """弹出栈顶 Span。

        Args:
            expected: 预期弹出的 Span 实例。若提供且栈顶不是它,说明 with 块
                      顺序错乱(如嵌套异常),此时不移除任何元素,返回 None,
                      避免错误 pop 导致父 Span 链断裂。

        Returns:
            弹出的 SpanImpl;栈空或栈顶不匹配时返回 None。
        """
        try:
            stack = _get_stack()
            if not stack:
                return None
            # 校验栈顶身份:若 expected 指定且不匹配,不移除(防错误 pop)
            if expected is not None and stack[-1] is not expected:
                return None
            return stack.pop()
        except Exception:
            # 栈操作异常不传播,保证 with 块的 finally 不再抛二次异常
            return None

    @staticmethod
    def current_span_id() -> str | None:
        """获取当前栈顶 Span 的 ID(用作新 Span 的 parent_id,O(1))。"""
        try:
            stack = _get_stack()
            if not stack:
                return None
            return stack[-1].span_id
        except Exception:
            return None

    @staticmethod
    def current_span() -> SpanImpl | None:
        """获取当前栈顶 Span 实例。"""
        try:
            stack = _get_stack()
            if not stack:
                return None
            return stack[-1]
        except Exception:
            return None

    @staticmethod
    def depth() -> int:
        """当前栈深度(Span 嵌套层数)。"""
        try:
            stack = _get_stack()
            return len(stack)
        except Exception:
            return 0

    @staticmethod
    def clear() -> None:
        """清空栈(异常恢复时使用)。

        重置为新的空列表,保证当前上下文后续 push 从干净状态开始。
        """
        try:
            _current_stack.set([])
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)


# ---------------------------------------------------------------------------
# 模块级便捷函数
# ---------------------------------------------------------------------------


def get_current_span() -> SpanImpl | None:
    """获取当前激活的 Span(栈顶)。"""
    return TracingScope.current_span()


def get_current_span_id() -> str | None:
    """获取当前激活的 Span ID。"""
    return TracingScope.current_span_id()
