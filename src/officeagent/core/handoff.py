"""类型化消息 + Handoff 协议 —— P3-1。

借鉴:
  - OpenAI Agents SDK:Handoff 作为 Agent 配置项,声明可移交的目标 Agent
  - LangGraph:状态在节点间显式传递,无隐式共享
  - AgentScope:Msg + 路由字段(send_to / sent_from / cause_by)支撑多 Agent

设计要点:
  1. Handoff 是声明(Agent 配置),不是行为 —— Runner 根据 NextStepHandoff 执行
  2. HandoffInput / HandoffOutput 显式契约,接收方可拒绝(accepted=False)
  3. input_filter 过滤传递的 history(避免上下文膨胀 / 隐私泄漏)
  4. max_depth 防止 handoff 死循环(A→B→A→B...)
  5. _exec_handoff 集成到 Runner,作为 NextStep.HANDOFF 的处理器

主循环集成(由 Runner._main_loop 调用):
    while True:
        next_step = self._compute_step(ctx, state)
        if next_step.kind == HANDOFF:
            next_step = self._exec_handoff(next_step, config)
            if next_step.kind == ERROR:
                return error_result
            # 继续主循环(目标 Agent 接管)
            continue
"""
from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from officeagent.core.types_msg import Msg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handoff 输入 / 输出(运行时契约)
# ---------------------------------------------------------------------------


