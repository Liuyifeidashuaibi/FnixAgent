"""单一 Runner 入口 —— P1-4。,
提供统一的 Agent 执行入口,收敛 lifecycle.py / graph.invoke / scheduler 三条路径。

核心概念:
  - NextStep:     联合类型,表示主循环每步的"下一步动作"
  - RunConfig:    运行配置(模式/步数上限/检查点/流式等)
  - RunResult:    运行结果(答案/usage/trace/步数等)
  - AgentRunner:  执行器,封装主循环(while True + NextStep)

三种执行模式:
  - auto:   自动选择(有 graph 用 graph,否则用 legacy)
  - legacy: 走 Lifecycle 7步流水线(core/orchestrator/lifecycle.py)
  - graph:  走 LangGraph 图执行(graph.invoke)

主循环伪代码:
    while True:
        next_step = self._compute_step(ctx, state)
        if next_step.kind == FINAL:
            return result
        elif next_step.kind == RUN_NODE:
            state = self._run_node(next_step.node_name, state)
        elif next_step.kind == HANDOFF:
            ctx = self._handoff(ctx, next_step)
        elif next_step.kind == INTERRUPT:
            self._save_checkpoint(...)
            return interrupted_result
        elif next_step.kind == ERROR:
            return error_result
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fnixagent.core.orchestrator.state import (
    OrchestratorContext,
)

# ---------------------------------------------------------------------------
# NextStep 联合类型
# ---------------------------------------------------------------------------


class StepKind(str, Enum):
    """主循环每步的动作类型。"""

    RUN_NODE = "run_node"  # 执行图节点
    HANDOFF = "handoff"  # Agent 间移交(P3-1)
    FINAL = "final"  # 完成,返回最终答案
    INTERRUPT = "interrupt"  # 中断(等待人工审核/外部输入)
    ERROR = "error"  # 错误,终止


@dataclass
class NextStep:
    """下一步动作基类。

    主循环根据 kind 分发到不同处理逻辑。
    """

    kind: StepKind


@dataclass
class NextStepRunNode(NextStep):
    """执行图节点。"""

    kind: StepKind = StepKind.RUN_NODE
    node_name: str = ""
    inputs: dict = field(default_factory=dict)


@dataclass
class NextStepHandoff(NextStep):
    """Agent 间移交(P3-1)。"""

    kind: StepKind = StepKind.HANDOFF
    target_agent: str = ""
    reason: str = ""


@dataclass
class NextStepFinal(NextStep):
    """完成,返回最终答案。"""

    kind: StepKind = StepKind.FINAL
    answer: str = ""
    usage: Any | None = None  # Usage(P1-5)


@dataclass
class NextStepInterrupt(NextStep):
    """中断(等待人工审核或外部输入)。"""

    kind: StepKind = StepKind.INTERRUPT
    reason: str = ""
    interrupt_id: str = ""
    resume_payload: dict | None = None


@dataclass
class NextStepError(NextStep):
    """错误终止。"""

    kind: StepKind = StepKind.ERROR
    error: str = ""
    error_type: str = ""


# ---------------------------------------------------------------------------
# RunConfig / RunResult
# ---------------------------------------------------------------------------


@dataclass
class RunConfig:
    """运行配置。

    Attributes:
        mode:               执行模式(auto/legacy/graph)
        max_steps:          最大步数(防无限循环)
        thread_id:          会话线程 ID(用于 Checkpoint)
        checkpoint_enabled: 是否启用 Checkpoint 持久化
        resume_from:        恢复点(checkpoint_id);None 表示新运行
        stream:             是否流式返回
        user_id / session_id / trace_id: 请求标识(透传到 Tracing/Billing)
    """

    mode: str = "auto"  # auto/legacy/graph
    max_steps: int = 50
    thread_id: str = ""
    checkpoint_enabled: bool = False
    resume_from: str | None = None
    stream: bool = False
    user_id: str = ""
    session_id: str = ""
    trace_id: str = ""


@dataclass
class RunResult:
    """运行结果。

    Attributes:
        answer:           最终答案
        success:          是否成功
        error:            错误信息(失败时)
        trace_id:         追踪 ID
        thread_id:        会话线程 ID
        usage:            Token/Cost 用量(P1-5)
        execution_trace:  执行轨迹(飞轮 ① 产出)
        duration_ms:      总耗时(毫秒)
        steps_taken:      实际执行步数
        final_step:       最后一步的 NextStep(用于调试)
    """

    answer: str = ""
    success: bool = True
    error: str = ""
    trace_id: str = ""
    thread_id: str = ""
    usage: Any | None = None
    execution_trace: dict | None = None
    duration_ms: float = 0.0
    steps_taken: int = 0
    final_step: NextStep | None = None

    def to_dict(self) -> dict:
        """转为字典(用于 API 响应/日志)。"""
        return {
            "answer": self.answer,
            "success": self.success,
            "error": self.error,
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
            "usage": (
                self.usage.to_dict() if self.usage and hasattr(self.usage, "to_dict") else None
            ),
            "duration_ms": self.duration_ms,
            "steps_taken": self.steps_taken,
            "final_step_kind": self.final_step.kind.value if self.final_step else None,
        }


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------


class AgentRunner:
    """单一 Runner 入口(P1-4)。

    统一 Agent 执行入口,支持三种模式:
      - auto:   自动选择(有 graph 用 graph,否则用 legacy)
      - legacy: 走 Lifecycle 7步流水线
      - graph:  走 LangGraph 图执行

    用法:
        runner = AgentRunner(ctx=orchestrator_ctx, graph=graph_builder.build())
        result = runner.run("帮我写一份周报", config=RunConfig(mode="auto"))

    流式:
        async for step in runner.astream("...", config=RunConfig(stream=True)):
            print(step.kind, step.answer if step.kind == StepKind.FINAL else "")
    """

    def __init__(
        self,
        ctx: OrchestratorContext,
        graph: Any | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        """初始化 Runner。

        Args:
            ctx:         OrchestratorContext(可用旧版 context.py 或新版 state.py)
            graph:       已编译的 LangGraph(可选;graph 模式必需)
            checkpointer: Checkpointer 实例(可选;checkpoint_enabled 时必需)
        """
        self._ctx = ctx
        self._graph = graph
        self._checkpointer = checkpointer
        # P3-1 Handoff 支持
        self._handoff_registry: Any | None = None  # HandoffRegistry
        self._agents: dict[str, Any] = {}  # name → Agent 实例(多 Agent 阶段填充)
        self._current_agent_name: str = "fnix-agent"  # 当前活跃 Agent 名
        self._handoff_depth: int = 0  # 当前 handoff 深度

    # -- 同步入口 -----------------------------------------------------------
    def run(
        self,
        user_input: str,
        config: RunConfig | None = None,
    ) -> RunResult:
        """同步执行。

        Args:
            user_input: 用户输入文本
            config:     运行配置(为 None 使用默认)

        Returns:
            RunResult

        Raises:
            TypeError:  user_input 不是 str
            ValueError: user_input 为空字符串
        """
        if not isinstance(user_input, str):
            raise TypeError(f"user_input must be str, got {type(user_input).__name__}")
        if not user_input.strip():
            raise ValueError("user_input must not be empty or whitespace-only")
        config = config or RunConfig()
        config.trace_id = config.trace_id or uuid.uuid4().hex[:16]
        config.thread_id = config.thread_id or config.trace_id

        t0 = time.monotonic()
        try:
            result = self._main_loop(user_input, config)
            result.duration_ms = (time.monotonic() - t0) * 1000
            return result
        except Exception as exc:
            return RunResult(
                answer=f"处理失败: {exc}",
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                trace_id=config.trace_id,
                thread_id=config.thread_id,
                duration_ms=(time.monotonic() - t0) * 1000,
            )

    # -- 异步入口 -----------------------------------------------------------
    async def arun(
        self,
        user_input: str,
        config: RunConfig | None = None,
    ) -> RunResult:
        """异步执行(默认委托给同步,子类可覆盖)。"""
        return self.run(user_input, config)

    async def astream(
        self,
        user_input: str,
        config: RunConfig | None = None,
    ) -> AsyncGenerator[NextStep, None]:
        """流式执行,yield 每个 NextStep。

        默认实现:执行 run(),最后 yield 一个 NextStepFinal。
        子类可覆盖以实现真正的流式(逐节点 yield)。
        """
        config = config or RunConfig()
        config.stream = True
        result = self.run(user_input, config)
        yield NextStepFinal(
            answer=result.answer,
            usage=result.usage,
        )

    # -- 恢复 ---------------------------------------------------------------
    def resume(
        self,
        thread_id: str,
        resume_payload: dict | None = None,
    ) -> RunResult:
        """从 Checkpoint 恢复执行。

        Args:
            thread_id:      会话线程 ID
            resume_payload: 恢复时传入的 payload(如人工审核结果)

        Returns:
            RunResult
        """
        if self._checkpointer is None:
            return RunResult(
                success=False,
                error="no checkpointer configured",
                thread_id=thread_id,
            )
        checkpoint_tuple = self._checkpointer.get_tuple({"thread_id": thread_id})
        if checkpoint_tuple is None:
            return RunResult(
                success=False,
                error=f"no checkpoint found for thread {thread_id}",
                thread_id=thread_id,
            )
        # 从检查点恢复 state,继续执行
        config = RunConfig(
            thread_id=thread_id,
            checkpoint_enabled=True,
            resume_from=checkpoint_tuple.checkpoint_id,
        )
        # 用恢复的 state 作为初始输入
        user_input = checkpoint_tuple.checkpoint.channel_values.get("user_input", "")
        return self.run(user_input, config)

    # -- 主循环 -------------------------------------------------------------
    def _main_loop(self, user_input: str, config: RunConfig) -> RunResult:
        """主循环:根据模式分发到 _run_legacy / _run_graph。"""
        # P1-1: 启动 Trace
        trace = None
        try:
            from fnixagent.core.observability.tracing import (
                AgentSpanData,
                get_provider,
            )

            provider = get_provider()
            trace = provider.start_trace(
                "agent_run",
                trace_id=config.trace_id,
                user_id=config.user_id,
                session_id=config.session_id,
                mode=config.mode,
            )
        except Exception:
            pass

        try:
            if trace is not None:
                with trace.start_span(
                    "agent",
                    AgentSpanData(agent_name="fnixagent", reasoning_mode=config.mode),
                ):
                    result = self._dispatch_mode(user_input, config)
                    return result
            return self._dispatch_mode(user_input, config)
        finally:
            if trace is not None:
                trace.end()

    def _dispatch_mode(self, user_input: str, config: RunConfig) -> RunResult:
        """根据 mode 分发到具体执行路径。"""
        mode = config.mode
        if mode == "auto":
            # 自动选择:有 graph 用 graph,否则 legacy
            # TODO(P1): 接入 AgentOS 模式
            #   - 当 self._agentos_kernel is not None 时，优先使用 agentos 模式
            #   - 实现 _run_agentos() 方法，将任务提交为 AgentProcess
            #   - 入口: core/agent/kernel.py -> AgentKernel
            if self._graph is not None:
                mode = "graph"
            else:
                mode = "legacy"
        if mode == "graph":
            return self._run_graph(user_input, config)
        return self._run_legacy(user_input, config)

    # -- Legacy 模式(走 Lifecycle)-----------------------------------------
    def _run_legacy(self, user_input: str, config: RunConfig) -> RunResult:
        """Legacy 模式:走 Lifecycle 7步流水线。"""
        from fnixagent.core.orchestrator.lifecycle import Lifecycle

        # 兼容新旧 OrchestratorContext
        legacy_ctx = self._ctx
        if hasattr(legacy_ctx, "state") and hasattr(legacy_ctx, "engines"):
            # 新版 OrchestratorContext,需要转回旧版(或直接用 engines)
            # 这里用一个轻量适配:把新版 ctx 的字段塞给 Lifecycle
            # Lifecycle 期望旧版 ctx(直接持有引擎引用)
            # 简单做法:用 from_legacy 反向不必要,直接构造旧版 ctx
            pass  # Lifecycle 直接用 self._ctx 的 engines 属性即可

        lifecycle = Lifecycle(legacy_ctx)
        pipeline_result = lifecycle.run(
            user_input=user_input,
            session_id=config.session_id,
            user_id=config.user_id,
        )

        return RunResult(
            answer=pipeline_result.final_answer,
            success=not bool(pipeline_result.error),
            error=pipeline_result.error,
            trace_id=config.trace_id,
            thread_id=config.thread_id,
            execution_trace=(
                pipeline_result.execution_trace.__dict__
                if pipeline_result.execution_trace
                and hasattr(pipeline_result.execution_trace, "__dict__")
                else None
            ),
            steps_taken=1,  # Legacy 模式算 1 步
            final_step=NextStepFinal(answer=pipeline_result.final_answer),
        )

    # -- Graph 模式(走 LangGraph)------------------------------------------
    def _run_graph(self, user_input: str, config: RunConfig) -> RunResult:
        """Graph 模式:走 LangGraph 图执行。"""
        if self._graph is None:
            return RunResult(
                success=False,
                error="graph mode requires a compiled graph",
                trace_id=config.trace_id,
                thread_id=config.thread_id,
            )

        from fnixagent.graph.state import create_initial_state

        initial_state = create_initial_state(user_input)
        invoke_config = {
            "configurable": {
                "thread_id": config.thread_id,
            },
        }

        # Checkpoint 恢复
        if config.resume_from and self._checkpointer:
            checkpoint_tuple = self._checkpointer.get_tuple(
                {"thread_id": config.thread_id, "checkpoint_id": config.resume_from}
            )
            if checkpoint_tuple is not None:
                # 用检查点的 channel_values 作为初始状态
                initial_state = {**initial_state, **checkpoint_tuple.checkpoint.channel_values}

        try:
            final_state = self._graph.invoke(initial_state, config=invoke_config)
        except Exception as exc:
            return RunResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                trace_id=config.trace_id,
                thread_id=config.thread_id,
            )

        answer = final_state.get("final_answer", "") or final_state.get("error", "")
        error = final_state.get("error", "")
        iteration = final_state.get("iteration", 0)

        return RunResult(
            answer=answer,
            success=not bool(error),
            error=error or "",
            trace_id=config.trace_id,
            thread_id=config.thread_id,
            execution_trace=final_state.get("trace"),
            steps_taken=iteration,
            final_step=NextStepFinal(answer=answer),
        )

    # -- 便捷方法 -----------------------------------------------------------
    @property
    def graph(self) -> Any | None:
        """已编译的 LangGraph(若有)。"""
        return self._graph

    @property
    def checkpointer(self) -> Any | None:
        """Checkpointer 实例(若有)。"""
        return self._checkpointer

    def set_graph(self, graph: Any) -> None:
        """设置/替换 LangGraph。"""
        self._graph = graph

    def set_checkpointer(self, checkpointer: Any) -> None:
        """设置/替换 Checkpointer。"""
        self._checkpointer = checkpointer

    # -- P3-1 Handoff 集成 --------------------------------------------------

    def set_handoff_registry(self, registry: Any) -> None:
        """设置 HandoffRegistry(P3-1)。

        Args:
            registry: HandoffRegistry 实例
        """
        self._handoff_registry = registry

    def register_agent(self, name: str, agent: Any) -> None:
        """注册一个 Agent 实例到 Runner(供 handoff 查找接收方)。

        Args:
            name:  Agent 名(与 Handoff.target_agent 对应)
            agent: Agent 实例

        Raises:
            TypeError:  name 不是 str
            ValueError: name 为空字符串
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name).__name__}")
        if not name.strip():
            raise ValueError("name must not be empty or whitespace-only")
        self._agents[name] = agent

    def set_current_agent(self, name: str) -> None:
        """设置当前活跃 Agent 名(用于 handoff 的 from_agent)。

        Args:
            name: Agent 名

        Raises:
            TypeError:  name 不是 str
            ValueError: name 为空字符串
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name).__name__}")
        if not name.strip():
            raise ValueError("name must not be empty or whitespace-only")
        self._current_agent_name = name

    def _exec_handoff(
        self,
        step: NextStepHandoff,
        config: RunConfig,
    ) -> NextStep:
        """执行 Handoff(P3-1)。

        主循环在遇到 NextStepHandoff 时调用本方法,完成:
          1. 调用 core.handoff.exec_handoff 执行移交
          2. 成功:更新 ctx.state(应用 handoff context),返回 NextStepRunNode
             让主循环以接收方身份继续执行
          3. 失败:返回 NextStepError

        Args:
            step:   NextStepHandoff(target_agent / reason)
            config: RunConfig

        Returns:
            NextStep:
              - NextStepRunNode:handoff 成功,主循环以接收方继续
              - NextStepError:  handoff 失败(未注册 / 拒绝 / 深度超限)
        """
        from fnixagent.core.handoff import (
            HandoffError,
            apply_handoff_to_state,
            exec_handoff,
        )

        if self._handoff_registry is None:
            return NextStepError(
                error="handoff requested but no HandoffRegistry configured",
                error_type="HandoffError",
            )

        target = step.target_agent or ""
        if not target:
            return NextStepError(
                error="NextStepHandoff.target_agent is empty",
                error_type="HandoffError",
            )

        # 获取 Tracer(用于埋点 HandoffSpan)
        tracer = None
        try:
            from fnixagent.core.observability.tracing import get_provider

            provider = get_provider()
            tracer = provider  # provider 提供 start_span / start_trace
        except Exception:
            pass

        try:
            output, target_instance = exec_handoff(
                from_agent=self._current_agent_name,
                target_agent=target,
                reason=step.reason,
                registry=self._handoff_registry,
                state=self._ctx.state,
                depth=self._handoff_depth,
                agents=self._agents or None,  # 空 dict 视为未提供
                tracer=tracer,
            )
        except HandoffError as exc:
            return NextStepError(
                error=f"handoff failed: {exc}",
                error_type="HandoffError",
            )

        if not output.accepted:
            return NextStepError(
                error=f"handoff rejected by '{target}': {output.message}",
                error_type="HandoffRejected",
            )

        # handoff 成功:构造 HandoffInput(用于 apply_handoff_to_state)
        from fnixagent.core.handoff import HandoffInput, build_handoff_context

        handoff_decl = self._handoff_registry.find(self._current_agent_name, target)
        context = build_handoff_context(
            state=self._ctx.state,
            handoff=handoff_decl,
            depth=self._handoff_depth,
        )
        handoff_input = HandoffInput(
            from_agent=self._current_agent_name,
            to_agent=target,
            reason=step.reason,
            context=context,
            depth=self._handoff_depth,
        )

        # 应用 handoff 到 state(产出接收方使用的新 state)
        new_state = apply_handoff_to_state(
            state=self._ctx.state,
            output=output,
            handoff_input=handoff_input,
        )
        self._ctx.state = new_state

        # 更新当前 Agent 名 + handoff 深度
        self._current_agent_name = target
        self._handoff_depth += 1

        # 返回 RUN_NODE,让主循环以接收方身份继续
        # node_name 留空,由 _dispatch_mode 根据接收方配置选择执行路径
        return NextStepRunNode(
            node_name="",
            inputs={"handoff_from": handoff_input.from_agent},
        )
