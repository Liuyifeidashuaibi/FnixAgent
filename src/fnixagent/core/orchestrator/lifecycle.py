"""
Agent 生命周期编排 (Lifecycle)。

7步流水线:
  1. 输入安全校验(敏感词 + 注入检测)
  2. 记忆上下文加载(短期 + 长期 + 实体)
  3. 推理模式选择(ReAct / Plan&Execute / Self-Reflect)
  4. 推理执行(LLM 推理 + 工具调用)
  5. 结果校验(规则 + LLM 反思)
  6. 输出审核(内容审核 + 脱敏)
  7. 记忆更新 + 落库
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fnixagent.core.orchestrator.context import OrchestratorContext
from fnixagent.core.reasoning.base import ReasoningContext
from fnixagent.core.reasoning.planner import PlanExecuteEngine
from fnixagent.core.reasoning.react import ReActEngine
from fnixagent.core.reasoning.reflector import SelfReflectEngine
from fnixagent.core.security.engine import SecurityCheckResult
from fnixagent.core.types import (
    ExecutionTrace,
    Message,
    MessageRole,
    ReasoningMode,
)


@dataclass
class PipelineResult:
    """流水线结果。"""
    security_input: Optional[SecurityCheckResult] = None
    memory_context: Optional[dict] = None
    reasoning_mode: Optional[ReasoningMode] = None
    execution_trace: Optional[ExecutionTrace] = None
    validation_result: Optional[Any] = None
    security_output: Optional[SecurityCheckResult] = None
    final_answer: str = ""
    original_answer: str = ""
    error: str = ""


class Lifecycle:
    """生命周期流水线编排器。"""

    def __init__(self, ctx: OrchestratorContext):
        self._ctx = ctx

    def run(
        self,
        user_input: str,
        session_id: str = "",
        user_id: str = "",
    ) -> PipelineResult:
        """执行完整7步流水线。

        P1-1/P1-4: 若有 active trace,包裹 AgentSpan;否则零开销。
        """
        result = PipelineResult()
        self._ctx.session_id = session_id
        self._ctx.user_id = user_id
        self._ctx.trace_id = f"{session_id}_{id(user_input)}"

        # P1-1: 尝试在 active trace 内创建 AgentSpan
        trace = None
        try:
            from fnixagent.core.observability.tracing import (
                AgentSpanData,
                get_provider,
            )
            trace = get_provider().get_current_trace()
        except Exception:
            pass

        if trace is not None:
            with trace.start_span(
                "lifecycle_run",
                AgentSpanData(
                    agent_name="lifecycle",
                    reasoning_mode="legacy",
                ),
                user_id=user_id,
                session_id=session_id,
            ):
                return self._run_impl(user_input, user_id, result)
        return self._run_impl(user_input, user_id, result)

    def _run_impl(
        self,
        user_input: str,
        user_id: str,
        result: PipelineResult,
    ) -> PipelineResult:
        """实际 7 步流水线执行(被 run() 包裹 Span)。"""
        try:
            result.security_input = self._step1_security(user_input)
            if not result.security_input.passed:
                result.final_answer = f"请求被拦截: {result.security_input.blocked_reason}"
                return result

            result.memory_context = self._step2_memory(user_input, user_id)
            result.reasoning_mode = self._step3_select(user_input)
            result.execution_trace = self._step4_reason(
                user_input, result.memory_context, result.reasoning_mode
            )
            result.validation_result = self._step5_validate(
                user_input, result.execution_trace
            )
            answer = self._extract_answer(result.execution_trace)
            result.original_answer = answer
            result.security_output = self._step6_output(answer)
            result.final_answer = result.security_output.sanitized_text or answer
            self._step7_save(user_input, result.final_answer, user_id)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            result.final_answer = result.final_answer or f"处理失败: {exc}"

        return result

    def _step1_security(self, text: str) -> SecurityCheckResult:
        """第 1 步: 输入安全校验(敏感词 + 注入检测)。"""
        return self._ctx.security_engine.check_input(text)

    def _step2_memory(self, query: str, user_id: str) -> dict:
        """第 2 步: 加载记忆上下文(短期 + 长期 + 实体)。"""
        return self._ctx.memory_manager.load_context(query=query, user_id=user_id)

    def _step3_select(self, goal: str) -> ReasoningMode:
        """第 3 步: 选择推理模式。"""
        return self._ctx.reasoning_selector.select(
            goal, self._ctx.tool_registry.count
        )

    def _step4_reason(
        self, goal: str, mem_ctx: dict, mode: ReasoningMode
    ) -> ExecutionTrace:
        """第 4 步: 构建推理上下文并执行选定模式的推理引擎。"""
        history = mem_ctx.get("short_term", [])
        long_term = mem_ctx.get("long_term", [])
        if long_term:
            mem_text = "\n".join(f"[记忆] {m.content}" for m in long_term)
            history = history + [
                Message(role=MessageRole.SYSTEM, content=mem_text)
            ]
        rctx = ReasoningContext(
            goal=goal,
            llm=self._ctx.llm_router,
            tool_registry=self._ctx.tool_registry,
            tool_executor=self._ctx.tool_executor,
            history=history,
            max_iterations=self._ctx.config.reasoning.max_reasoning_iterations,
            user_id=self._ctx.user_id,
            session_id=self._ctx.session_id,
            trace_id=self._ctx.trace_id,
        )
        if mode == ReasoningMode.PLAN_EXECUTE:
            engine = PlanExecuteEngine()
        elif mode == ReasoningMode.SELF_REFLECT:
            engine = SelfReflectEngine(ReActEngine())
        else:
            engine = ReActEngine()
        return engine.reason(rctx)

    def _step5_validate(self, goal: str, trace: ExecutionTrace):
        """第 5 步: 结果校验(规则 + LLM 反思)。"""
        return self._ctx.validator.validate(goal, trace)

    def _step6_output(self, text: str) -> SecurityCheckResult:
        """第 6 步: 输出审核(内容审核 + 脱敏)。"""
        return self._ctx.security_engine.review_output(text)

    def _step7_save(self, user_input: str, answer: str, user_id: str) -> None:
        """第 7 步: 记忆更新与落库(写入用户消息和助手回复)。"""
        self._ctx.memory_manager.save(
            self._ctx.session_id,
            Message(role=MessageRole.USER, content=user_input),
            user_id,
        )
        self._ctx.memory_manager.save(
            self._ctx.session_id,
            Message(role=MessageRole.ASSISTANT, content=answer),
            user_id,
        )

    def _extract_answer(self, trace: ExecutionTrace) -> str:
        """从执行轨迹中提取最终答案文本。"""
        if not trace.steps:
            return "无法完成任务"
        last = trace.steps[-1]
        if hasattr(last, "thought") and last.thought:
            return last.thought
        if hasattr(last, "description"):
            return last.description
        return "任务执行完成"
