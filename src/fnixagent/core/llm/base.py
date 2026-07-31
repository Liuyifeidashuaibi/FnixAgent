"""
LLM 基础服务层 · 统一抽象接口。

所有闭源(GLM/OpenAI/Claude)与开源(Qwen/Llama3+vLLM) provider 均实现同一抽象,
上层 Router/Cache/Billing 只依赖 BaseLLMProvider,不感知具体厂商差异。
"""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.text import estimate_tokens
from fnixagent.core.types import LLMResponse, Message, MessageRole, TokenUsage

# ---------------------------------------------------------------------------
# 请求结构
# ---------------------------------------------------------------------------


@dataclass
class LLMRequest:
    """一次 LLM 调用请求(模型无关)。

    P2-8 新增字段:
      - think_mode: 是否启用思考模式(GLM-4.5 / DeepSeek-R1)
      - cost_preference: 成本偏好(cheap/quality/auto,影响 Router 选 provider)
    """

    messages: list[Message]  # 完整对话历史
    model: str = ""  # 指定模型;空串表示走 Router 默认
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False
    tools: list[dict] = field(default_factory=list)  # function-calling 工具描述
    tool_choice: str = "auto"  # auto / none / required
    stop: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)  # provider 专属参数透传
    user_id: str = ""  # 用于计费/限流隔离
    trace_id: str = ""  # 全链路追踪
    # -- P2-8: 思考/非思考模式 ----------------------------------------------
    think_mode: bool = False  # 是否启用思考模式
    cost_preference: str = "auto"  # cheap / quality / auto(影响 Router 路由)


# ---------------------------------------------------------------------------
# Provider 抽象基类
# ---------------------------------------------------------------------------


