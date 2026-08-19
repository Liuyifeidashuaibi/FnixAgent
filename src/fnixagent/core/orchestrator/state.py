"""
上下文拆分(可持久化 vs 引擎引用)—— A-5。

将原 OrchestratorContext(core/orchestrator/context.py)拆为两部分:
  - AgentState:  可序列化、可跨 Agent 传递、可 Checkpoint 持久化的纯数据状态
  - EngineRefs:  不可序列化的引擎引用(LLMRouter/MemoryManager/ToolRegistry 等),
                  不参与 handoff/checkpoint,仅在同进程内传递

新的 OrchestratorContext = AgentState + EngineRefs(组合)。

设计动机:
  - handoff 时只传递 AgentState,避免引擎引用被序列化/跨网络传输
  - Checkpoint 时只持久化 AgentState,EngineRefs 在恢复时由 Runner 重新注入
  - 多 Agent 协作时,每个 Agent 收到的是同一份 EngineRefs + 各自的 AgentState 副本

向后兼容:
  - 原 core/orchestrator/context.py 的 OrchestratorContext 仍保留,供现有 lifecycle.py 使用
  - P1-4 Runner 将切换到本模块的新 OrchestratorContext
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 可持久化的 Agent 状态
# ---------------------------------------------------------------------------


@dataclass
class AgentState:
    """可持久化的 Agent 状态(可序列化、可跨 Agent 传递)。

    所有字段均为纯数据(无引擎引用),可安全:
      - pickle / json 序列化
      - 跨 Agent handoff
      - 写入 Checkpoint(BaseCheckpointer)
      - 跨网络传输(多 Agent 分布式协作)

    字段说明:
      - goal:                当前任务目标(L1 候选)
      - messages:            对话历史(list[Msg] 或 list[dict],建议用 Msg)
      - reasoning_mode:      选定的推理模式(react/cot/plan_execute/...)
      - execution_trace:     执行轨迹(飞轮 ① 产出,飞轮 ② 消费)
      - final_response:      最终回复
      - blocked / blocked_reason: 安全拦截标记
      - user_id / session_id / tenant_id / trace_id / project_id: 请求标识
      - short_term_history:  短期记忆(可序列化部分)
      - long_term_memories:  长期记忆检索结果
      - user_profile:        用户画像
    """

    # 任务与对话
    goal: str = ""
    messages: list = field(default_factory=list)  # list[Msg]
    reasoning_mode: str = ""
    execution_trace: dict | None = None
    final_response: str = ""

    # 安全拦截
    blocked: bool = False
    blocked_reason: str = ""

    # 请求标识(用于多租户/审计/追踪)
    user_id: str = ""
    session_id: str = ""
    tenant_id: str = ""
    trace_id: str = ""
    project_id: str = ""

    # 记忆上下文(仅可序列化部分)
    short_term_history: list = field(default_factory=list)
    long_term_memories: list = field(default_factory=list)
    user_profile: dict | None = None

    def to_dict(self) -> dict:
        """转为字典(用于日志/调试/序列化)。

        引擎引用不在其中,可安全序列化。
        """
        return {
            "goal": self.goal[:100],
            "reasoning_mode": self.reasoning_mode,
            "final_response": self.final_response[:100],
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id,
            "project_id": self.project_id,
            "messages_count": len(self.messages),
            "short_term_count": len(self.short_term_history),
            "long_term_count": len(self.long_term_memories),
            "has_user_profile": self.user_profile is not None,
            "has_execution_trace": self.execution_trace is not None,
        }

    def to_serializable(self) -> dict:
        """转为可 pickle 序列化的纯数据字典(用于 Checkpoint 持久化)。

        与 to_dict 的区别:to_serializable 保留全部字段完整内容,
        便于恢复时重建 AgentState;to_dict 仅保留摘要用于日志。
        """
        return {
            "goal": self.goal,
            "messages": list(self.messages),
            "reasoning_mode": self.reasoning_mode,
            "execution_trace": self.execution_trace,
            "final_response": self.final_response,
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "trace_id": self.trace_id,
            "project_id": self.project_id,
            "short_term_history": list(self.short_term_history),
            "long_term_memories": list(self.long_term_memories),
            "user_profile": self.user_profile,
        }

    @classmethod
    def from_serializable(cls, data: dict) -> AgentState:
        """从 to_serializable 产出的字典重建 AgentState。

        Args:
            data: to_serializable 产出的字典(允许缺失部分字段,用默认值填充)

        Returns:
            重建的 AgentState 实例

        Raises:
            TypeError: data 不是 dict
        """
        if not isinstance(data, dict):
            raise TypeError(f"data must be dict, got {type(data).__name__}")
        return cls(
            goal=data.get("goal", ""),
            messages=list(data.get("messages", [])),
            reasoning_mode=data.get("reasoning_mode", ""),
            execution_trace=data.get("execution_trace"),
            final_response=data.get("final_response", ""),
            blocked=data.get("blocked", False),
            blocked_reason=data.get("blocked_reason", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            tenant_id=data.get("tenant_id", ""),
            trace_id=data.get("trace_id", ""),
            project_id=data.get("project_id", ""),
            short_term_history=list(data.get("short_term_history", [])),
            long_term_memories=list(data.get("long_term_memories", [])),
            user_profile=data.get("user_profile"),
        )


# ---------------------------------------------------------------------------
# 不可序列化的引擎引用
# ---------------------------------------------------------------------------


@dataclass
class EngineRefs:
    """不可序列化的引擎引用(不参与 handoff/checkpoint)。

    所有引擎实例在此聚合,Runner 在恢复 Checkpoint 时重新注入本对象。
    字段类型用 Any 而非具体类型,避免循环 import:
      - llm_router:          LLMRouter
      - memory_manager:      MemoryManager
      - tool_registry:       ToolRegistry
      - tool_executor:       ToolExecutor
      - security_engine:     SecurityEngine
      - prompt_manager:      PromptManager
      - reasoning_selector:  ReasoningSelector
      - validator:           ResultValidator
      - replanner:           Replanner
      - config:              CoreConfig

    注意:本对象不可 pickle(含线程池/连接池等不可序列化资源)。
    """

    llm_router: Any = None
    memory_manager: Any = None
    tool_registry: Any = None
    tool_executor: Any = None
    security_engine: Any = None
    prompt_manager: Any = None
    reasoning_selector: Any = None
    validator: Any = None
    replanner: Any = None
    config: Any = None

    @property
    def has_security_engine(self) -> bool:
        """是否注入了安全引擎。"""
        return self.security_engine is not None

    def to_dict(self) -> dict:
        """转为字典(仅含可用性标记,不含引擎实例本身)。"""
        return {
            "has_llm_router": self.llm_router is not None,
            "has_memory_manager": self.memory_manager is not None,
            "has_tool_registry": self.tool_registry is not None,
            "has_tool_executor": self.tool_executor is not None,
            "has_security_engine": self.security_engine is not None,
            "has_prompt_manager": self.prompt_manager is not None,
            "has_reasoning_selector": self.reasoning_selector is not None,
            "has_validator": self.validator is not None,
            "has_replanner": self.replanner is not None,
            "has_config": self.config is not None,
        }


# ---------------------------------------------------------------------------
# 组合上下文 = AgentState + EngineRefs
# ---------------------------------------------------------------------------


@dataclass
class OrchestratorContext:
    """拆分后的上下文 = AgentState + EngineRefs。

    与 core/orchestrator/context.py 的 OrchestratorContext 区别:
      - 本类将"可序列化状态"与"引擎引用"显式分离
      - handoff 时只传递 self.state
      - Checkpoint 时只持久化 self.state
      - self.engines 由 Runner 在恢复时重新注入

    用法:
        ctx = OrchestratorContext(state=AgentState(...), engines=EngineRefs(...))
        # handoff:
        handoff_state = ctx.state
        # 持久化:
        checkpointer.put(thread_id, ctx.state.to_serializable())
    """

    state: AgentState = field(default_factory=AgentState)
    engines: EngineRefs | None = None

    # -- 便捷访问代理(向后兼容旧 ctx.xxx 写法)-------------------------------
    @property
    def goal(self) -> str:
        return self.state.goal

    @goal.setter
    def goal(self, value: str) -> None:
        self.state.goal = value

    @property
    def messages(self) -> list:
        return self.state.messages

    @messages.setter
    def messages(self, value: list) -> None:
        self.state.messages = value

    @property
    def user_id(self) -> str:
        return self.state.user_id

    @user_id.setter
    def user_id(self, value: str) -> None:
        self.state.user_id = value

    @property
    def session_id(self) -> str:
        return self.state.session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self.state.session_id = value

    @property
    def trace_id(self) -> str:
        return self.state.trace_id

    @trace_id.setter
    def trace_id(self, value: str) -> None:
        self.state.trace_id = value

    @property
    def tenant_id(self) -> str:
        return self.state.tenant_id

    @tenant_id.setter
    def tenant_id(self, value: str) -> None:
        self.state.tenant_id = value

    # -- 引擎便捷访问 -------------------------------------------------------
    @property
    def llm_router(self) -> Any:
        return self.engines.llm_router if self.engines else None

    @property
    def memory_manager(self) -> Any:
        return self.engines.memory_manager if self.engines else None

    @property
    def tool_registry(self) -> Any:
        return self.engines.tool_registry if self.engines else None

    @property
    def tool_executor(self) -> Any:
        return self.engines.tool_executor if self.engines else None

    @property
    def security_engine(self) -> Any:
        return self.engines.security_engine if self.engines else None

    @property
    def has_security_engine(self) -> bool:
        return self.engines is not None and self.engines.has_security_engine

    def to_dict(self) -> dict:
        """合并状态与引擎可用性,用于日志/调试。"""
        result = {"state": self.state.to_dict()}
        if self.engines:
            result["engines"] = self.engines.to_dict()
        else:
            result["engines"] = None
        return result

    @classmethod
    def from_legacy(
        cls,
        legacy_ctx: Any,
    ) -> OrchestratorContext:
        """从旧版 OrchestratorContext(core/orchestrator/context.py)转换。

        用于 P1-4 Runner 兼容现有 lifecycle.py 创建的旧上下文。

        Args:
            legacy_ctx: 旧版 OrchestratorContext 实例(必须支持 getattr 取字段)

        Returns:
            新版 OrchestratorContext(state + engines 已填充)

        Raises:
            TypeError: legacy_ctx 为 None
        """
        if legacy_ctx is None:
            raise TypeError("legacy_ctx must not be None")
        state = AgentState(
            goal=getattr(legacy_ctx, "current_goal", ""),
            messages=list(getattr(legacy_ctx, "messages", [])),
            reasoning_mode=(
                getattr(legacy_ctx, "reasoning_mode", "").value
                if getattr(legacy_ctx, "reasoning_mode", None) is not None
                and hasattr(getattr(legacy_ctx, "reasoning_mode", ""), "value")
                else getattr(legacy_ctx, "reasoning_mode", "") or ""
            ),
            execution_trace=getattr(legacy_ctx, "execution_trace", None),
            final_response=getattr(legacy_ctx, "final_response", ""),
            blocked=getattr(legacy_ctx, "blocked", False),
            blocked_reason=getattr(legacy_ctx, "blocked_reason", ""),
            user_id=getattr(legacy_ctx, "user_id", ""),
            session_id=getattr(legacy_ctx, "session_id", ""),
            tenant_id=getattr(legacy_ctx, "tenant_id", "default"),
            trace_id=getattr(legacy_ctx, "trace_id", ""),
            project_id=getattr(legacy_ctx, "project_id", ""),
            short_term_history=list(getattr(legacy_ctx, "short_term_history", [])),
            long_term_memories=list(getattr(legacy_ctx, "long_term_memories", [])),
            user_profile=getattr(legacy_ctx, "user_profile", None),
        )
        engines = EngineRefs(
            llm_router=getattr(legacy_ctx, "llm_router", None),
            memory_manager=getattr(legacy_ctx, "memory_manager", None),
            tool_registry=getattr(legacy_ctx, "tool_registry", None),
            tool_executor=getattr(legacy_ctx, "tool_executor", None),
            security_engine=getattr(legacy_ctx, "security_engine", None),
            prompt_manager=getattr(legacy_ctx, "prompt_manager", None),
            reasoning_selector=getattr(legacy_ctx, "reasoning_selector", None),
            validator=getattr(legacy_ctx, "validator", None),
            replanner=getattr(legacy_ctx, "replanner", None),
            config=getattr(legacy_ctx, "config", None),
        )
        return cls(state=state, engines=engines)
