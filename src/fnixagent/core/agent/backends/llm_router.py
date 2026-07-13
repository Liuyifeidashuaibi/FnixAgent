"""
LLMRouter 适配器 (LLMRouter Adapter)
=====================================
将 core/llm/router.py 的 LLMRouter 适配为 LLMBackend 协议。

适配要点:
  - 同步→异步: LLMRouter.chat 同步, 用 asyncio.to_thread 包装
  - 消息格式: list[dict] → list[Message]
  - 返回类型: LLMResponse → str
  - embed: LLMRouter 无 embed, 需单独注入 BaseEmbedder
  - stream: 构造 stream=True 的 LLMRequest

使用方式:
    from fnixagent.core.llm.router import LLMRouter
    from fnixagent.core.agent.backends.llm_router import LLMRouterAdapter

    router = LLMRouter(...)
    backend = LLMRouterAdapter(router, embedder=some_embedder)
    kernel = AgentKernel(llm_backend=backend)
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from fnixagent.core.agent.types import LLMBackend


class LLMRouterAdapter:
    """LLMRouter → LLMBackend 适配器。

    将 core/llm/router.py 的同步 LLMRouter 适配为 async LLMBackend。

    Args:
        router: LLMRouter 实例
        embedder: BaseEmbedder 实例 (可选, 用于 embed 方法)
        default_model: 默认模型名
        default_temperature: 默认温度
        default_max_tokens: 默认最大 token
    """

    def __init__(
        self,
        router: Any,
        embedder: Any | None = None,
        default_model: str = "",
        default_temperature: float = 0.7,
        default_max_tokens: int = 4096,
    ):
        self._router = router
        self._embedder = embedder
        self._default_model = default_model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    async def complete(self, messages: list[dict[str, Any]],
                       **kwargs: Any) -> str:
        """同步补全, 返回完整文本。"""
        # 构造 LLMRequest (延迟导入避免硬依赖)
        try:
            from fnixagent.core.llm.base import LLMRequest, Message
        except ImportError:
            # 降级: 直接调用 chat (假设 router 接受 dict)
            response = await asyncio.to_thread(
                self._router.chat, messages
            )
            return getattr(response, "content", str(response))

        msg_objects = [Message(**m) if isinstance(m, dict) else m for m in messages]
        request = LLMRequest(
            messages=msg_objects,
            model=kwargs.get("model", self._default_model),
            temperature=kwargs.get("temperature", self._default_temperature),
            max_tokens=kwargs.get("max_tokens", self._default_max_tokens),
            stream=False,
            user_id=kwargs.get("user_id", ""),
            trace_id=kwargs.get("trace_id", ""),
        )
        # 同步→异步
        response = await asyncio.to_thread(self._router.chat, request)
        return getattr(response, "content", str(response))

    async def stream(self, messages: list[dict[str, Any]],
                     **kwargs: Any) -> AsyncIterator[str]:
        """流式补全, 异步迭代返回 token 片段。"""
        try:
            from fnixagent.core.llm.base import LLMRequest, Message
        except ImportError:
            # 降级: 一次性返回
            response = await asyncio.to_thread(self._router.chat, messages)
            content = getattr(response, "content", str(response))
            yield content
            return

        msg_objects = [Message(**m) if isinstance(m, dict) else m for m in messages]
        request = LLMRequest(
            messages=msg_objects,
            model=kwargs.get("model", self._default_model),
            temperature=kwargs.get("temperature", self._default_temperature),
            max_tokens=kwargs.get("max_tokens", self._default_max_tokens),
            stream=True,
            user_id=kwargs.get("user_id", ""),
            trace_id=kwargs.get("trace_id", ""),
        )
        # LLMRouter 的 stream 路径在 chat 内部
        response = await asyncio.to_thread(self._router.chat, request)
        # 若 response 是流式迭代器
        if hasattr(response, "__iter__") and not isinstance(response, str):
            for chunk in response:
                chunk_text = getattr(chunk, "content", str(chunk))
                if chunk_text:
                    yield chunk_text
        else:
            yield getattr(response, "content", str(response))

    async def embed(self, text: str) -> list[float]:
        """文本向量化。"""
        if self._embedder is None:
            raise NotImplementedError(
                "LLMRouterAdapter 需要注入 embedder 才能使用 embed 方法"
            )
        # 假设 embedder 有 embed 方法 (可能是 sync 或 async)
        import inspect
        if inspect.iscoroutinefunction(self._embedder.embed):
            return await self._embedder.embed(text)
        return await asyncio.to_thread(self._embedder.embed, text)

    async def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """统计 token 数 (简单空格分词, 精确计数需注入 tokenizer)。"""
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            # 简单估算: 1 token ≈ 4 字符 (英文) 或 1.5 字符 (中文)
            chinese_count = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
            other_count = len(content) - chinese_count
            total += chinese_count + other_count // 4
        return total


__all__ = ["LLMRouterAdapter"]
