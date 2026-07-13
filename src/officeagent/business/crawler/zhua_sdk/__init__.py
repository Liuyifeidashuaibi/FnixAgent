"""zhua_client SDK - ZhuaCrawler Python SDK(vendored)。

本目录为 zhua-crawler 项目 sdk/python/zhua_client 的 vendored 副本,
保留原 SDK 的完整代码结构,便于 OfficeAgent 直接 import 使用,无需额外安装。

子模块:
  - client:     ZhuaClient 同步+异步 HTTP 客户端
  - exceptions: ZhuaError 异常层级
  - models:     Pydantic 请求/响应模型

典型用法:
    from officeagent.business.crawler.zhua_sdk import ZhuaClient

    with ZhuaClient(base_url="http://localhost:8000", operator_token="...") as client:
        result = client.scrape("https://example.com/")

更新源: 若 zhua-crawler SDK 有更新,从原仓库同步本目录文件即可。
"""
from __future__ import annotations

from .client import ZhuaClient, __version__
from .exceptions import (
    ZhuaAuthError,
    ZhuaConnectionError,
    ZhuaError,
    ZhuaNotFoundError,
    ZhuaQuotaError,
    ZhuaRequestError,
    ZhuaServerError,
)

__all__ = [
    "ZhuaClient",
    "__version__",
    # 异常类(便于调用方精确捕获)
    "ZhuaError",
    "ZhuaAuthError",
    "ZhuaQuotaError",
    "ZhuaNotFoundError",
    "ZhuaRequestError",
    "ZhuaServerError",
    "ZhuaConnectionError",
]
