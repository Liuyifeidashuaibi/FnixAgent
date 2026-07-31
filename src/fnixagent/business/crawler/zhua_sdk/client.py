"""ZhuaClient - ZhuaCrawler Python SDK(同步 + 异步双模式)

设计要点:
- 同步方法用 httpx.Client,方法名:scrape/extract/agent/task_create/...
- 异步方法用 httpx.AsyncClient,方法名加 a 前缀:async_scrape/async_extract/...
- 流式方法 task_stream 用 websockets 库连接 WS /v1/stream/{task_id}
- 上下文管理器:with ZhuaClient(...) as client: 自动关闭底层 HTTP 连接
- 自动鉴权:提供 operator_token 时自动调用 /v1/token 获取 JWT
- 自动重试:5xx 错误指数退避重试 3 次
- request_id 透传:从响应 header X-Request-ID 读取并保留在异常中
- 异常分级:ZhuaAuthError / ZhuaQuotaError / ZhuaNotFoundError / ZhuaServerError / ...

典型用法:
    # 同步
    with ZhuaClient(base_url="http://localhost:8000", operator_token="...") as client:
        result = client.scrape("https://example.com/")

    # 异步
    async with ZhuaClient(base_url="http://localhost:8000", operator_token="...") as client:
        result = await client.async_scrape("https://example.com/")

    # 流式
    for event in client.task_stream("task-123"):
        print(event)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from types import TracebackType
from typing import Any

import httpx

from .exceptions import (
    ZhuaAuthError,
    ZhuaConnectionError,
    ZhuaError,
    ZhuaNotFoundError,
    ZhuaQuotaError,
    ZhuaRequestError,
    ZhuaServerError,
)
from .models import (
    AgentResponse,
    ExtractResponse,
    HealthResponse,
    ReverseApiResponse,
    ScrapeResponse,
    TaskCancelResponse,
    TaskCreateResponse,
    TaskResultResponse,
    TaskStatusResponse,
)

__version__ = "0.1.0"

# 默认请求头
_DEFAULT_USER_AGENT = f"zhua-client-python/{__version__}"

# 请求 ID 响应头(与服务端约定)
_REQUEST_ID_HEADER = "X-Request-ID"

# 5xx 自动重试配置
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5  # 指数退避基数(秒):0.5, 1, 2


class ZhuaClient:
    """ZhuaCrawler Python SDK 客户端

    同步与异步方法并存,可按需选用。上下文管理器自动释放底层连接。

    Args:
        base_url:        服务地址,默认 http://localhost:8000
        token:           已有 JWT(与 operator_token 二选一,优先使用 token)
        operator_token:  运维静态令牌;提供时自动调用 /v1/token 换取 JWT
        timeout:         HTTP 超时(秒)
        max_retries:     5xx 重试次数(默认 3)
        headers:         自定义请求头(覆盖默认)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: str | None = None,
        operator_token: str | None = None,
        timeout: float = 60.0,
        max_retries: int = _MAX_RETRIES,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.operator_token = operator_token
        # 内部缓存的 JWT
        self._token: str | None = token
        # [P1] token 过期管理：临近过期(>80% TTL)时自动刷新
        self._token_issued_at: float = 0.0
        self._token_ttl: float = 3600.0
        # 默认请求头
        self._default_headers: dict[str, str] = {
            "User-Agent": _DEFAULT_USER_AGENT,
            "Accept": "application/json",
        }
        if headers:
            self._default_headers.update(headers)

        # 同步 / 异步客户端(惰性创建)
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------ #
    # 上下文管理器(同步)
    # ------------------------------------------------------------------ #
    def __enter__(self) -> ZhuaClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # 上下文管理器(异步)
    # ------------------------------------------------------------------ #
    async def __aenter__(self) -> ZhuaClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ #
    # 资源释放
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        """关闭同步 HTTP 客户端"""
        if self._sync_client is not None:
            try:
                self._sync_client.close()
            except Exception:
                pass
            self._sync_client = None

    async def aclose(self) -> None:
        """关闭异步 HTTP 客户端"""
        if self._async_client is not None:
            try:
                await self._async_client.aclose()
            except Exception:
                pass
            self._async_client = None

    # ------------------------------------------------------------------ #
    # 鉴权
    # ------------------------------------------------------------------ #
    def _is_token_expired(self) -> bool:
        """token 不存在或已临近过期(超过 80% TTL)时返回 True,触发刷新。"""
        if not self._token:
            return True
        if self._token_ttl <= 0:
            return False
        return (time.monotonic() - self._token_issued_at) > self._token_ttl * 0.8

    def _auth_headers(self) -> dict[str, str]:
        """构造鉴权请求头(就近过期自动刷新 JWT)"""
        headers: dict[str, str] = {}
        if self._is_token_expired() and self.operator_token:
            try:
                self._fetch_token_sync()
            except ZhuaError:
                pass  # 刷新失败则退化为使用可能仍有效的旧 token
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _auth_headers_async(self) -> dict[str, str]:
        """异步构造鉴权请求头(就近过期自动刷新 JWT)"""
        headers: dict[str, str] = {}
        if self._is_token_expired() and self.operator_token:
            try:
                await self._fetch_token_async()
            except ZhuaError:
                pass  # 刷新失败则退化为使用可能仍有效的旧 token
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _fetch_token_sync(self) -> None:
        """同步获取 JWT(用 operator_token 调用 /v1/token)"""
        try:
            client = self._get_sync_client()
            resp = client.post(
                "/v1/token",
                json={"operator_token": self.operator_token},
                headers={"Accept": "application/json"},
            )
            request_id = resp.headers.get(_REQUEST_ID_HEADER)
            if resp.status_code >= 400:
                raise _build_error(
                    f"获取 token 失败: HTTP {resp.status_code}",
                    resp,
                    request_id,
                )
            data = resp.json()
            self._token = data.get("access_token")
            self._token_issued_at = time.monotonic()
            self._token_ttl = float(data.get("expires_in") or 3600)
        except ZhuaError:
            raise
        except httpx.HTTPError as e:
            raise ZhuaConnectionError(f"获取 token 网络异常: {e}") from e

    async def _fetch_token_async(self) -> None:
        """异步获取 JWT"""
        try:
            client = await self._get_async_client()
            resp = await client.post(
                "/v1/token",
                json={"operator_token": self.operator_token},
                headers={"Accept": "application/json"},
            )
            request_id = resp.headers.get(_REQUEST_ID_HEADER)
            if resp.status_code >= 400:
                raise _build_error(
                    f"获取 token 失败: HTTP {resp.status_code}",
                    resp,
                    request_id,
                )
            data = resp.json()
            self._token = data.get("access_token")
            self._token_issued_at = time.monotonic()
            self._token_ttl = float(data.get("expires_in") or 3600)
        except ZhuaError:
            raise
        except httpx.HTTPError as e:
            raise ZhuaConnectionError(f"获取 token 网络异常: {e}") from e

    # ------------------------------------------------------------------ #
    # 底层 HTTP 客户端(惰性创建)
    # ------------------------------------------------------------------ #
    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._default_headers,
            )
        return self._sync_client

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._default_headers,
            )
        return self._async_client

    # ------------------------------------------------------------------ #
    # 同步方法
    # ------------------------------------------------------------------ #
    def scrape(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """单页抓取(POST /v1/scrape)"""
        payload = _build_scrape_payload(url, kwargs)
        return self._request_sync("POST", "/v1/scrape", json=payload)

    def extract(
        self,
        url: str,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """LLM 提取(POST /v1/extract)"""
        payload: dict[str, Any] = {"url": url}
        if schema is not None:
            payload["schema"] = schema
        payload.update(kwargs)
        return self._request_sync("POST", "/v1/extract", json=payload)

    def agent(self, url: str, task: str, **kwargs: Any) -> dict[str, Any]:
        """Agent 多步(POST /v1/agent)"""
        payload = {"url": url, "task": task, **kwargs}
        return self._request_sync("POST", "/v1/agent", json=payload)

    def task_create(self, urls: list[str], **kwargs: Any) -> dict[str, Any]:
        """批量任务(POST /v1/task)"""
        payload = {"urls": urls, **kwargs}
        return self._request_sync("POST", "/v1/task", json=payload)

    def task_status(self, task_id: str) -> dict[str, Any]:
        """查任务状态(GET /v1/task/{task_id})"""
        return self._request_sync("GET", f"/v1/task/{task_id}")

    def task_result(self, task_id: str) -> dict[str, Any]:
        """取任务结果(GET /v1/task/{task_id}/result)"""
        return self._request_sync("GET", f"/v1/task/{task_id}/result")

    def task_cancel(self, task_id: str) -> dict[str, Any]:
        """取消任务(DELETE /v1/task/{task_id})"""
        return self._request_sync("DELETE", f"/v1/task/{task_id}")

    def reverse_api(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """API 嗅探(POST /v1/reverse-api)"""
        payload = {"url": url, **kwargs}
        return self._request_sync("POST", "/v1/reverse-api", json=payload)

    def health(self) -> dict[str, Any]:
        """健康检查(GET /v1/health)"""
        return self._request_sync("GET", "/v1/health")

    def task_stream(self, task_id: str) -> Iterator[dict[str, Any]]:
        """流式订阅任务事件(WS /v1/stream/{task_id})

        同步生成器,内部用 websockets.sync.client.connect。
        每条事件为 dict;连接断开时抛 ZhuaConnectionError。
        """
        try:
            from websockets.sync.client import connect  # type: ignore[import-untyped]
        except ImportError as e:
            raise ZhuaConnectionError(
                "未安装 websockets 库,无法使用流式接口。请 pip install websockets"
            ) from e

        ws_url = self._ws_url(task_id)
        # 构造鉴权头(websockets 用 additional_headers)
        headers: list[tuple[str, str]] = []
        auth = self._auth_headers().get("Authorization")
        if auth:
            headers.append(("Authorization", auth))

        try:
            with connect(ws_url, additional_headers=headers) as ws:  # type: ignore[call-arg]
                for raw in ws:
                    try:
                        event = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    yield event
        except Exception as e:
            raise ZhuaConnectionError(f"WS 连接异常: {e}") from e

    # ------------------------------------------------------------------ #
    # 异步方法
    # ------------------------------------------------------------------ #
    async def async_scrape(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """单页抓取(异步)"""
        payload = _build_scrape_payload(url, kwargs)
        return await self._request_async("POST", "/v1/scrape", json=payload)

    async def async_extract(
        self,
        url: str,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """LLM 提取(异步)"""
        payload: dict[str, Any] = {"url": url}
        if schema is not None:
            payload["schema"] = schema
        payload.update(kwargs)
        return await self._request_async("POST", "/v1/extract", json=payload)

    async def async_agent(self, url: str, task: str, **kwargs: Any) -> dict[str, Any]:
        """Agent 多步(异步)"""
        payload = {"url": url, "task": task, **kwargs}
        return await self._request_async("POST", "/v1/agent", json=payload)

    async def async_task_create(self, urls: list[str], **kwargs: Any) -> dict[str, Any]:
        """批量任务(异步)"""
        payload = {"urls": urls, **kwargs}
        return await self._request_async("POST", "/v1/task", json=payload)

    async def async_task_status(self, task_id: str) -> dict[str, Any]:
        """查任务状态(异步)"""
        return await self._request_async("GET", f"/v1/task/{task_id}")

    async def async_task_result(self, task_id: str) -> dict[str, Any]:
        """取任务结果(异步)"""
        return await self._request_async("GET", f"/v1/task/{task_id}/result")

    async def async_task_cancel(self, task_id: str) -> dict[str, Any]:
        """取消任务(异步)"""
        return await self._request_async("DELETE", f"/v1/task/{task_id}")

    async def async_reverse_api(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """API 嗅探(异步)"""
        payload = {"url": url, **kwargs}
        return await self._request_async("POST", "/v1/reverse-api", json=payload)

    async def async_health(self) -> dict[str, Any]:
        """健康检查(异步)"""
        return await self._request_async("GET", "/v1/health")

    async def async_task_stream(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        """流式订阅任务事件(异步生成器)"""
        try:
            import websockets  # type: ignore[import-untyped]
        except ImportError as e:
            raise ZhuaConnectionError(
                "未安装 websockets 库,无法使用流式接口。请 pip install websockets"
            ) from e

        ws_url = self._ws_url(task_id)
        headers: dict[str, str] = {}
        auth = (await self._auth_headers_async()).get("Authorization")
        if auth:
            headers["Authorization"] = auth

        try:
            async with websockets.connect(ws_url, additional_headers=headers) as ws:  # type: ignore[call-arg]
                async for raw in ws:
                    try:
                        event = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    yield event
        except Exception as e:
            raise ZhuaConnectionError(f"WS 连接异常: {e}") from e

    # ------------------------------------------------------------------ #
    # 内部:请求执行(含重试与异常映射)
    # ------------------------------------------------------------------ #
    def _request_sync(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """同步请求(带 5xx 重试)"""
        client = self._get_sync_client()
        last_exc: ZhuaError | None = None
        for attempt in range(self.max_retries + 1):
            # 每次重试都刷新鉴权头(token 可能过期)
            headers = kwargs.pop("headers", None) or {}
            headers.update(self._auth_headers())
            try:
                resp = client.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as e:
                last_exc = ZhuaConnectionError(f"网络异常: {e}")
                if attempt < self.max_retries:
                    time.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
                    continue
                raise last_exc

            request_id = resp.headers.get(_REQUEST_ID_HEADER)
            if 200 <= resp.status_code < 300:
                # 成功:返回 JSON(若非 JSON 则包装)
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    data = {"text": resp.text, "status_code": resp.status_code}
                # 透传 request_id
                if isinstance(data, dict) and request_id:
                    data.setdefault("request_id", request_id)
                return data

            # 错误状态码:映射异常
            err = _build_error(_extract_error_message(resp), resp, request_id)
            # 5xx 才重试
            if 500 <= resp.status_code < 600 and attempt < self.max_retries:
                last_exc = err
                time.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
                continue
            raise err
        # 理论不可达(循环要么 return 要么 raise)
        if last_exc:
            raise last_exc
        raise ZhuaError("未知错误:重试循环结束但未返回结果")

    async def _request_async(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """异步请求(带 5xx 重试)"""
        client = await self._get_async_client()
        last_exc: ZhuaError | None = None
        for attempt in range(self.max_retries + 1):
            headers = kwargs.pop("headers", None) or {}
            headers.update(await self._auth_headers_async())
            try:
                resp = await client.request(method, path, headers=headers, **kwargs)
            except httpx.HTTPError as e:
                last_exc = ZhuaConnectionError(f"网络异常: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
                    continue
                raise last_exc

            request_id = resp.headers.get(_REQUEST_ID_HEADER)
            if 200 <= resp.status_code < 300:
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    data = {"text": resp.text, "status_code": resp.status_code}
                if isinstance(data, dict) and request_id:
                    data.setdefault("request_id", request_id)
                return data

            err = _build_error(_extract_error_message(resp), resp, request_id)
            if 500 <= resp.status_code < 600 and attempt < self.max_retries:
                last_exc = err
                await asyncio.sleep(_RETRY_BACKOFF_BASE * (2**attempt))
                continue
            raise err
        if last_exc:
            raise last_exc
        raise ZhuaError("未知错误:重试循环结束但未返回结果")

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def _ws_url(self, task_id: str) -> str:
        """构造 WebSocket URL(http(s) -> ws(s))"""
        base = self.base_url
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = base
        return f"{ws_base}/v1/stream/{task_id}"


# --------------------------------------------------------------------------- #
# 模块级工具函数
# --------------------------------------------------------------------------- #
def _build_scrape_payload(url: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """构造 scrape 请求体"""
    payload: dict[str, Any] = {"url": url}
    # 支持的关键字参数(与 ScrapeRequest 字段对齐)
    # 注意：zhua 服务端字段为 fit_markdown，SDK 入参兼容 fit / fit_markdown 两种写法
    key_map = {
        "adapter": "adapter",
        "output": "output",
        "fit": "fit_markdown",
        "fit_markdown": "fit_markdown",
        "screenshot": "screenshot",
        "wait_for": "wait_for",
        "timeout": "timeout",
        "impersonate": "impersonate",
        "proxy": "proxy",
    }
    for src, dst in key_map.items():
        if src in kwargs and kwargs[src] is not None:
            payload[dst] = kwargs[src]
    # 允许透传其他自定义字段
    for k, v in kwargs.items():
        if k not in payload:
            payload[k] = v
    return payload


def _build_error(message: str, resp: httpx.Response, request_id: str | None) -> ZhuaError:
    """按 HTTP 状态码构造对应的异常"""
    status = resp.status_code
    if status in (401, 403):
        return ZhuaAuthError(message, status_code=status, request_id=request_id, response=resp)
    if status == 404:
        return ZhuaNotFoundError(message, status_code=status, request_id=request_id, response=resp)
    if status == 429:
        return ZhuaQuotaError(message, status_code=status, request_id=request_id, response=resp)
    if 500 <= status < 600:
        return ZhuaServerError(message, status_code=status, request_id=request_id, response=resp)
    if 400 <= status < 500:
        return ZhuaRequestError(message, status_code=status, request_id=request_id, response=resp)
    return ZhuaError(message, status_code=status, request_id=request_id, response=resp)


def _extract_error_message(resp: httpx.Response) -> str:
    """从错误响应中提取错误描述(detail / message / 文本)"""
    try:
        data = resp.json()
        if isinstance(data, dict):
            for key in ("detail", "message", "error", "reason"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    return val
            return json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        pass
    text = resp.text.strip()
    if text:
        return text[:500]
    return f"HTTP {resp.status_code}"


__all__ = [
    "ZhuaClient",
    "__version__",
    # 重导出异常与模型,便于 from zhua_client import ZhuaError
    "ZhuaError",
    "ZhuaAuthError",
    "ZhuaQuotaError",
    "ZhuaNotFoundError",
    "ZhuaRequestError",
    "ZhuaServerError",
    "ZhuaConnectionError",
    "ScrapeResponse",
    "ExtractResponse",
    "AgentResponse",
    "TaskCreateResponse",
    "TaskStatusResponse",
    "TaskResultResponse",
    "TaskCancelResponse",
    "ReverseApiResponse",
    "HealthResponse",
]
