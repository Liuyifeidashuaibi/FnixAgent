"""
LLM Provider 适配器 - Anthropic Messages API 原生协议。

适用于 Claude 系列模型 (claude-sonnet / claude-opus / claude-haiku),
直连 Anthropic 官方 Messages API (/v1/messages),不走 OpenAI 兼容层。

协议要点:
  - 鉴权:x-api-key 请求头(非 Authorization Bearer) + anthropic-version 头
  - system 提示词为请求体顶层字段,不在 messages 数组内
  - 消息 content 为 block 列表:text / thinking / tool_use / tool_result
  - 工具结果以 user 角色 tool_result block 回传(非 role=tool)
  - 停止原因 stop_reason 需映射到 OpenAI 风格 finish_reason
  - 流式 SSE:message_start → content_block_start → content_block_delta*
    → content_block_stop* → message_delta → message_stop
  - usage 从 message_start(input_tokens)与 message_delta(output_tokens)
    取真实值,无 token 字符估算
  - response_format:无原生字段,仿真实现(emulated)——在 system 前部
    注入严格 JSON 输出指令(json_schema 附带 schema 摘要),见
    _response_format_directive

设计要点(对齐 openai.py):
  - 延迟初始化 httpx.Client(无网络/无 httpx 环境下 import 不报错)
  - 仅对 5xx 服务端错误、429 与网络错误重试,4xx 客户端错误立即抛出
  - 异常信息脱敏:不携带 API Key 与完整请求头
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

from fnixagent.core.exceptions import LLMError
from fnixagent.core.llm.base import BaseLLMProvider, LLMRequest
from fnixagent.core.llm.providers.openai import (
    _MAX_RESPONSE_BYTES,
    _parse_tool_args_json,
)
from fnixagent.core.types import LLMResponse, TokenUsage

# Anthropic API 版本头(2023-06-01 为 Messages API 稳定版本)
_ANTHROPIC_VERSION = "2023-06-01"

# stop_reason → OpenAI 风格 finish_reason 映射
_STOP_REASON_MAP = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "refusal": "refusal",
}


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Messages API 原生 Provider。

    直接对接 https://api.anthropic.com/v1/messages,实现完整的
    x-api-key 鉴权、system 顶层字段、content blocks、tool_use/tool_result、
    流式 SSE 事件解析与真实 usage 回填。

    response_format 支持:Anthropic Messages API 无原生 response_format
    字段,本 provider 采用仿真方案(emulated)——在 system 前部注入严格
    JSON 输出指令实现结构化输出约束,非协议级保证。

    用法:
        provider = AnthropicProvider(
            api_key="your-key",
            model_name="claude-sonnet-4-5",
        )
        router.register(provider)   # 无缝接入 Router 的 failover/熔断/限流
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "claude-sonnet-4-5",
        base_url: str = "https://api.anthropic.com",
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        """初始化 Anthropic Provider。

        Args:
            api_key: Anthropic API Key;为空时回退到环境变量 ANTHROPIC_API_KEY。
            model_name: 默认模型名(claude-sonnet-4-5 等)。
            base_url: API 基础 URL(末尾 / 可选,兼容自建网关/代理)。
            timeout: 请求超时秒数,必须为正。
            max_retries: 最大重试次数(仅对 5xx/429/网络错误重试),必须为非负整数。

        Raises:
            TypeError: timeout/max_retries 类型错误。
            ValueError: timeout 非正或 max_retries 为负。
        """
        super().__init__(name="anthropic", model_name=model_name)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError(f"timeout must be numeric, got {type(timeout).__name__}")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError(f"max_retries must be int, got {type(max_retries).__name__}")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = None  # 延迟初始化

    # -- HTTP 客户端 --------------------------------------------------------

    def _get_client(self):
        """延迟初始化 httpx 客户端(避免无网络环境启动失败)。

        SSL 适配与 openai.py 一致:启用 OP_LEGACY_SERVER_CONNECT 兼容
        云端网关的 TLS 重协商。
        """
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise LLMError("httpx is required for AnthropicProvider") from exc
            import ssl as _ssl

            _ssl_ctx = _ssl.create_default_context()
            _legacy_reneg = getattr(_ssl, "OP_LEGACY_SERVER_CONNECT", None)
            if _legacy_reneg is not None:
                _ssl_ctx.options |= _legacy_reneg
            self._client = httpx.Client(timeout=self._timeout, verify=_ssl_ctx)
        return self._client

    def _headers(self) -> dict[str, str]:
        """构建请求头:x-api-key + anthropic-version(Anthropic 协议要求)。"""
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[bool, str]:
        """将异常分类为可重试/不可重试,并返回脱敏后的错误描述(同 openai.py)。"""
        try:
            import httpx
        except ImportError:
            httpx = None  # type: ignore[assignment]

        if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            retryable = status >= 500 or status == 429
            detail = ""
            try:
                body = exc.response.json()
                err_obj = body.get("error") if isinstance(body, dict) else None
                msg = err_obj.get("message") if isinstance(err_obj, dict) else None
                if isinstance(msg, str) and msg:
                    detail = f" ({msg[:160]})"
            except Exception:  # noqa: S110 — 响应体非 JSON 时忽略,保留状态码即可
                pass
            return retryable, f"HTTP {status}{detail}"
        if httpx is not None and isinstance(exc, httpx.RequestError):
            return True, f"{type(exc).__name__}: {exc}"
        return False, f"{type(exc).__name__}: {exc}"

    # -- 请求体转换 ---------------------------------------------------------

    @staticmethod
    def _response_format_directive(response_format: Any) -> str | None:
        """将 OpenAI 风格 response_format 转换为注入 system 的严格 JSON 指令。

        Anthropic Messages API 无原生 response_format 字段,此处做仿真
        (emulated):生成一段强制 JSON 输出的 system 指令,json_schema 类型
        时附带 schema 摘要引导模型按结构输出。

        Args:
            response_format: {"type":"json_object"} 或
                {"type":"json_schema","json_schema":{...}}(OpenAI 风格);
                其他取值返回 None(不注入)。

        Returns:
            指令文本;response_format 为空或类型不支持时返回 None。
        """
        if not isinstance(response_format, dict):
            return None
        rf_type = response_format.get("type", "")
        if rf_type == "json_object":
            return (
                "[JSON 输出模式(emulated)]\n"
                "你必须只输出一个合法的 JSON 对象作为最终回答:\n"
                "- 不要输出任何解释、前言、Markdown 代码围栏或 JSON 以外的文本;\n"
                "- 确保输出可以被 json.loads 直接解析。"
            )
        if rf_type == "json_schema":
            js = response_format.get("json_schema")
            schema_summary = ""
            if isinstance(js, dict):
                schema_body = js.get("schema") if isinstance(js.get("schema"), dict) else js
                try:
                    schema_summary = json.dumps(schema_body, ensure_ascii=False)
                except (TypeError, ValueError):
                    schema_summary = ""
            directive = (
                "[JSON 输出模式(emulated)]\n"
                "你必须只输出一个合法的 JSON 对象作为最终回答:\n"
                "- 严格遵守下方 JSON Schema 定义的字段名/类型/必填项;\n"
                "- 不要输出任何解释、前言、Markdown 代码围栏或 JSON 以外的文本;\n"
                "- 确保输出可以被 json.loads 直接解析。"
            )
            if schema_summary:
                directive += f"\nJSON Schema:\n{schema_summary}"
            return directive
        return None

    def _build_payload(
        self, request: LLMRequest, messages: list[dict], stream: bool
    ) -> dict[str, Any]:
        """将通用消息列表转换为 Anthropic Messages API 请求体。

        转换规则:
          - system 角色消息合并为顶层 system 字符串
          - assistant 的 tool_calls 转为 tool_use content block
          - role=tool 消息转为 user 角色的 tool_result content block
          - 连续同角色消息自动合并(Anthropic 要求 user/assistant 交替)
          - response_format 仿真(emulated):Messages API 无原生
            response_format 字段,改为在 system 前部追加严格 JSON 输出指令
            (json_object / json_schema 均生效,json_schema 附带 schema 摘要)

        Args:
            request: LLM 调用请求。
            messages: 已预处理的 OpenAI 风格消息 dict 列表。
            stream: 是否流式调用。

        Returns:
            Anthropic Messages API 请求体 dict。
        """
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        # response_format 仿真(emulated):JSON 输出指令插入 system 最前部,
        # 优先级高于用户 system 提示词
        rf_directive = self._response_format_directive(
            getattr(request, "response_format", None)
        )
        if rf_directive:
            system_parts.append(rf_directive)

        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "") or ""

            # system → 顶层字段
            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            blocks: list[dict[str, Any]] = []
            if role == "assistant":
                if content:
                    blocks.append({"type": "text", "text": content})
                # assistant 声明的工具调用 → tool_use block
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    args_raw = fn.get("arguments", {})
                    if isinstance(args_raw, str):
                        args = _parse_tool_args_json(args_raw)
                    elif isinstance(args_raw, dict):
                        args = args_raw
                    else:
                        args = {"value": args_raw} if args_raw is not None else {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "input": args,
                        }
                    )
            elif role == "tool":
                # 工具执行结果 → user 角色内的 tool_result block
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": content,
                    }
                )
            else:  # user
                blocks.append({"type": "text", "text": content})

            if not blocks:
                continue

            # 合并连续同角色消息(Anthropic 要求 user/assistant 严格交替)
            a_role = "user" if role in ("user", "tool") else "assistant"
            if converted and converted[-1]["role"] == a_role:
                converted[-1]["content"].extend(blocks)
            else:
                converted.append({"role": a_role, "content": blocks})

        payload: dict[str, Any] = {
            "model": request.model or self._model_name,
            "max_tokens": request.max_tokens,  # Anthropic 必填字段
            "messages": converted,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        payload["temperature"] = request.temperature
        if request.stop:
            payload["stop_sequences"] = request.stop

        # tools 转换:OpenAI function 格式 → Anthropic name/description/input_schema
        if request.tools:
            payload["tools"] = self._convert_tools(request.tools)
            choice = self._convert_tool_choice(request.tool_choice)
            if choice is not None:
                payload["tool_choice"] = choice

        if stream:
            payload["stream"] = True

        # 透传 provider 专属参数(如 top_k/top_p/metadata);不覆盖已生成的规范键
        if request.extra:
            for k, v in request.extra.items():
                if v is not None and k not in payload:
                    payload[k] = v
        return payload

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """OpenAI tools 格式转 Anthropic tools 格式。"""
        out: list[dict] = []
        for t in tools:
            fn = t.get("function") or {} if isinstance(t, dict) else {}
            if not fn:
                continue
            out.append(
                {
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
        return out

    @staticmethod
    def _convert_tool_choice(tool_choice: Any) -> dict | None:
        """OpenAI tool_choice 转 Anthropic tool_choice。

        auto → {"type":"auto"};required → {"type":"any"};
        指定工具名 → {"type":"tool","name":...};none → None(不传)。
        """
        if isinstance(tool_choice, dict):
            fn = tool_choice.get("function") or {}
            if fn.get("name"):
                return {"type": "tool", "name": fn["name"]}
            return {"type": "auto"}
        if tool_choice == "required":
            return {"type": "any"}
        if tool_choice == "none":
            return None
        return {"type": "auto"}

    # -- 同步对话 -----------------------------------------------------------

    def _do_chat(self, request: LLMRequest, messages: list[dict]) -> LLMResponse:
        """调用 Anthropic Messages API (/v1/messages)。

        重试策略与 openai.py 一致:仅对 5xx 服务端错误、429 限流、网络层
        错误(httpx.RequestError)重试;4xx 客户端错误与响应解析错误立即抛出。

        Args:
            request: LLM 调用请求。
            messages: 已预处理的消息列表。

        Returns:
            LLMResponse: 解析后的响应(usage 为 API 真实回报值)。

        Raises:
            LLMError: API Key 未配置、HTTP 错误、响应解析失败等。
        """
        if not self._api_key:
            raise LLMError(f"[{self._name}] API key not configured")

        payload = self._build_payload(request, messages, stream=False)
        headers = self._headers()
        url = f"{self._base_url}/v1/messages"
        model_for_err = request.model or self._model_name

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
                return self._parse_response(data)
            except LLMError:
                # 响应解析类错误不重试,直接抛出
                raise
            except Exception as exc:
                retryable, err_msg = self._classify_error(exc)
                last_error = err_msg
                if not retryable or attempt >= self._max_retries - 1:
                    raise LLMError(
                        f"[{self._name}] request failed (model={model_for_err}): {err_msg}"
                    ) from exc
                # 指数退避:0.8s, 1.6s, 2.4s ...
                time.sleep(0.8 * (attempt + 1))
                continue

        raise LLMError(
            f"[{self._name}] request failed after {self._max_retries} retries "
            f"(model={model_for_err}): {last_error}"
        )

    # -- 响应解析 -----------------------------------------------------------

    def _parse_response(self, data: dict) -> LLMResponse:
        """解析 Anthropic Messages API 响应为统一 LLMResponse。

        - text block → content
        - thinking block → reasoning_content(Claude 扩展思考链)
        - tool_use block → tool_calls(input 已是 dict,无需 JSON 解析)
        - usage.input_tokens / output_tokens → 真实 token 计数

        Args:
            data: 响应 JSON 解析后的 dict。

        Returns:
            LLMResponse: 统一响应结构。

        Raises:
            LLMError: content blocks 为空或结构非法。
        """
        blocks = data.get("content")
        # 结构非法(缺失/非列表)视为协议错误;空列表仅代表空响应(如被安全策略拦截)
        if not isinstance(blocks, list):
            raise LLMError(f"[{self._name}] invalid content blocks in response")

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[dict] = []

        for b in blocks:
            if not isinstance(b, dict):
                continue
            b_type = b.get("type", "")
            if b_type == "text":
                content_parts.append(b.get("text", "") or "")
            elif b_type == "thinking":
                # Claude 扩展思考链(thinking mode)
                thinking = b.get("thinking", "") or ""
                if thinking:
                    reasoning_parts.append(thinking)
            elif b_type == "redacted_thinking":
                # 加密思考块不可展示,跳过
                continue
            elif b_type == "tool_use":
                inp = b.get("input")
                if not isinstance(inp, dict):
                    inp = {"value": inp} if inp is not None else {}
                tool_calls.append(
                    {
                        "id": b.get("id", ""),
                        "name": b.get("name", ""),
                        "arguments": inp,
                    }
                )

        # usage:Anthropic 返回 input_tokens/output_tokens 真实计数
        usage_raw = data.get("usage") or {}
        prompt_tokens = int(usage_raw.get("input_tokens", 0) or 0)
        completion_tokens = int(usage_raw.get("output_tokens", 0) or 0)
        # P4.2: prompt cache 命中(cache_read_input_tokens)
        cached_tokens = int(usage_raw.get("cache_read_input_tokens", 0) or 0)
        total_tokens = prompt_tokens + completion_tokens

        finish_reason = _STOP_REASON_MAP.get(data.get("stop_reason"), "stop")

        return LLMResponse(
            content="".join(content_parts),
            model=data.get("model", self._model_name),
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
            ),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw=data,
            reasoning_content="\n\n".join(reasoning_parts),
        )

    # -- 流式 ---------------------------------------------------------------

    async def _aiter_sse_events(
        self, request: LLMRequest, messages: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """逐条产出 Anthropic 流式 SSE 数据帧(解析后的 JSON dict)。

        Anthropic SSE 每个事件形如 ``event: xxx`` + ``data: {...}``,
        其中 data JSON 自带 type 字段(message_start/content_block_delta/...),
        因此只需按行提取 data 行即可。HTTP 错误在首个产出前抛出,
        保证调用方可以用"是否已产出 chunk"判断是否可安全重试。
        """
        if not self._api_key:
            raise LLMError(f"[{self._name}] API key not configured")

        payload = self._build_payload(request, messages, stream=True)
        headers = self._headers()
        url = f"{self._base_url}/v1/messages"
        model_for_err = request.model or self._model_name

        try:
            import httpx
        except ImportError as exc:
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
                    raise LLMError(
                        f"[{self._name}] stream HTTP {resp.status_code} "
                        f"(model={model_for_err}): {body[:500]}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    # SSE 注释行(: ping)与非 data 行直接跳过
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    async def _do_stream(
        self, request: LLMRequest, messages: list[dict]
    ) -> AsyncGenerator[str, None]:
        """流式调用 Anthropic Messages API,逐 chunk 产出正文文本。

        只产出 text_delta(正式回答);thinking_delta 思考链仅在
        stream_chat_full 中收集,与 openai.py 行为一致。

        Yields:
            str: 模型生成的文本片段(text delta)。
        """
        async for frame in self._aiter_sse_events(request, messages):
            f_type = frame.get("type")
            if f_type == "content_block_delta":
                delta = frame.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text = delta.get("text")
                    if text:
                        yield text
            elif f_type == "message_stop":
                break
            elif f_type == "error":
                err = frame.get("error") or {}
                raise LLMError(
                    f"[{self._name}] stream error event: {err.get('type', 'unknown')}"
                    f": {err.get('message', '')}"
                )

    async def stream_chat_full(
        self,
        request: LLMRequest,
        on_chunk: Any = None,
    ) -> LLMResponse:
        """完整流式调用:逐 chunk 回调正文,同时累积 thinking / tool_use / usage。

        事件解析:
          - message_start:捕获真实 input_tokens 与 model 名
          - content_block_start:登记 tool_use block(id/name)
          - content_block_delta:text_delta 正文回调 / thinking_delta 思考链 /
            input_json_delta 工具参数增量拼接
          - message_delta:stop_reason 与累计 output_tokens(真实值)
          - message_stop:结束

        流结束后组装等价于非流式的响应 dict,复用 _parse_response 标准化。

        Args:
            request: LLM 调用请求。
            on_chunk: 可选回调 on_chunk(text),可为同步函数或 coroutine 函数。

        Returns:
            LLMResponse: 与 chat() 结构一致的完整响应(含真实 usage)。
        """
        import inspect as _inspect

        messages = self._prepare_messages(request)
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        # 按 block index 登记 tool_use:id/name 固定,input 由 partial_json 增量拼出
        tu_slots: dict[int, dict] = {}
        input_tokens = 0
        output_tokens = 0
        stop_reason = "end_turn"
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
            async for frame in self._aiter_sse_events(request, messages):
                f_type = frame.get("type")

                if f_type == "message_start":
                    msg = frame.get("message") or {}
                    model_seen = msg.get("model") or model_seen
                    u = msg.get("usage") or {}
                    # 真实输入 token 计数(message_start 事件)
                    input_tokens = int(u.get("input_tokens", 0) or 0)
                    output_tokens = int(u.get("output_tokens", 0) or 0)

                elif f_type == "content_block_start":
                    cb = frame.get("content_block") or {}
                    if cb.get("type") == "tool_use":
                        idx = frame.get("index", 0)
                        tu_slots[idx] = {
                            "id": cb.get("id", ""),
                            "name": cb.get("name", ""),
                            "_json": "",
                        }

                elif f_type == "content_block_delta":
                    delta = frame.get("delta") or {}
                    d_type = delta.get("type")
                    if d_type == "text_delta":
                        await _emit(delta.get("text", ""))
                    elif d_type == "thinking_delta":
                        t = delta.get("thinking", "")
                        if t:
                            reasoning_parts.append(t)
                    elif d_type == "input_json_delta":
                        slot = tu_slots.get(frame.get("index", 0))
                        if slot is not None:
                            slot["_json"] += delta.get("partial_json", "")

                elif f_type == "message_delta":
                    delta = frame.get("delta") or {}
                    if delta.get("stop_reason"):
                        stop_reason = delta["stop_reason"]
                    u = frame.get("usage") or {}
                    # 真实输出 token 计数(message_delta 事件,累计值)
                    if u.get("output_tokens") is not None:
                        output_tokens = int(u.get("output_tokens") or 0)

                elif f_type == "message_stop":
                    break

                elif f_type == "error":
                    err = frame.get("error") or {}
                    raise LLMError(
                        f"[{self._name}] stream error event: {err.get('type', 'unknown')}"
                        f": {err.get('message', '')}"
                    )
        except Exception as exc:
            # 已向外发过正文中途断流:无安全重试点,直接上抛
            raise LLMError(
                f"[{self._name}] stream_chat_full failed: {exc}"
            ) from exc

        # 组装成等价非流式响应结构,复用 _parse_response 标准化解构
        blocks: list[dict[str, Any]] = []
        if reasoning_parts:
            blocks.append({"type": "thinking", "thinking": "".join(reasoning_parts)})
        text_content = "".join(content_parts)
        if text_content:
            blocks.append({"type": "text", "text": text_content})
        for idx in sorted(tu_slots):
            s = tu_slots[idx]
            # 工具参数宽容解析(修复非法 JSON 转义,复用 openai.py 工具函数)
            blocks.append(
                {
                    "type": "tool_use",
                    "id": s["id"],
                    "name": s["name"],
                    "input": _parse_tool_args_json(s["_json"]),
                }
            )
        data: dict[str, Any] = {
            "model": model_seen or request.model or self._model_name,
            "content": blocks,
            "stop_reason": stop_reason,
            # 真实 usage(message_start + message_delta);取不到时为 0,
            # 由基类 chat/stream_chat_full 兜底粗估
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }
        response = self._parse_response(data)
        response.model = response.model or self._model_name
        if response.usage.total_tokens == 0:
            response.usage = self._estimate_usage(messages, response.content)
        return response


__all__ = ["AnthropicProvider"]
