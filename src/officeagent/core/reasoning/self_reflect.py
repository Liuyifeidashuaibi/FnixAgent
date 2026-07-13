"""Self-Reflection 推理引擎。

算法: Execute → Evaluate → Fix 闭环(参考 MiniMax Office Skills 自进化机制)
  1. Execute:  用 ReAct/Plan&Execute 执行任务
  2. Evaluate: LLM 对执行结果做反思校验(完整性/正确性/格式)
  3. Fix:      校验不通过 → 生成改进建议 → 重新规划执行
  4. 最多重规划 max_replans 次,超过则抛 ReflectionFailedError

适用场景: 对结果质量要求高的任务,需要自我纠错。

评分边界(BUG 修复):
  LLM 返回的 score 强制 clamp 到 [0.0, 1.0],避免 LLM 输出 1.5/-0.1
  等越界值污染下游(原实现直接 float() 不做边界检查)。

进阶质量评估(P0-04):
  若需更精细的多维度质量评估(长度/结构/关键词/引用/格式/LLM 6 维加权),
  请改用 officeagent.core.reflection.get_reflection_manager()。
  该管理器并行执行 6 个评估器,返回 ReflectionResult 含 sub_scores/
  issues/feedback_message,适合对生成内容做结构化质量反思。
  本引擎的 _evaluate 适用于"执行轨迹校验",进阶反思系统适用于
  "生成内容质量评估",二者可叠加使用。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from officeagent.core.exceptions import (
    MaxIterationsExceededError,
    ReasoningError,
    ReflectionFailedError,
)
from officeagent.core.reasoning.base import ReasoningContext, ReasoningEngine
from officeagent.core.reasoning.react import ReActEngine
from officeagent.core.types import (
    ExecutionTrace,
    Message,
    MessageRole,
    ReasoningMode,
    ReflectionResult,
)


class SelfReflectEngine(ReasoningEngine):
    """Self-Reflection 推理引擎。

    内部委托 ReActEngine 做实际执行,
    自身负责 Evaluate + Fix 的闭环。

    并发安全:
      - 不修改传入的 ctx,inner ReAct 引擎通过自己的 scratchpad 维护状态
      - 反思 trace 与 inner trace 独立,通过显式 extend 合并
    """

    # 最大重规划次数(防止 LLM 与反思之间无限循环)
    DEFAULT_MAX_REPLANS: int = 2

    def __init__(self, inner_engine: Optional[ReActEngine] = None) -> None:
        """初始化 Self-Reflect 引擎。

        Args:
            inner_engine: 可选的内部执行引擎(默认 ReActEngine)。
                允许上层注入自定义引擎实例(如带缓存的 ReActEngine),
                也兼容无参构造(保持 public API 向后兼容)。
        """
        self._inner = inner_engine if inner_engine is not None else ReActEngine()

    @property
    def mode(self) -> ReasoningMode:
        """返回 Self-Reflect 推理模式标识。"""
        return ReasoningMode.SELF_REFLECT

    def reason(self, ctx: ReasoningContext) -> ExecutionTrace:
        """Execute → Evaluate → Fix 循环。

        异常策略:
          - inner.reason 抛 MaxIterationsExceededError 时不再重规划
            (inner 已耗尽迭代,继续重规划无意义)
          - 其他 ReasoningError 也终止反思循环,透传给上层
          - 反思 LLM 调用失败 → 视为反思未通过,触发重规划
        """
        trace = self._make_trace(ctx)
        # 使用注入的 inner engine(若上层未传,默认 ReActEngine)
        inner = self._inner
        replan_count = 0
        max_replans = self.DEFAULT_MAX_REPLANS

        current_goal = ctx.goal

        # ---- 反思主循环 ---------------------------------------------------
        while True:
            # Phase 1: Execute(委托 ReActEngine)
            inner_ctx = ReasoningContext(
                goal=current_goal,
                llm=ctx.llm,
                tool_registry=ctx.tool_registry,
                tool_executor=ctx.tool_executor,
                # history 复制浅拷贝,inner 用自己的 scratchpad,不回写 ctx.history
                history=list(ctx.history),
                max_iterations=ctx.max_iterations,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                trace_id=ctx.trace_id,
            )
            try:
                inner_trace = inner.reason(inner_ctx)
            except MaxIterationsExceededError:
                # inner 已耗尽迭代,重规划也无法改善,直接抛给上层
                raise
            except ReasoningError as exc:
                # inner 出现非迭代异常,不再继续反思,透传
                raise ReflectionFailedError(
                    f"内部执行异常,终止反思: {exc}"
                ) from exc

            # 合并轨迹(并发安全:不修改 inner_trace,只读访问)
            trace.steps.extend(inner_trace.steps)
            trace.tool_calls.extend(inner_trace.tool_calls)
            trace.tool_results.extend(inner_trace.tool_results)
            trace.total_usage = trace.total_usage.add(inner_trace.total_usage)
            trace.iterations += inner_trace.iterations

            # Phase 2: Evaluate
            try:
                reflection = self._evaluate(ctx, current_goal, inner_trace)
            except ReasoningError:
                # 反思 LLM 调用失败,视为本次未通过,走重规划路径
                reflection = ReflectionResult(
                    passed=False,
                    score=0.0,
                    reason="反思 LLM 调用失败,默认未通过",
                    needs_replan=True,
                )
            trace.reflections.append(reflection)

            # Phase 3: Fix
            if reflection.passed:
                return trace

            if replan_count >= max_replans:
                raise ReflectionFailedError(
                    f"反思校验未通过,已达最大重规划次数 {max_replans}"
                )

            replan_count += 1
            # 根据反思建议调整目标(若 suggestion 为空,仅追加 reason)
            if reflection.suggestion:
                current_goal = (
                    f"{ctx.goal}\n\n"
                    f"上次执行问题: {reflection.reason}\n"
                    f"改进建议: {reflection.suggestion}\n"
                    f"请基于以上反馈重新执行。"
                )
            else:
                current_goal = (
                    f"{ctx.goal}\n\n"
                    f"上次执行问题: {reflection.reason}\n"
                    f"请重新执行并改进。"
                )

    # -- Phase 2: Evaluate ------------------------------------------------

    def _evaluate(
        self,
        ctx: ReasoningContext,
        goal: str,
        trace: ExecutionTrace,
    ) -> ReflectionResult:
        """用 LLM 对执行结果做反思校验。

        校验维度: 完整性 / 正确性 / 格式
        """
        results_summary = self._summarize_results(trace)

        system_msg = Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是一个结果校验器。请对以下执行结果进行反思校验:\n"
                "1. 完整性: 是否完成了目标的所有要求?\n"
                "2. 正确性: 结果是否逻辑合理、数值正确?\n"
                "3. 格式: 输出是否符合要求的格式?\n\n"
                "输出 JSON:\n"
                '{"passed": true/false, "score": 0.0-1.0, '
                '"check_type": "completeness", "reason": "...", '
                '"suggestion": "...", "needs_replan": true/false}'
            ),
        )
        user_msg = Message(
            role=MessageRole.USER,
            content=(
                f"目标: {goal}\n\n"
                f"执行结果:\n{results_summary}"
            ),
        )

        raw = self._call_llm(ctx, [system_msg, user_msg])
        return self._parse_reflection(raw)

    def _summarize_results(self, trace: ExecutionTrace) -> str:
        """汇总执行结果用于反思。"""
        if not trace.tool_results:
            return "无工具执行结果"
        parts: list[str] = []
        for i, result in enumerate(trace.tool_results):
            status = result.status.value if result.status else "unknown"
            output_str = str(result.output)[:200] if result.output else ""
            error = f" (错误: {result.error})" if result.error else ""
            parts.append(
                f"[{i+1}] {result.name} ({status}): {output_str}{error}"
            )
        return "\n".join(parts)

    def _parse_reflection(self, raw: str) -> ReflectionResult:
        """解析 LLM 反思结果。

        BUG 修复:
          - score 强制 clamp 到 [0.0, 1.0](原实现直接 float() 不做边界检查)
          - 解析失败时默认 passed=False + needs_replan=True,
            触发显式重规划而非静默通过(原实现默认 passed=True 危险)
        """
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if isinstance(data, dict):
                    return ReflectionResult(
                        passed=bool(data.get("passed", False)),
                        score=self._clamp_score(data.get("score", 0.0)),
                        check_type=str(data.get("check_type", "completeness")),
                        reason=str(data.get("reason", "")),
                        suggestion=str(data.get("suggestion", "")),
                        needs_replan=bool(data.get("needs_replan", False)),
                    )
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        # 解析失败:默认未通过 + 触发重规划(原实现默认通过,危险)
        return ReflectionResult(
            passed=False,
            score=0.0,
            reason="反思结果解析失败,默认未通过以触发重规划",
            needs_replan=True,
        )

    @staticmethod
    def _clamp_score(value: object) -> float:
        """把 LLM 输出的 score 限制在 [0.0, 1.0] 区间。

        防 LLM 输出 1.5/-0.1/"0.8" 等越界/字符串值。
        """
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score
