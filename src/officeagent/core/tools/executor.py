"""
工具执行器 (Tool Executor)。

核心算法:
  1. 单工具执行: 入参校验 → 权限检查 → 超时控制 → 执行 → 异常包装
  2. 串行执行: 按顺序依次调用, 前一步结果可注入下一步参数
  3. 并行执行: concurrent.futures.ThreadPoolExecutor, 同步等待全部完成
  4. DAG 拓扑编排: 基于 depends_on 的 Kahn 算法拓扑排序, 同层并行执行

安全设计(参考 OWASP ASI02 工具滥用防护):
  - 权限分级: LOW/MIDDLE/HIGH, 调用前检查调用者权限
  - 超时强制: 防止工具无限阻塞
  - 最大步数限制: 防止无限循环(ASI08 级联故障)
  - 最小权限原则: 默认只授予 LOW 权限
"""
from __future__ import annotations

import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any, Optional

from officeagent.core.config import ToolConfig
from officeagent.core.exceptions import (
    ToolCyclicDependencyError,
    ToolNotFoundError,
    ToolPermissionDeniedError,
    ToolTimeoutError,
    ToolValidationError,
)
from officeagent.core.scheduler import AutoscaledPool
from officeagent.core.tools.protocol import (
    RegisteredTool,
    ToolMetadata,
    validate_arguments,
)
from officeagent.core.tools.registry import ToolRegistry
from officeagent.core.types import (
    ToolCall,
    ToolCallState,
    ToolExecutionStatus,
    ToolPermission,
    ToolResult,
)


