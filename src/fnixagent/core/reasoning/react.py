"""ReAct 推理引擎。

算法(Thought-Action-Observation 循环):
  1. Thought:  LLM 分析当前状态,决定下一步行动
  2. Action:   LLM 输出工具调用(name + arguments)
  3. Observation: 执行工具,获取返回结果
  4. 回到步骤1,直到 LLM 输出 Final Answer 或达到最大迭代

适用场景: 简单通用任务,工具数少,步骤可动态决定。

输出格式解析:
  LLM 按模板输出:
    Thought: ...
    Action: tool_name
    Action Input: {"key": "value"}
  或:
    Thought: ...
    Final Answer: ...

终止条件(BUG 修复):
  - LLM 输出 Final Answer → 成功返回
  - LLM 输出 Thought 但无 Action 且无 Final Answer → 视为 LLM 卡在思考,
    追加 observation 提示并终止循环(避免空转耗尽 max_iterations)
  - 达到 max_iterations → 追加"未完成"步骤后返回(不抛异常,保留 trace)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import re
from typing import Any

from fnixagent.core.reasoning.base import ReasoningContext, ReasoningEngine
from fnixagent.core.types import (
    ExecutionTrace,
    Message,
    MessageRole,
    ReasoningMode,
    ThoughtStep,
    ToolCall,
)


class ReActEngine(ReasoningEngine):
    """ReAct 推理引擎。

    通过 Thought → Action → Observation 循环驱动 LLM 与工具交互,
    直到 LLM 给出 Final Answer 或触发终止条件。
    """

    @property
    def mode(self) -> ReasoningMode:
        """返回 ReAct 推理模式标识。"""
        return ReasoningMode.REACT

    def reason(self, ctx: ReasoningContext) -> ExecutionTrace:
        """ReAct 循环: Thought → Action → Observation → ...

        循环上限由 ctx.max_iterations 强制执行(for 循环天然限制),
        不再在循环内重复调用 _check_iterations(原实现为死代码)。
        """
        trace = self._make_trace(ctx)
        # scratchpad 为本引擎私有可变状态,不回写 ctx.history(并发安全)
        scratchpad: list[Message] = list(ctx.history)

        # 构建初始 prompt(包含工具列表 + 输出格式约定)
        system_msg = self._build_system_message(ctx)

        # ---- ReAct 主循环 -------------------------------------------------
        # for 循环天然强制 max_iterations 上限,无需再调用 _check_iterations
        for iteration in range(ctx.max_iterations):
            trace.iterations = iteration + 1

            # 步骤 1: 调 LLM 生成 Thought + Action/Final Answer
            messages = [system_msg] + scratchpad
            raw = self._call_llm(ctx, messages)

            # 步骤 2: 解析 LLM 输出
            thought, action, action_input, final_answer = self._parse(raw)

            # 步骤 3a: 命中 Final Answer → 任务完成,直接返回
            if final_answer:
                trace.steps.append(
                    ThoughtStep(
                        thought=thought or final_answer,
                        action=None,
                        observation=None,
                    )
                )
                return trace

            # 步骤 3b: 命中 Action → 执行工具,记录 Observation
            if action:
                call = ToolCall(
                    name=action,
                    arguments=action_input or {},
                    call_id=f"react_{iteration}",
                )
                result = self._execute_tool(ctx, call)
                trace.tool_calls.append(call)
                trace.tool_results.append(result)

                step = ThoughtStep(
                    thought=thought or "",
                    action=call,
                    observation=result,
                )
                trace.steps.append(step)

                # 将本轮 LLM 输出 + 工具结果加入 scratchpad,供下一轮 LLM 参考
                scratchpad.append(
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=raw,
                    )
                )
                scratchpad.append(
                    Message(
                        role=MessageRole.TOOL,
                        content=json.dumps(
                            {
                                "tool": action,
                                "result": str(result.output),
                                "status": result.status.value,
                            },
                            ensure_ascii=False,
                        ),
                        name=action,
                    )
                )
                continue

            # 步骤 3c: LLM 仅输出 Thought,无 Action 也无 Final Answer
            # BUG 修复:原实现只追加 raw 后继续循环,可能让 LLM 反复空转耗尽迭代
            # 现追加显式提示并终止循环,保留已完成的 trace 供上层决策
            trace.steps.append(
                ThoughtStep(
                    thought=thought or raw or "LLM 未输出 Action/Final Answer",
                    action=None,
                    observation=None,
                )
            )
            scratchpad.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=raw,
                )
            )
            # 终止循环:LLM 卡在思考,继续重试无意义
            break

        # 循环耗尽 max_iterations 仍未得到 Final Answer
        # 不抛异常,保留 trace 供上层(反思/重规划)决策
        if not trace.steps or trace.steps[-1].action is not None:
            trace.steps.append(
                ThoughtStep(
                    thought="达到最大迭代次数,未能完成任务",
                )
            )
        return trace

    # -- Prompt 构建 -------------------------------------------------------

    def _build_system_message(self, ctx: ReasoningContext) -> Message:
        """构建 ReAct 系统 prompt(含工具列表 + 输出格式约定)。"""
        tool_desc = ctx.tool_registry.list_for_llm()
        return Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是一个智能助手,通过工具完成任务。\n"
                "可用工具:\n"
                + "\n".join(
                    f"- {t['function']['name']}: {t['function']['description']}" for t in tool_desc
                )
                + "\n\n请按以下格式回复:\n"
                "Thought: 你的思考\n"
                "Action: 工具名\n"
                'Action Input: {"参数": "值"}\n\n'
                "或完成后:\n"
                "Thought: 任务完成\n"
                "Final Answer: 最终答案"
            ),
        )

    # -- 输出解析 ----------------------------------------------------------

    def _parse(self, raw: str) -> tuple[str | None, str | None, dict[str, Any] | None, str | None]:
        """解析 LLM 的 ReAct 格式输出。

        Returns:
            (thought, action, action_input, final_answer)
            - 命中 Final Answer:返回 (thought, None, None, final_answer)
            - 命中 Action:返回 (thought, action, action_input, None)
            - 仅 Thought:返回 (thought, None, None, None)
            - 全部解析失败:返回 (None, None, None, None)
        """
        if not raw:
            return None, None, None, None

        thought: str | None = None
        action: str | None = None
        action_input: dict[str, Any] | None = None
        final_answer: str | None = None

        # Thought: 非贪婪匹配到下一个 "首字母大写标签" 行或文末
        m = re.search(r"Thought:\s*(.+?)(?=\n[A-Z]|\Z)", raw, re.DOTALL)
        if m:
            thought = m.group(1).strip()

        # Final Answer 优先于 Action(同一回复中二者并存时,以 Final Answer 为准)
        m = re.search(r"Final Answer:\s*(.+)", raw, re.DOTALL)
        if m:
            final_answer = m.group(1).strip()
            return thought, None, None, final_answer

        # Action: 行内单值
        m = re.search(r"Action:\s*(.+?)(?=\n|$)", raw)
        if m:
            action = m.group(1).strip()
            # 空串视为未命中
            if not action:
                action = None

        # Action Input: JSON 对象(非贪婪到下一个 }
        m = re.search(r"Action Input:\s*(\{.*?\})", raw, re.DOTALL)
        if m and action:
            try:
                parsed = json.loads(m.group(1))
            except json.JSONDecodeError:
                # JSON 解析失败时给空 dict,避免后续 ToolCall.arguments 为 None
                action_input = {}
            else:
                # 强制要求 arguments 为 dict,拒绝 LLM 输出 array/scalar
                if isinstance(parsed, dict):
                    action_input = parsed
                else:
                    action_input = {}

        return thought, action, action_input, final_answer
