"""推理引擎抽象基类。

定义所有推理模式(ReAct/Plan&Execute/Self-Reflect)的统一接口:
  - reason(): 输入任务目标 → 输出执行轨迹(ThoughtStep/PlanStep 列表 + 工具调用记录)

ReasoningContext 封装推理所需的全部依赖:
  - LLM 调用入口
  - 工具注册表 + 执行器
  - 消息历史
  - 最大迭代次数

设计: 策略模式,各模式为独立策略,selector 选择策略。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.exceptions import (
    LLMError,
    MaxIterationsExceededError,
    ReasoningError,
)
from fnixagent.core.llm.router import LLMRouter
from fnixagent.core.tools.executor import ToolExecutor
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.types import (
    ExecutionTrace,
    Message,
    ReasoningMode,
    ToolCall,
    ToolResult,
)


@dataclass
class ReasoningContext:
    """推理运行时上下文。

    P1-5 新增字段:usage / usage_limits / billing_meter(用于 Token/Cost 归因)。

    不变性约定:
      - history 在推理期间视为只读(共享上下文),引擎应通过 scratchpad/trace
        维护中间状态,而非回写 ctx.history
      - max_iterations 在构造时校验,运行期不允许引擎修改原 ctx
        (Fast/Cheap/Precise 等策略应通过 _build_reasoning_context 复制)
    """

    goal: str  # 用户目标
    llm: LLMRouter  # LLM 调用入口
    tool_registry: ToolRegistry  # 工具注册表
    tool_executor: ToolExecutor  # 工具执行器
    history: list[Message] = field(default_factory=list)  # 对话历史
    max_iterations: int = 10  # 最大推理循环次数
    user_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    # -- P1-5: Token/Cost 归因 ---------------------------------------------
    usage: Any | None = None  # Usage(累积用量)
    usage_limits: Any | None = None  # UsageLimits(限额,超限抛异常)
    billing_meter: Any = None  # BillingMeter(计费器,可选)

    def __post_init__(self) -> None:
        """构造期参数校验,避免运行期才暴露配置错误。"""
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("ReasoningContext.goal 不能为空字符串")
        if self.llm is None:
            raise ValueError("ReasoningContext.llm 不能为 None")
        if self.tool_registry is None:
            raise ValueError("ReasoningContext.tool_registry 不能为 None")
        if self.tool_executor is None:
            raise ValueError("ReasoningContext.tool_executor 不能为 None")
        # max_iterations 必须为正整数,否则循环边界异常
        if not isinstance(self.max_iterations, int) or self.max_iterations <= 0:
            raise ValueError(
                f"ReasoningContext.max_iterations 必须为正整数,实际: {self.max_iterations!r}"
            )


class ReasoningEngine(abc.ABC):
    """
    推理引擎抽象基类。

    子类实现 reason() 方法,返回 ExecutionTrace。
    """

    @property
    @abc.abstractmethod
    def mode(self) -> ReasoningMode:
        """推理模式标识。"""
        ...

    @abc.abstractmethod
    def reason(self, ctx: ReasoningContext) -> ExecutionTrace:
        """
        执行推理流程。
        输入: ReasoningContext(目标 + LLM + 工具 + 历史)
        输出: ExecutionTrace(完整执行轨迹)
        """
        ...

    # -- 工具方法 ----------------------------------------------------------

    def _make_trace(self, ctx: ReasoningContext) -> ExecutionTrace:
        """初始化执行轨迹。"""
        return ExecutionTrace(
            task_id=ctx.session_id,
            trace_id=ctx.trace_id,
            mode=self.mode,
        )

    def _call_llm(self, ctx: ReasoningContext, messages: list[Message]) -> str:
        """调用 LLM 并返回文本内容。

        异常处理:
          - LLMError / MaxIterationsExceededError / ReasoningError 透传给上层
          - 其他非预期异常包装为 ReasoningError,避免引擎内部裸露 Exception
        """
        from fnixagent.core.llm.base import LLMRequest

        if not messages:
            raise ReasoningError("LLM 调用失败: messages 为空")
        request = LLMRequest(
            messages=messages,
            user_id=ctx.user_id,
            trace_id=ctx.trace_id,
        )
        try:
            response = ctx.llm.chat(request)
        except (LLMError, ReasoningError):
            # 已知内核异常,直接透传,避免重复包装破坏异常类型
            raise
        except Exception as exc:
            # 兜底:把 provider 抛出的杂项异常归一为 ReasoningError
            raise ReasoningError(f"LLM 调用非预期失败: {exc.__class__.__name__}: {exc}") from exc
        if response is None or not getattr(response, "content", None):
            raise ReasoningError("LLM 返回空内容,无法继续推理")
        return response.content

    def _execute_tool(self, ctx: ReasoningContext, call: ToolCall) -> ToolResult:
        """执行工具调用。

        工具调用参数消毒:
          - 仅允许 JSON 可序列化的 dict 作为 arguments
          - 拒绝包含 __ 开头属性(防 __import__ 等反射滥用)
        """
        self._sanitize_tool_arguments(call.arguments)
        return ctx.tool_executor.execute(call)

    def _check_iterations(self, current: int, max_iter: int) -> None:
        """检查是否超过最大迭代次数。

        强制执行 max_iterations 上限,防止 LLM 进入无限循环。
        current 为已完成迭代数(0-based 转为 1-based 比较)。
        """
        if max_iter <= 0:
            raise MaxIterationsExceededError(f"max_iterations 配置非法: {max_iter}")
        if current >= max_iter:
            raise MaxIterationsExceededError(f"超过最大推理迭代次数: {max_iter}")

    # -- 安全:工具参数消毒 -------------------------------------------------

    @staticmethod
    def _sanitize_tool_arguments(arguments: Any) -> None:
        """消毒工具调用参数,阻止反射型注入。

        - 必须为 dict
        - key 不能以 __ 开头(防止 __import__/__class__ 等魔术属性)
        - 不允许包含可执行字符串逃逸(callable/eval 字符等不做执行,只校验结构)
        """
        if arguments is None:
            return
        if not isinstance(arguments, dict):
            raise ReasoningError(f"工具参数必须为 dict,实际类型: {type(arguments).__name__}")
        for key in arguments.keys():
            if not isinstance(key, str):
                raise ReasoningError(f"工具参数 key 必须为字符串,实际: {type(key).__name__}")
            if key.startswith("__"):
                raise ReasoningError(f"工具参数 key 不允许以 __ 开头(拒绝反射注入): {key!r}")


# 向后兼容别名:部分调用方/文档使用 BaseReasoningEngine 命名
# (与"推理引擎抽象基类"语义一致,保留以兼容现有 import)
BaseReasoningEngine = ReasoningEngine
