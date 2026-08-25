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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import os
from typing import Any

from fnixagent.core.exceptions import LLMError
from fnixagent.core.llm.base import BaseLLMProvider, LLMRequest
from fnixagent.core.llm.providers.anthropic import AnthropicProvider
from fnixagent.core.llm.providers.gemini import GeminiProvider
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
    # 原生协议 provider(Anthropic Messages API / Google Gemini generateContent)
    {
        "name": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-5",
    },
    {
        "name": "gemini",
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com",
        "default_model": "gemini-2.5-flash",
        "alt_env_keys": ["GOOGLE_API_KEY"],
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
        timeout: float | None = None,
        fallback_models: list[str] | None = None,
    ):
        """
        Args:
            api_key: API Key (为空时自动检测环境变量)
            base_url: API 基础 URL (为空时使用默认值)
            model_name: 模型名 (为空时使用默认值)
            provider_name: 提供商名 (为空时自动检测)
            timeout: 单条 LLM 请求超时(秒)；为空时取环境变量 FNIX_LLM_TIMEOUT，默认 120s
            fallback_models: 模型熔断兜底链；主模型出现授权/配额类终态错误
                (HTTP 401/403/404, insufficient_quota 等) 时自动切换到下一模型。
                为空时依次从 ~/.fnix/config.toml `model_fallbacks`、环境变量
                LLM_MODEL_FALLBACKS / BENCH_MODEL_FALLBACKS (逗号分隔) 读取。
        """
        self._provider: BaseLLMProvider | None = None
        self._provider_name = provider_name
        self._api_key = api_key
        self._base_url = base_url
        self._model_name = model_name
        self._timeout = float(timeout) if timeout else float(os.getenv("FNIX_LLM_TIMEOUT", "120"))
        self._fallback_models: list[str] = list(fallback_models or [])
        self._fallback_cursor = 0
        self._configured = False

    def _instantiate_provider(
        self, name: str, model_name: str, api_key: str, base_url: str
    ) -> BaseLLMProvider:
        """按 provider 名实例化对应的 Provider 实例。

        anthropic/gemini 走原生协议 Provider(Anthropic Messages API /
        Google Gemini generateContent),其余走 OpenAI 兼容层。
        base_url 规范化:OpenAI 兼容层保证尾斜杠;原生协议去掉尾斜杠
        (anthropic.py / gemini.py 内部自行拼接 /v1/messages、/v1beta/models)。

        Args:
            name: provider 标识名(anthropic/gemini/openai/glm/qwen/deepseek/custom)。
            model_name: 模型名。
            api_key: API Key。
            base_url: API 基础 URL(可为空,空则用各协议默认值)。

        Returns:
            BaseLLMProvider 实例(可直接 router.register)。
        """
        if name == "anthropic":
            return AnthropicProvider(
                api_key=api_key,
                model_name=model_name or "claude-sonnet-4-5",
                base_url=(base_url or "https://api.anthropic.com").rstrip("/"),
                timeout=self._timeout,
            )
        if name == "gemini":
            return GeminiProvider(
                api_key=api_key,
                model_name=model_name or "gemini-2.5-flash",
                base_url=(base_url or "https://generativelanguage.googleapis.com").rstrip("/"),
                timeout=self._timeout,
            )
        # OpenAI 兼容层(含 custom):保证尾斜杠
        if base_url and not base_url.endswith("/"):
            base_url = base_url + "/"
        return OpenAICompatibleProvider(
            name=name,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1/",
            timeout=self._timeout,
        )

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
        if not self._fallback_models:
            cfg_fb = harness_cfg.get("model_fallbacks")
            if isinstance(cfg_fb, (list, tuple)):
                self._fallback_models = [str(m) for m in cfg_fb if str(m).strip()]
            else:
                env_fb = os.getenv("LLM_MODEL_FALLBACKS", "") or os.getenv(
                    "BENCH_MODEL_FALLBACKS", ""
                )
                if env_fb:
                    self._fallback_models = [m.strip() for m in env_fb.split(",") if m.strip()]

        # 优先使用显式 / harness 配置
        if self._api_key:
            name = (self._provider_name or "custom").lower()
            defaults = {
                "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1/", "qwen-plus"),
                "openai": ("https://api.openai.com/v1/", "gpt-4o"),
                "deepseek": ("https://api.deepseek.com/v1/", "deepseek-chat"),
                "glm": ("https://open.bigmodel.cn/api/paas/v4/", "glm-4"),
                "anthropic": ("https://api.anthropic.com", "claude-sonnet-4-5"),
                "gemini": (
                    "https://generativelanguage.googleapis.com",
                    "gemini-2.5-flash",
                ),
            }
            def_base, def_model = defaults.get(name, ("https://api.openai.com/v1/", "gpt-4o"))
            base = self._base_url or def_base
            self._provider = self._instantiate_provider(
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
                self._provider = self._instantiate_provider(
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
                    timeout=self._timeout,
                )
                self._configured = True
                return

    @staticmethod
    def _is_terminal_model_error(exc: LLMError) -> bool:
        """判断是否为模型级终态错误（授权/配额/模型不存在），不可靠重试解决。"""
        msg = str(exc)
        return any(
            marker in msg
            for marker in (
                "HTTP 401",
                "HTTP 403",
                "HTTP 404",
                "insufficient_quota",
                "invalid_api_key",
            )
        )

    def _try_next_fallback(self) -> bool:
        """切换到下一个兜底模型；无可用兜底时返回 False。"""
        if self._provider is None:
            return False
        candidates = [m for m in self._fallback_models if m and m != (self._model_name or "")]
        if self._fallback_cursor >= len(candidates):
            return False
        prev = self._model_name or "<default>"
        next_model = candidates[self._fallback_cursor]
        self._fallback_cursor += 1
        import logging

        logging.getLogger(__name__).warning(
            "模型 %s 授权/配额不可用，自动切换兜底模型 %s",
            prev,
            next_model,
        )
        self._model_name = next_model
        self._provider = self._instantiate_provider(
            name=self._provider._name,
            model_name=next_model,
            api_key=self._provider._api_key,
            base_url=self._provider._base_url,
        )
        return True

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
        response_format: dict | None = None,
    ) -> dict:
        """
        AgenticLoop 兼容的 chat 接口。

        Args:
            messages: 消息列表 [{"role": "...", "content": "..."}]
            tools: OpenAI tools API 格式的工具定义列表
            model: 模型名 (为空使用默认)
            temperature: 温度
            max_tokens: 最大 token 数
            response_format: 结构化输出约束(OpenAI 风格,dict | None):
                {"type":"json_object"} 或 {"type":"json_schema","json_schema":{...}}。
                None(默认)时不约束输出,payload 与历史行为完全一致。
                各 provider 落地方式:openai 直传 / anthropic system 注入仿真 /
                gemini generationConfig 映射。

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
                "  ANTHROPIC_API_KEY=xxx (Anthropic Messages API 原生协议)\n"
                "  GEMINI_API_KEY=xxx (Google Gemini generateContent 原生协议)\n"
                "  CUSTOM_API_KEY=xxx (需同时设置 CUSTOM_BASE_URL)"
            )

        # 将 raw dict 消息转换为 Message 对象
        # Bug-037: 必须透传 tool_calls / tool_call_id——assistant 声明的
        # 工具调用与 role=tool 结果的配对关系一旦丢失，严格校验的模型
        # （qwen-max 等）直接 400 "must be a response to tool_calls"。
        msg_objects = [
            Message(
                role=MessageRole(m.get("role", "user")),
                content=str(m.get("content", "")),
                name=m.get("name"),
                tool_calls=m.get("tool_calls") or None,
                tool_call_id=m.get("tool_call_id"),
            )
            for m in messages
        ]

        # 构建 LLMRequest
        # Spec 2: 自动注入 enable_thinking=true，触发 reasoning model 思考模式
        # — DashScope OpenAI 兼容模式下，支持的模型返回 message.reasoning_content
        # — 检测规则保守：仅对 Qwen3 系列 / qwen-plus-latest / qwen-turbo-latest /
        #   qwen3-max-preview / QwQ / DeepSeek-R1 / DeepSeek-V3.1+ / GLM-4.5+ 注入
        # — 不支持的模型忽略此参数（DashScope 会拒绝未知参数，所以必须严格筛选）
        # Bug-034: qwen3.7+ 模型默认启用思考模式（即使不传 enable_thinking），
        # 导致每次调用多消耗 200+ reasoning tokens 且响应时间大幅增加。
        # 对不在显式启用列表中的 Qwen3.x 模型，传 enable_thinking=false 关闭默认思考。
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

        # glm-4.7 系列(含 glm-4.7-flash)是推理模型：即使不传 enable_thinking，
        # 智谱端默认也会进入思考模式，把全部 max_tokens 花在 reasoning_content 上，
        # 导致 content 为空、finish_reason=length，进而 write 工具产出空源码被校验拦截。
        # 编码/工具调用场景必须显式关闭思考，确保 content 真正产出代码。
        is_glm47 = "glm-4.7" in model_name or model_name == "glm-4.7"

        extra_params: dict[str, Any] = {}
        if should_enable_thinking:
            extra_params["enable_thinking"] = True
        elif "qwen3." in model_name or "qwen3-" in model_name or is_glm47:
            # Qwen3.7+ / glm-4.7 默认启用思考，显式关闭以减少延迟和 token 消耗，
            # 避免 reasoning_content 吞掉 content 预算导致空输出。
            extra_params["enable_thinking"] = False

        request = LLMRequest(
            model=model or self._model_name or "",
            messages=msg_objects,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
            extra=extra_params,
            response_format=response_format,
        )

        # Sync httpx providers block the event loop if awaited directly —
        # always offload so /health and other requests stay responsive.
        # 熔断兜底：主模型遇到授权/配额类终态错误时自动切换兜底模型重试。
        while True:
            request.model = model or self._model_name or ""
            provider = self._provider
            if provider is None:
                raise LLMError(f"[{self._provider_name or 'llm'}] provider not initialized")
            try:
                response: LLMResponse = await asyncio.to_thread(provider.chat, request)
                break
            except LLMError as exc:
                if self._is_terminal_model_error(exc) and self._try_next_fallback():
                    continue
                raise

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

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_chunk: Any = None,
        response_format: dict | None = None,
    ) -> dict:
        """流式版 chat：逐 chunk 回调正文，返回与 chat() 完全一致的 dict。

        供 AgenticLoop 在保留 function calling 能力的同时获得 token 级
        流式输出（Trae/Cursor 同架构：SSE 流式 + 流尾解析 tool_calls）。

        Args:
            messages: 消息列表 [{"role": "...", "content": "..."}]
            tools: OpenAI tools API 格式的工具定义列表
            model: 模型名 (为空使用默认)
            temperature: 温度
            max_tokens: 最大 token 数
            on_chunk: 可选回调 on_chunk(text)，每个 content delta 调用一次，
                可为同步函数或 coroutine 函数。
            response_format: 结构化输出约束(OpenAI 风格,dict | None)，
                语义与 chat() 的同名参数一致；None(默认)时零回归。

        Returns:
            与 chat() 相同的 dict 结构。

        Raises:
            LLMError: 首个 chunk 前的失败（可安全重试）。已产出 chunk 后
                中途断流同样上抛，由调用方决定是否保留部分输出。
        """
        self._auto_detect()
        if self._provider is None:
            raise LLMError(
                "未配置 LLM API Key。请在 .env 文件中设置环境变量。"
            )

        msg_objects = [
            Message(
                role=MessageRole(m.get("role", "user")),
                content=str(m.get("content", "")),
                name=m.get("name"),
                tool_calls=m.get("tool_calls") or None,
                tool_call_id=m.get("tool_call_id"),
            )
            for m in messages
        ]

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
        is_glm47 = "glm-4.7" in model_name or model_name == "glm-4.7"

        extra_params: dict[str, Any] = {}
        if should_enable_thinking:
            extra_params["enable_thinking"] = True
        elif "qwen3." in model_name or "qwen3-" in model_name or is_glm47:
            extra_params["enable_thinking"] = False

        request = LLMRequest(
            model=model or self._model_name or "",
            messages=msg_objects,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
            extra=extra_params,
            response_format=response_format,
        )

        emitted = False

        if on_chunk is not None:
            import inspect as _inspect

            async def _guarded_on_chunk(text: str) -> None:
                nonlocal emitted
                emitted = True
                out = on_chunk(text)
                if _inspect.isawaitable(out):
                    await out

            chunk_cb: Any = _guarded_on_chunk
        else:
            chunk_cb = None

        # 熔断兜底：与 chat() 一致。仅当尚未向外输出任何 chunk 时才允许
        # 切换兜底模型重试；已发出部分正文的断流直接上抛，避免正文重复。
        while True:
            request.model = model or self._model_name or ""
            provider = self._provider
            if provider is None:
                raise LLMError(
                    f"[{self._provider_name or 'llm'}] provider not initialized"
                )
            try:
                response: LLMResponse = await provider.stream_chat_full(
                    request, on_chunk=chunk_cb
                )
                break
            except LLMError as exc:
                if (
                    not emitted
                    and self._is_terminal_model_error(exc)
                    and self._try_next_fallback()
                ):
                    continue
                raise

        return self._build_loop_result(response)

    @staticmethod
    def _build_loop_result(response: LLMResponse) -> dict:
        """将 LLMResponse 转换为 AgenticLoop 期望的 dict（与 chat() 尾部一致）。"""
        result: dict[str, Any] = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": response.content,
                        "reasoning_content": getattr(
                            response, "reasoning_content", ""
                        )
                        or "",
                    }
                }
            ],
            "usage": {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "cached_tokens": getattr(response.usage, "cached_tokens", 0) or 0,
            },
        }
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

    async def stream_chat(
        self,
        messages: list[dict],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Any:
        """流式对话接口，逐 chunk 产出文本。

        与 chat() 返回 dict 不同，此方法为 async generator，
        每次 yield 一个 str 文本片段。

        Args:
            messages: 消息列表 [{"role": "...", "content": "..."}]
            model: 模型名 (为空使用默认)
            temperature: 温度
            max_tokens: 最大 token 数

        Yields:
            str: 模型生成的文本片段
        """
        from collections.abc import AsyncGenerator

        self._auto_detect()
        if self._provider is None:
            raise LLMError(
                "未配置 LLM API Key。请在 .env 文件中设置环境变量。"
            )

        msg_objects = [
            Message(
                role=MessageRole(m.get("role", "user")),
                content=str(m.get("content", "")),
                name=m.get("name"),
                tool_calls=m.get("tool_calls") or None,
                tool_call_id=m.get("tool_call_id"),
            )
            for m in messages
        ]

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
        is_glm47 = "glm-4.7" in model_name or model_name == "glm-4.7"

        extra_params: dict[str, Any] = {}
        if should_enable_thinking:
            extra_params["enable_thinking"] = True
        elif "qwen3." in model_name or "qwen3-" in model_name or is_glm47:
            extra_params["enable_thinking"] = False

        request = LLMRequest(
            model=model or self._model_name or "",
            messages=msg_objects,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=[],
            extra=extra_params,
        )

        async for chunk in self._provider.stream_chat(request):
            yield chunk


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
