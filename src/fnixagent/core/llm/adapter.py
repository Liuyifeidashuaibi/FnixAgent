"""
LLM 适配器 — 连接 OpenAI 兼容 API 与 AgenticLoop

提供统一的 chat(messages, tools) 接口，封装 OpenAICompatibleProvider。
从环境变量读取 API Key 和模型配置，无需内置模型。

用法:
    from fnixagent.core.llm.adapter import create_llm_adapter

    adapter = create_llm_adapter()
    response = await adapter.chat(messages, tools=tools)
    # response = {"choices": [{"message": {"content": ..., "tool_calls": [...]}}], "usage": {...}}
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fnixagent.core.exceptions import LLMError
from fnixagent.core.llm.base import LLMRequest
from fnixagent.core.llm.providers.openai import OpenAICompatibleProvider
from fnixagent.core.types import LLMResponse, Message, MessageRole, TokenUsage


# 默认提供商配置 (按优先级检测环境变量)
_PROVIDER_CONFIGS = [
    {
        "name": "openai",
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1/",
        "default_model": "gpt-4o",
    },
    {
        "name": "glm",
        "env_key": "GLM_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_model": "glm-4",
    },
    {
        "name": "qwen",
        "env_key": "QWEN_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/",
        "default_model": "qwen-plus",
    },
    {
        "name": "deepseek",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1/",
        "default_model": "deepseek-chat",
    },
    {
        "name": "custom",
        "env_key": "CUSTOM_API_KEY",
        "base_url": "https://api.openai.com/v1/",
        "default_model": "gpt-4o",
    },
]


class LLMAdapter:
    """
    LLM 适配器 — 连接 OpenAI 兼容 API 与 AgenticLoop。

    自动检测环境变量中的 API Key，选择对应提供商。
    支持自定义 base_url 和 model_name。

    用法:
        adapter = LLMAdapter()
        result = await adapter.chat(messages, tools=tools)
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model_name: str = "",
        provider_name: str = "",
    ):
        """
        Args:
            api_key: API Key (为空时自动检测环境变量)
            base_url: API 基础 URL (为空时使用默认值)
            model_name: 模型名 (为空时使用默认值)
            provider_name: 提供商名 (为空时自动检测)
        """
        self._provider: Optional[OpenAICompatibleProvider] = None
        self._provider_name = provider_name
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model_name
        self._configured = False

    def _auto_detect(self) -> None:
        """自动检测可用的 API 提供商"""
        if self._configured:
            return

        # 优先使用显式传入的配置
        if self._api_key:
            name = self._provider_name or "custom"
            self._provider = OpenAICompatibleProvider(
                name=name,
                model_name=self._model_name or "gpt-4o",
                api_key=self._api_key,
                base_url=self._base_url or "https://api.openai.com/v1/",
            )
            self._configured = True
            return

        # 自动检测环境变量
        for config in _PROVIDER_CONFIGS:
            api_key = os.getenv(config["env_key"], "")
            if api_key:
                self._provider = OpenAICompatibleProvider(
                    name=config["name"],
                    model_name=self._model_name or os.getenv(
                        f"{config['name'].upper()}_MODEL", config["default_model"],
                    ),
                    api_key=api_key,
                    base_url=self._base_url or os.getenv(
                        f"{config['name'].upper()}_BASE_URL", config["base_url"],
                    ),
                )
                self._configured = True
                return

    @property
    def is_configured(self) -> bool:
        """是否已配置 API Key"""
        self._auto_detect()
        return self._provider is not None

    @property
    def provider_name(self) -> str:
        """获取当前使用的提供商名称"""
        self._auto_detect()
        if self._provider:
            return self._provider._name
        return "未配置"

    async def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        """
        AgenticLoop 兼容的 chat 接口。

        Args:
            messages: 消息列表 [{"role": "...", "content": "..."}]
            tools: OpenAI tools API 格式的工具定义列表
            model: 模型名 (为空使用默认)
            temperature: 温度
            max_tokens: 最大 token 数

        Returns:
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "响应文本",
                        "tool_calls": [{"id": "...", "function": {"name": "...", "arguments": "..."}}]
                    }
                }],
                "usage": {"total_tokens": N, "prompt_tokens": N, "completion_tokens": N}
            }
        """
        self._auto_detect()
        if self._provider is None:
            raise LLMError(
                "未配置 LLM API Key。请在 .env 文件中设置以下任一环境变量:\n"
                "  OPENAI_API_KEY=sk-xxx\n"
                "  GLM_API_KEY=xxx\n"
                "  QWEN_API_KEY=xxx\n"
                "  DEEPSEEK_API_KEY=xxx\n"
                "  CUSTOM_API_KEY=xxx (需同时设置 CUSTOM_BASE_URL)"
            )

        # 将 raw dict 消息转换为 Message 对象
        msg_objects = [
            Message(
                role=MessageRole(m.get("role", "user")),
                content=str(m.get("content", "")),
                name=m.get("name"),
            )
            for m in messages
        ]

        # 构建 LLMRequest
        request = LLMRequest(
            model=model or self._model_name or "",
            messages=msg_objects,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
        )

        # 调用提供商 (同步，但 AgenticLoop 会 await)
        response: LLMResponse = self._provider.chat(request)

        # 转换为 AgenticLoop 期望的格式
        result: dict[str, Any] = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response.content,
                }
            }],
            "usage": {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
        }

        # 添加 tool_calls
        if response.tool_calls:
            result["choices"][0]["message"]["tool_calls"] = [
                {
                    "id": tc.get("id", f"call_{i}"),
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", "{}"),
                    },
                }
                for i, tc in enumerate(response.tool_calls)
            ]

        return result


def create_llm_adapter(
    api_key: str = "",
    base_url: str = "",
    model_name: str = "",
) -> LLMAdapter:
    """便捷创建 LLMAdapter。

    自动检测环境变量，也可显式传入 API Key。

    Args:
        api_key: API Key (为空则从环境变量检测)
        base_url: 自定义 API 地址
        model_name: 自定义模型名

    Returns:
        LLMAdapter 实例
    """
    return LLMAdapter(
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
    )


__all__ = ["LLMAdapter", "create_llm_adapter"]