@dataclass
class HandoffInput:
    """Handoff 输入(由发起方构造,传递给接收方)。

    Attributes:
        from_agent:   发起方 Agent 名
        to_agent:     接收方 Agent 名
        reason:       移交原因(供接收方决策 / 审计)
        context:      传递的上下文(含 history / trace / state 摘要)
                      已由 input_filter 过滤,接收方可直接使用
        depth:        当前 handoff 深度(0=首次,1=A→B 后 B 再 handoff)
    """

    from_agent: str
    to_agent: str
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转为字典(仅含摘要字段,不含 context 完整内容)。

        Returns:
            含 from_agent / to_agent / reason / depth / context_keys 的字典
        """
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "reason": self.reason,
            "depth": self.depth,
            "context_keys": list(self.context.keys()),
        }


@dataclass
class HandoffOutput:
    """Handoff 输出(由接收方返回)。

    Attributes:
        accepted:         是否接受移交(False 表示拒绝,Runner 转为 ERROR 或回退)
        receiving_agent:  实际接收方 Agent 名(可能与 to_agent 不同,如别名解析)
        message:          接受 / 拒绝原因(供日志与用户提示)
        new_context:      接收方修改后的上下文(可选;None 表示原样使用 input.context)
    """

    accepted: bool
    receiving_agent: str
    message: str = ""
    new_context: Optional[dict[str, Any]] = None

    @classmethod
    def accept(cls, agent: str, message: str = "") -> "HandoffOutput":
        """便捷构造:接受移交。"""
        return cls(accepted=True, receiving_agent=agent, message=message)

    @classmethod
    def reject(cls, agent: str, message: str) -> "HandoffOutput":
        """便捷构造:拒绝移交。"""
        return cls(accepted=False, receiving_agent=agent, message=message)

    def to_dict(self) -> dict[str, Any]:
        """转为字典(仅含摘要字段,不含 new_context 完整内容)。

        Returns:
            含 accepted / receiving_agent / message / has_new_context 的字典
        """
        return {
            "accepted": self.accepted,
            "receiving_agent": self.receiving_agent,
            "message": self.message,
            "has_new_context": self.new_context is not None,
        }


# ---------------------------------------------------------------------------
# Handoff 声明(Agent 配置项)
# ---------------------------------------------------------------------------


@dataclass
class Handoff:
    """Handoff 声明(作为 Agent 配置项,声明可移交的目标)。

    与 OpenAI Agents SDK 的 Handoff 对齐:
      - target_agent:    目标 Agent 名(必须在 Environment 中已注册)
      - description:     描述(供 LLM 决策何时 handoff)
      - input_filter:    过滤传递的 history(可选)
      - max_depth:       防死循环上限(默认 5)
      - on_handoff:      回调(可选,接收 HandoffInput,返回 HandoffOutput)
                         None 表示接收方默认接受

    用法:
        # Agent 配置中声明
        agent.handoffs = [
            Handoff(target_agent="researcher", description="文献检索移交"),
            Handoff(target_agent="writer", description="文档撰写移交"),
        ]
    """

    target_agent: str
    description: str = ""
    input_filter: Optional[Callable[[list[Msg]], list[Msg]]] = None
    max_depth: int = 5
    on_handoff: Optional[Callable[[HandoffInput], HandoffOutput]] = None

    def __post_init__(self) -> None:
        # 校验 target_agent:必须是非空字符串,否则 handoff 无法路由
        if not isinstance(self.target_agent, str):
            raise TypeError(
                f"target_agent must be str, got {type(self.target_agent).__name__}"
            )
        if not self.target_agent.strip():
            raise ValueError("target_agent must not be empty or whitespace-only")
        if not isinstance(self.max_depth, int):
            raise TypeError(
                f"max_depth must be int, got {type(self.max_depth).__name__}"
            )
        if self.max_depth < 1:
            raise ValueError(
                f"Handoff.max_depth must be >= 1, got {self.max_depth}"
            )


def make_handoff(target: str, **kwargs: Any) -> Handoff:
    """便捷工厂:构造 Handoff 声明。

    Args:
        target:  目标 Agent 名
        **kwargs: 透传给 Handoff 构造函数(description / input_filter / ...)

    Returns:
        Handoff 实例

    用法:
        h = make_handoff("researcher", description="文献检索移交", max_depth=3)
    """
    return Handoff(target_agent=target, **kwargs)


# ---------------------------------------------------------------------------
# HandoffRegistry(Agent → 可用 Handoff 列表)
# ---------------------------------------------------------------------------


class HandoffRegistry:
    """Handoff 注册表:管理每个 Agent 的可移交目标。

    线程安全:内部用 threading.Lock 保护 _handoffs,所有读写操作均加锁。

    用法:
        registry = HandoffRegistry()
        registry.register("office-agent", make_handoff("researcher"))
        registry.register("office-agent", make_handoff("writer"))

        targets = registry.list_targets("office-agent")
        # ["researcher", "writer"]

        h = registry.find("office-agent", "researcher")
        # Handoff(target_agent="researcher", ...)
    """

    def __init__(self) -> None:
        self._handoffs: dict[str, list[Handoff]] = {}
        # 保护 _handoffs 的锁;register/unregister/find 等均加锁,避免并发 check-then-act 竞态
        self._lock = threading.Lock()

    def register(self, agent_name: str, handoff: Handoff) -> None:
        """为 agent_name 注册一个 handoff。

        重复注册同 target_agent 会覆盖旧的(以最新为准)。

        Args:
            agent_name: 发起方 Agent 名
            handoff:    Handoff 声明

        Raises:
            TypeError:  agent_name 不是 str 或 handoff 不是 Handoff
            ValueError: agent_name 为空
        """
        if not isinstance(agent_name, str):
            raise TypeError(
                f"agent_name must be str, got {type(agent_name).__name__}"
            )
        if not agent_name.strip():
            raise ValueError("agent_name must not be empty or whitespace-only")
        if not isinstance(handoff, Handoff):
            raise TypeError(
                f"handoff must be Handoff, got {type(handoff).__name__}"
            )
        with self._lock:
            handoffs = self._handoffs.setdefault(agent_name, [])
            # 去重:同 target 替换
            for i, h in enumerate(handoffs):
                if h.target_agent == handoff.target_agent:
                    handoffs[i] = handoff
                    return
            handoffs.append(handoff)

    def unregister(self, agent_name: str, target_agent: str) -> bool:
        """移除指定 handoff,返回是否成功。

        Args:
            agent_name:   发起方 Agent 名
            target_agent: 要移除的目标 Agent 名

        Returns:
            是否成功移除(未找到返回 False)
        """
        with self._lock:
            handoffs = self._handoffs.get(agent_name)
            if not handoffs:
                return False
            for i, h in enumerate(handoffs):
                if h.target_agent == target_agent:
                    handoffs.pop(i)
                    return True
            return False

    def list_targets(self, agent_name: str) -> list[str]:
        """列出 agent_name 可移交的所有目标 Agent 名。

        Args:
            agent_name: 发起方 Agent 名

        Returns:
            目标 Agent 名列表(空列表表示无注册或 agent_name 不存在)
        """
        with self._lock:
            return [h.target_agent for h in self._handoffs.get(agent_name, [])]

    def list_handoffs(self, agent_name: str) -> list[Handoff]:
        """列出 agent_name 的全部 Handoff 声明。

        Args:
            agent_name: 发起方 Agent 名

        Returns:
            Handoff 列表副本(修改返回值不影响注册表内部状态)
        """
        with self._lock:
            return list(self._handoffs.get(agent_name, []))

    def find(
        self,
        agent_name: str,
        target_agent: str,
    ) -> Optional[Handoff]:
        """查找指定 handoff 声明,未找到返回 None。

        Args:
            agent_name:   发起方 Agent 名
            target_agent: 目标 Agent 名

        Returns:
            Handoff 实例或 None
        """
        with self._lock:
            for h in self._handoffs.get(agent_name, []):
                if h.target_agent == target_agent:
                    return h
            return None

    def can_handoff(self, agent_name: str, target_agent: str) -> bool:
        """是否可以从 agent_name 移交到 target_agent。

        Args:
            agent_name:   发起方 Agent 名
            target_agent: 目标 Agent 名

        Returns:
            True 表示存在已注册的 handoff 声明
        """
        return self.find(agent_name, target_agent) is not None


# ---------------------------------------------------------------------------
# 默认 input_filter 实现
# ---------------------------------------------------------------------------


def default_input_filter(history: list[Msg], max_messages: int = 20) -> list[Msg]:
    """默认 input_filter:保留最近 max_messages 条消息。

    用于避免 handoff 时传递全部历史导致上下文膨胀。
    子类可提供自定义 input_filter 实现更精细的过滤(如按角色 / 按工具调用)。

    Args:
        history:      完整消息历史
        max_messages: 保留的最大消息数(必须 >= 1)

    Returns:
        过滤后的消息列表(新对象,不修改入参)

    Raises:
        TypeError:  history 不是 list 或 max_messages 不是 int
        ValueError: max_messages < 1
    """
    if not isinstance(history, list):
        raise TypeError(
            f"history must be list[Msg], got {type(history).__name__}"
        )
    if not isinstance(max_messages, int):
        raise TypeError(
            f"max_messages must be int, got {type(max_messages).__name__}"
        )
    if max_messages < 1:
        raise ValueError(f"max_messages must be >= 1, got {max_messages}")
    if not history:
        return []
    if len(history) <= max_messages:
        return list(history)
    return list(history[-max_messages:])


def filter_by_role(
    history: list[Msg],
    keep_roles: tuple[str, ...] = ("user", "assistant"),
) -> list[Msg]:
    """按角色过滤历史(默认仅保留 user / assistant,丢弃 tool / system)。

    Args:
        history:    完整消息历史
        keep_roles: 要保留的角色元组

    Returns:
        过滤后的消息列表(新对象)

    Raises:
        TypeError: history 不是 list 或 keep_roles 不是 tuple
    """
    if not isinstance(history, list):
        raise TypeError(
            f"history must be list[Msg], got {type(history).__name__}"
        )
    if not isinstance(keep_roles, tuple):
        raise TypeError(
            f"keep_roles must be tuple, got {type(keep_roles).__name__}"
        )
    return [m for m in history if m.role in keep_roles]


# ---------------------------------------------------------------------------
# Runner 集成:AgentRunner._exec_handoff
# ---------------------------------------------------------------------------


class HandoffError(Exception):
    """Handoff 执行错误。"""


def build_handoff_context(
    state: Any,
    handoff: Handoff,
    depth: int,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """从 AgentState 构造 HandoffInput.context。

    Args:
        state:    AgentState(可序列化状态)
        handoff:  Handoff 声明(提供 input_filter)
        depth:    当前 handoff 深度
        extra:    额外上下文(可选,合并到 context)

    Returns:
        context 字典,包含:
          - history:    过滤后的消息历史
          - goal:       当前任务目标
          - trace_id:   追踪 ID
          - session_id: 会话 ID
          - tenant_id:  租户 ID
          - project_id: 项目 ID
          - execution_trace: 执行轨迹摘要(若有)
          - extra:      额外字段

    Raises:
        TypeError: handoff 不是 Handoff 或 depth 不是 int
    """
    # 参数校验(public API 入口)
    if not isinstance(handoff, Handoff):
        raise TypeError(
            f"handoff must be Handoff, got {type(handoff).__name__}"
        )
    if not isinstance(depth, int):
        raise TypeError(f"depth must be int, got {type(depth).__name__}")

    # 获取历史消息
    raw_history = getattr(state, "messages", None) or []
    # 应用 input_filter(若配置)
    if handoff.input_filter is not None:
        try:
            history = list(handoff.input_filter(list(raw_history)))
        except Exception as exc:
            logger.warning(
                "handoff.input_filter failed: %s; falling back to default",
                exc,
            )
            history = default_input_filter(list(raw_history))
    else:
        history = default_input_filter(list(raw_history))

    context: dict[str, Any] = {
        "history": history,
        "goal": getattr(state, "goal", "") or "",
        "trace_id": getattr(state, "trace_id", "") or "",
        "session_id": getattr(state, "session_id", "") or "",
        "tenant_id": getattr(state, "tenant_id", "") or "",
        "project_id": getattr(state, "project_id", "") or "",
        "depth": depth,
    }
    # 执行轨迹摘要(若有)
    exec_trace = getattr(state, "execution_trace", None)
    if exec_trace is not None:
        context["execution_trace"] = exec_trace
    # 合并额外字段
    if extra:
        for k, v in extra.items():
            # 不覆盖已有键
            context.setdefault(k, v)
    return context


def exec_handoff(
    *,
    from_agent: str,
    target_agent: str,
    reason: str,
    registry: HandoffRegistry,
    state: Any,
    depth: int = 0,
    extra_context: Optional[dict[str, Any]] = None,
    agents: Optional[dict[str, Any]] = None,
    tracer: Optional[Any] = None,
) -> tuple[HandoffOutput, Optional[Any]]:
    """执行一次 Handoff(供 AgentRunner._exec_handoff 调用)。

    流程:
      1. 校验 from_agent 可移交到 target_agent(查 registry)
      2. 校验 depth < handoff.max_depth(防死循环)
      3. 构造 HandoffInput(含过滤后的 context)
      4. 调用 handoff.on_handoff(若配置),否则默认接受
      5. 若 accepted,返回 (HandoffOutput, target_agent_instance)
         若 rejected,返回 (HandoffOutput(reject), None)

    Args:
        from_agent:     发起方 Agent 名
        target_agent:   目标 Agent 名
        reason:         移交原因
        registry:       HandoffRegistry
        state:          AgentState(可序列化状态)
        depth:          当前 handoff 深度
        extra_context:  额外上下文字段
        agents:         Agent 注册表(name → Agent 实例),用于查找接收方
        tracer:         Tracer(可选,用于埋点 HandoffSpanData)

    Returns:
        (HandoffOutput, target_agent_instance_or_None)

    Raises:
        HandoffError: 校验失败(未注册 / 深度超限 / 目标 Agent 不存在)
        TypeError:   from_agent / target_agent 不是 str,或 registry 不是 HandoffRegistry
        ValueError:  from_agent / target_agent 为空
    """
    # 参数校验(public API 入口)
    if not isinstance(from_agent, str):
        raise TypeError(
            f"from_agent must be str, got {type(from_agent).__name__}"
        )
    if not from_agent.strip():
        raise ValueError("from_agent must not be empty or whitespace-only")
    if not isinstance(target_agent, str):
        raise TypeError(
            f"target_agent must be str, got {type(target_agent).__name__}"
        )
    if not target_agent.strip():
        raise ValueError("target_agent must not be empty or whitespace-only")
    if not isinstance(registry, HandoffRegistry):
        raise TypeError(
            f"registry must be HandoffRegistry, got {type(registry).__name__}"
        )

    # 1. 查找 handoff 声明
    handoff = registry.find(from_agent, target_agent)
    if handoff is None:
        raise HandoffError(
            f"no handoff declared from '{from_agent}' to '{target_agent}'"
        )

    # 2. 深度校验(防死循环)
    if depth >= handoff.max_depth:
        raise HandoffError(
            f"handoff depth {depth} exceeds max_depth {handoff.max_depth} "
            f"(from '{from_agent}' to '{target_agent}'); possible loop"
        )

    # 3. 构造 HandoffInput
    context = build_handoff_context(
        state=state,
        handoff=handoff,
        depth=depth,
        extra=extra_context,
    )
    handoff_input = HandoffInput(
        from_agent=from_agent,
        to_agent=target_agent,
        reason=reason,
        context=context,
        depth=depth,
    )

    # 4. 埋点 HandoffSpan(可选)
    span_cm = None
    if tracer is not None:
        try:
            from officeagent.core.observability.tracing.span import HandoffSpanData
            span_cm = tracer.start_span(
                "handoff",
                HandoffSpanData(
                    from_agent=from_agent,
                    to_agent=target_agent,
                    reason=reason,
                ),
            )
        except Exception:
            span_cm = None

    # 5. 调用 on_handoff 回调(若有)
    try:
        if span_cm is not None:
            span_cm.__enter__()
        if handoff.on_handoff is not None:
            output = handoff.on_handoff(handoff_input)
        else:
            # 默认接受
            output = HandoffOutput.accept(
                agent=target_agent,
                message=f"handoff accepted by {target_agent}",
            )
    except Exception as exc:
        logger.exception("handoff.on_handoff raised: %s", exc)
        output = HandoffOutput.reject(
            agent=target_agent,
            message=f"on_handoff raised: {type(exc).__name__}: {exc}",
        )
        if span_cm is not None:
            try:
                span_cm.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
        return output, None
    else:
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:
                pass

    # 6. 查找目标 Agent 实例(若 agents 注册表提供)
    target_instance = None
    if output.accepted and agents is not None:
        target_instance = agents.get(target_agent)
        if target_instance is None:
            # 接受但找不到实例 —— 降级为拒绝
            output = HandoffOutput.reject(
                agent=target_agent,
                message=f"target agent '{target_agent}' not found in agents registry",
            )

    return output, target_instance


def apply_handoff_to_state(
    state: Any,
    output: HandoffOutput,
    handoff_input: HandoffInput,
) -> Any:
    """将 HandoffOutput 应用到 AgentState,产出接收方使用的新 state。

    语义:
      - 复制 state(避免修改原 state)
      - 用 output.new_context 覆盖(若提供)
      - 用 handoff_input.context.history 替换 messages
      - 重置 blocked / final_response(接收方重新计算)

    Args:
        state:          原 AgentState
        output:         HandoffOutput
        handoff_input:  HandoffInput(含 context)

    Returns:
        新的 AgentState 副本

    Raises:
        TypeError: output 不是 HandoffOutput 或 handoff_input 不是 HandoffInput
    """
    # 参数校验(public API 入口)
    if not isinstance(output, HandoffOutput):
        raise TypeError(
            f"output must be HandoffOutput, got {type(output).__name__}"
        )
    if not isinstance(handoff_input, HandoffInput):
        raise TypeError(
            f"handoff_input must be HandoffInput, got {type(handoff_input).__name__}"
        )

    try:
        new_state = copy.deepcopy(state)
    except Exception:
        # deepcopy 失败(含不可序列化字段),退化为浅拷贝
        new_state = copy.copy(state)

    # 用 handoff 的 context 覆盖
    ctx = handoff_input.context
    if output.new_context:
        # 接收方修改的上下文优先
        merged = dict(ctx)
        merged.update(output.new_context)
        ctx = merged

    # 替换 messages(已过滤的历史)
    history = ctx.get("history")
    if history is not None:
        try:
            new_state.messages = list(history)
        except AttributeError:
            pass

    # 更新 goal(若 context 中有)
    goal = ctx.get("goal")
    if goal:
        try:
            new_state.goal = goal
        except AttributeError:
            pass

    # 重置接收方需要重新计算的字段
    for attr in ("final_response", "blocked_reason"):
        try:
            setattr(new_state, attr, "")
        except AttributeError:
            pass
    try:
        new_state.blocked = False
    except AttributeError:
        pass

    # 清空执行轨迹(接收方重新生成)
    try:
        new_state.execution_trace = None
    except AttributeError:
        pass

    return new_state


__all__ = [
    "HandoffInput",
    "HandoffOutput",
    "Handoff",
    "HandoffRegistry",
    "HandoffError",
    "make_handoff",
    "default_input_filter",
    "filter_by_role",
    "build_handoff_context",
    "exec_handoff",
    "apply_handoff_to_state",
]
