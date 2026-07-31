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

from __future__ import annotations

import json
import os
import time
from typing import Any

from fnixagent.core.exceptions import LLMError
from fnixagent.core.llm.base import BaseLLMProvider, LLMRequest
from fnixagent.core.types import LLMResponse, MessageRole, TokenUsage

# 单次响应体大小上限(字节),超过则拒绝解析以防 OOM
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024  # 32 MiB


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
    ):
        """初始化 OpenAI 兼容 Provider。

        Args:
            name: provider 标识名(如 'glm' / 'openai'),亦用于读取环境变量 {NAME}_API_KEY。
            model_name: 默认模型名。
            api_key: API Key;为空时回退到环境变量 {NAME}_API_KEY。
            base_url: API 基础 URL(末尾 / 可选)。
            timeout: 请求超时秒数,必须为正。
            max_retries: 最大重试次数(仅对 5xx/429/网络错误重试),必须为非负整数。

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
        self._client = None  # 延迟初始化

    def _get_client(self):
        """延迟初始化 httpx 客户端(避免无网络环境启动失败)。"""
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise LLMError("httpx is required for OpenAICompatibleProvider") from exc
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

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

        # 构建请求体
        payload: dict[str, Any] = {
            "model": request.model or self._model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = request.tool_choice
        if request.stop:
            payload["stop"] = request.stop

        # Spec 2: 透传 provider 专属参数（如 DashScope enable_thinking / OpenAI reasoning_effort）
        # — request.extra 由上层 (LLMAdapter / AgenticLoop) 注入，用于触发思考模式
        # — 思考模式开启后，response.message.reasoning_content 会被 _parse_response 提取
        if request.extra:
            for k, v in request.extra.items():
                if v is not None and k not in payload:
                    payload[k] = v

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
            return retryable, f"HTTP {status}"
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
        # - Claude (Anthropic API): thinking blocks (需 adapter 转换)
        # - GLM-4.5/4.6: message.reasoning_content (启用 thinking 参数后)
        reasoning_content = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or message.get("thinking")
            or ""
        )
        if not isinstance(reasoning_content, str):
            # 某些 provider 可能返回 list[dict] (Anthropic thinking blocks)
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
                    args = json.loads(args_raw) if args_raw.strip() else {}
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