class BaseLLMProvider(abc.ABC):
    """
    LLM Provider 统一抽象。

    子类只需实现 _do_chat (同步) 和 _do_stream (流式),
    框架层自动处理消息预处理、token 估算、异常包装。
    """

    def __init__(self, name: str, model_name: str):
        self._name = name
        self._model_name = model_name

    @property
    def name(self) -> str:
        """provider 标识名,如 'glm' / 'openai' / 'qwen'。"""
        return self._name

    @property
    def model_name(self) -> str:
        """默认模型名。"""
        return self._model_name

    # -- 公开入口 ----------------------------------------------------------

    def chat(self, request: LLMRequest) -> LLMResponse:
        """同步对话入口。

        框架层在此做消息预处理与 token 估算,然后委托 _do_chat。
        子类抛出的任意异常被统一包装为 LLMError,保留原始异常链。

        Args:
            request: LLM 调用请求(模型无关)。

        Returns:
            LLMResponse: provider 返回的响应,usage 缺失时由框架粗估回填。

        Raises:
            LLMError: provider 调用失败时包装抛出。
        """
        if not isinstance(request, LLMRequest):
            raise TypeError(f"request must be LLMRequest, got {type(request).__name__}")
        messages = self._prepare_messages(request)
        try:
            response = self._do_chat(request, messages)
        except Exception as exc:
            # 注:asyncio.CancelledError 在 Py3.8+ 继承自 BaseException,不会被此处捕获
            from fnixagent.core.exceptions import LLMError

            raise LLMError(f"[{self._name}] chat failed: {exc}") from exc
        response.model = response.model or self._model_name
        # 若 provider 未回填 usage,做粗估
        if response.usage.total_tokens == 0:
            response.usage = self._estimate_usage(messages, response.content)
        return response

    async def stream_chat(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式对话入口,逐 chunk 产出文本。

        子类实现 _do_stream 返回 AsyncGenerator;默认实现回退到同步 chat
        整段返回。异常被统一包装为 LLMError。

        Args:
            request: LLM 调用请求(模型无关)。

        Yields:
            str: 模型生成的文本片段。

        Raises:
            LLMError: provider 流式调用失败时包装抛出。
        """
        if not isinstance(request, LLMRequest):
            raise TypeError(f"request must be LLMRequest, got {type(request).__name__}")
        messages = self._prepare_messages(request)
        try:
            async for chunk in self._do_stream(request, messages):
                yield chunk
        except Exception as exc:
            # 注:asyncio.CancelledError 在 Py3.8+ 继承自 BaseException,不会被此处捕获,
            # 流式取消可正常向上传播,不会被吞掉
            from fnixagent.core.exceptions import LLMError

            raise LLMError(f"[{self._name}] stream failed: {exc}") from exc

    # -- 子类实现 ----------------------------------------------------------

    @abc.abstractmethod
    def _do_chat(self, request: LLMRequest, messages: list[dict]) -> LLMResponse:
        """子类实现:实际调用 LLM API 并返回 LLMResponse。"""
        ...

    async def _do_stream(
        self, request: LLMRequest, messages: list[dict]
    ) -> AsyncGenerator[str, None]:
        """子类实现:流式调用。默认回退到同步 chat 整段返回（线程池，避免堵事件循环）。"""
        import asyncio

        resp = await asyncio.to_thread(self._do_chat, request, messages)
        yield resp.content

    # -- 框架工具方法 -------------------------------------------------------

    def _prepare_messages(self, request: LLMRequest) -> list[dict]:
        """将 Message 列表转为 provider 通用 dict 列表。"""
        return [m.to_llm_dict() for m in request.messages]

    def _estimate_usage(self, messages: list[dict], output_text: str) -> TokenUsage:
        """无精确 tokenizer 时的 token 粗估(精确值由 provider 回填)。"""
        prompt_tokens = 0
        for m in messages:
            prompt_tokens += estimate_tokens(str(m.get("content", ""))) + 4
        completion_tokens = estimate_tokens(output_text)
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self._name} model={self._model_name}>"


# ---------------------------------------------------------------------------
# 消息预处理工具
# ---------------------------------------------------------------------------


def ensure_system_role(messages: list[Message], system_text: str) -> list[Message]:
    """确保消息列表首条是 system 角色;若无则插入。

    Args:
        messages: 原始消息列表(可为空)。
        system_text: 缺失 system 消息时插入的 system 文本。

    Returns:
        list[Message]: 处理后的消息列表(原列表未修改)。

    Raises:
        TypeError: messages 不是 list 或 system_text 不是 str。
    """
    if not isinstance(messages, list):
        raise TypeError(f"messages must be list, got {type(messages).__name__}")
    if not isinstance(system_text, str):
        raise TypeError(f"system_text must be str, got {type(system_text).__name__}")
    if messages and messages[0].role == MessageRole.SYSTEM:
        return messages
    return [Message(role=MessageRole.SYSTEM, content=system_text)] + messages


def truncate_messages(messages: list[Message], max_total_tokens: int) -> list[Message]:
    """当对话历史超出 token 预算时,从最早的非 system 消息开始裁剪。

    保留 system 消息 + 最近若干轮对话,使总 token 数不超过预算。

    Args:
        messages: 原始消息列表(可为空)。
        max_total_tokens: 允许的最大 token 总数,必须为正整数。

    Returns:
        list[Message]: 裁剪后的消息列表(原列表未修改)。

    Raises:
        TypeError: messages 不是 list 或 max_total_tokens 不是 int。
        ValueError: max_total_tokens 非正数。
    """
    if not isinstance(messages, list):
        raise TypeError(f"messages must be list, got {type(messages).__name__}")
    if not isinstance(max_total_tokens, int) or isinstance(max_total_tokens, bool):
        raise TypeError(f"max_total_tokens must be int, got {type(max_total_tokens).__name__}")
    if max_total_tokens <= 0:
        raise ValueError(f"max_total_tokens must be positive, got {max_total_tokens}")
    if not messages:
        return messages
    total = sum(estimate_tokens(m.content) + 4 for m in messages)
    if total <= max_total_tokens:
        return messages
    system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM]
    non_system = [m for m in messages if m.role != MessageRole.SYSTEM]
    while non_system and total > max_total_tokens:
        removed = non_system.pop(0)
        total -= estimate_tokens(removed.content) + 4
    return system_msgs + non_system
