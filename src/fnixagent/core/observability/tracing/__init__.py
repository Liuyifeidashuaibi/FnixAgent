"""分层 Tracing Span 模块 —— P1-1。

借鉴 OpenAI Agents SDK 的 Tracing 设计 + OpenTelemetry 的 Span 模型,
提供分层、可嵌套、可导出的 Tracing 能力。

模块组成:
  - span:     Span 数据模型(immutable Span + mutable SpanImpl + 6 种 SpanData)
  - trace:    Trace 实现(一个 Trace 含多个 Span,构成树形结构)
  - scope:    基于 contextvars 的 Span 栈(支持嵌套 with 语法)
  - provider: 顶层 Provider(start_trace + span/trace exporter 注册)

典型用法:
    from fnixagent.core.observability.tracing import get_provider

    provider = get_provider()
    with provider.start_trace("agent_run", user_id="u1") as trace:
        with trace.start_span("agent", AgentSpanData(agent_name="paper")) as span:
            with trace.start_span("llm", LLMSpanData(provider="glm")) as llm_span:
                ...
            with trace.start_span("tool", ToolSpanData(tool_name="search")) as tool_span:
                ...

Span 类型层级:
    Trace
    └── AgentSpan (顶层)
        ├── LLMSpan
        ├── ToolSpan
        ├── GuardrailSpan
        └── HandoffSpan
"""
from fnixagent.core.observability.tracing.provider import (
    TracingProvider,
    get_provider,
    set_provider,
    reset_provider,
)
from fnixagent.core.observability.tracing.scope import TracingScope, get_current_span, get_current_span_id
from fnixagent.core.observability.tracing.span import (
    SpanStatus,
    SpanData,
    AgentSpanData,
    LLMSpanData,
    ToolSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    Span,
    SpanImpl,
)
from fnixagent.core.observability.tracing.trace import TraceImpl

__all__ = [
    # provider
    "TracingProvider",
    "get_provider",
    "set_provider",
    "reset_provider",
    # scope
    "TracingScope",
    "get_current_span",
    "get_current_span_id",
    # span
    "SpanStatus",
    "SpanData",
    "AgentSpanData",
    "LLMSpanData",
    "ToolSpanData",
    "GuardrailSpanData",
    "HandoffSpanData",
    "Span",
    "SpanImpl",
    # trace
    "TraceImpl",
]
