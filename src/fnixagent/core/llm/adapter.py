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

import asyncio
import os
from typing import Any

from fnixagent.core.exceptions import LLMError
from fnixagent.core.llm.base import LLMRequest
from fnixagent.core.llm.providers.openai import OpenAICompatibleProvider
from fnixagent.core.types import LLMResponse, Message, MessageRole

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
        "alt_env_keys": ["DASHSCOPE_API_KEY"],
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
        self._provider: OpenAICompatibleProvider | None = None
        self._provider_name = provider_name
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model_name
        self._configured = False

    def _auto_detect(self) -> None:
        """自动检测可用的 API 提供商"""
        if self._configured:
            return

        # 优先 ~/.fnix（Desktop / CLI / Dashboard 共享 BYOK）
        from fnixagent.harness.config import read_config_toml
        from fnixagent.harness.secrets import get_llm_api_key

        harness_cfg = read_config_toml()
        harness_key = get_llm_api_key()
        if harness_key and not self._api_key:
            self._api_key = harness_key
        if not self._provider_name and harness_cfg.get("provider"):
            self._provider_name = str(harness_cfg.get("provider") or "")
        if not self._model_name and harness_cfg.get("model"):
            self._model_name = str(harness_cfg.get("model") or "")
        if not self._base_url and harness_cfg.get("base_url"):
            self._base_url = str(harness_cfg.get("base_url") or "")

        # 优先使用显式 / harness 配置
        if self._api_key:
            name = (self._provider_name or "custom").lower()
            defaults = {
                "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1/", "qwen-plus"),
                "openai": ("https://api.openai.com/v1/", "gpt-4o"),
                "deepseek": ("https://api.deepseek.com/v1/", "deepseek-chat"),
                "glm": ("https://open.bigmodel.cn/api/paas/v4/", "glm-4"),
            }
            def_base, def_model = defaults.get(name, ("https://api.openai.com/v1/", "gpt-4o"))
            base = self._base_url or def_base
            if base and not base.endswith("/"):
                base = base + "/"
            self._provider = OpenAICompatibleProvider(
                name=name,
                model_name=self._model_name or def_model,
                api_key=self._api_key,
                base_url=base,
            )
            self._configured = True
            return

        # 自动检测环境变量
        for config in _PROVIDER_CONFIGS:
            api_key = os.getenv(config["env_key"], "")
            if not api_key:
                for alt in config.get("alt_env_keys") or []:
                    api_key = os.getenv(alt, "")
                    if api_key:
                        break
            if api_key:
                env_prefix = config["name"].upper()
                model = (
                    self._model_name
                    or os.getenv(f"{env_prefix}_MODEL")
                    or os.getenv("LLM_MODEL")
                    or config["default_model"]
                )
                base = (
                    self._base_url
                    or os.getenv(f"{env_prefix}_BASE_URL")
                    or (os.getenv("DASHSCOPE_BASE_URL") if config["name"] == "qwen" else "")
                    or config["base_url"]
                )
                if base and not base.endswith("/"):
                    base = base + "/"
                self._provider = OpenAICompatibleProvider(
                    name=config["name"],
                    model_name=model,
                    api_key=api_key,
                    base_url=base,
                )
                self._configured = True
                return

        # 显式 LLM_PROVIDER=qwen + DASHSCOPE 兜底
        provider_pref = (os.getenv("LLM_PROVIDER") or "").strip().lower()
        if provider_pref in ("qwen", "dashscope"):
            api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
            if api_key:
                model = (
                    self._model_name
                    or os.getenv("QWEN_MODEL")
                    or os.getenv("LLM_MODEL")
                    or "qwen-plus"
                )
                base = (
                    self._base_url
                    or os.getenv("QWEN_BASE_URL")
                    or os.getenv("DASHSCOPE_BASE_URL")
                    or "https://dashscope.aliyuncs.com/compatible-mode/v1/"
                )
                if not base.endswith("/"):
                    base = base + "/"
                self._provider = OpenAICompatibleProvider(
                    name="qwen",
                    model_name=model,
                    api_key=api_key,
                    base_url=base,
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
        tools: list[dict] | None = None,
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
        # Spec 2: 自动注入 enable_thinking=true，触发 reasoning model 思考模式
        # — DashScope OpenAI 兼容模式下，支持的模型返回 message.reasoning_content
        # — 检测规则保守：仅对 Qwen3 系列 / qwen-plus-latest / qwen-turbo-latest /
        #   qwen3-max-preview / QwQ / DeepSeek-R1 / DeepSeek-V3.1+ / GLM-4.5+ 注入
        # — 不支持的模型忽略此参数（DashScope 会拒绝未知参数，所以必须严格筛选）
        model_name = (model or self._model_name or "").lower()
        enable_thinking_models = (
            "qwen3-",
            "qwq",
            "qwen-plus-latest",
            "qwen-turbo-latest",
            "qwen3-max",
            "qwen-plus-2025",
            "qwen-turbo-2025",
            "deepseek-r1",
            "deepseek-v3.1",
            "deepseek-v3.2",
            "glm-4.5",
            "glm-4.6",
            "glm-5",
        )
        should_enable_thinking = any(m in model_name for m in enable_thinking_models)

        extra_params: dict[str, Any] = {}
        if should_enable_thinking:
            extra_params["enable_thinking"] = True

        request = LLMRequest(
            model=model or self._model_name or "",
            messages=msg_objects,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
            extra=extra_params,
        )

        # Sync httpx providers block the event loop if awaited directly —
        # always offload so /health and other requests stay responsive.
        provider = self._provider
        response: LLMResponse = await asyncio.to_thread(provider.chat, request)

        # 转换为 AgenticLoop 期望的格式
        result: dict[str, Any] = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": response.content,
                        # Spec 2: 透传 reasoning model 的思考链 (Qwen3 reasoning_content /
                        # o1 reasoning / DeepSeek-R1 reasoning_content / GLM-4.5 thinking)
                        # AgenticLoop.run_stream 会把 reasoning_content 作为 thought chunk 单独
                        # 流出，让前端 ProcessTimeline 折叠展示模型"在想什么"。
                        "reasoning_content": getattr(response, "reasoning_content", "") or "",
                    }
                }
            ],
            "usage": {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                # P4.2: 透传 prompt cache 命中 token 数 (qwen-plus 隐式 20% / GLM 50% / DeepSeek 2%)
                # 用于监控 cache 优化效果, 0 表示无 cache 命中
                "cached_tokens": getattr(response.usage, "cached_tokens", 0) or 0,
            },
        }

        # 添加 tool_calls（arguments 统一为 JSON 字符串，兼容 OpenAI tool 消息回传）
        if response.tool_calls:
            import json as _json

            normalized_calls = []
            for i, tc in enumerate(response.tool_calls):
                args = tc.get("arguments", {})
                if not isinstance(args, str):
                    args = _json.dumps(args or {}, ensure_ascii=False)
                normalized_calls.append(
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": args,
                        },
                    }
                )
            result["choices"][0]["message"]["tool_calls"] = normalized_calls

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
