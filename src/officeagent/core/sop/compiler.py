"""SOP 编译器 —— P3-3。

将 SOP 编译为 LangGraph 子图,使其可作为更大图的一个节点嵌入。

设计要点:
  1. 每个 Action 编译为一个 LangGraph 节点
  2. 依赖关系编译为边(Action[i] → Action[j] 若 j 依赖 i)
  3. 同层无依赖的 Action 通过 fan-out 并行(LangGraph 原生支持)
  4. LangGraph 未安装时降级为 SOPExecutor 直接执行

编译产物:
  - CompiledGraph(可 graph.invoke(initial_state))
  - 子图状态使用 SOPGraphState(继承 GraphState,附加 sop_trace 字段)

用例:
    compiler = SOPCompiler()
    subgraph = compiler.compile(sop)
    result = subgraph.invoke({"user_input": "生成周报"})
    trace = result.get("sop_trace")  # ExecutionTrace
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from officeagent.core.sop.executor import SOPExecutor
from officeagent.core.sop.models import (
    ActionStatus,
    ExecutionTrace,
    SOP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SOP 子图状态(LangGraph 用)
# ---------------------------------------------------------------------------


# SOP 子图在 LangGraph StateGraph 使用的状态键:
#   - user_input:   用户输入(透传)
#   - sop_trace:    ExecutionTrace(执行轨迹)
#   - sop_name:     SOP 名
#   - final_answer: 最终答案(可选,由 SOP 产出)
#
# 注:LangGraph 状态用 TypedDict 或 dict,这里用 dict 风格,兼容现有 GraphState。


# ---------------------------------------------------------------------------
# SOPCompiler
# ---------------------------------------------------------------------------


class SOPCompiler:
    """SOP → LangGraph 子图编译器。

    用法:
        compiler = SOPCompiler(tool_executor=tool_exec)
        subgraph = compiler.compile(sop)
        result = subgraph.invoke({"user_input": "..."})

    降级模式(LangGraph 未安装):
        compiled = compiler.compile(sop)  # 返回 _FallbackCompiled
        result = compiled.invoke({"user_input": "..."})
        # 内部用 SOPExecutor 执行
    """

    def __init__(
        self,
        tool_executor: Any = None,
        failure_policy: str = "continue",
        parallel: bool = False,
        max_workers: int = 4,
        strict_validation: bool = False,
    ) -> None:
        """初始化编译器。

        Args:
            tool_executor:    透传给 SOPExecutor
            failure_policy:   透传给 SOPExecutor
            parallel:         透传给 SOPExecutor
            max_workers:      透传给 SOPExecutor
            strict_validation: 透传给 SOPExecutor
        """
        self._executor = SOPExecutor(
            tool_executor=tool_executor,
            failure_policy=failure_policy,
            parallel=parallel,
            max_workers=max_workers,
            strict_validation=strict_validation,
        )

    def compile(self, sop: SOP) -> Any:
        """编译 SOP 为可执行对象。

        编译流程:
          1. 校验 SOP(拓扑排序检测依赖环,环存在则抛 ValueError)
          2. 尝试导入 LangGraph,成功则编译为 StateGraph 子图
          3. LangGraph 未安装则降级为 _FallbackCompiled(用 SOPExecutor 执行)

        Args:
            sop: SOP 实例

        Returns:
            CompiledGraph(LangGraph 已安装)或 _FallbackCompiled(降级)

        Raises:
            ValueError: SOP 存在依赖环
        """
        # 编译前先做拓扑排序,检测依赖环(抛 ValueError)
        sop.topological_order()
        try:
            from langgraph.graph import END, START, StateGraph
            from typing import TypedDict
        except ImportError:
            logger.info(
                "LangGraph not installed; SOPCompiler falls back to SOPExecutor"
            )
            return _FallbackCompiled(sop, self._executor)

        # 定义子图状态类型
        sop_state_keys = ["user_input", "sop_trace", "sop_name", "final_answer"]

        class SOPGraphState(TypedDict, total=False):
            user_input: str
            sop_trace: Any  # ExecutionTrace
            sop_name: str
            final_answer: str

        graph = StateGraph(SOPGraphState)

        # 为每个 Action 创建节点
        for i, action in enumerate(sop.actions):
            node_name = self._action_node_name(i, action)
            node_fn = self._make_node_fn(i, action, sop)
            graph.add_node(node_name, node_fn)

        # 构建边:基于依赖关系 + 拓扑分层
        layers = sop.topological_order()

        # START → 第一层
        first_layer = layers[0] if layers else []
        if not first_layer:
            # 无 Action,直接 END
            graph.add_edge(START, END)
        else:
            # START → 每个 first-layer 节点(fan-out 并行)
            for idx in first_layer:
                node_name = self._action_node_name(idx, sop.actions[idx])
                graph.add_edge(START, node_name)

            # 中间层:通过条件边实现 fan-out
            # 对每个 Action,其所有 dependent 作为下游
            for layer_idx in range(len(layers) - 1):
                current_layer = layers[layer_idx]
                next_layer = layers[layer_idx + 1]
                for idx in current_layer:
                    action = sop.actions[idx]
                    node_name = self._action_node_name(idx, action)
                    # 找到下一层中依赖本 Action 的
                    dependents = [
                        j for j in next_layer
                        if idx in sop.actions[j].depends_on
                    ]
                    if not dependents:
                        # 无下游依赖,但仍需连到下一层(通过条件边)
                        continue
                    for dep_idx in dependents:
                        dep_node = self._action_node_name(dep_idx, sop.actions[dep_idx])
                        graph.add_edge(node_name, dep_node)

            # 最后一层 → END
            last_layer = layers[-1] if layers else []
            for idx in last_layer:
                action = sop.actions[idx]
                node_name = self._action_node_name(idx, action)
                graph.add_edge(node_name, END)

        compiled = graph.compile()
        # 附加 SOP 元数据(供调用方查询)
        compiled.sop = sop  # type: ignore[attr-defined]
        return compiled

    # -- 内部 --------------------------------------------------------------

    @staticmethod
    def _action_node_name(index: int, action: Any) -> str:
        """生成 Action 节点名。"""
        return f"action_{index}_{action.name}"

    def _make_node_fn(self, index: int, action: Any, sop: SOP) -> Any:
        """为单个 Action 创建 LangGraph 节点函数。

        节点函数签名:(state) -> state_update
        """

        def node_fn(state: dict) -> dict:
            # 复用 SOPExecutor 执行单个 Action
            trace = state.get("sop_trace")
            if trace is None:
                trace = ExecutionTrace(
                    sop_name=sop.name,
                    started_at=time.time(),
                )
                trace.results = []

            # 确保 results 列表足够长
            while len(trace.results) <= index:
                trace.results.append(
                    type(
                        "R",
                        (),
                        {
                            "action_name": "",
                            "action_index": -1,
                            "status": ActionStatus.PENDING,
                            "output": None,
                            "error": "",
                            "duration_ms": 0.0,
                            "attempts": 0,
                            "validation_error": "",
                        },
                    )()
                )

            # 执行(单 Action)
            from officeagent.core.sop.models import ActionResult
            result = ActionResult(
                action_name=action.name,
                action_index=index,
                status=ActionStatus.RUNNING,
            )
            trace.results[index] = result

            t0 = time.monotonic()
            try:
                output = self._executor._call_tool(action, state)
                result.output = output
                result.status = ActionStatus.SUCCESS
                result.attempts = 1
            except Exception as e:
                result.status = ActionStatus.FAILED
                result.error = f"{type(e).__name__}: {e}"
                result.attempts = 1
            finally:
                result.duration_ms = (time.monotonic() - t0) * 1000

            return {"sop_trace": trace}

        return node_fn


# ---------------------------------------------------------------------------
# 降级模式(LangGraph 未安装)
# ---------------------------------------------------------------------------


class _FallbackCompiled:
    """LangGraph 未安装时的降级编译产物。

    提供 invoke() 接口,内部用 SOPExecutor 执行。
    不支持流式 / 中断恢复(LangGraph 才有)。
    """

    def __init__(self, sop: SOP, executor: SOPExecutor) -> None:
        self.sop = sop
        self._executor = executor

    def invoke(self, state: Optional[dict] = None, config: Optional[dict] = None) -> dict:
        """执行 SOP,返回最终状态。"""
        state = state or {}
        ctx = state.get("ctx") or state
        trace = self._executor.execute(self.sop, ctx=ctx)
        return {
            "user_input": state.get("user_input", ""),
            "sop_name": self.sop.name,
            "sop_trace": trace,
            "final_answer": (
                trace.results[-1].output if trace.results and trace.results[-1].success
                else None
            ),
        }


__all__ = ["SOPCompiler"]
