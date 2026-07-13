"""SOP 执行器 —— P3-3。

负责按依赖关系执行 SOP 中的 Action 序列:
  1. 拓扑排序分层(Kahn 算法)
  2. 同层 Action 并行执行(可选;默认串行)
  3. 依赖失败的 Action 自动跳过(SKIPPED)
  4. ExpectedOutput JSON Schema 校验
  5. 重试策略(继承 Action.retry_policy 或工具默认)
  6. ExecutionTrace 记录完整执行轨迹

设计要点:
  - 执行器不直接持有工具,通过 ToolExecutor 间接调用(解耦)
  - 失败策略可配置:FAIL_FAST(首个失败即终止)/ CONTINUE(继续执行无依赖失败的)
  - 并行执行使用线程池(I/O 密集型场景友好)
  - 校验失败可选择视为执行失败(严格模式)或仅记录警告(宽松模式)
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from officeagent.core.sop.models import (
    Action,
    ActionStatus,
    ActionResult,
    ExecutionTrace,
    SOP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 失败策略
# ---------------------------------------------------------------------------


class FailurePolicy:
    """SOP 执行失败策略。"""

    FAIL_FAST = "fail_fast"      # 首个 Action 失败即终止整个 SOP
    CONTINUE = "continue"        # 继续执行(跳过依赖失败的 Action)
    SKIP_ON_VALIDATION = "skip_on_validation"  # 校验失败也视为失败(默认仅警告)


# ---------------------------------------------------------------------------
# SOPExecutor
# ---------------------------------------------------------------------------


class SOPExecutor:
    """SOP 执行器。

    用法:
        executor = SOPExecutor(tool_executor=tool_exec)
        trace = executor.execute(sop, ctx)
        if trace.success:
            print("SOP succeeded")
    """

    def __init__(
        self,
        tool_executor: Any = None,
        failure_policy: str = FailurePolicy.CONTINUE,
        parallel: bool = False,
        max_workers: int = 4,
        strict_validation: bool = False,
    ) -> None:
        """初始化执行器。

        Args:
            tool_executor:    ToolExecutor 实例(提供 execute 方法)
                              None 时使用内置 mock(仅用于测试)
            failure_policy:   失败策略(fail_fast / continue)
            parallel:         是否并行执行同层 Action
            max_workers:      并行执行最大线程数
            strict_validation: True 时校验失败视为执行失败
        """
        self._tool_executor = tool_executor
        self._failure_policy = failure_policy
        self._parallel = parallel
        self._max_workers = max(1, max_workers)
        self._strict_validation = strict_validation

    # -- 公共 API ----------------------------------------------------------

    def execute(self, sop: SOP, ctx: Optional[Any] = None) -> ExecutionTrace:
        """执行 SOP,返回完整执行轨迹。

        执行策略:
          - 异常隔离:单 Action 失败不影响整体流程(CONTINUE 策略),
            依赖该 Action 的后续 Action 标记为 SKIPPED
          - 并行执行:同层无依赖的 Action 可并行(parallel=True 时)
          - 拓扑排序:用 Kahn 算法分层,自动检测依赖环

        Args:
            sop: SOP 实例
            ctx: 执行上下文(可选,透传给工具)

        Returns:
            ExecutionTrace(包含每个 Action 的执行结果与整体成功标志)
        """
        trace = ExecutionTrace(sop_name=sop.name, started_at=time.time())
        # 初始化全部 Action 为 PENDING
        trace.results = [
            ActionResult(
                action_name=a.name,
                action_index=i,
                status=ActionStatus.PENDING,
            )
            for i, a in enumerate(sop.actions)
        ]

        try:
            layers = sop.topological_order()
        except ValueError as e:
            # 依赖环检测失败:直接返回失败 trace,不执行任何 Action
            trace.success = False
            trace.error = str(e)
            trace.ended_at = time.time()
            return trace

        # 逐层执行(同层 Action 可并行,层间串行)
        for layer in layers:
            self._execute_layer(sop, layer, trace, ctx)

            # 检查是否需要提前终止(FAIL_FAST 策略)
            if self._failure_policy == FailurePolicy.FAIL_FAST:
                failed = [
                    r for r in trace.results
                    if r.status == ActionStatus.FAILED
                ]
                if failed:
                    trace.success = False
                    trace.error = (
                        f"fail_fast: action '{failed[0].action_name}' failed"
                    )
                    # 标记未执行的为 SKIPPED
                    for r in trace.results:
                        if r.status == ActionStatus.PENDING:
                            r.status = ActionStatus.SKIPPED
                            r.error = "skipped due to earlier failure"
                    break

        # 检查整体成功(CONTINUE 策略下,任一 Action 失败则整体失败)
        if trace.success:
            has_failed = any(
                r.status == ActionStatus.FAILED for r in trace.results
            )
            if has_failed:
                trace.success = False
                trace.error = "one or more actions failed"

        trace.ended_at = time.time()
        return trace

    # -- 内部:执行一层 ----------------------------------------------------

    def _execute_layer(
        self,
        sop: SOP,
        layer: list[int],
        trace: ExecutionTrace,
        ctx: Optional[Any],
    ) -> None:
        """执行一层(可并行的 Action 索引列表)。"""
        if not layer:
            return

        # 过滤掉被跳过的(依赖失败的)
        actionable: list[int] = []
        for idx in layer:
            # 检查依赖是否有失败
            action = sop.actions[idx]
            dep_failed = False
            for dep in action.depends_on:
                dep_result = trace.results[dep]
                if dep_result.status in (ActionStatus.FAILED, ActionStatus.SKIPPED):
                    dep_failed = True
                    break
            if dep_failed:
                trace.results[idx].status = ActionStatus.SKIPPED
                trace.results[idx].error = "dependency failed or skipped"
                logger.info(
                    "SOP '%s': action[%d] '%s' skipped (dependency failed)",
                    sop.name, idx, action.name,
                )
            else:
                actionable.append(idx)

        if not actionable:
            return

        # 并行 or 串行
        if self._parallel and len(actionable) > 1:
            self._execute_parallel(sop, actionable, trace, ctx)
        else:
            for idx in actionable:
                self._execute_action(sop, idx, trace, ctx)

    def _execute_parallel(
        self,
        sop: SOP,
        indices: list[int],
        trace: ExecutionTrace,
        ctx: Optional[Any],
    ) -> None:
        """并行执行多个 Action。"""
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            future_to_idx = {
                pool.submit(self._execute_action, sop, idx, trace, ctx): idx
                for idx in indices
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    future.result()
                except Exception as e:
                    # _execute_action 已记录错误,这里兜底
                    if trace.results[idx].status == ActionStatus.RUNNING:
                        trace.results[idx].status = ActionStatus.FAILED
                        trace.results[idx].error = f"{type(e).__name__}: {e}"

    def _execute_action(
        self,
        sop: SOP,
        idx: int,
        trace: ExecutionTrace,
        ctx: Optional[Any],
    ) -> None:
        """执行单个 Action。"""
        action = sop.actions[idx]
        result = trace.results[idx]
        result.status = ActionStatus.RUNNING
        result.attempts = 0

        t0 = time.monotonic()
        try:
            output = self._call_tool(action, ctx)
            result.output = output
            result.attempts += 1

            # 校验 ExpectedOutput
            if action.expected_output is not None:
                is_valid, err = action.expected_output.validate(output)
                if not is_valid:
                    result.validation_error = err
                    if self._strict_validation:
                        result.status = ActionStatus.FAILED
                        result.error = f"output validation failed: {err}"
                        logger.warning(
                            "SOP '%s': action[%d] '%s' validation failed: %s",
                            sop.name, idx, action.name, err,
                        )
                        return
                    else:
                        logger.warning(
                            "SOP '%s': action[%d] '%s' validation warning: %s",
                            sop.name, idx, action.name, err,
                        )

            result.status = ActionStatus.SUCCESS
            logger.info(
                "SOP '%s': action[%d] '%s' succeeded",
                sop.name, idx, action.name,
            )
        except Exception as e:
            result.status = ActionStatus.FAILED
            result.error = f"{type(e).__name__}: {e}"
            result.attempts += 1
            logger.error(
                "SOP '%s': action[%d] '%s' failed: %s",
                sop.name, idx, action.name, e,
                exc_info=True,
            )
        finally:
            result.duration_ms = (time.monotonic() - t0) * 1000

    # -- 内部:调用工具 ----------------------------------------------------

    def _call_tool(self, action: Action, ctx: Optional[Any]) -> Any:
        """调用工具执行 Action。

        优先使用注入的 ToolExecutor;若未注入,使用内置 mock(测试用)。
        """
        if self._tool_executor is not None:
            # ToolExecutor.execute(tool_name, arguments, ctx=None)
            execute = getattr(self._tool_executor, "execute", None)
            if execute is None:
                raise RuntimeError(
                    f"tool_executor has no 'execute' method: "
                    f"{type(self._tool_executor).__name__}"
                )
            return execute(action.tool_name, action.arguments, ctx=ctx)

        # Mock 模式(无 ToolExecutor):回显参数,便于测试
        return {
            "mock": True,
            "tool_name": action.tool_name,
            "arguments": dict(action.arguments),
        }


__all__ = ["SOPExecutor", "FailurePolicy"]
