"""Agent 基类。

设计哲学(AgentScope 核心):
  单 Agent 极致健壮 + 多 Agent 平滑扩展
  —— 多 Agent 所需的全部原语,在单 Agent 阶段就内建,避免 P3 返工。

Agent 是比 ReasoningEngine 更高层的抽象:
  - 单 Agent 阶段:由 Runner(P1-4)包装单实例,调用 reply()
  - 多 Agent 阶段:由 Environment(P3-4)驱动多实例,根据 handoff 转交
  - Agent 子类不感知自身是"单 Agent"还是"多 Agent 成员"

生命周期(4 步 ReAct):
  prepare → [think → act] × N → reflect

  - prepare:  加载记忆/工具/技能到 ctx
  - think:    LLM 推理,返回思考消息(含 ToolCallBlock 或 TextBlock)
  - act:      执行工具调用,返回工具结果消息
  - reflect:  汇总结果,返回最终回复

终止条件:
  - think 返回 None:无更多思考,进入 reflect
  - think 返回的消息不含 ToolCallBlock:已是最终答案,直接返回
  - 达到 max_iterations:进入 reflect(可能不完整)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

__version__ = "1.0.0"

from fnixagent.core.messages import Msg


@dataclass
class AgentContext:
    """Agent 运行上下文(每次 reply 创建)。

    设计要点:
      - history: 对话历史(list[Msg]),think/act 可读取
      - max_iterations: ReAct 循环上限,防止无限循环
      - extra: 扩展字段(供子类存放自定义状态)

    P1-4 Runner 会在此 ctx 中注入 usage/tracing 等字段。
    P3 多 Agent 阶段,Environment 通过此 ctx 传递 handoff 信息。

    Attributes:
        goal:           当前任务目标
        user_id:        用户 ID
        session_id:     会话 ID
        trace_id:       追踪 ID
        project_id:     项目 ID
        history:        对话历史(list[Msg])
        max_iterations: ReAct 循环上限(必须 >= 1)
        extra:          扩展字段(供子类存放自定义状态)
    """

    goal: str = ""
    user_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    project_id: str = ""
    history: list[Msg] = field(default_factory=list)
    max_iterations: int = 10
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 校验 max_iterations 范围,防止配置错误导致循环不可执行或无上限
        if not isinstance(self.max_iterations, int):
            raise TypeError(f"max_iterations must be int, got {type(self.max_iterations).__name__}")
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")

    def add_message(self, msg: Msg) -> None:
        """追加消息到历史(便捷方法)。

        Args:
            msg: 要追加的 Msg 实例

        Raises:
            TypeError: msg 不是 Msg 实例
        """
        if not isinstance(msg, Msg):
            raise TypeError(f"msg must be Msg, got {type(msg).__name__}")
        self.history.append(msg)


class Agent(abc.ABC):
    """Agent 基类:4 步 ReAct + 双入口(同步/流式)。

    子类需实现 4 个抽象方法:prepare / think / act / reflect。
    reply() 与 reply_stream() 为模板方法,子类无需重写。

    单 Agent 用法:
        class MyAgent(Agent):
            async def prepare(self, ctx): ...
            async def think(self, ctx): ...
            async def act(self, ctx, thought): ...
            async def reflect(self, ctx, trace): ...

        agent = MyAgent("fnix-agent")
        result = await agent.reply(ctx)

    多 Agent 用法(P3):
        env = Environment(bus, [agent1, agent2, ...])
        env.publish(user_msg)
        final = env.step()
    """

    def __init__(self, name: str, **config: Any) -> None:
        """初始化 Agent。

        Args:
            name:    Agent 名称(多 Agent 阶段作为路由标识,非空字符串)
            **config: Agent 配置(透传给子类)

        Raises:
            TypeError:  name 不是 str
            ValueError: name 为空字符串或仅空白
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name).__name__}")
        if not name.strip():
            raise ValueError("name must not be empty or whitespace-only")
        self._name = name
        self._config = config

    @property
    def name(self) -> str:
        """Agent 名称(多 Agent 阶段作为路由标识)。"""
        return self._name

    @property
    def config(self) -> dict[str, Any]:
        """Agent 配置(只读)。"""
        return dict(self._config)

    # -- 4 个抽象生命周期方法 ------------------------------------------------

    @abc.abstractmethod
    async def prepare(self, ctx: AgentContext) -> AgentContext:
        """准备阶段:加载记忆/工具/技能到 ctx。

        可修改 ctx(如追加 system 消息到 history),返回更新后的 ctx。
        """
        ...

    @abc.abstractmethod
    async def think(self, ctx: AgentContext) -> Msg | None:
        """思考阶段:LLM 推理,返回思考消息。

        返回值:
          - Msg 含 ToolCallBlock:需执行 act
          - Msg 仅含 TextBlock:已是最终答案,reply 会直接返回
          - None:无更多思考,进入 reflect
        """
        ...

    @abc.abstractmethod
    async def act(self, ctx: AgentContext, thought: Msg) -> Msg | None:
        """行动阶段:执行 thought 中的工具调用,返回工具结果消息。

        可返回 None 表示无结果(如工具被取消)。
        """
        ...

    @abc.abstractmethod
    async def reflect(self, ctx: AgentContext, trace: list[Msg]) -> Msg:
        """反思阶段:汇总 trace,返回最终回复。

        即使达到 max_iterations 也会调用此方法(可能产出不完整回复)。
        """
        ...

    # -- 双入口(模板方法,子类无需重写) ------------------------------------

    async def reply(self, ctx: AgentContext) -> Msg:
        """同步入口:4 步 ReAct 循环。

        流程:
          1. prepare(ctx)
          2. 循环 max_iterations 次:
             a. think(ctx) → thought
             b. thought 为 None → break
             c. thought 不含 ToolCallBlock → 直接返回 thought(最终答案)
             d. act(ctx, thought) → result
             e. result 非 None → 追加到 trace 与 history
          3. reflect(ctx, trace) → 最终回复
        """
        ctx = await self.prepare(ctx)
        trace: list[Msg] = []
        for i in range(ctx.max_iterations):
            thought = await self.think(ctx)
            if thought is None:
                break
            trace.append(thought)
            # 不含工具调用 → 已是最终答案
            if not thought.has_tool_call():
                return thought
            result = await self.act(ctx, thought)
            if result is not None:
                trace.append(result)
                ctx.history.append(result)
        return await self.reflect(ctx, trace)

    async def reply_stream(self, ctx: AgentContext) -> AsyncGenerator[Msg, None]:
        """流式入口:逐步 yield 思考与结果消息。

        最后 yield 的一定是 reflect 产出的最终回复。
        """
        ctx = await self.prepare(ctx)
        trace: list[Msg] = []
        for i in range(ctx.max_iterations):
            thought = await self.think(ctx)
            if thought is None:
                break
            yield thought
            trace.append(thought)
            if not thought.has_tool_call():
                return  # thought 已是最终答案,流式结束
            result = await self.act(ctx, thought)
            if result is not None:
                yield result
                trace.append(result)
                ctx.history.append(result)
        final = await self.reflect(ctx, trace)
        yield final
