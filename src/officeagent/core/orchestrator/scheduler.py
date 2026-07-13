"""
Agent 调度中枢 (Agent Scheduler)。

对外统一入口: process(user_input) -> AgentResponse

串联全部引擎的完整生命周期:
  输入 → 安全 → 记忆 → 推理 → 工具 → 反思 → 审核 → 回复 → 落库
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from officeagent.core.orchestrator.context import OrchestratorContext
from officeagent.core.orchestrator.lifecycle import Lifecycle
from officeagent.core.types import ExecutionTrace


@dataclass
class AgentResponse:
    """Agent 响应。"""
    final_answer: str
    trace: Optional[ExecutionTrace] = None
    security_input_passed: bool = True
    security_output_passed: bool = True
    sanitized: bool = False
    error: str = ""
    duration_ms: float = 0.0
    stats: dict = field(default_factory=dict)


class AgentScheduler:
    """
    Agent 调度中枢。

    用法:
        ctx = OrchestratorContext(
            llm_router=...,
            memory_manager=...,
            tool_registry=...,
            tool_executor=...,
            security_engine=...,
            prompt_manager=...,
            reasoning_selector=...,
            validator=...,
            replanner=...,
            config=...,
        )
        ctx.llm_router.register(MyProvider(...))
        ctx.tool_registry.register(metadata, func)

        scheduler = AgentScheduler(ctx)
        resp = scheduler.process("帮我搜论文", "s1", "u1")
        print(resp.final_answer)
    """

    def __init__(self, ctx: OrchestratorContext):
        self._ctx = ctx
        self._lifecycle = Lifecycle(ctx)

    def process(
        self,
        user_input: str,
        session_id: str = "",
        user_id: str = "",
    ) -> AgentResponse:
        """处理一次用户请求。"""
        t0 = time.monotonic()
        result = self._lifecycle.run(user_input, session_id, user_id)
        ms = (time.monotonic() - t0) * 1000
        stats = self._build_stats(result, ms)
        return AgentResponse(
            final_answer=result.final_answer,
            trace=result.execution_trace,
            security_input_passed=(
                result.security_input.passed if result.security_input else True
            ),
            security_output_passed=(
                result.security_output.passed if result.security_output else True
            ),
            sanitized=result.security_output is not None
                and bool(result.security_output.sanitized_text)
                and result.security_output.sanitized_text != result.original_answer,
            error=result.error,
            duration_ms=ms,
            stats=stats,
        )

    def _build_stats(self, result, ms: float) -> dict:
        """汇总本次请求的运行统计(用于日志/监控)。"""
        trace = result.execution_trace
        s = {
            "duration_ms": round(ms, 2),
            "reasoning_mode": result.reasoning_mode.value if result.reasoning_mode else "unknown",
            "iterations": trace.iterations if trace else 0,
            "tool_calls": len(trace.tool_calls) if trace else 0,
        }
        if trace and trace.total_usage.total_tokens > 0:
            s["tokens"] = {
                "prompt": trace.total_usage.prompt_tokens,
                "completion": trace.total_usage.completion_tokens,
                "total": trace.total_usage.total_tokens,
            }
        if result.validation_result:
            s["validation"] = {
                "passed": result.validation_result.passed,
                "score": result.validation_result.score,
            }
        return s

    def register_tool(self, metadata, func) -> None:
        """注册一个工具到工具注册中心。"""
        self._ctx.tool_registry.register(metadata, func)

    def get_stats(self) -> dict:
        """获取 LLM/记忆/工具的运行统计。"""
        return {
            "llm": self._ctx.llm_router.get_stats(),
            "memory": self._ctx.memory_manager.get_stats(),
            "tools": {"count": self._ctx.tool_registry.count},
        }

    def reset_session(self) -> None:
        """重置短期记忆(开启新会话)。"""
        self._ctx.memory_manager.reset()

    def cleanup(self) -> int:
        """清理过期长期记忆, 返回清理条数。"""
        return self._ctx.memory_manager.cleanup()
