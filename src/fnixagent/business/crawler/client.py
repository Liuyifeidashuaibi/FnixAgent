"""爬虫系统瘦客户端。

核心约束:
  - 无状态:不维护 session/cookie,每次调用独立请求
  - 无缓存:不缓存任何响应
  - 无落盘:不写任何文件
  - 无本地存储:不存任何抓取内容
  - 审计最小化:仅记录调用元数据(路径/状态/耗时),不记录请求体/响应体

使用 httpx(可选依赖,缺失时降级到 urllib.request)。

重试策略:
  - 仅 retry_on_status(默认 500/502/503/504/429)+ 网络错误重试
  - 4xx 不重试(直接抛 CrawlerError)
  - 指数退避 + 抖动(retry_backoff 起始,retry_max_delay 封顶)

安全防护:
  - API Key 不打印(日志脱敏,仅记录路径/状态/耗时)
  - 请求超时(防无限等待)
  - 响应体大小限制(防 OOM,超限截断)
  - SSL 证书校验默认开启
  - 不记录请求体/响应体(隐私)

线程安全:
  - httpx.Client 内置线程安全(连接池加锁)
  - urllib 降级时每次新建连接(无共享状态)
"""

from __future__ import annotations

import dataclasses
import json
import logging
import random
import ssl
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from fnixagent.business.crawler.config import CrawlerConfig, load_config
from fnixagent.business.crawler.schema import (
    BatchRequest,
    BatchResponse,
    ExtractRequest,
    ExtractResponse,
    FetchRequest,
    FetchResponse,
    HealthStatus,
    RenderRequest,
    RenderResponse,
    SearchRequest,
    SearchResponse,
    SummaryRequest,
    SummaryResponse,
    TaskStatus,
)

# 尝试导入 httpx(与 business/web/fetcher.py 一致的降级模式)
try:
    import httpx

    _HAS_HTTPX = True
except ImportError:  # pragma: no cover
    _HAS_HTTPX = False
    httpx = None  # type: ignore

_logger = logging.getLogger(__name__)

# 读取响应体的 chunk 大小
_CHUNK_SIZE = 65536


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class CrawlerError(Exception):
    """爬虫客户端错误。

    Attributes:
        status_code: HTTP 状态码(网络错误时为 None)
        endpoint:    接口路径(如 /api/v1/fetch)
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


class _RetryableError(Exception):
    """内部:可重试错误(retry_on_status 状态码 / 网络错误)。

    不对外暴露,仅用于 _retry 内部控制流。

    Attributes:
        status_code: HTTP 状态码(网络错误时为 None)
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# CrawlerClient
# ---------------------------------------------------------------------------


