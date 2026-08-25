"""
LLM Provider 适配器 - OpenAI 兼容接口。

适用于 GLM(智谱)/ OpenAI / Qwen / DeepSeek 等兼容 OpenAI Chat Completions API 的厂商。
只需配置不同的 base_url 和 api_key 即可复用。

设计要点:
  - 延迟初始化 httpx.Client(无网络/无 httpx 环境下 import 不报错)
  - 仅对 5xx 服务端错误与网络错误重试,4xx 客户端错误立即抛出
  - 异常信息脱敏:不携带 API Key 与完整请求头
  - 响应体大小限制,避免恶意/异常大响应导致 OOM
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from fnixagent.core.exceptions import LLMError
from fnixagent.core.llm.base import BaseLLMProvider, LLMRequest
from fnixagent.core.types import LLMResponse, MessageRole, TokenUsage

# 单次响应体大小上限(字节),超过则拒绝解析以防 OOM
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024  # 32 MiB

# JSON 合法转义字符（含 \uXXXX 的 u）
_VALID_JSON_ESCAPES = frozenset('"\\/bfnrtu')


def _repair_json_escapes(text: str) -> str:
    """修复 LLM 输出 tool_call 参数里常见的非法 JSON 转义。

    模型（如 qwen-turbo）偶发在参数里写 ``\\d``、``\\s``（正则）或行尾孤立 ``\\``，
    均不是合法 JSON 转义 → json.loads 报 "Invalid escape"。这里把
    ``\\x``(x 非合法转义) 补成 ``\\\\x``，保留字面反斜杠语义后再解析。
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 < n:
            nxt = text[i + 1]
            if nxt in _VALID_JSON_ESCAPES:
                out.append(ch)
                out.append(nxt)
            else:
                # 非法转义：补反斜杠成 \\x（字面反斜杠 + x）
                out.append("\\\\")
                out.append(nxt)
            i += 2
        else:
            # 行尾孤立反斜杠
            out.append("\\\\")
            i += 1
    return "".join(out)


