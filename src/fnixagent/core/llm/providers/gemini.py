"""
LLM Provider 适配器 - Google Gemini generateContent 原生协议。

适用于 Gemini 系列模型 (gemini-2.5-pro / gemini-2.5-flash 等),
直连 Google Generative Language API,不走 OpenAI 兼容层。

协议要点:
  - 鉴权:x-goog-api-key 请求头(非 Authorization Bearer)
  - 端点:/v1beta/models/{model}:generateContent(同步)
         /v1beta/models/{model}:streamGenerateContent?alt=sse(流式)
  - 消息格式:contents[{role: user|model, parts:[{text}|{functionCall}|{functionResponse}]}]
    (Gemini 只有 user/model 两种角色;assistant→model,
     工具结果以 user 角色 functionResponse part 回传)
   - system 提示词走顶层 systemInstruction 字段
   - safetySettings 可选透传(默认不传,用服务端默认安全阈值)
   - 结构化输出:response_format 映射为 generationConfig.responseMimeType
     ("application/json"),json_schema 内含 schema 对象时再映射
     generationConfig.responseSchema
  - 流式 SSE 每帧为一个增量 GenerateContentResponse
  - usage 从 usageMetadata.promptTokenCount/candidatesTokenCount 取真实值

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

# finishReason → OpenAI 风格 finish_reason 映射
_FINISH_REASON_MAP = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
    "BLOCKLIST": "content_filter",
    "PROHIBITED_CONTENT": "content_filter",
    "SPII": "content_filter",
}


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini generateContent 原生 Provider。

    直接对接 https://generativelanguage.googleapis.com 的
    generateContent / streamGenerateContent 接口,实现完整的
    x-goog-api-key 鉴权、contents/roles 转换、systemInstruction、
    可选 safetySettings、SSE 流式解析与真实 usageMetadata 回填。

    用法:
        provider = GeminiProvider(
            api_key="your-key",
            model_name="gemini-2.5-flash",
        )
        router.register(provider)   # 无缝接入 Router 的 failover/熔断/限流
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com",
        timeout: float = 120.0,
        max_retries: int = 3,
        safety_settings: list[dict] | None = None,
    ):
        """初始化 Gemini Provider。

        Args:
            api_key: Google API Key;为空时回退到环境变量 GEMINI_API_KEY /
                GOOGLE_API_KEY。
            model_name: 默认模型名(gemini-2.5-flash 等)。
            base_url: API 基础 URL(末尾 / 可选,兼容自建网关/代理)。
            timeout: 请求超时秒数,必须为正。
            max_retries: 最大重试次数(仅对 5xx/429/网络错误重试),必须为非负整数。
            safety_settings: 可选 SafetySetting 列表,原样透传为请求体
                safetySettings 字段;None 表示使用 Google 服务端默认阈值。

        Raises:
            TypeError: timeout/max_retries 类型错误。
            ValueError: timeout 非正或 max_retries 为负。
        """
        super().__init__(name="gemini", model_name=model_name)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError(f"timeout must be numeric, got {type(timeout).__name__}")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError(f"max_retries must be int, got {type(max_retries).__name__}")
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        self._api_key = (
            api_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        )
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._safety_settings = list(safety_settings) if safety_settings else None
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
                raise LLMError("httpx is required for GeminiProvider") from exc
            import ssl as _ssl

            _ssl_ctx = _ssl.create_default_context()
            _legacy_reneg = getattr(_ssl, "OP_LEGACY_SERVER_CONNECT", None)
            if _legacy_reneg is not None:
                _ssl_ctx.options |= _legacy_reneg
            self._client = httpx.Client(timeout=self._timeout, verify=_ssl_ctx)
        return self._client

    def _headers(self) -> dict[str, str]:
        """构建请求头:x-goog-api-key(Gemini 协议要求的鉴权方式)。"""
        return {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    def _endpoint(self, request: LLMRequest, stream: bool) -> str:
        """构建模型端点 URL。

        Args:
            request: LLM 调用请求。
            stream: True 返回 streamGenerateContent(?alt=sse),否则 generateContent。
        """
        # 兼容用户传入 "models/gemini-xxx" 或裸模型名两种写法
        model = (request.model or self._model_name).removeprefix("models/")
        method = "streamGenerateContent" if stream else "generateContent"
        url = f"{self._base_url}/v1beta/models/{model}:{method}"
        if stream:
            # alt=sse:强制服务端以 SSE 分帧输出
            url += "?alt=sse"
        return url

    @staticmethod
    def _classify_error(exc: Exception) -> tuple[bool, str]:
        """将异常分类为可重试/不可重试,并返回脱敏后的错误描述。

        Gemini 错误体形如 {"error": {"code": 429, "message": ..., "status": ...}},
        与 openai.py 相同按 HTTP 状态码分类。
        """
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

    def _build_payload(
        self, request: LLMRequest, messages: list[dict], stream: bool
    ) -> dict[str, Any]:
        """将通用消息列表转换为 Gemini generateContent 请求体。

        转换规则:
          - system 角色消息合并为顶层 systemInstruction.parts[].text
          - assistant → role="model";其 tool_calls 转 functionCall part
          - role=tool → role="user" + functionResponse part(按 name 关联回执)
          - 连续同角色 contents 自动合并

        Args:
            request: LLM 调用请求。
            messages: 已预处理的 OpenAI 风格消息 dict 列表。
            stream: 是否流式调用(仅影响日志语义,payload 结构相同)。

        Returns:
            Gemini generateContent 请求体 dict。
        """
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "") or ""

            # system → 顶层 systemInstruction
            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            parts: list[dict[str, Any]] = []
            g_role = "user"
            if role == "assistant":
                g_role = "model"
                if content:
                    parts.append({"text": content})
                # assistant 声明的工具调用 → functionCall part
                for tc in m.get("tool_calls") or []:
                    fn = tc.get("function") or {}
                    args_raw = fn.get("arguments", {})
                    if isinstance(args_raw, str):
                        args = _parse_tool_args_json(args_raw)
                    elif isinstance(args_raw, dict):
                        args = args_raw
                    else:
                        args = {"value": args_raw} if args_raw is not None else {}
                    parts.append({"functionCall": {"name": fn.get("name", ""), "args": args}})
            elif role == "tool":
                # 工具执行结果 → user 角色的 functionResponse part
                # response 必须是 JSON object:非 JSON 内容包装成 {"result": ...}
                try:
                    resp_val = json.loads(content)
                    if not isinstance(resp_val, dict):
                        resp_val = {"result": resp_val}
                except (json.JSONDecodeError, TypeError):
                    resp_val = {"result": content}
                parts.append(
                    {
                        "functionResponse": {
                            "name": m.get("name") or m.get("tool_call_id") or "tool",
                            "response": resp_val,
                        }
                    }
                )
            else:  # user
                parts.append({"text": content})

            if not parts:
                continue

            # 合并连续同角色 contents(Gemini 期望 user/model 交替)
            if contents and contents[-1]["role"] == g_role:
                contents[-1]["parts"].extend(parts)
            else:
                contents.append({"role": g_role, "parts": parts})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }

        # 结构化输出映射(OpenAI response_format → Gemini generationConfig):
        #   - 任意 json_object/json_schema 类型 → responseMimeType="application/json"
        #   - json_schema 内含 schema 对象 → 映射为 responseSchema
        #     (兼容两种形态:{"json_schema":{"schema":{...}}} 标准包装,
        #      或 {"json_schema":{...}} 直接就是 schema 对象)
        rf = getattr(request, "response_format", None)
        if isinstance(rf, dict) and rf.get("type") in ("json_object", "json_schema"):
            payload["generationConfig"]["responseMimeType"] = "application/json"
            schema = GeminiProvider._extract_json_schema(rf)
            if schema is not None:
                payload["generationConfig"]["responseSchema"] = schema

        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if request.stop:
            payload["generationConfig"]["stopSequences"] = request.stop

        # tools 转换:OpenAI function 格式 → functionDeclarations
        if request.tools:
            declarations = []
            for t in request.tools:
                fn = t.get("function") or {} if isinstance(t, dict) else {}
                if not fn:
                    continue
                declarations.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters")
                        or {"type": "object", "properties": {}},
                    }
                )
            if declarations:
                payload["tools"] = [{"functionDeclarations": declarations}]

        # safetySettings 可选透传(构造参数优先,request.extra 可逐次覆盖)
        safety = self._safety_settings
        if request.extra and isinstance(request.extra.get("safetySettings"), list):
            safety = request.extra["safetySettings"]
        if safety:
            payload["safetySettings"] = safety

        # tool_choice 映射:functionCallingConfig(mode=AUTO/ANY/NONE)
        if request.tools and request.tool_choice != "auto":
            mode = {
                "none": "NONE",
                "required": "ANY",
            }.get(request.tool_choice)
            cfg: dict[str, Any] = {}
            if mode:
                cfg["mode"] = mode
            elif isinstance(request.tool_choice, dict):
                fn_name = (request.tool_choice.get("function") or {}).get("name")
                if fn_name:
                    cfg = {"mode": "ANY", "allowedFunctionNames": [fn_name]}
            if cfg:
                payload["toolConfig"] = {"functionCallingConfig": cfg}

        # 透传 provider 专属参数(如 topP/topK/candidateCount);不覆盖规范键
        if request.extra:
            for k, v in request.extra.items():
                if v is not None and k not in payload and k != "safetySettings":
                    payload[k] = v
        return payload

    @staticmethod
    def _extract_json_schema(response_format: dict) -> dict | None:
        """从 OpenAI 风格 json_schema 中提取 schema 对象(用于 responseSchema)。

        兼容两种形态:
          - {"type":"json_schema","json_schema":{"name":...,"schema":{...}}}
            (OpenAI 标准包装,取内层 schema)
          - {"type":"json_schema","json_schema":{"type":"object","properties":...}}
            (json_schema 本身就是 schema 对象)

        Returns:
            schema dict;无法识别时返回 None(仅保留 responseMimeType)。
        """
        js = response_format.get("json_schema")
        if not isinstance(js, dict):
            return None
        inner = js.get("schema")
        if isinstance(inner, dict):
            return inner
        # 无标准包装:若自身带 type/properties 等结构化特征则视为 schema 对象
        if "type" in js or "properties" in js:
            return js
        return None

    # -- 同步对话 -----------------------------------------------------------

    def _do_chat(self, request: LLMRequest, messages: list[dict]) -> LLMResponse:
        """调用 Gemini generateContent API。

        重试策略与 openai.py 一致:仅对 5xx 服务端错误、429 限流、网络层
        错误(httpx.RequestError)重试;4xx 客户端错误与响应解析错误立即抛出。

        Args:
            request: LLM 调用请求。
            messages: 已预处理的消息列表。

        Returns:
            LLMResponse: 解析后的响应(usage 为 API 真实回报值)。

        Raises:
            LLMError: API Key 未配置、HTTP 错误、被安全策略拦截等。
        """
        if not self._api_key:
            raise LLMError(f"[{self._name}] API key not configured")

        payload = self._build_payload(request, messages, stream=False)
        headers = self._headers()
        url = self._endpoint(request, stream=False)
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
        """解析 Gemini generateContent 响应为统一 LLMResponse。

        - parts[].text → content
        - parts[].functionCall → tool_calls(Gemini 无 call id,合成 call_{i})
        - usageMetadata → 真实 token 计数(thoughtsTokenCount 计入 completion)

        Args:
            data: 响应 JSON 解析后的 dict。

        Returns:
            LLMResponse: 统一响应结构。

        Raises:
            LLMError: 无 candidates(如被安全策略拦截且无候选)或结构非法。
        """
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            raise LLMError(f"[{self._name}] invalid candidates in response")
        if not candidates:
            # 无候选:通常是 promptFeedback.blockReason(安全拦截),给出可诊断信息
            feedback = data.get("promptFeedback") or {}
            reason = feedback.get("blockReason", "unknown")
            raise LLMError(f"[{self._name}] no candidates (blocked: {reason})")

        cand = candidates[0]
        cand_content = cand.get("content") or {}
        parts = cand_content.get("parts") or []
        if not isinstance(parts, list):
            parts = []

        content_parts: list[str] = []
        tool_calls: list[dict] = []
        for i, p in enumerate(parts):
            if not isinstance(p, dict):
                continue
            if "text" in p:
                content_parts.append(p.get("text", "") or "")
            fc = p.get("functionCall")
            if isinstance(fc, dict):
                # Gemini 不返回工具调用 id,合成稳定 id 供上层回传 tool 结果关联
                args = fc.get("args")
                if not isinstance(args, dict):
                    args = {"value": args} if args is not None else {}
                tool_calls.append(
                    {
                        "id": f"call_{i}",
                        "name": fc.get("name", ""),
                        "arguments": args,
                    }
                )

        # usageMetadata:Gemini 真实 token 计数
        usage_raw = data.get("usageMetadata") or {}
        prompt_tokens = int(usage_raw.get("promptTokenCount", 0) or 0)
        # thoughtsTokenCount(思考模型)不计入 candidatesTokenCount,
        # 但计入 totalTokenCount 且实际计费 — 并入 completion 保持账目一致
        completion_tokens = int(usage_raw.get("candidatesTokenCount", 0) or 0) + int(
            usage_raw.get("thoughtsTokenCount", 0) or 0
        )
        total_tokens = int(usage_raw.get("totalTokenCount", 0) or 0) or (
            prompt_tokens + completion_tokens
        )
        # P4.2: context cache 命中 token 数
        cached_tokens = int(usage_raw.get("cachedContentTokenCount", 0) or 0)

        finish_reason = _FINISH_REASON_MAP.get(cand.get("finishReason"), "stop")

        return LLMResponse(
            content="".join(content_parts),
            model=data.get("modelVersion", self._model_name),
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cached_tokens=cached_tokens,
            ),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw=data,
            reasoning_content="",
        )

    # -- 流式 ---------------------------------------------------------------

    async def _aiter_sse_events(
        self, request: LLMRequest, messages: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """逐条产出 Gemini 流式 SSE 数据帧(解析后的 JSON dict)。

        streamGenerateContent?alt=sse 的每个 data 行是一个增量的
        GenerateContentResponse(结构与非流式一致)。HTTP 错误在首个
        产出前抛出,保证调用方可以用"是否已产出 chunk"判断是否可安全重试。
        """
        if not self._api_key:
            raise LLMError(f"[{self._name}] API key not configured")

        payload = self._build_payload(request, messages, stream=True)
        headers = self._headers()
        url = self._endpoint(request, stream=True)
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
        """流式调用 Gemini streamGenerateContent,逐 chunk 产出正文文本。

        Yields:
            str: 模型生成的文本片段(text part delta)。
        """
        async for frame in self._aiter_sse_events(request, messages):
            candidates = frame.get("candidates") or []
            if not candidates:
                continue
            parts = (candidates[0].get("content") or {}).get("parts") or []
            for p in parts:
                if isinstance(p, dict) and "text" in p:
                    text = p.get("text")
                    if text:
                        yield text
            # 首个候选给出终止信号即结束(单候选场景)
            if candidates[0].get("finishReason"):
                break

    async def stream_chat_full(
        self,
        request: LLMRequest,
        on_chunk: Any = None,
    ) -> LLMResponse:
        """完整流式调用:逐 chunk 回调正文,同时累积 functionCall / usageMetadata。

        SSE 每帧结构与非流式一致:text part 即正文增量,functionCall part
        为完整工具调用(无增量拼接),usageMetadata 在尾帧给出真实累计计数,
        finishReason 出现在最后一个内容帧。

        Args:
            request: LLM 调用请求。
            on_chunk: 可选回调 on_chunk(text),可为同步函数或 coroutine 函数。

        Returns:
            LLMResponse: 与 chat() 结构一致的完整响应(含真实 usage)。
        """
        import inspect as _inspect

        messages = self._prepare_messages(request)
        content_parts: list[str] = []
        fc_parts: list[dict] = []  # 原样保留 functionCall part,交由 _parse_response 统一解析
        usage_data: dict = {}
        finish_reason = ""
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
                if frame.get("modelVersion"):
                    model_seen = frame["modelVersion"]
                # usageMetadata:每帧可能携带累计值,以最后一帧为准(真实 token 计数)
                if frame.get("usageMetadata"):
                    usage_data = frame["usageMetadata"]
                candidates = frame.get("candidates") or []
                if not candidates:
                    continue
                cand = candidates[0]
                parts = (cand.get("content") or {}).get("parts") or []
                for p in parts:
                    if not isinstance(p, dict):
                        continue
                    if "text" in p:
                        await _emit(p.get("text", ""))
                    if isinstance(p.get("functionCall"), dict):
                        fc_parts.append({"functionCall": p["functionCall"]})
                if cand.get("finishReason"):
                    finish_reason = cand["finishReason"]
        except Exception as exc:
            from fnixagent.core.exceptions import LLMError

            # 已向外发过正文中途断流:无安全重试点,直接上抛
            raise LLMError(
                f"[{self._name}] stream_chat_full failed: {exc}"
            ) from exc

        # 组装成等价非流式响应结构,复用 _parse_response 标准化解构
        parts_out: list[dict[str, Any]] = [{"text": "".join(content_parts)}]
        parts_out.extend(fc_parts)
        data: dict[str, Any] = {
            "candidates": [
                {
                    "content": {"parts": parts_out},
                    "finishReason": finish_reason or "STOP",
                }
            ],
            "usageMetadata": usage_data,
        }
        if model_seen:
            data["modelVersion"] = model_seen
        response = self._parse_response(data)
        response.model = response.model or self._model_name
        if response.usage.total_tokens == 0:
            response.usage = self._estimate_usage(messages, response.content)
        return response


__all__ = ["GeminiProvider"]
