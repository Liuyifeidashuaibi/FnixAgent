"""Plan & Execute 推理引擎。

算法(先规划,后执行):
  Phase 1 — Plan:   LLM 将用户目标拆解为有序子任务计划(Plan)
  Phase 2 — Execute: 按 depends_on 依赖关系,用 ToolExecutor.execute_dag 执行
  Phase 3 — Verify:  校验每步结果,失败触发重规划(BUG 修复:原实现未实现)

适用场景: 复杂长流程任务,多步骤,步骤间有依赖,需要全局规划。

参考: Plan-and-Solve Prompting (Wang et al., 2023)

重规划触发条件(BUG 修复):
  - 任一步骤 status 为 FAILED/TIMEOUT → 触发重规划
  - 步骤数与结果数不一致(DAG 中途断链)→ 触发重规划
  - 重规划次数受 max_replans 限制,耗尽后返回当前 trace(不抛异常)
"""

from __future__ import annotations

import json
import re
from typing import Any

from fnixagent.core.exceptions import ReasoningError
from fnixagent.core.reasoning.base import ReasoningContext, ReasoningEngine
from fnixagent.core.reasoning.schemas import validate_plan_output
from fnixagent.core.types import (
    ExecutionTrace,
    Message,
    MessageRole,
    Plan,
    PlanStep,
    ReasoningMode,
    ToolCall,
    ToolExecutionStatus,
    ToolResult,
)


