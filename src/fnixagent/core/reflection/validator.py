"""结果校验器 (Result Validator)。

双层校验:
  Layer 1 — 规则校验(快速,确定性):
    - 工具是否全部成功执行
    - 返回值是否非空
    - 是否有必填字段缺失
    - 超时/失败标记
  Layer 2 — LLM 校验(深度,语义):
    - 结果是否完整回答了用户目标
    - 结果是否逻辑合理
    - 输出格式是否正确

先用规则层快速过滤明显问题,再用 LLM 层做深度语义校验。

异常处理(BUG 修复):
  - LLM 调用 try-except,失败时降级为规则层结论(原实现裸调 chat,
    provider 异常会直接中断 validate)
  - score 强制 clamp 到 [0.0, 1.0](原实现直接 float() 不做边界检查)
  - 解析失败默认 passed=True + reason 标注(保持原行为,但显式标注)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from fnixagent.core.exceptions import LLMError, ReasoningError
from fnixagent.core.llm.router import LLMRouter
from fnixagent.core.types import (
    ExecutionTrace,
    Message,
    MessageRole,
    ReflectionResult,
    ToolExecutionStatus,
    ToolResult,
)


@dataclass
class ValidationResult:
    """校验结果。"""
    passed: bool
    score: float                         # 0~1(已 clamp)
    rule_checks: list[str] = field(default_factory=list)   # 规则层检查项
    rule_failures: list[str] = field(default_factory=list)  # 规则层失败项
    llm_reflection: Optional[ReflectionResult] = None       # LLM 层校验
    overall_reason: str = ""


class ResultValidator:
    """结果校验器。

    用法:
        validator = ResultValidator(llm=llm_router)
        result = validator.validate(goal, trace)
        if not result.passed:
            # 触发重规划
    """

    def __init__(
        self,
        llm: Optional[LLMRouter] = None,
        llm_check_enabled: bool = True,
    ):
        self._llm = llm
        self._llm_check_enabled = llm_check_enabled

    def validate(
        self,
        goal: str,
        trace: ExecutionTrace,
    ) -> ValidationResult:
        """对执行轨迹做双层校验。

        Args:
            goal: 用户目标(供 LLM 校验语义完整性)
            trace: 执行轨迹

        Returns:
            ValidationResult(含规则层 + LLM 层结论)
        """
        # 参数校验(public API 入口)
        if not isinstance(goal, str):
            raise TypeError(f"goal 必须为 str,实际: {type(goal).__name__}")
        if trace is None:
            raise TypeError("trace 不能为 None")

        # Layer 1: 规则校验(确定性,无 LLM 依赖)
        rule_passed, rule_failures, rule_checks = self._rule_check(trace)

        # Layer 2: LLM 校验(仅当规则层通过或配置启用)
        llm_reflection: Optional[ReflectionResult] = None
        if self._llm_check_enabled and self._llm:
            llm_reflection = self._safe_llm_check(goal, trace)

        # 综合判定
        passed = rule_passed and (
            llm_reflection is None or llm_reflection.passed
        )
        score = self._compute_score(rule_passed, llm_reflection)

        reason_parts: list[str] = []
        if rule_failures:
            reason_parts.append(f"规则校验失败: {rule_failures}")
        if llm_reflection and not llm_reflection.passed:
            reason_parts.append(f"LLM校验: {llm_reflection.reason}")

        return ValidationResult(
            passed=passed,
            score=score,
            rule_checks=rule_checks,
            rule_failures=rule_failures,
            llm_reflection=llm_reflection,
            overall_reason="; ".join(reason_parts),
        )

    # -- Layer 1: 规则校验 ------------------------------------------------

    def _rule_check(
        self, trace: ExecutionTrace
    ) -> tuple[bool, list[str], list[str]]:
        """确定性规则校验:
        - 所有工具调用是否成功
        - 返回值是否非空
        - 是否有超时
        """
        failures: list[str] = []
        checks: list[str] = []

        if not trace.tool_results:
            checks.append("无工具调用记录")
            # 无工具调用不一定是失败(可能直接回答)
            return True, [], checks

        all_success = True
        for i, result in enumerate(trace.tool_results):
            checks.append(f"工具[{i+1}] {result.name}: {result.status.value}")
            if result.status == ToolExecutionStatus.FAILED:
                failures.append(
                    f"工具 {result.name} 执行失败: {result.error}"
                )
                all_success = False
            elif result.status == ToolExecutionStatus.TIMEOUT:
                failures.append(f"工具 {result.name} 超时")
                all_success = False
            elif result.output is None:
                failures.append(f"工具 {result.name} 返回值为空")
                all_success = False

        return all_success, failures, checks

    # -- Layer 2: LLM 校验 ------------------------------------------------

    def _safe_llm_check(
        self, goal: str, trace: ExecutionTrace
    ) -> Optional[ReflectionResult]:
        """LLM 校验的异常安全包装。

        BUG 修复:原 _llm_check 裸调 self._llm.chat,provider 抛异常会
        直接中断 validate。现 try-except 降级为 None(仅用规则层结论)。
        """
        try:
            return self._llm_check(goal, trace)
        except (LLMError, ReasoningError):
            # LLM 调用失败:降级为 None,仅用规则层结论
            return None
        except Exception:
            # 兜底:其他异常也降级,保证 validate 不中断
            return None

    def _llm_check(
        self, goal: str, trace: ExecutionTrace
    ) -> ReflectionResult:
        """调用 LLM 做语义校验。"""
        results_summary = self._summarize(trace)

        system_msg = Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是结果校验器。检查执行结果是否满足用户目标。\n"
                "校验维度: 完整性、正确性、格式。\n"
                "输出 JSON: "
                '{"passed": bool, "score": float, "reason": str, '
                '"suggestion": str, "needs_replan": bool}'
            ),
        )
        user_msg = Message(
            role=MessageRole.USER,
            content=f"目标: {goal}\n执行结果:\n{results_summary}",
        )

        from fnixagent.core.llm.base import LLMRequest
        request = LLMRequest(
            messages=[system_msg, user_msg],
            temperature=0.3,  # 校验用低温度,提升确定性
        )
        response = self._llm.chat(request)
        if response is None or not getattr(response, "content", None):
            # LLM 返回空,降级为默认通过
            return ReflectionResult(
                passed=True, score=0.8, reason="LLM 返回空,默认通过"
            )
        return self._parse_reflection(response.content)

    @staticmethod
    def _compute_score(
        rule_passed: bool,
        llm_reflection: Optional[ReflectionResult],
    ) -> float:
        """综合评分,clamp 到 [0.0, 1.0]。"""
        if llm_reflection:
            raw = llm_reflection.score
        elif rule_passed:
            raw = 0.8
        else:
            raw = 0.2
        # BUG 修复:强制 clamp 到 [0, 1],防 LLM 输出越界值
        try:
            score = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score

    def _summarize(self, trace: ExecutionTrace) -> str:
        """汇总执行轨迹为文本。"""
        parts = [f"迭代: {trace.iterations}"]
        for i, r in enumerate(trace.tool_results):
            status = r.status.value if r.status else "?"
            out = str(r.output)[:150] if r.output else "空"
            parts.append(f"[{i+1}] {r.name}({status}): {out}")
        return "\n".join(parts)

    def _parse_reflection(self, text: str) -> ReflectionResult:
        """解析 LLM 校验输出。

        BUG 修复:
          - score 强制 clamp 到 [0, 1]
          - 解析失败保持默认 passed=True(原行为,避免阻塞主流程),
            但 reason 显式标注"解析失败"
        """
        if not text:
            return ReflectionResult(
                passed=True, score=0.8, reason="LLM 输出为空,默认通过"
            )
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return ReflectionResult(
                passed=True, score=0.8, reason="解析失败,默认通过"
            )
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return ReflectionResult(
                passed=True, score=0.8, reason="解析失败,默认通过"
            )

        if not isinstance(data, dict):
            return ReflectionResult(
                passed=True, score=0.8, reason="解析结果非 dict,默认通过"
            )

        try:
            return ReflectionResult(
                passed=bool(data.get("passed", True)),
                score=self._clamp_score(data.get("score", 0.8)),
                check_type=str(data.get("check_type", "completeness")),
                reason=str(data.get("reason", "")),
                suggestion=str(data.get("suggestion", "")),
                needs_replan=bool(data.get("needs_replan", False)),
            )
        except (TypeError, ValueError):
            return ReflectionResult(
                passed=True, score=0.8, reason="字段类型异常,默认通过"
            )

    @staticmethod
    def _clamp_score(value: object) -> float:
        """把 LLM 输出的 score 限制在 [0.0, 1.0] 区间。"""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score