def _parse_tool_args_json(raw: str) -> dict:
    """宽容解析 tool_call 参数：先严格解析，失败则修复非法转义后重试。"""
    s = raw.strip()
    if not s:
        return {}
    try:
        args = json.loads(s)
    except json.JSONDecodeError:
        repaired = _repair_json_escapes(s)
        try:
            args = json.loads(repaired)
        except json.JSONDecodeError:
            # 仍失败：降级为原始字符串参数（避免整个响应失败），
            # 由工具层自行处理/报错，任务可继续或重试
            return {"value": raw}
    if not isinstance(args, dict):
        return {"value": args}
    return args


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    OpenAI 兼容接口的 LLM Provider。

    适用于所有遵循 OpenAI Chat Completions API 规范的服务:
      - GLM (https://open.bigmodel.cn/api/paas/v4/)
      - OpenAI (https://api.openai.com/v1/)
      - Qwen (https://dashscope.aliyuncs.com/compatible-mode/v1/)
      - DeepSeek (https://api.deepseek.com/v1/)

    用法:
        provider = OpenAICompatibleProvider(
            name="glm",
            model_name="glm-4",
            api_key="your-key",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )
        router.register(provider)
    """

    def __init__(
        self,
        name: str,
        model_name: str,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1/",
        timeout: float = 120.0,
        max_retries: int = 3,
        response_format_support: bool = True,
    ):
        """初始化 OpenAI 兼容 Provider。

        Args:
            name: provider 标识名(如 'glm' / 'openai'),亦用于读取环境变量 {NAME}_API_KEY。
            model_name: 默认模型名。
            api_key: API Key;为空时回退到环境变量 {NAME}_API_KEY。
            base_url: API 基础 URL(末尾 / 可选)。
            timeout: 请求超时秒数,必须为正。
            max_retries: 最大重试次数(仅对 5xx/429/网络错误重试),必须为非负整数。
            response_format_support: 是否把 request.response_format 直传为请求体
                response_format 字段(OpenAI 风格)。默认 True;不支持该字段的
                兼容网关(GLM/Qwen/DeepSeek 等子类如不支持)可在各自 __init__
                传 False 关闭,关闭后 response_format 被忽略,payload 不变。

        Raises:
            TypeError: timeout/max_retries 类型错误。
            ValueError: timeout 非正或 max_retries 为负。
        """
        super().__init__(name=name, model_name=model_name)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError(f"timeout must be numeric, got {type(timeout).__name__}")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError(f"max_retries must be int, got {type(max_retries).__name__}")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        self._api_key = api_key or os.getenv(f"{name.upper()}_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._response_format_support = bool(response_format_support)
        self._client = None  # 延迟初始化

    def _get_client(self):
        """延迟初始化 httpx 客户端(避免无网络环境启动失败)。

        SSL 适配: 部分云端 API 网关(如阿里云百炼 MaaS)在 TLS 握手阶段
        会请求重协商(renegotiation)。OpenSSL 3.0+ 默认禁用 legacy
        renegotiation,导致 ``SSL: UNEXPECTED_EOF_WHILE_READING`` 错误。
        此处显式启用 ``OP_LEGACY_SERVER_CONNECT`` 以兼容此类服务器。
        """
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise LLMError("httpx is required for OpenAICompatibleProvider") from exc
            import ssl as _ssl

            _ssl_ctx = _ssl.create_default_context()
            _legacy_reneg = getattr(_ssl, "OP_LEGACY_SERVER_CONNECT", None)
            if _legacy_reneg is not None:
                _ssl_ctx.options |= _legacy_reneg
            self._client = httpx.Client(timeout=self._timeout, verify=_ssl_ctx)
        return self._client

    # -- 请求体构建 ---------------------------------------------------------

    def _build_payload(
        self,
        request: LLMRequest,
        messages: list[dict],
        stream: bool = False,
    ) -> dict[str, Any]:
        """构建 OpenAI Chat Completions 请求体(非流式/流式共用)。

        Args:
            request: LLM 调用请求。
            messages: 已预处理的消息列表。
            stream: 是否流式调用(仅追加 stream=True,其余字段一致)。

        Returns:
            OpenAI Chat Completions 请求体 dict。
        """
        payload: dict[str, Any] = {
            "model": request.model or self._model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if stream:
            payload["stream"] = True
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = request.tool_choice
        if request.stop:
            payload["stop"] = request.stop

        # 结构化输出:request.response_format 直传为 response_format 字段。
        # 仅当构造时声明支持(response_format_support=True)才注入;
        # request.response_format 为 None 时 payload 与历史行为完全一致。
        rf = getattr(request, "response_format", None)
        if self._response_format_support and isinstance(rf, dict):
            payload["response_format"] = rf

        # Spec 2: 透传 provider 专属参数（如 DashScope enable_thinking / OpenAI reasoning_effort）
        # — request.extra 由上层 (LLMAdapter / AgenticLoop) 注入，用于触发思考模式
        # — 思考模式开启后，response.message.reasoning_content 会被 _parse_response 提取
        if request.extra:
            for k, v in request.extra.items():
                if v is not None and k not in payload:
                    payload[k] = v

        return payload

    def _do_chat(self, request: LLMRequest, messages: list[dict]) -> LLMResponse:
        """调用 OpenAI 兼容的 Chat Completions API。

        重试策略:仅对 5xx 服务端错误、429 限流、网络层错误(httpx.RequestError)
        重试;4xx 客户端错误(鉴权/参数等)与响应解析错误立即抛出,不重试。

        Args:
            request: LLM 调用请求。
            messages: 已预处理的消息列表。

        Returns:
            LLMResponse: 解析后的响应。

        Raises:
            LLMError: API Key 未配置、HTTP 错误、响应解析失败等。
        """
        if not self._api_key:
            raise LLMError(f"[{self._name}] API key not configured")

        # 构建请求体(非流式/流式/usage 精确化共用 _build_payload)
        payload = self._build_payload(request, messages, stream=False)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        model_for_err = request.model or self._model_name

        # 重试逻辑:仅对可重试错误重试(保持 max_retries 为总尝试次数的语义)
        last_error: str | None = None
        for attempt in range(self._max_retries):
            try:
                client = self._get_client()
                resp = client.post(url, json=payload, headers=headers)
                # 响应体大小限制,防 OOM
                if len(resp.content) > _MAX_RESPONSE_BYTES:
                    raise LLMError(
                        f"[{self._name}] response too large: "
                        f"{len(resp.content)} bytes (model={model_for_err})"
                    )
                resp.raise_for_status()
                data = resp.json()
                # 解析错误(LLMError)不在此 except 捕获,直接向上传播
                return self._parse_response(data)
            except LLMError:
                # 响应解析类错误不重试,直接抛出
                raise
            except Exception as exc:
                # 区分可重试(5xx/429/网络)与不可重试(4xx)
                retryable, err_msg = self._classify_error(exc)
                last_error = err_msg
                if not retryable or attempt >= self._max_retries - 1:
                    raise LLMError(
                        f"[{self._name}] request failed (model={model_for_err}): {err_msg}"
                    ) from exc
                # 指数退避:0.8s, 1.6s, 2.4s ...
                time.sleep(0.8 * (attempt + 1))
                continue

        # 理论不可达(for 循环已覆盖),防御性兜底
        raise LLMError(
            f"[{self._name}] request failed after {self._max_retries} retries "
            f"(model={model_for_err}): {last_error}"
        )

    async def _do_stream(
        self, request: LLMRequest, messages: list[dict]
    ) -> AsyncGenerator[str, None]:
        """流式调用 OpenAI 兼容 Chat Completions API (SSE)。

        使用 httpx 流式读取 SSE 事件，逐 chunk 产出 content delta 文本。
        失败时回退到同步 _do_chat 整段返回（基类默认行为）。

        Args:
            request: LLM 调用请求。
            messages: 已预处理的消息列表。

        Yields:
            str: 模型生成的文本片段 (content delta)。
        """
        if not self._api_key:
            raise LLMError(f"[{self._name}] API key not configured")

        # 构建请求体 (与 _do_chat 共用 _build_payload,追加 stream=True)
        payload = self._build_payload(request, messages, stream=True)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        model_for_err = request.model or self._model_name

        import json as _json

        try:
            import httpx
        except ImportError as exc:
            raise LLMError("httpx is required for streaming") from exc

        import ssl as _ssl

        _ssl_ctx = _ssl.create_default_context()
        _legacy_reneg = getattr(_ssl, "OP_LEGACY_SERVER_CONNECT", None)
        if _legacy_reneg is not None:
            _ssl_ctx.options |= _legacy_reneg

        # 使用独立 client 以支持流式读取（避免与 _get_client 的同步 client 冲突）
        async with httpx.AsyncClient(
            timeout=self._timeout, verify=_ssl_ctx
        ) as async_client:
            async with async_client.stream(
                "POST", url, json=payload, headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise LLMError(
                        f"[{self._name}] stream HTTP {resp.status_code} "
                        f"(model={model_for_err}): {body[:500]}"
                    )

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_data = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue
                    choices = chunk_data.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content_chunk = delta.get("content")
                    if content_chunk:
                        yield content_chunk

    async def stream_chat_full(
        self,
        request: LLMRequest,
        on_chunk: Any = None,
    ) -> LLMResponse:
        """完整流式调用：逐 chunk 回调 content，同时累积 tool_calls / reasoning / usage。

        与 stream_chat 只产文本不同，此方法在流结束后返回与 chat() 等价的
        LLMResponse（含 tool_calls、reasoning_content、usage），供 AgenticLoop
        在保持工具调用能力的前提下获得 token 级流式体验。

        Args:
            request: LLM 调用请求。
            on_chunk: 可选回调 on_chunk(text)，每个 content delta 调用一次。
                回调可以是同步函数或 coroutine 函数。

        Returns:
            LLMResponse: 与非流式 chat() 结构一致的完整响应。

        Raises:
            LLMError: 流式调用失败（HTTP 错误在首个 chunk 前抛出）。
        """
        import inspect as _inspect

        messages = self._prepare_messages(request)
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tc_slots: dict[int, dict] = {}
        usage_data: dict = {}
        finish_reason = "stop"
        model_seen = ""
        emitted = False

        async def _emit(text: str) -> None:
            nonlocal emitted
            if not text:
                return
            content_parts.append(text)
            if on_chunk is not None:
                emitted = True
                out = on_chunk(text)
                if _inspect.isawaitable(out):
                    await out

        try:
            async for raw_line in self._aiter_sse_lines(request, messages):
                choices = raw_line.get("choices", [])
                if raw_line.get("usage"):
                    usage_data = raw_line["usage"]
                if raw_line.get("model"):
                    model_seen = raw_line["model"]
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta", {}) or {}
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]

                content_chunk = delta.get("content")
                if content_chunk:
                    await _emit(content_chunk)

                rc = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(rc, str) and rc:
                    reasoning_parts.append(rc)

                for tc_delta in delta.get("tool_calls") or []:
                    idx = tc_delta.get("index", 0)
                    slot = tc_slots.setdefault(
                        idx,
                        {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    if tc_delta.get("id"):
                        slot["id"] = tc_delta["id"]
                    fn = tc_delta.get("function") or {}
                    if fn.get("name"):
                        slot["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["function"]["arguments"] += fn["arguments"]
        except Exception as exc:
            from fnixagent.core.exceptions import LLMError

            # 已向外发过正文中途断流：无安全重试点，直接上抛
            raise LLMError(
                f"[{self._name}] stream_chat_full failed: {exc}"
            ) from exc

        # 组装成 OpenAI 非流式响应结构，复用 _parse_response 的标准化解构
        # （含 <think> 内联思考剥离、tool arguments JSON 解析、cache token 提取）
        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_parts),
        }
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if tc_slots:
            message["tool_calls"] = [tc_slots[i] for i in sorted(tc_slots)]
        data: dict[str, Any] = {
            "model": model_seen or request.model or self._model_name,
            "choices": [
                {"message": message, "finish_reason": finish_reason}
            ],
            "usage": usage_data,
        }
        response = self._parse_response(data)
        response.model = response.model or self._model_name
        if response.usage.total_tokens == 0:
            response.usage = self._estimate_usage(messages, response.content)
        return response

    async def _aiter_sse_lines(
        self, request: LLMRequest, messages: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """逐条产出 SSE 数据帧（解析后的 dict）。

        与 _do_stream 共用请求构建逻辑；HTTP 错误在首个产出前抛出，
        保证调用方可以用"是否已产出 chunk"判断是否可安全重试。
        """
        if not self._api_key:
            from fnixagent.core.exceptions import LLMError

            raise LLMError(f"[{self._name}] API key not configured")

        payload = self._build_payload(request, messages, stream=True)

        # Usage 精确化:按 OpenAI stream_options 规范请求服务端在流中回报
        # 真实 usage(通常在最后一个 chunk),stream_chat_full 会优先读取该值;
        # 取不到时才回退基类的字符粗估。
        # 个别严格网关若拒绝未知参数导致 400,可通过
        # request.extra["stream_options"] = False 关闭(合并逻辑会先写入 False,
        # 使下方默认注入跳过)。
        if "stream_options" not in payload:
            payload["stream_options"] = {"include_usage": True}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        model_for_err = request.model or self._model_name

        import json as _json

        try:
            import httpx
        except ImportError as exc:
            from fnixagent.core.exceptions import LLMError

            raise LLMError("httpx is required for streaming") from exc

        import ssl as _ssl

        _ssl_ctx = _ssl.create_default_context()
        _legacy_reneg = getattr(_ssl, "OP_LEGACY_SERVER_CONNECT", None)
        if _legacy_reneg is not None:
            _ssl_ctx.options |= _legacy_reneg

        async with httpx.AsyncClient(
            timeout=self._timeout, verify=_ssl_ctx
        ) as async_client:
            async with async_client.stream(
                "POST", url, json=payload, headers=headers
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    from fnixagent.core.exceptions import LLMError

                    raise LLMError(
                        f"[{self._name}] stream HTTP {resp.status_code} "
                        f"(model={model_for_err}): {body[:500]}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        yield _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[bool, str]:
        """将异常分类为可重试/不可重试,并返回脱敏后的错误描述。

        - httpx.HTTPStatusError:5xx 与 429 可重试,其余 4xx 不可重试
        - httpx.RequestError(连接/超时/解析等):可重试
        - 其它:不可重试

        Returns:
            (retryable, message):retryable 表示是否建议重试,message 已脱敏
            (不含 Authorization 头或完整 URL 查询串)。
        """
        try:
            import httpx
        except ImportError:
            httpx = None  # type: ignore[assignment]

        if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            # 5xx 服务端错误或 429 限流可重试;其余 4xx 不可重试
            retryable = status >= 500 or status == 429
            # 附带服务端错误简述（如 insufficient_quota），截断防日志膨胀
            detail = ""
            try:
                body = exc.response.json()
                err_obj = body.get("error") if isinstance(body, dict) else None
                msg = err_obj.get("message") if isinstance(err_obj, dict) else None
                if isinstance(msg, str) and msg:
                    detail = f" ({msg[:160]})"
            except Exception:
                pass
            return retryable, f"HTTP {status}{detail}"
        if httpx is not None and isinstance(exc, httpx.RequestError):
            # 网络层错误(连接超时/DNS/读取超时等)可重试;
            # httpx 的异常默认不携带 Authorization 头,使用类名 + 简要信息
            return True, f"{type(exc).__name__}: {exc}"
        # 未知异常:保守不重试
        return False, f"{type(exc).__name__}: {exc}"

    def _parse_response(self, data: dict) -> LLMResponse:
        """解析 OpenAI 格式的响应。

        Args:
            data: 响应 JSON 解析后的 dict。

        Returns:
            LLMResponse: 提取 content / tool_calls / usage 后的响应。

        Raises:
            LLMError: choices 为空或 tool_calls 的 arguments 不是合法 JSON。
        """
        choices = data.get("choices", [])
        if not choices:
            raise LLMError(f"[{self._name}] empty choices in response")

        choice = choices[0]
        message = choice.get("message", {})

        # 提取内容
        content = message.get("content", "") or ""

        # Spec 2: 提取 reasoning model 的思考链 (reasoning_content / reasoning / thinking)
        # - Qwen3 (DashScope OpenAI 兼容模式): message.reasoning_content
        # - OpenAI o1/o3: message.reasoning (汇总) 或 reasoning_content (per-step)
        # - DeepSeek-R1: message.reasoning_content
        # - Claude ( API): thinking blocks (需 adapter 转换)
        # - GLM-4.5/4.6: message.reasoning_content (启用 thinking 参数后)
        reasoning_content = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or message.get("thinking")
            or ""
        )
        if not isinstance(reasoning_content, str):
            # 某些 provider 可能返回 list[dict] ( thinking blocks)
            try:
                if isinstance(reasoning_content, list):
                    reasoning_content = "\n\n".join(
                        str(b.get("thinking", b.get("text", "")))
                        for b in reasoning_content
                        if isinstance(b, dict)
                    )
                else:
                    reasoning_content = str(reasoning_content)
            except Exception:
                reasoning_content = ""

        # Bug-Fix: DeepSeek-V4-Flash (硅基流动) 等推理模型会把思考链内联进
        # content (形如 "<think>思考</think>回答" 或省略开标签的 "思考</think>回答"),
        # 而不放在独立的 reasoning_content 字段。下游 JSON 解析器
        # (CodingAgent._parse_plan / _parse_review) 会被思考文本里的花括号/关键词
        # 干扰, 导致计划解析失败或审查误判。这里统一剥离内联思考块,
        # 并入 reasoning_content 供前端 ProcessTimeline 折叠展示。
        if content and ("<think>" in content or "</think>" in content):
            inline_think = ""
            _t = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if _t:
                inline_think = _t.group(1)
                content = (content[: _t.start()] + content[_t.end() :]).strip()
            elif "</think>" in content:
                # 省略开标签: 开标签前的内容视为思考, 之后为正式回答
                _head, _sep, _tail = content.partition("</think>")
                inline_think = _head
                content = _tail.strip()
            else:
                # 只有开标签 (响应被 max_tokens 截断在思考阶段):
                # 全部内容都是未闭合的思考, content 置空交由上层按空响应处理
                _head, _sep, _tail = content.partition("<think>")
                inline_think = _head + _tail
                content = _head.strip()
            if inline_think.strip() and not reasoning_content:
                reasoning_content = inline_think.strip()

        # 提取工具调用
        tool_calls_raw = message.get("tool_calls", [])
        tool_calls = []
        for tc in tool_calls_raw:
            func = tc.get("function", {})
            args_raw = func.get("arguments", "{}")
            # arguments 可能是 JSON 字符串，也可能已被上游解析成 dict
            try:
                if isinstance(args_raw, dict):
                    args = args_raw
                elif isinstance(args_raw, (bytes, bytearray)):
                    args = json.loads(args_raw.decode("utf-8") or "{}")
                elif isinstance(args_raw, str):
                    args = _parse_tool_args_json(args_raw)
                elif args_raw is None:
                    args = {}
                else:
                    args = {"value": args_raw}
                if not isinstance(args, dict):
                    args = {"value": args}
            except (json.JSONDecodeError, TypeError, UnicodeDecodeError) as je:
                raise LLMError(f"[{self._name}] invalid tool_call arguments JSON: {je}") from je
            tool_calls.append(
                {
                    "id": tc.get("id", ""),
                    "name": func.get("name", ""),
                    "arguments": args,
                }
            )

        # 提取 usage
        usage_raw = data.get("usage", {}) or {}
        # P4.2: 解析 prompt cache 命中 token 数
        # 兼容三种字段:
        #   - OpenAI / qwen-plus / GLM: usage.prompt_tokens_details.cached_tokens
        #   - DeepSeek: usage.prompt_cache_hit_tokens
        #   - 旧 provider 无 cache 字段: 0
        prompt_details = usage_raw.get("prompt_tokens_details") or {}
        cached_tokens = (
            prompt_details.get("cached_tokens", 0)
            or usage_raw.get("prompt_cache_hit_tokens", 0)
            or 0
        )
        usage = TokenUsage(
            prompt_tokens=usage_raw.get("prompt_tokens", 0),
            completion_tokens=usage_raw.get("completion_tokens", 0),
            total_tokens=usage_raw.get("total_tokens", 0),
            cached_tokens=int(cached_tokens),
        )

        return LLMResponse(
            content=content,
            model=data.get("model", self._model_name),
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            raw=data,
            reasoning_content=reasoning_content,
        )


class GLMProvider(OpenAICompatibleProvider):
    """智谱 GLM Provider。"""

    def __init__(self, api_key: str = "", model_name: str = "glm-4", **kwargs):
        super().__init__(
            name="glm",
            model_name=model_name,
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            **kwargs,
        )


class OpenAIProvider(OpenAICompatibleProvider):
    """OpenAI Provider。"""

    def __init__(self, api_key: str = "", model_name: str = "gpt-4-turbo", **kwargs):
        super().__init__(
            name="openai",
            model_name=model_name,
            api_key=api_key,
            base_url="https://api.openai.com/v1/",
            **kwargs,
        )


class QwenProvider(OpenAICompatibleProvider):
    """通义千问 Provider。"""

    def __init__(self, api_key: str = "", model_name: str = "qwen-plus", **kwargs):
        super().__init__(
            name="qwen",
            model_name=model_name,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/",
            **kwargs,
        )


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM Provider(用于无 API Key 环境的本地测试)。

    不调用真实 API,直接返回基于规则的简单响应。
    """

    def __init__(self, name: str = "mock", model_name: str = "mock-model"):
        super().__init__(name=name, model_name=model_name)

    def _do_chat(self, request: LLMRequest, messages: list[dict]) -> LLMResponse:
        """基于规则的简单响应。"""
        # 取最后一条用户消息
        last_user_msg = ""
        for m in reversed(request.messages):
            if m.role == MessageRole.USER:
                last_user_msg = m.content
                break

        # 简单规则响应
        content = f"[Mock LLM] 已收到您的请求: {last_user_msg[:50]}...。当前为 Mock 模式,请配置真实 API Key 以启用完整功能。"

        return LLMResponse(
            content=content,
            model=self._model_name,
            usage=TokenUsage(
                prompt_tokens=len(last_user_msg) // 4 + 10,
                completion_tokens=len(content) // 4 + 5,
                total_tokens=len(last_user_msg + content) // 4 + 15,
            ),
            finish_reason="stop",
        )
