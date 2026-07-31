"""zhua_client 异常类层级

所有 SDK 错误都继承自 ZhuaError,便于调用方一次性捕获。
按 HTTP 语义分为:
- ZhuaAuthError:    401 / 403(鉴权/权限问题)
- ZhuaQuotaError:   429(配额耗尽,需退避)
- ZhuaNotFoundError:404(资源不存在/任务不属于当前主体)
- ZhuaServerError:  5xx(服务端异常,可重试)
- ZhuaRequestError: 其他 4xx(请求参数问题)
- ZhuaConnectionError: 网络层异常(连接失败/超时/WS 断开)

每个异常保留 request_id(从响应 header X-Request-ID 透传),便于服务端排查。
"""

from __future__ import annotations

from typing import Any


class ZhuaError(Exception):
    """所有 SDK 异常的基类

    Attributes:
        message:    错误描述
        status_code: HTTP 状态码(网络层异常时为 None)
        request_id: 请求 ID(从响应 header 透传,便于服务端排查)
        response:   原始响应对象(httpx.Response),便于调用方取更多上下文
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.response = response

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " | ".join(parts)


class ZhuaAuthError(ZhuaError):
    """鉴权失败(401)或权限不足(403)"""


class ZhuaQuotaError(ZhuaError):
    """配额耗尽(429),调用方应退避并重试"""


class ZhuaNotFoundError(ZhuaError):
    """资源不存在(404),常见于任务不属于当前主体或 task_id 错误"""


class ZhuaRequestError(ZhuaError):
    """请求参数错误(其他 4xx)"""


class ZhuaServerError(ZhuaError):
    """服务端错误(5xx),通常可重试"""


class ZhuaConnectionError(ZhuaError):
    """网络层异常(连接失败 / 超时 / WS 断开)"""


__all__ = [
    "ZhuaAuthError",
    "ZhuaConnectionError",
    "ZhuaError",
    "ZhuaNotFoundError",
    "ZhuaQuotaError",
    "ZhuaRequestError",
    "ZhuaServerError",
]
