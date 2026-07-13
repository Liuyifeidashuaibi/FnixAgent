"""
飞轮 1: 感知-执行环(实时)。

触发: 每次用户对话
职责:
    1. 初始化全局 State(消息/目标/技能列表/拓扑路径/迭代次数)
    2. 调用 LangGraph 图执行感知→检索→选技能→执行→反思循环
    3. 完整保存本次全链路推理轨迹(TraceRecord)

核心特性: 有状态可回溯、可暂停、可重试;技能按需调用。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from officeagent.core.types import ReasoningMode, TraceRecord
from officeagent.graph.state import GraphState, create_initial_state


class PerceptionFlywheel:
    """飞轮 ① 感知-执行环。

    用法:
        flywheel1 = PerceptionFlywheel(graph)
        trace = flywheel1.run("搜索关于 GPT-4 的论文")
    """

    def __init__(
        self,
        graph: Any,
        reasoning_mode: ReasoningMode = ReasoningMode.REACT,
    ) -> None:
        """初始化感知-执行飞轮。

        Args:
            graph: 编译后的 LangGraph 实例(GraphBuilder.build() 产出)
            reasoning_mode: 推理模式(默认 ReAct)
        """
        self._graph = graph
        self._reasoning_mode = reasoning_mode

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> TraceRecord:
        """执行感知-执行环。

        Args:
            user_input: 用户输入
            session_id: 会话 ID(用于检查点恢复,可选)
            config: LangGraph 配置(如 thread_id)

        Returns:
            完整的执行轨迹(TraceRecord)
        """
        start_time = time.time()

        # 初始化状态
        initial_state = create_initial_state(user_input)

        # 调用 LangGraph
        invoke_config = {}
        if session_id is not None:
            invoke_config["configurable"] = {"thread_id": session_id}
        if config:
            invoke_config.update(config)

        try:
            final_state: GraphState = self._graph.invoke(
                initial_state, config=invoke_config
            )
            success = final_state.get("trace", {}).get("success", False)
            error = final_state.get("error")
        except Exception as e:
            final_state = initial_state
            success = False
            error = str(e)

        # 构建轨迹记录
        duration_ms = (time.time() - start_time) * 1000
        trace_data = final_state.get("trace", {})

        trace = TraceRecord(
            trace_id=trace_data.get("trace_id", str(uuid.uuid4())),
            task_id=trace_data.get("task_id", str(uuid.uuid4())),
            goal=user_input,
            mode=self._reasoning_mode,
            concept_path=final_state.get("concept_path", []),
            tool_calls=trace_data.get("tool_calls", []),
            success=success,
            duration_ms=duration_ms,
            usage_tokens=0,  # 由 LLM 路由器回填
            reflection_score=0.0,  # 由飞轮 ③ 回填
            created_at=time.time(),
        )

        if error:
            trace.metadata = {"error": error} if hasattr(trace, "metadata") else {}

        return trace

    def run_stream(
        self,
        user_input: str,
        session_id: Optional[str] = None,
    ) -> Any:
        """流式执行(逐节点产出状态更新)。

        Yields:
            每个 LangGraph 节点执行后的状态更新
        """
        initial_state = create_initial_state(user_input)
        invoke_config = {}
        if session_id is not None:
            invoke_config["configurable"] = {"thread_id": session_id}

        for event in self._graph.stream(initial_state, config=invoke_config):
            yield event

    def resume(self, session_id: str) -> Any:
        """从检查点恢复执行(中断后继续)。

        Args:
            session_id: 会话 ID(必须与 run() 时相同)

        Returns:
            恢复后的最终状态
        """
        return self._graph.invoke(
            None,  # None 表示从检查点恢复
            config={"configurable": {"thread_id": session_id}},
        )


def trace_to_dict(trace: TraceRecord) -> dict:
    """将 TraceRecord 序列化为 dict(供持久化)。"""
    return {
        "trace_id": trace.trace_id,
        "task_id": trace.task_id,
        "goal": trace.goal,
        "mode": trace.mode.value if hasattr(trace.mode, "value") else str(trace.mode),
        "concept_path": trace.concept_path,
        "tool_calls": trace.tool_calls,
        "success": trace.success,
        "duration_ms": trace.duration_ms,
        "usage_tokens": trace.usage_tokens,
        "reflection_score": trace.reflection_score,
        "created_at": trace.created_at,
    }


def trace_from_dict(d: dict) -> TraceRecord:
    """从 dict 反序列化为 TraceRecord。"""
    mode_str = d.get("mode", "react")
    try:
        mode = ReasoningMode(mode_str)
    except ValueError:
        mode = ReasoningMode.REACT
    return TraceRecord(
        trace_id=d["trace_id"],
        task_id=d["task_id"],
        goal=d["goal"],
        mode=mode,
        concept_path=d.get("concept_path", []),
        tool_calls=d.get("tool_calls", []),
        success=d.get("success", False),
        duration_ms=d.get("duration_ms", 0.0),
        usage_tokens=d.get("usage_tokens", 0),
        reflection_score=d.get("reflection_score", 0.0),
        created_at=d.get("created_at", 0.0),
    )
