"""重规划器 (Replanner)。

当反思校验不通过时,生成改进方案:
  1. 分析失败原因(从 ValidationResult 提取)
  2. 调用 LLM 生成重规划建议(补充工具调用/修改参数/换工具)
  3. 输出 ReplanResult: 新的目标描述 + 建议步骤

重规划策略:
  - 局部修复: 只修复失败的步骤(补充参数/重试)
  - 全局重规划: 重新生成完整计划
  - 工具替换: 原工具不可用时换替代工具

异常处理(BUG 修复):
  - LLM 调用 try-except,失败时降级为规则重规划(原实现裸调 chat)
  - JSON 解析 try-except(json.JSONDecodeError),失败时保留原 suggestion
  - replan_count 边界检查:在递增前判断,避免越界后仍生成新计划
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from fnixagent.core.exceptions import LLMError, ReasoningError
from fnixagent.core.llm.router import LLMRouter
from fnixagent.core.reflection.validator import ValidationResult
from fnixagent.core.types import (
    ExecutionTrace,
    Message,
    MessageRole,
    ToolExecutionStatus,
)


@dataclass
class ReplanResult:
    """重规划结果。"""

    success: bool
    new_goal: str = ""  # 调整后的目标(含失败上下文)
    suggestion: str = ""  # 改进建议
    failed_tools: list[str] = field(default_factory=list)
    retry_steps: list[dict] = field(default_factory=list)  # 需重试的步骤
    replan_strategy: str = "local"  # local / global / tool_swap


class Replanner:
    """重规划器。

    用法:
        replanner = Replanner(llm=llm_router)
        replan = replanner.replan(goal, trace, validation)
        if replan.success:
            new_goal = replan.new_goal
            # 用新目标重新执行

    并发安全:
        _replan_count 为实例内部状态,Replanner 实例不跨任务共享。
        新任务前需调 reset() 重置计数器(同一 Replanner 实例)。
    """

    def __init__(
        self,
        llm: LLMRouter | None = None,
        max_replans: int = 2,
    ):
        # 参数校验(public API 入口)
        if not isinstance(max_replans, int) or max_replans <= 0:
            raise ValueError(f"max_replans 必须为正整数,实际: {max_replans!r}")
        self._llm = llm
        self._max_replans = max_replans
        self._replan_count = 0

    def can_replan(self) -> bool:
        """是否还可重规划。"""
        return self._replan_count < self._max_replans

    def reset(self) -> None:
        """重置计数器(新任务)。"""
        self._replan_count = 0

    def replan(
        self,
        goal: str,
        trace: ExecutionTrace,
        validation: ValidationResult,
    ) -> ReplanResult:
        """根据校验结果生成重规划方案。

        Args:
            goal: 原始用户目标
            trace: 上次执行的完整轨迹
            validation: 校验结果(含失败原因)

        Returns:
            ReplanResult(success=True 表示可继续重规划,
                         success=False 表示已达上限或参数非法)
        """
        # 参数校验(public API 入口)
        if not isinstance(goal, str):
            raise TypeError(f"goal 必须为 str,实际: {type(goal).__name__}")
        if trace is None:
            raise TypeError("trace 不能为 None")
        if validation is None:
            raise TypeError("validation 不能为 None")

        # BUG 修复:在递增前判断,避免越界后仍生成新计划
        # 原实现先 +1 再判断 >,逻辑虽对但不直观;改为先判断再 +1
        if not self.can_replan():
            return ReplanResult(
                success=False,
                suggestion=(f"已达最大重规划次数 {self._max_replans}"),
            )
        self._replan_count += 1

        # 分析失败工具
        failed_tools = self._find_failed_tools(trace)

        # 确定重规划策略
        strategy = self._choose_strategy(trace, validation)

        # 用 LLM 生成改进建议(LLM 调用异常时降级为规则重规划)
        suggestion = ""
        retry_steps: list[dict] = []
        if self._llm:
            try:
                suggestion, retry_steps = self._llm_replan(goal, trace, validation, strategy)
            except (LLMError, ReasoningError):
                # LLM 调用失败:降级为规则重规划(保证 replan 不中断)
                suggestion = self._rule_replan(trace, validation)
                retry_steps = self._build_retry_steps(trace)
        else:
            # 无 LLM 时用规则生成
            suggestion = self._rule_replan(trace, validation)
            retry_steps = self._build_retry_steps(trace)

        # 构建新目标(加入失败上下文)
        new_goal = self._build_new_goal(goal, validation, suggestion)

        return ReplanResult(
            success=True,
            new_goal=new_goal,
            suggestion=suggestion,
            failed_tools=failed_tools,
            retry_steps=retry_steps,
            replan_strategy=strategy,
        )

    # -- 分析 --------------------------------------------------------------

    def _find_failed_tools(self, trace: ExecutionTrace) -> list[str]:
        """找出执行失败的工具名。"""
        failed: list[str] = []
        for result in trace.tool_results:
            if result.status in (ToolExecutionStatus.FAILED, ToolExecutionStatus.TIMEOUT):
                failed.append(result.name)
        return failed

    def _choose_strategy(self, trace: ExecutionTrace, validation: ValidationResult) -> str:
        """选择重规划策略:
        - 只有个别工具失败 → local(局部修复)
        - 多数工具失败 → global(全局重规划)
        - 工具不存在/超时 → tool_swap(换工具)
        """
        total = len(trace.tool_results)
        failed = len(self._find_failed_tools(trace))
        if total == 0:
            return "global"
        fail_rate = failed / total
        if fail_rate >= 0.5:
            return "global"
        # rule_failures 文本中包含"不存在"/"超时"关键词 → 换工具
        if any(("不存在" in f) or ("超时" in f) for f in validation.rule_failures):
            return "tool_swap"
        return "local"

    # -- LLM 重规划 --------------------------------------------------------

    def _llm_replan(
        self,
        goal: str,
        trace: ExecutionTrace,
        validation: ValidationResult,
        strategy: str,
    ) -> tuple[str, list[dict]]:
        """调用 LLM 生成重规划建议。

        异常处理:JSON 解析失败时保留原 suggestion(用 LLM 原始文本),
        retry_steps 返回空列表(交由规则层补充)。
        """
        results_summary = self._summarize(trace)
        system_msg = Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是任务重规划器。上次执行未通过校验,请分析失败原因并生成改进方案。\n"
                f"重规划策略: {strategy}\n"
                "输出 JSON: "
                '{"suggestion": "改进建议", '
                '"retry_steps": [{"step_no": 1, "tool_name": "...", '
                '"arguments": {}, "reason": "..."}]}'
            ),
        )
        user_msg = Message(
            role=MessageRole.USER,
            content=(
                f"原始目标: {goal}\n"
                f"执行结果:\n{results_summary}\n"
                f"校验失败: {validation.overall_reason}"
            ),
        )

        from fnixagent.core.llm.base import LLMRequest

        request = LLMRequest(messages=[system_msg, user_msg], temperature=0.3)
        response = self._llm.chat(request)
        if response is None or not getattr(response, "content", None):
            # LLM 返回空,降级为规则重规划
            return self._rule_replan(trace, validation), []

        # 默认 suggestion 为 LLM 原始文本(防 JSON 解析失败时无内容可回退)
        suggestion = response.content
        retry_steps: list[dict] = []
        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                # JSON 解析失败:保留 suggestion 为 LLM 原始文本
                pass
            else:
                if isinstance(data, dict):
                    suggestion = str(data.get("suggestion", suggestion))
                    raw_steps = data.get("retry_steps", [])
                    if isinstance(raw_steps, list):
                        retry_steps = [s for s in raw_steps if isinstance(s, dict)]

        return suggestion, retry_steps

    # -- 规则重规划(无LLM降级) -------------------------------------------

    def _rule_replan(self, trace: ExecutionTrace, validation: ValidationResult) -> str:
        """无 LLM 时用规则生成简单建议。"""
        failed = self._find_failed_tools(trace)
        if failed:
            return f"工具 {failed} 执行失败,建议检查参数后重试或换用替代工具"
        return "结果不完整,建议补充工具调用"

    def _build_retry_steps(self, trace: ExecutionTrace) -> list[dict]:
        """构建重试步骤(失败的工具重新执行)。"""
        steps: list[dict] = []
        for i, result in enumerate(trace.tool_results):
            if result.status in (ToolExecutionStatus.FAILED, ToolExecutionStatus.TIMEOUT):
                # 找到原始调用参数
                if i < len(trace.tool_calls):
                    call = trace.tool_calls[i]
                    steps.append(
                        {
                            "step_no": i + 1,
                            "tool_name": call.name,
                            "arguments": call.arguments,
                            "reason": f"重试失败的工具 {call.name}",
                        }
                    )
        return steps

    # -- 辅助 --------------------------------------------------------------

    def _build_new_goal(self, goal: str, validation: ValidationResult, suggestion: str) -> str:
        """构建包含失败上下文的新目标。"""
        return (
            f"{goal}\n\n"
            f"上次执行问题: {validation.overall_reason}\n"
            f"改进建议: {suggestion}\n"
            f"请基于以上反馈重新执行。"
        )

    def _summarize(self, trace: ExecutionTrace) -> str:
        """将执行轨迹汇总为文本(供 LLM 重规划 prompt 使用)。"""
        parts = [f"迭代: {trace.iterations}"]
        for i, r in enumerate(trace.tool_results):
            status = r.status.value if r.status else "?"
            out = str(r.output)[:150] if r.output else "空"
            err = f" (错误: {r.error})" if r.error else ""
            parts.append(f"[{i + 1}] {r.name}({status}): {out}{err}")
        return "\n".join(parts)
