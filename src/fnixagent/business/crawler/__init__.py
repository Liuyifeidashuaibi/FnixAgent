"""爬虫系统瘦客户端(fnixagent ↔ 爬虫系统 HTTP 接口)。

核心约束:
  - 无状态:每次调用都是独立 HTTP 请求,不维护 session/cookie
  - 无缓存:不缓存任何响应数据
  - 无落盘:不写任何文件
  - 无本地存储:不存任何抓取内容
  - 仅调用:只发 HTTP 请求,接收响应,返回给调用方
  - 审计最小化:仅记录调用元数据(接口路径/状态码/耗时),不记录请求体/响应体

子模块:
  - schema:      接口契约(请求/响应 dataclass)
  - config:      配置层(CrawlerConfig,环境变量 / YAML 加载)
  - client:      瘦客户端核心(HTTP 调用,httpx 优先 + urllib 降级)
  - tools:       工具注册(crawler_* 工具,对接旧爬虫系统 /api/v1/*)
  - zhua_sdk:    zhua-crawler SDK(vendored,同步+异步双模式)
  - zhua_config: ZhuaConfig 配置层(环境变量 / YAML 的 zhua: 段)
  - zhua_tools:  工具注册(zhua_* 工具,对接 zhua-crawler /v1/*)

两套爬虫系统并存:
  1. 旧爬虫系统(CrawlerConfig + crawler_* 工具,端口 9100,/api/v1/* 接口)
     POST /api/v1/fetch          抓取单个 URL(返回 HTML)
     POST /api/v1/render         浏览器渲染(JS 执行后返回 HTML)
     POST /api/v1/extract        内容提取(返回结构化数据)
     POST /api/v1/search         搜索(返回结果列表)
     POST /api/v1/summary        摘要(LLM 摘要,可选)
     POST /api/v1/batch          批量任务(异步,返回 task_id)
     GET  /api/v1/task/{task_id} 查询异步任务状态
     GET  /api/v1/health         健康检查

  2. zhua-crawler 系统(ZhuaConfig + zhua_* 工具,端口 8000,/v1/* 接口)
     POST /v1/scrape             单页抓取(多适配器:auto/http/browser/agent)
     POST /v1/extract            LLM 结构化提取(按 JSON Schema)
     POST /v1/agent              Agent 多步任务(浏览器自动化)
     POST /v1/task               批量任务(异步)
     GET  /v1/task/{task_id}     任务状态
     GET  /v1/task/{task_id}/result  任务结果
     DELETE /v1/task/{task_id}   取消任务
     POST /v1/reverse-api        API 嗅探(逆向工程)
     GET  /v1/health             健康检查
     WS   /v1/stream/{task_id}   流式任务事件(SDK 内使用,不暴露为工具)

用法示例:
    # 旧爬虫系统
    from fnixagent.business.crawler import CrawlerClient, FetchRequest

    with CrawlerClient() as client:
        resp = client.fetch(FetchRequest(url="https://example.com"))
        if resp.success:
            print(resp.html)

    # zhua-crawler 系统
    from fnixagent.business.crawler import ZhuaClient

    with ZhuaClient(base_url="http://localhost:8000", operator_token="...") as client:
        result = client.scrape("https://example.com/")

配置(环境变量优先,其次 config/crawler.yaml):
    # 旧爬虫系统
    CRAWLER_BASE_URL=http://crawler:9100
    CRAWLER_API_KEY=sk-xxx
    CRAWLER_TIMEOUT=60

    # zhua-crawler 系统
    fnixagent_ZHUA_BASE_URL=http://zhua:8000
    fnixagent_ZHUA_OPERATOR_TOKEN=xxx
    fnixagent_ZHUA_TIMEOUT=60
"""

from fnixagent.business.crawler.client import (
    CrawlerClient,
    CrawlerError,
)
from fnixagent.business.crawler.config import (
    CrawlerConfig,
    load_config,
    load_config_from_env,
    load_config_from_yaml,
)
from fnixagent.business.crawler.schema import (
    BatchRequest,
    BatchResponse,
    ExtractRequest,
    ExtractResponse,
    # 请求
    FetchRequest,
    # 响应
    FetchResponse,
    HealthStatus,
    RenderRequest,
    RenderResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SummaryRequest,
    SummaryResponse,
    TaskStatus,
)
from fnixagent.business.crawler.tools import (
    _get_client,  # noqa: F401
    _set_global_client,  # noqa: F401
    register_crawler_tools,
)
from fnixagent.business.crawler.zhua_config import (
    ZhuaConfig,
    load_zhua_config,
    load_zhua_config_from_env,
    load_zhua_config_from_yaml,
)

# zhua-crawler 系统(SDK + 配置 + 工具)
from fnixagent.business.crawler.zhua_sdk import (
    ZhuaAuthError,
    ZhuaClient,
    ZhuaConnectionError,
    ZhuaError,
    ZhuaNotFoundError,
    ZhuaQuotaError,
    ZhuaRequestError,
    ZhuaServerError,
)
from fnixagent.business.crawler.zhua_tools import (
    register_zhua_tools,
)

__all__ = [
    # schema - 请求
    "FetchRequest",
    "RenderRequest",
    "ExtractRequest",
    "SearchRequest",
    "SummaryRequest",
    "BatchRequest",
    # schema - 响应
    "FetchResponse",
    "RenderResponse",
    "ExtractResponse",
    "SearchResult",
    "SearchResponse",
    "SummaryResponse",
    "BatchResponse",
    "TaskStatus",
    "HealthStatus",
    # config(旧爬虫系统)
    "CrawlerConfig",
    "load_config",
    "load_config_from_env",
    "load_config_from_yaml",
    # client(旧爬虫系统)
    "CrawlerClient",
    "CrawlerError",
    # tools(旧爬虫系统)
    "register_crawler_tools",
    # zhua-crawler SDK
    "ZhuaClient",
    "ZhuaError",
    "ZhuaAuthError",
    "ZhuaQuotaError",
    "ZhuaNotFoundError",
    "ZhuaRequestError",
    "ZhuaServerError",
    "ZhuaConnectionError",
    # zhua-crawler config
    "ZhuaConfig",
    "load_zhua_config",
    "load_zhua_config_from_env",
    "load_zhua_config_from_yaml",
    # zhua-crawler tools
    "register_zhua_tools",
]