class CrawlerClient:
    """爬虫系统瘦客户端。

    用法:
        client = CrawlerClient(CrawlerConfig(base_url="http://crawler:9100"))
        resp = client.fetch(FetchRequest(url="https://example.com"))
        client.close()

        # 或上下文管理器
        with CrawlerClient() as client:
            resp = client.fetch(...)

    Attributes:
        config: 客户端配置
    """

    def __init__(self, config: CrawlerConfig | None = None) -> None:
        """初始化。

        Args:
            config: 客户端配置;为 None 时从环境变量加载
        """
        self.config: CrawlerConfig = config if config is not None else load_config()
        # httpx.Client 懒初始化(避免 __init__ 阶段建立连接)
        self._client: Any = None
        self._client_lock = threading.Lock()
        self._closed = False

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def fetch(self, request: FetchRequest) -> FetchResponse:
        """POST /api/v1/fetch —— 抓取单个 URL。

        Args:
            request: 抓取请求

        Returns:
            FetchResponse

        Raises:
            CrawlerError: URL 为空 / timeout <= 0 / 4xx / 重试耗尽
        """
        self._validate_url(request.url, "/api/v1/fetch")
        self._validate_timeout(request.timeout, "/api/v1/fetch")
        data = self._request("POST", "/api/v1/fetch", json_body=dataclasses.asdict(request))
        return self._build_response(FetchResponse, data, "/api/v1/fetch")

    def render(self, request: RenderRequest) -> RenderResponse:
        """POST /api/v1/render —— 浏览器渲染。

        Args:
            request: 渲染请求

        Returns:
            RenderResponse

        Raises:
            CrawlerError: URL 为空 / timeout <= 0 / 4xx / 重试耗尽
        """
        self._validate_url(request.url, "/api/v1/render")
        self._validate_timeout(request.timeout, "/api/v1/render")
        data = self._request("POST", "/api/v1/render", json_body=dataclasses.asdict(request))
        return self._build_response(RenderResponse, data, "/api/v1/render")

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        """POST /api/v1/extract —— 内容提取。

        Args:
            request: 提取请求(html 与 url 至少一个非空)

        Returns:
            ExtractResponse

        Raises:
            CrawlerError: html 与 url 均为空 / 4xx / 重试耗尽
        """
        if not (request.html and request.html.strip()) and not (
            request.url and request.url.strip()
        ):
            raise CrawlerError(
                "ExtractRequest.html 与 ExtractRequest.url 至少一个非空",
                endpoint="/api/v1/extract",
            )
        data = self._request("POST", "/api/v1/extract", json_body=dataclasses.asdict(request))
        return self._build_response(ExtractResponse, data, "/api/v1/extract")

    def search(self, request: SearchRequest) -> SearchResponse:
        """POST /api/v1/search —— 搜索。

        Args:
            request: 搜索请求

        Returns:
            SearchResponse

        Raises:
            CrawlerError: query 为空 / 4xx / 重试耗尽
        """
        if not request.query or not request.query.strip():
            raise CrawlerError("SearchRequest.query 不能为空", endpoint="/api/v1/search")
        data = self._request("POST", "/api/v1/search", json_body=dataclasses.asdict(request))
        return self._build_response(SearchResponse, data, "/api/v1/search")

    def summary(self, request: SummaryRequest) -> SummaryResponse:
        """POST /api/v1/summary —— 摘要。

        Args:
            request: 摘要请求(url/html/text 至少一个非空)

        Returns:
            SummaryResponse

        Raises:
            CrawlerError: 输入全空 / 4xx / 重试耗尽
        """
        if not any(v and str(v).strip() for v in (request.url, request.html, request.text)):
            raise CrawlerError(
                "SummaryRequest.url/html/text 至少一个非空", endpoint="/api/v1/summary"
            )
        data = self._request("POST", "/api/v1/summary", json_body=dataclasses.asdict(request))
        return self._build_response(SummaryResponse, data, "/api/v1/summary")

    def submit_batch(self, request: BatchRequest) -> BatchResponse:
        """POST /api/v1/batch —— 提交批量任务(异步)。

        Args:
            request: 批量任务请求

        Returns:
            BatchResponse(含 task_id)

        Raises:
            CrawlerError: urls 为空 / 4xx / 重试耗尽
        """
        if not request.urls:
            raise CrawlerError("BatchRequest.urls 不能为空", endpoint="/api/v1/batch")
        data = self._request("POST", "/api/v1/batch", json_body=dataclasses.asdict(request))
        return self._build_response(BatchResponse, data, "/api/v1/batch")

    def get_task_status(self, task_id: str) -> TaskStatus:
        """GET /api/v1/task/{task_id} —— 查询任务状态。

        Args:
            task_id: 任务 ID(非空)

        Returns:
            TaskStatus

        Raises:
            CrawlerError: task_id 为空 / 4xx / 重试耗尽
        """
        if not task_id or not task_id.strip():
            raise CrawlerError("task_id 不能为空", endpoint="/api/v1/task")
        endpoint = f"/api/v1/task/{task_id}"
        data = self._request("GET", endpoint)
        return self._build_response(TaskStatus, data, endpoint)

    def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout: float = 600.0,
    ) -> TaskStatus:
        """轮询等待任务完成。

        Args:
            task_id:       任务 ID(非空)
            poll_interval: 轮询间隔(秒,必须 > 0)
            timeout:       最大等待时间(秒,必须 > 0)

        Returns:
            TaskStatus(status 为 completed/failed)

        Raises:
            CrawlerError: 参数非法 / 轮询超时 / 4xx / 重试耗尽
        """
        if not task_id or not task_id.strip():
            raise CrawlerError("task_id 不能为空", endpoint="/api/v1/task")
        if poll_interval <= 0:
            raise CrawlerError(f"poll_interval 必须 > 0, 实为 {poll_interval}")
        if timeout <= 0:
            raise CrawlerError(f"timeout 必须 > 0, 实为 {timeout}")

        deadline = time.monotonic() + timeout
        while True:
            status = self.get_task_status(task_id)
            if status.status in ("completed", "failed"):
                return status
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CrawlerError(
                    f"wait_for_task 超时({timeout}s): task_id={task_id}, "
                    f"last_status={status.status}",
                    endpoint="/api/v1/task",
                )
            time.sleep(min(poll_interval, remaining))

    def health(self) -> HealthStatus:
        """GET /api/v1/health —— 健康检查。

        连接失败时返回 unhealthy(不抛错,便于探活场景使用)。

        Returns:
            HealthStatus
        """
        try:
            data = self._request("GET", "/api/v1/health")
            return self._build_response(HealthStatus, data, "/api/v1/health")
        except CrawlerError as e:
            _logger.warning("crawler health check failed: %s", e)
            return HealthStatus(healthy=False)

    def close(self) -> None:
        """释放资源(关闭 httpx.Client)。"""
        if self._closed:
            return
        self._closed = True
        client = self._client
        self._client = None
        if client is not None and _HAS_HTTPX and isinstance(client, httpx.Client):
            try:
                client.close()
            except Exception as e:  # pragma: no cover
                _logger.debug("crawler httpx client close failed: %s", e)

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    def __enter__(self) -> CrawlerClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 内部:HTTP 请求
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """统一 HTTP 请求(含认证/超时/重试/响应大小限制)。

        - 构造 headers(认证 + User-Agent)
        - 发起请求(httpx 或 urllib 降级)
        - 重试(retry_on_status + 网络错误)
        - 响应体大小限制(max_response_size)
        - 审计日志(仅路径/状态/耗时,不含 body)
        - 错误处理(4xx 抛 CrawlerError,5xx/网络错误触发重试)
        - 返回 JSON dict

        Args:
            method:   HTTP 方法(GET/POST)
            endpoint: 接口路径(如 /api/v1/fetch)
            json_body:JSON 请求体(POST)
            params:   查询参数(GET)

        Returns:
            响应 JSON dict

        Raises:
            CrawlerError: 4xx / 重试耗尽 / JSON 解析失败
        """
        url = f"{self.config.base_url}{endpoint}"
        headers = self._build_headers()
        return self._retry(self._do_request, method, url, endpoint, headers, json_body, params)

    def _do_request(
        self,
        method: str,
        url: str,
        endpoint: str,
        headers: dict[str, str],
        json_body: dict | None,
        params: dict | None,
    ) -> dict:
        """单次 HTTP 请求(不含重试)。

        Raises:
            _RetryableError: retry_on_status 状态码 / 网络错误
            CrawlerError:    4xx / 5xx(非 retry_on_status) / JSON 解析失败
        """
        start = time.monotonic()
        if _HAS_HTTPX:
            status, text = self._do_httpx(method, url, headers, json_body, params)
        else:
            status, text = self._do_urllib(method, url, headers, json_body, params)

        elapsed_ms = (time.monotonic() - start) * 1000
        # 审计日志:仅记录路径/状态/耗时(不含 body,隐私保护)
        _logger.info("crawler %s %s -> %d %.1fms", method, endpoint, status, elapsed_ms)

        # 状态码分类
        if status in self.config.retry_on_status:
            raise _RetryableError(f"HTTP {status}", status_code=status)
        if 400 <= status < 500:
            raise CrawlerError(
                f"HTTP {status}: {text[:200]}", status_code=status, endpoint=endpoint
            )
        if status >= 500:
            raise CrawlerError(
                f"HTTP {status}: {text[:200]}", status_code=status, endpoint=endpoint
            )

        # 2xx:解析 JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise CrawlerError(f"JSON 解析失败: {e}", status_code=status, endpoint=endpoint) from e

    def _do_httpx(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict | None,
        params: dict | None,
    ) -> tuple[int, str]:
        """httpx 同步实现(流式读取 + 响应体大小限制)。

        Returns:
            (status_code, response_text)

        Raises:
            _RetryableError: 网络错误(httpx.RequestError / TimeoutException)
        """
        client = self._get_client()
        max_size = self.config.max_response_size
        try:
            with client.stream(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            ) as response:
                status = response.status_code
                # 流式读取响应体,超 max_size 截断
                chunks: list[bytes] = []
                size = 0
                truncated = False
                for chunk in response.iter_raw(chunk_size=_CHUNK_SIZE):
                    if size + len(chunk) > max_size:
                        remaining = max_size - size
                        if remaining > 0:
                            chunks.append(chunk[:remaining])
                        truncated = True
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                raw = b"".join(chunks)
                text = raw.decode("utf-8", errors="replace")
                if truncated:
                    _logger.warning(
                        "crawler response truncated to %d bytes (url=%s)",
                        max_size,
                        url,
                    )
                return status, text
        except httpx.RequestError as e:  # type: ignore[union-attr]
            raise _RetryableError(f"{type(e).__name__}: {e}") from e
        except httpx.TimeoutException as e:  # type: ignore[union-attr]
            raise _RetryableError(f"timeout: {e}") from e

    def _do_urllib(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict | None,
        params: dict | None,
    ) -> tuple[int, str]:
        """urllib 同步降级实现(httpx 不可用时)。

        每次新建连接(无连接复用),响应体大小限制。

        Returns:
            (status_code, response_text)

        Raises:
            _RetryableError: 网络错误(URLError / OSError / TimeoutError)
        """
        import urllib.request

        # 拼接查询参数
        full_url = url
        if params:
            full_url = f"{url}?{urlencode(params)}"

        # 请求体
        body_bytes: bytes | None = None
        if json_body is not None:
            body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers = {**headers, "Content-Type": "application/json"}

        # SSL 上下文
        ssl_context = ssl.create_default_context()
        if not self.config.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        max_size = self.config.max_response_size
        try:
            req = urllib.request.Request(full_url, data=body_bytes, method=method, headers=headers)
            try:
                resp = urllib.request.urlopen(req, timeout=self.config.timeout, context=ssl_context)
                status = resp.status if hasattr(resp, "status") else resp.code
                resp_stream = resp
            except HTTPError as e:
                # HTTPError 携带响应体,作为可读对象
                status = e.code
                resp_stream = e

            # 流式读取响应体,超 max_size 截断
            chunks: list[bytes] = []
            size = 0
            truncated = False
            while True:
                chunk = resp_stream.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if size + len(chunk) > max_size:
                    remaining = max_size - size
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                    truncated = True
                    break
                chunks.append(chunk)
                size += len(chunk)
            raw = b"".join(chunks)
            text = raw.decode("utf-8", errors="replace")
            if truncated:
                _logger.warning(
                    "crawler response truncated to %d bytes (url=%s)",
                    max_size,
                    full_url,
                )
            return status, text
        except (URLError, OSError, TimeoutError) as e:
            raise _RetryableError(f"{type(e).__name__}: {e}") from e

    # ------------------------------------------------------------------
    # 内部:重试 / headers / 客户端管理 / 辅助
    # ------------------------------------------------------------------

    def _retry(self, fn: Any, *args: Any, **kwargs: Any) -> dict:
        """重试包装(指数退避 + 抖动)。

        - _RetryableError:重试(retry_on_status / 网络错误)
        - CrawlerError:直接抛出(4xx,不可重试)

        Raises:
            CrawlerError: 重试耗尽或不可重试错误
        """
        total_attempts = self.config.max_retries + 1  # 首次 + 重试次数
        last_error: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except _RetryableError as e:
                last_error = e
                if attempt < total_attempts:
                    delay = self._compute_backoff(attempt)
                    _logger.info(
                        "crawler retry: attempt=%d/%d status=%s delay=%.2fs",
                        attempt,
                        total_attempts,
                        e.status_code,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                break
            except CrawlerError:
                # 4xx 等不可重试错误,直接抛出
                raise

        # 重试耗尽
        raise CrawlerError(
            f"重试耗尽({self.config.max_retries} 次): {last_error}",
            status_code=getattr(last_error, "status_code", None) if last_error else None,
        )

    def _build_headers(self) -> dict[str, str]:
        """构造请求头(认证 + User-Agent)。

        认证格式:`{api_key_header}: {api_key_prefix} {api_key}`
        (如 `Authorization: Bearer xxx`)

        Returns:
            请求头 dict
        """
        headers: dict[str, str] = {"User-Agent": self.config.user_agent}
        if self.config.api_key:
            prefix = self.config.api_key_prefix
            if prefix:
                headers[self.config.api_key_header] = f"{prefix} {self.config.api_key}"
            else:
                headers[self.config.api_key_header] = self.config.api_key
        return headers

    def _get_client(self) -> Any:
        """获取或创建 httpx.Client(懒初始化,线程安全)。

        Returns:
            httpx.Client 实例
        """
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    # _HAS_HTTPX 已在调用前判断,此处 httpx 必然可用
                    self._client = httpx.Client(  # type: ignore[union-attr]
                        verify=self.config.verify_ssl,
                        timeout=httpx.Timeout(  # type: ignore[union-attr]
                            self.config.timeout,
                            connect=self.config.connect_timeout,
                        ),
                        follow_redirects=True,
                    )
        return self._client

    def _compute_backoff(self, attempt: int) -> float:
        """计算重试退避时间(指数退避 + 抖动)。

        Args:
            attempt: 当前尝试序号(1 = 首次重试)

        Returns:
            退避秒数(0 ~ retry_max_delay)
        """
        base = min(
            self.config.retry_backoff * (2 ** (attempt - 1)),
            self.config.retry_max_delay,
        )
        # 抖动:±10% 避免重试风暴
        jitter = base * 0.1 * random.uniform(-1, 1)
        return max(0.0, base + jitter)

    # ------------------------------------------------------------------
    # 内部:参数校验 / 响应构造
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_url(url: str, endpoint: str) -> None:
        """URL 非空校验。"""
        if not isinstance(url, str) or not url.strip():
            raise CrawlerError("url 不能为空", endpoint=endpoint)

    @staticmethod
    def _validate_timeout(timeout: float, endpoint: str) -> None:
        """timeout > 0 校验。"""
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise CrawlerError(f"timeout 必须 > 0, 实为 {timeout}", endpoint=endpoint)

    @staticmethod
    def _build_response(
        response_cls: type,
        data: dict,
        endpoint: str,
    ) -> Any:
        """从 dict 构造响应 dataclass(过滤未知字段)。

        Args:
            response_cls: 响应 dataclass 类型
            data:         响应 dict
            endpoint:     接口路径(用于错误信息)

        Returns:
            响应 dataclass 实例

        Raises:
            CrawlerError: data 不是 dict
        """
        if not isinstance(data, dict):
            raise CrawlerError(f"响应不是 JSON 对象: {type(data).__name__}", endpoint=endpoint)
        valid_fields = {f.name for f in dataclasses.fields(response_cls)}
        kwargs = {k: v for k, v in data.items() if k in valid_fields}
        try:
            return response_cls(**kwargs)
        except TypeError as e:
            raise CrawlerError(f"响应字段不匹配: {e}", endpoint=endpoint) from e
