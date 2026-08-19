"""中间件洋葱。

中间件是横切关注点的通用钩子框架,比 Guardrail 管道更通用:
  - Guardrail(P0-2)是 SecurityMiddleware 的内部实现
  - Tracing(P1-1)通过 TracingMiddleware 开关 Span
  - 日志/审计/限流等均可作为中间件实现

6 个钩子点(覆盖请求/响应/异常/工具调用全生命周期):
  请求方向(顺序执行):
    on_request_start → on_request_end
  响应方向(逆序执行):
    on_response_start → on_response_end
  异常处理:
    on_error(可吞掉异常或转换异常)
  工具调用:
    on_tool_call(可修改工具名/参数)

设计要点:
  - is_implemented 自动检测子类实现了哪些钩子(避免空调用开销)
  - MiddlewareChain 按注册顺序执行请求钩子,逆序执行响应钩子(洋葱模型)
  - 中间件可同步可异步(全部用 async def 定义,内部可同步实现)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
from typing import Any

from fnixagent.core.messages import Msg


class MiddlewareBase(abc.ABC):
    """中间件基类:6 钩子,子类按需实现。

    子类只需重写关心的钩子,未重写的钩子走默认实现(直接返回入参)。
    is_implemented 属性自动检测子类实现了哪些钩子,MiddlewareChain 据此跳过空调用。
    """

    async def on_request_start(self, msg: Msg, ctx: Any) -> Msg:
        """请求开始(用户消息进入 Agent 前)。

        典型用途:开 Trace Span、记录请求日志。
        """
        return msg

    async def on_request_end(self, msg: Msg, ctx: Any) -> Msg:
        """请求结束(Agent 处理前最后一道)。

        典型用途:Guardrail 输入校验、权限检查。
        """
        return msg

    async def on_response_start(self, msg: Msg, ctx: Any) -> Msg:
        """响应开始(Agent 产出后第一道)。

        典型用途:Guardrail 输出校验、脱敏。
        """
        return msg

    async def on_response_end(self, msg: Msg, ctx: Any) -> Msg:
        """响应结束(返回用户前最后一道)。

        典型用途:关 Trace Span、记录响应日志。
        """
        return msg

    async def on_error(self, error: Exception, ctx: Any) -> Exception | None:
        """异常处理。

        返回值:
          - None:吞掉异常(视为已处理)
          - Exception:转换后的异常(或原异常)
        典型用途:错误格式化、降级处理。
        """
        return error

    async def on_tool_call(self, tool_name: str, args: dict, ctx: Any) -> tuple[str, dict]:
        """工具调用前(可修改工具名/参数)。

        返回 (tool_name, args),可为修改后的值。
        典型用途:参数脱敏、工具替换。
        """
        return tool_name, args

    @property
    def is_implemented(self) -> dict[str, bool]:
        """自动检测哪些钩子被子类实现。

        通过比较子类方法与基类方法是否同一对象判断。
        MiddlewareChain 据此跳过未实现的钩子,减少开销。

        Returns:
            6 个钩子名 → 是否被实现的字典
        """
        # 结果按 type 缓存,避免每次访问都重新做 6 次对象比较
        cls = type(self)
        cached = getattr(cls, "_is_implemented_cache", None)
        if cached is not None:
            return cached
        result = {
            "on_request_start": cls.on_request_start is not MiddlewareBase.on_request_start,
            "on_request_end": cls.on_request_end is not MiddlewareBase.on_request_end,
            "on_response_start": cls.on_response_start is not MiddlewareBase.on_response_start,
            "on_response_end": cls.on_response_end is not MiddlewareBase.on_response_end,
            "on_error": cls.on_error is not MiddlewareBase.on_error,
            "on_tool_call": cls.on_tool_call is not MiddlewareBase.on_tool_call,
        }
        # 缓存到类对象上(子类各自一份,不污染基类)
        cls._is_implemented_cache = result
        return result


class MiddlewareChain:
    """中间件链:按注册顺序执行请求钩子,逆序执行响应钩子(洋葱模型)。

    洋葱模型示意(3 个中间件 MW1, MW2, MW3):
        请求 → MW1.on_request_start → MW2.on_request_start → MW3.on_request_start
            → MW1.on_request_end   → MW2.on_request_end   → MW3.on_request_end
            → [Agent 处理]
            → MW3.on_response_start → MW2.on_response_start → MW1.on_response_start
            → MW3.on_response_end   → MW2.on_response_end   → MW1.on_response_end
            → 响应

    用法:
        chain = MiddlewareChain([SecurityMiddleware(engine), TracingMiddleware()])
        msg = await chain.run_request(msg, ctx)
        # ... Agent 处理 ...
        msg = await chain.run_response(msg, ctx)
    """

    def __init__(self, middlewares: list[MiddlewareBase] | None = None) -> None:
        """初始化中间件链。

        Args:
            middlewares: 中间件列表(可选;为 None 时初始化为空列表)

        Raises:
            TypeError: middlewares 不是 list 或元素不是 MiddlewareBase 实例
        """
        if middlewares is None:
            self._middlewares: list[MiddlewareBase] = []
        elif not isinstance(middlewares, list):
            raise TypeError(f"middlewares must be list or None, got {type(middlewares).__name__}")
        else:
            for i, mw in enumerate(middlewares):
                if not isinstance(mw, MiddlewareBase):
                    raise TypeError(
                        f"middlewares[{i}] must be MiddlewareBase, got {type(mw).__name__}"
                    )
            self._middlewares = list(middlewares)

    def add(self, mw: MiddlewareBase) -> MiddlewareChain:
        """追加中间件(返回 self,支持链式调用)。

        Args:
            mw: 要追加的中间件实例

        Returns:
            self(支持链式调用)

        Raises:
            TypeError: mw 不是 MiddlewareBase 实例
        """
        if not isinstance(mw, MiddlewareBase):
            raise TypeError(f"mw must be MiddlewareBase, got {type(mw).__name__}")
        self._middlewares.append(mw)
        return self

    @property
    def middlewares(self) -> list[MiddlewareBase]:
        """已注册的中间件列表(只读)。"""
        return list(self._middlewares)

    async def run_request(self, msg: Msg, ctx: Any) -> Msg:
        """请求方向:顺序执行 on_request_start → on_request_end。

        任一中间件抛异常将中断链路(由调用方捕获)。
        """
        for mw in self._middlewares:
            impl = mw.is_implemented
            if impl["on_request_start"]:
                msg = await mw.on_request_start(msg, ctx)
            if impl["on_request_end"]:
                msg = await mw.on_request_end(msg, ctx)
        return msg

    async def run_response(self, msg: Msg, ctx: Any) -> Msg:
        """响应方向:逆序执行 on_response_start → on_response_end。"""
        for mw in reversed(self._middlewares):
            impl = mw.is_implemented
            if impl["on_response_start"]:
                msg = await mw.on_response_start(msg, ctx)
            if impl["on_response_end"]:
                msg = await mw.on_response_end(msg, ctx)
        return msg

    async def run_tool_call(self, tool_name: str, args: dict, ctx: Any) -> tuple[str, dict]:
        """工具调用方向:顺序执行 on_tool_call(可修改工具名/参数)。"""
        for mw in self._middlewares:
            if mw.is_implemented["on_tool_call"]:
                tool_name, args = await mw.on_tool_call(tool_name, args, ctx)
        return tool_name, args

    async def run_error(self, error: Exception, ctx: Any) -> Exception | None:
        """异常方向:顺序执行 on_error(任一返回 None 则吞掉异常)。"""
        for mw in self._middlewares:
            if mw.is_implemented["on_error"]:
                result = await mw.on_error(error, ctx)
                if result is None:
                    return None  # 异常被吞掉
                error = result
        return error


# ---------------------------------------------------------------------------
# 现有模块适配为中间件(P0-2 / P1-1 实现具体逻辑,此处为骨架)
# ---------------------------------------------------------------------------


class SecurityMiddleware(MiddlewareBase):
    """安全中间件(包装 SecurityEngine / GuardrailPipeline)。

    P0-2 阶段实现具体逻辑:
      - on_request_end: 调用 GuardrailPipeline.run_input(输入校验)
      - on_response_start: 调用 GuardrailPipeline.run_output(输出校验/脱敏)
    """

    def __init__(self, security_engine: Any) -> None:
        self._engine = security_engine

    async def on_request_end(self, msg: Msg, ctx: Any) -> Msg:
        """输入 Guardrail 校验。

        调用 SecurityEngine.run_input_guardrails 进行注入检测 + 敏感词 + 内容审核。
        tripwire 触发时替换消息内容为拦截提示,并标记 metadata。
        Guardrail 异常降级放行(不阻塞主流程)。
        """
        if self._engine is None:
            return msg
        text = msg.text_content
        if not text:
            return msg
        try:
            result = self._engine.run_input_guardrails(text)
            if result.tripwire_triggered:
                from fnixagent.core.messages import TextBlock

                msg.content = [TextBlock(text=f"[安全拦截] {result.blocked_reason}")]
                msg.metadata["guardrail_blocked"] = True
                msg.metadata["guardrail_risk_score"] = result.risk_score
        except Exception:
            # Guardrail 异常不应阻塞主流程(降级而非崩溃)
            pass
        return msg

    async def on_response_start(self, msg: Msg, ctx: Any) -> Msg:
        """输出 Guardrail 校验 + PII 脱敏。

        调用 SecurityEngine.run_output_guardrails 进行内容审核 + 脱敏。
        sanitized_text 非空时替换消息文本。
        """
        if self._engine is None:
            return msg
        text = msg.text_content
        if not text:
            return msg
        try:
            result = self._engine.run_output_guardrails(text)
            if result.sanitized_text and result.sanitized_text != text:
                from fnixagent.core.messages import TextBlock

                msg.content = [TextBlock(text=result.sanitized_text)]
            if result.tripwire_triggered:
                msg.metadata["guardrail_output_tripwire"] = True
        except Exception:
            pass
        return msg


class TracingMiddleware(MiddlewareBase):
    """Tracing 中间件(开/关 Span)。

    P1-1 阶段实现具体逻辑:
      - on_request_start: 开 AgentSpan
      - on_response_end: 关 AgentSpan,记录 attributes
    """

    def __init__(self, tracer: Any = None) -> None:
        self._tracer = tracer

    async def on_request_start(self, msg: Msg, ctx: Any) -> Msg:
        """开 Span。"""
        if self._tracer is not None:
            try:
                ctx.span = self._tracer.start_span("agent_reply")
            except Exception:
                pass
        return msg

    async def on_response_end(self, msg: Msg, ctx: Any) -> Msg:
        """关 Span。"""
        if self._tracer is not None and hasattr(ctx, "span") and ctx.span is not None:
            try:
                ctx.span.end()
            except Exception:
                pass
        return msg