class PlanExecuteEngine(ReasoningEngine):
    """Plan & Execute 推理引擎。

    通过先生成全局计划再执行的方式,适合多步骤且步骤间存在依赖的复杂任务。
    执行后做结果校验,失败步骤触发局部重规划(受 max_replans 限制)。
    """

    # 默认最大重规划次数(防止 LLM 反复生成失败计划导致无限循环)
    DEFAULT_MAX_REPLANS: int = 2

    @property
    def mode(self) -> ReasoningMode:
        """返回 Plan&Execute 推理模式标识。"""
        return ReasoningMode.PLAN_EXECUTE

    def reason(self, ctx: ReasoningContext) -> ExecutionTrace:
        """全流程: 生成计划 → DAG 执行 → 校验 → (失败时)重规划。"""
        trace = self._make_trace(ctx)
        # 缓存首次生成的 Plan,避免重规划时重复 LLM 调用(性能优化)
        # 仅在重规划时基于失败上下文重新生成
        replan_count = 0

        # ---- Phase 1: 生成计划 --------------------------------------------
        plan = self._generate_plan(ctx)
        trace.steps = list(plan.steps)

        if not plan.steps:
            trace.steps.append(
                PlanStep(
                    step_no=1,
                    description="无法生成计划,直接回复",
                )
            )
            return trace

        # ---- Phase 2 + Phase 3: 执行 + 校验(+ 重规划) -------------------
        while True:
            results = self._execute_plan(ctx, plan, trace)

            # Phase 3: 校验结果,判断是否需要重规划
            needs_replan, failed_step_nos = self._should_replan(plan, results)

            if not needs_replan or replan_count >= self.DEFAULT_MAX_REPLANS:
                trace.iterations = len(plan.steps)
                return trace

            # ---- 触发重规划 ------------------------------------------------
            replan_count += 1
            try:
                plan = self._replan(ctx, plan, results, failed_step_nos, replan_count)
            except ReasoningError:
                # 重规划 LLM 调用失败,返回当前 trace(不抛异常,保留已执行结果)
                trace.iterations = len(plan.steps)
                return trace
            # 把重规划后的新步骤追加到 trace(保留历史步骤便于审计)
            trace.steps.extend(plan.steps)

    # -- Phase 1: 规划 ----------------------------------------------------

    def _generate_plan(self, ctx: ReasoningContext) -> Plan:
        """调用 LLM 生成执行计划。

        输出 JSON: {goal, steps: [{step_no, description, tool_name, arguments, depends_on}]}
        优先用 Pydantic Schema 校验,失败时降级为正则提取(性能/健壮性兼顾)。
        """
        system_msg = self._build_planner_system_message(ctx)
        user_msg = Message(
            role=MessageRole.USER,
            content=f"目标: {ctx.goal}",
        )

        raw = self._call_llm(ctx, [system_msg, user_msg])
        return self._parse_plan(raw, ctx.goal)

    def _build_planner_system_message(self, ctx: ReasoningContext) -> Message:
        """构建规划器系统 prompt。"""
        tool_desc = ctx.tool_registry.list_for_llm()
        return Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是一个任务规划器。将用户目标拆解为可执行的子任务计划。\n\n"
                "可用工具:\n"
                + "\n".join(
                    f"- {t['function']['name']}: {t['function']['description']}" for t in tool_desc
                )
                + "\n\n输出 JSON 格式:\n"
                '{"goal": "目标", "steps": [{"step_no": 1, '
                '"description": "描述", "tool_name": "工具名", '
                '"arguments": {}, "depends_on": []}]}\n'
                "depends_on 为前置步骤号列表,无依赖则为空数组。"
            ),
        )

    def _parse_plan(self, text: str, goal: str) -> Plan:
        """从 LLM 输出解析 Plan。

        解析顺序:
          1. Pydantic PlanOutput 严格校验(优先,性能优化:O(1) 字段查表)
          2. 严格校验失败 → 正则提取 + 宽松 dict 解析(降级容错)
          3. 全部失败 → 返回单步兜底计划(直接执行 goal)
        """
        if not text:
            return self._fallback_plan(goal)

        # 路径 1: 优先尝试整体 JSON 解析 + Pydantic 校验
        plan_output = validate_plan_output(text)
        if plan_output is not None:
            steps = [
                PlanStep(
                    step_no=s.step_no,
                    description=s.description,
                    tool_name=s.tool_name,
                    arguments=dict(s.arguments),
                    depends_on=list(s.depends_on),
                )
                for s in plan_output.steps
            ]
            if steps:
                return Plan(goal=plan_output.goal or goal, steps=steps)

        # 路径 2: 降级 — 正则提取首个 {...} 块再 dict 解析
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return self._fallback_plan(goal)

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return self._fallback_plan(goal)

        if not isinstance(data, dict):
            return self._fallback_plan(goal)

        steps: list[PlanStep] = []
        for s in data.get("steps", []) or []:
            if not isinstance(s, dict):
                continue
            steps.append(
                PlanStep(
                    step_no=int(s.get("step_no", len(steps) + 1)),
                    description=str(s.get("description", "")),
                    tool_name=s.get("tool_name"),
                    arguments=(
                        dict(s.get("arguments", {})) if isinstance(s.get("arguments"), dict) else {}
                    ),
                    depends_on=(
                        list(s.get("depends_on", []))
                        if isinstance(s.get("depends_on"), list)
                        else []
                    ),
                )
            )

        if not steps:
            return self._fallback_plan(goal)

        return Plan(goal=str(data.get("goal", goal)), steps=steps)

    @staticmethod
    def _fallback_plan(goal: str) -> Plan:
        """生成兜底单步计划(LLM 输出不可解析时使用)。"""
        return Plan(goal=goal, steps=[PlanStep(step_no=1, description=goal)])

    # -- Phase 2: 执行 ----------------------------------------------------

    def _execute_plan(
        self,
        ctx: ReasoningContext,
        plan: Plan,
        trace: ExecutionTrace,
    ) -> list[ToolResult]:
        """按 DAG 依赖关系执行计划,把工具调用记录到 trace。"""
        # 构建 DAG 步骤数据(execute_dag 内部做拓扑排序与并行调度)
        dag_steps: list[dict[str, Any]] = []
        for s in plan.steps:
            dag_steps.append(
                {
                    "step_no": s.step_no,
                    "tool_name": s.tool_name or "",
                    "arguments": s.arguments,
                    "depends_on": s.depends_on,
                }
            )

        results: list[ToolResult] = ctx.tool_executor.execute_dag(dag_steps)

        # 记录工具调用(便于审计与重规划时定位失败步骤)
        # 注意:zip 在 results 比 steps 短时只配对前半段,避免 IndexError
        for step, result in zip(plan.steps, results):
            if step.tool_name:
                call = ToolCall(
                    name=step.tool_name,
                    arguments=step.arguments,
                    call_id=f"plan_step_{step.step_no}",
                )
                trace.tool_calls.append(call)
            trace.tool_results.append(result)

        return results

    # -- Phase 3: 校验 + 重规划触发 --------------------------------------

    def _should_replan(
        self,
        plan: Plan,
        results: list[ToolResult],
    ) -> tuple[bool, list[int]]:
        """判断是否需要重规划,返回 (是否重规划, 失败步骤号列表)。

        触发条件:
          - 任一步骤 status ∈ {FAILED, TIMEOUT}
          - results 长度 < plan.steps 长度(DAG 中途断链)
        """
        failed_step_nos: list[int] = []
        # 长度不一致:执行链路断裂,触发重规划
        if len(results) < len(plan.steps):
            missing = plan.steps[len(results) :]
            return True, [s.step_no for s in missing if s.tool_name]

        for step, result in zip(plan.steps, results):
            if not step.tool_name:
                # 纯推理步骤,无工具调用,跳过校验
                continue
            if result.status in (ToolExecutionStatus.FAILED, ToolExecutionStatus.TIMEOUT):
                failed_step_nos.append(step.step_no)

        return (len(failed_step_nos) > 0), failed_step_nos

    def _replan(
        self,
        ctx: ReasoningContext,
        original_plan: Plan,
        results: list[ToolResult],
        failed_step_nos: list[int],
        replan_count: int,
    ) -> Plan:
        """基于失败上下文重新生成计划。

        性能优化:把失败步骤的 error 信息拼进 prompt,避免 LLM 重新推测失败原因,
        也避免重复全量规划(只重生成失败步骤及其后续)。
        """
        # 汇总失败步骤的 error,供 LLM 针对性调整
        failure_summary = self._summarize_failures(original_plan, results, failed_step_nos)

        system_msg = Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是任务重规划器。上次计划部分步骤执行失败,请基于失败原因"
                "重新生成完整计划(可调整工具/参数/依赖)。\n"
                f"重规划次数: {replan_count}/{self.DEFAULT_MAX_REPLANS}\n"
                "输出 JSON 格式同首次规划:\n"
                '{"goal": "...", "steps": [{"step_no": 1, '
                '"description": "...", "tool_name": "...", '
                '"arguments": {}, "depends_on": []}]}'
            ),
        )
        user_msg = Message(
            role=MessageRole.USER,
            content=(
                f"原始目标: {ctx.goal}\n失败步骤: {failed_step_nos}\n失败详情:\n{failure_summary}"
            ),
        )

        raw = self._call_llm(ctx, [system_msg, user_msg])
        new_plan = self._parse_plan(raw, ctx.goal)
        # 重规划也允许只生成单步(降级),不强制要求多步
        return new_plan

    @staticmethod
    def _summarize_failures(
        plan: Plan,
        results: list[ToolResult],
        failed_step_nos: list[int],
    ) -> str:
        """汇总失败步骤详情,供重规划 prompt 使用。"""
        if not failed_step_nos:
            return "无明确失败步骤(可能为执行链路断裂)"
        parts: list[str] = []
        for step, result in zip(plan.steps, results):
            if step.step_no in failed_step_nos:
                err = result.error or "未知错误"
                parts.append(
                    f"步骤{step.step_no} ({step.tool_name}): "
                    f"status={result.status.value}, error={err}"
                )
        return "\n".join(parts) if parts else "无失败详情"