class ToolExecutor:
    """
    工具执行器。

    用法:
        executor = ToolExecutor(registry, config=tool_config)
        result = executor.execute(ToolCall(name="search_paper", arguments={"q": "AI"}))
    """

    def __init__(
        self,
        registry: ToolRegistry,
        config: Optional[ToolConfig] = None,
        autoscale_pool: Optional[AutoscaledPool] = None,
    ) -> None:
        self._registry = registry
        self._config = config or ToolConfig()
        # Hook 列表(借鉴 Lagent before/after_action 机制)
        # before_hooks: 工具执行前调用,可修改参数或拦截执行
        # after_hooks: 工具执行后调用,可修改结果或触发副作用
        self._before_hooks: list = []
        self._after_hooks: list = []
        # 编排线程池:用于 execute_parallel / execute_dag 的并行调度
        self._executor_pool = ThreadPoolExecutor(
            max_workers=self._config.max_parallel
        )
        # P0-05: 自适应并发池(可选)。提供时由其信号量动态限流,
        # 工具执行改用按 max_concurrency 配置的共享执行器;否则回退固定池。
        self._autoscale_pool: Optional[AutoscaledPool] = autoscale_pool
        if autoscale_pool is not None:
            # 不创建固定 _tool_pool;改用共享执行器,容量按 max_concurrency 配置,
            # 实际并发由 autoscale_pool 的信号量(current_concurrency)动态限制
            self._tool_pool: Optional[ThreadPoolExecutor] = None
            self._autoscale_executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
                max_workers=autoscale_pool.config.max_concurrency
            )
        else:
            # 向后兼容: 工具执行线程池,专门运行 tool.func,与编排池隔离
            # 避免 execute_parallel → execute → tool.func 嵌套提交导致死锁
            self._tool_pool = ThreadPoolExecutor(
                max_workers=max(self._config.max_parallel * 2, 8)
            )
            self._autoscale_executor = None
        self._step_counter = 0
        self._lock = threading.Lock()

    # -- Hook 机制(借鉴 Lagent) -------------------------------------------

    def add_before_hook(self, hook: Any) -> None:
        """注册前置 Hook。

        Hook 签名: hook(call: ToolCall) -> Optional[ToolResult]
        - 返回 ToolResult 则拦截执行(跳过工具调用,直接返回该结果)
        - 返回 None 则继续执行
        - 可修改 call 的 arguments(通过返回修改后的 call)

        典型用途: 参数预处理、权限二次检查、调用日志、限流
        """
        self._before_hooks.append(hook)

    def add_after_hook(self, hook: Any) -> None:
        """注册后置 Hook。

        Hook 签名: hook(call: ToolCall, result: ToolResult) -> ToolResult
        - 接收原始结果,返回(可能修改后的)结果
        - 可用于结果后处理、缓存写入、审计日志、质量评估

        典型用途: 结果清洗、缓存写入、审计记录、质量评估
        """
        self._after_hooks.append(hook)

    def _run_before_hooks(self, call: ToolCall) -> Optional[ToolResult]:
        """执行前置 Hook,返回非 None 则拦截。"""
        for hook in self._before_hooks:
            try:
                result = hook(call)
                if result is not None:
                    return result
            except Exception:
                pass  # Hook 异常不阻断主流程
        return None

    def _run_after_hooks(self, call: ToolCall, result: ToolResult) -> ToolResult:
        """执行后置 Hook,返回可能修改后的结果。"""
        for hook in self._after_hooks:
            try:
                modified = hook(call, result)
                if modified is not None:
                    result = modified
            except Exception:
                pass  # Hook 异常不阻断主流程
        return result

    # -- 执行器选择(P0-05) ------------------------------------------------

    def _get_tool_executor(self) -> ThreadPoolExecutor:
        """获取工具执行线程池。

        自适应模式下返回按 max_concurrency 配置的共享执行器(实际并发由
        autoscale_pool 的信号量动态限制);否则返回固定 _tool_pool。
        """
        if self._autoscale_pool is not None and self._autoscale_executor is not None:
            return self._autoscale_executor
        # 向后兼容: 无 autoscale_pool 时使用固定池(_tool_pool 必然非 None)
        assert self._tool_pool is not None
        return self._tool_pool

    # -- 单工具执行 --------------------------------------------------------

    def execute(self, call: ToolCall) -> ToolResult:
        """
        执行单个工具调用。
        流程: 查找工具 → 权限检查 → 入参校验 → 超时执行 → 包装结果

        P1-1: 若有 active trace,包裹 ToolSpan(无 trace 时零开销)。
        """
        # P1-1: 检查 active trace
        trace = None
        try:
            from officeagent.core.observability.tracing import get_provider
            trace = get_provider().get_current_trace()
        except Exception:
            pass

        if trace is not None:
            from officeagent.core.observability.tracing import ToolSpanData
            tool_span_data = ToolSpanData(
                tool_name=call.name,
                arguments=dict(call.arguments),
            )
            with trace.start_span("tool_call", tool_span_data) as span:
                result = self._execute_impl(call)
                # 回填结果到 Span
                tool_span_data.status = (
                    "success" if result.status == ToolExecutionStatus.SUCCESS
                    else result.status.value if hasattr(result.status, "value")
                    else str(result.status)
                )
                tool_span_data.duration_ms = result.duration_ms or (span.duration_ms or 0.0)
                tool_span_data.error = result.error or ""
                tool_span_data.attempts = call.attempts or 1
                if result.error:
                    span.set_error(result.error)
                return result
        result = self._execute_impl(call)
        # Hook: 后置处理(审计日志、缓存、质量评估等)
        return self._run_after_hooks(call, result)

    def _execute_impl(self, call: ToolCall) -> ToolResult:
        """实际执行逻辑(被 execute() 包裹 Span)。"""
        # P1-02: 请求去重(借鉴 zhua FNV-64a + Simhash)。
        # 启用方式: 调用 executor.add_before_hook 注册 dedup before_hook,或在
        # 业务编排层显式调用 core.tools.deduplicator.get_deduplicator() 进行
        # check_and_record(method="TOOL", target=call.name, arguments=call.arguments)。
        # dont_filter=True 可跳过去重(重试场景)。命中重复时 before_hook 返回
        # 缓存的 ToolResult 即可拦截执行,节省 LLM/工具调用资源。
        # Hook: 前置拦截(可能跳过工具调用)
        intercepted = self._run_before_hooks(call)
        if intercepted is not None:
            return self._run_after_hooks(call, intercepted)

        # 步数限制(防止无限循环)
        with self._lock:
            self._step_counter += 1
            if self._step_counter > self._config.max_total_steps:
                return ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    status=ToolExecutionStatus.FAILED,
                    error=f"超过最大工具调用步数 {self._config.max_total_steps}",
                )

        # 查找工具
        try:
            tool = self._registry.get(call.name)
        except ToolNotFoundError:
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status=ToolExecutionStatus.FAILED,
                error=f"工具 '{call.name}' 未注册",
            )

        # 权限检查(最小权限原则)
        if not self._check_permission(tool.metadata):
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status=ToolExecutionStatus.FAILED,
                error=f"权限不足: 工具 '{call.name}' 需要 {tool.metadata.permission_level.value} 权限",
            )

        # 入参校验
        ok, errors = validate_arguments(tool.metadata, call.arguments)
        if not ok:
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status=ToolExecutionStatus.FAILED,
                error="; ".join(errors),
            )

        # 执行(带超时)——使用独立的 _tool_pool 避免与编排池嵌套死锁
        # P0-4: 若配置了 retry_policy,超时/失败时按策略重试
        # P0-05: 若配置了 autoscale_pool,先获取并发槽位(阻塞),finally 释放
        timeout_sec = tool.metadata.timeout_ms / 1000.0
        retry_policy = tool.metadata.retry_policy
        max_attempts = retry_policy.max_attempts if retry_policy is not None else 1
        last_error: Optional[Exception] = None
        # P0-05: 获取自适应并发槽位(阻塞直到有可用槽位;无 autoscale_pool 时跳过)
        if self._autoscale_pool is not None:
            self._autoscale_pool.acquire()
        try:
            for attempt in range(1, max_attempts + 1):
                t0 = time.monotonic()
                try:
                    future = self._get_tool_executor().submit(tool.func, call.arguments)
                    output = future.result(timeout=timeout_sec)
                    duration_ms = (time.monotonic() - t0) * 1000
                    # P0-05: 记录延迟供自适应滚动窗口采样
                    if self._autoscale_pool is not None:
                        self._autoscale_pool.record_latency(duration_ms)
                    # Phase 2.10: 记录工具执行指标
                    try:
                        from officeagent.core.observability.metrics import record_tool_execution
                        record_tool_execution(tool_name=call.name, duration_seconds=duration_ms / 1000, success=True)
                    except Exception:
                        pass
                    # P0-4: 成功时更新 ToolCall 状态
                    call.state = ToolCallState.SUCCESS
                    return ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        status=ToolExecutionStatus.SUCCESS,
                        output=output,
                        duration_ms=duration_ms,
                        state=ToolCallState.SUCCESS,
                    )
                except FuturesTimeout:
                    last_error = TimeoutError(f"工具 '{call.name}' 执行超时 ({timeout_sec}s)")
                    # 尝试取消未开始的 future,释放线程池资源
                    future.cancel()
                    # Phase 2.10: 记录工具超时错误
                    try:
                        from officeagent.core.observability.metrics import record_tool_error
                        record_tool_error(tool_name=call.name, error_type="timeout")
                    except Exception:
                        pass
                    # 超时可重试:检查 retry_policy
                    if retry_policy is not None and retry_policy.should_retry(last_error, attempt):
                        delay = retry_policy.compute_delay(attempt)
                        if delay > 0:
                            time.sleep(delay)
                        call.attempts = attempt + 1
                        continue
                    call.state = ToolCallState.FAILED
                    return ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        status=ToolExecutionStatus.TIMEOUT,
                        error=f"工具 '{call.name}' 执行超时 ({timeout_sec}s)",
                        state=ToolCallState.FAILED,
                    )
                except Exception as exc:
                    last_error = exc
                    # Phase 2.10: 记录工具执行错误
                    try:
                        from officeagent.core.observability.metrics import record_tool_error
                        record_tool_error(tool_name=call.name, error_type=type(exc).__name__)
                    except Exception:
                        pass
                    # 异常可重试:检查 retry_policy
                    if retry_policy is not None and retry_policy.should_retry(exc, attempt):
                        delay = retry_policy.compute_delay(attempt)
                        if delay > 0:
                            time.sleep(delay)
                        call.attempts = attempt + 1
                        continue
                    call.state = ToolCallState.FAILED
                    return ToolResult(
                        call_id=call.call_id,
                        name=call.name,
                        status=ToolExecutionStatus.FAILED,
                        error=str(exc),
                        state=ToolCallState.FAILED,
                    )

            # P0-4: 达到最大重试次数仍失败
            call.state = ToolCallState.CANCELLED
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status=ToolExecutionStatus.FAILED,
                error=f"工具 '{call.name}' 在 {max_attempts} 次尝试后仍失败: {last_error}",
                state=ToolCallState.CANCELLED,
            )
        finally:
            # P0-05: 释放并发槽位 + 惰性调整(acquire 内部已调用,此处兜底确保触发)
            if self._autoscale_pool is not None:
                self._autoscale_pool.release()
                self._autoscale_pool.maybe_adjust()

    # -- 串行执行 ----------------------------------------------------------

    def execute_serial(
        self, calls: list[ToolCall]
    ) -> list[ToolResult]:
        """
        串行执行工具链。
        每步结果独立返回;若需将前一步结果注入下一步,由上层编排器处理。
        """
        results: list[ToolResult] = []
        for call in calls:
            result = self.execute(call)
            results.append(result)
            # 失败是否中断? 默认继续,由上层判断
        return results

    # -- 并行执行 ----------------------------------------------------------

    def execute_parallel(
        self, calls: list[ToolCall]
    ) -> list[ToolResult]:
        """
        并行执行多个无依赖的工具调用。
        使用 ThreadPoolExecutor, 最大并行数由 config.max_parallel 控制。
        """
        if not calls:
            return []
        future_map = {}
        for call in calls:
            future = self._executor_pool.submit(self.execute, call)
            future_map[future] = call

        results: list[ToolResult] = []
        for future in as_completed(future_map):
            call = future_map[future]
            try:
                results.append(future.result())
            except Exception as exc:
                # execute() 内部已包装异常为 ToolResult,
                # 此处兜底防止编排线程池本身的异常逃逸
                results.append(ToolResult(
                    call_id=call.call_id,
                    name=call.name,
                    status=ToolExecutionStatus.FAILED,
                    error=f"并行执行异常: {exc}",
                    state=ToolCallState.FAILED,
                ))
        # 按原始调用顺序排序
        call_order = {c.call_id or c.name: i for i, c in enumerate(calls)}
        results.sort(
            key=lambda r: call_order.get(r.call_id or r.name, 0)
        )
        return results

    # -- DAG 拓扑编排 ------------------------------------------------------

    def execute_dag(
        self,
        steps: list[dict],
    ) -> list[ToolResult]:
        """
        DAG 编排执行(核心算法)。

        steps: [{"step_no": 1, "tool_name": "search", "arguments": {},
                 "depends_on": []}, ...]

        算法:
          1. 拓扑排序(Kahn 算法): 计算入度, 入度为0的步骤入队
          2. 同层(同一批次入度为0)的步骤并行执行
          3. 执行完成后, 将依赖该步骤的后继步骤入度减1
          4. 重复直到全部完成
          5. 检测环: 若最终执行的步骤数 < 总步骤数, 则存在环
        """
        # 构建依赖图
        step_map = {s["step_no"]: s for s in steps}
        in_degree: dict[int, int] = {s["step_no"]: 0 for s in steps}
        dependents: dict[int, list[int]] = {
            s["step_no"]: [] for s in steps
        }

        for s in steps:
            for dep in s.get("depends_on", []):
                if dep in step_map:
                    in_degree[s["step_no"]] += 1
                    dependents[dep].append(s["step_no"])

        # Kahn 拓扑排序
        from collections import deque
        queue = deque(
            s_no for s_no, deg in in_degree.items() if deg == 0
        )
        results: list[ToolResult] = []
        completed: set[int] = set()

        while queue:
            # 同层并行: 取出所有入度为0的步骤
            batch = list(queue)
            queue.clear()

            calls = []
            for s_no in batch:
                step = step_map[s_no]
                calls.append(ToolCall(
                    name=step.get("tool_name", ""),
                    arguments=step.get("arguments", {}),
                    call_id=f"step_{s_no}",
                ))

            # 并行执行当前层
            batch_results = self.execute_parallel(calls) if len(calls) > 1 else [self.execute(calls[0])]

            for s_no, result in zip(batch, batch_results):
                completed.add(s_no)
                results.append(result)
                # 后继步骤入度减1
                for dep_s in dependents[s_no]:
                    in_degree[dep_s] -= 1
                    if in_degree[dep_s] == 0:
                        queue.append(dep_s)

        # 环检测
        if len(completed) < len(steps):
            uncompleted = set(step_map.keys()) - completed
            raise ToolCyclicDependencyError(
                f"DAG 存在环依赖, 未完成的步骤: {uncompleted}"
            )

        return results

    # -- 权限检查 ----------------------------------------------------------

    def _check_permission(self, metadata: ToolMetadata) -> bool:
        """
        权限检查(最小权限原则)。
        默认只允许 LOW 权限; MIDDLE/HIGH 需上层显式授权。
        子类可覆盖此方法实现更精细的权限控制。
        """
        return metadata.permission_level == ToolPermission.LOW

    def reset_step_counter(self) -> None:
        """重置步数计数器(新任务开始时调用)。"""
        with self._lock:
            self._step_counter = 0

    def shutdown(self) -> None:
        """关闭线程池(编排池 + 工具执行池 / 自适应执行器)。"""
        self._executor_pool.shutdown(wait=False)
        # P0-05: 自适应模式下 _tool_pool 为 None,改关 _autoscale_executor
        if self._tool_pool is not None:
            self._tool_pool.shutdown(wait=False)
        if self._autoscale_executor is not None:
            self._autoscale_executor.shutdown(wait=False)
        if self._autoscale_pool is not None:
            self._autoscale_pool.shutdown()
