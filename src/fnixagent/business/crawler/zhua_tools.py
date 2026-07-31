"""zhua-crawler 工具注册 —— 将 ZhuaCrawler API 暴露为 fnixagent 工具。

注册工具(对应 ZhuaClient 方法):
  zhua_scrape        单页抓取(POST /v1/scrape)
  zhua_extract       LLM 结构化提取(POST /v1/extract)
  zhua_agent         Agent 多步任务(POST /v1/agent)
  zhua_task_create   批量任务创建(POST /v1/task,异步返回 task_id)
  zhua_task_status   查询任务状态(GET /v1/task/{task_id})
  zhua_task_result   取任务结果(GET /v1/task/{task_id}/result)
  zhua_task_cancel   取消任务(DELETE /v1/task/{task_id})
  zhua_reverse_api   API 嗅探(POST /v1/reverse-api)
  zhua_health        健康检查(GET /v1/health)

核心约束(瘦客户端,与 tools.py 一致):
  - 工具函数返回 dict(ZhuaClient 方法本身已返回 dict,无需转换)
  - 全局单例 ZhuaClient(首次调用时从 load_zhua_config() 创建)
  - 工具内部捕获 ZhuaError,返回 {"success": False, "error": ...}(单工具失败不影响其他)
  - 不缓存/不落盘/不本地存储
  - task_stream(WS 流式)不作为工具暴露(生成器语义不适合工具调用)

工具元数据(与 crawler_* 一致):
  - layer:      ToolLayer.L2_ECOSYSTEM(办公生态层)
  - category:   "crawler"
  - cost_score: 0.5(网络调用,中等成本)
  - timeout_ms: 60000

与 crawler_* 工具的关系:
  两套工具并存,Agent 可同时使用:
    - crawler_*  对接旧爬虫系统(/api/v1/* 接口,端口 9100)
    - zhua_*     对接 zhua-crawler 系统(/v1/* 接口,端口 8000,能力更丰富:
                  含 agent 多步 / reverse_api 嗅探 / 异步任务全生命周期)
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from fnixagent.business.crawler.zhua_config import load_zhua_config
from fnixagent.business.crawler.zhua_sdk import (
    ZhuaClient,
    ZhuaError,
)
from fnixagent.core.tools.protocol import ToolLayer, ToolMetadata, ToolPermission

_logger = logging.getLogger(__name__)

# 全局单例 ZhuaClient(首次调用时从配置创建)
_global_client: ZhuaClient | None = None
_global_client_lock = threading.Lock()


def _get_client() -> ZhuaClient:
    """获取全局单例 ZhuaClient(线程安全懒初始化)。

    若 register_zhua_tools 传入 client,则使用传入的;
    否则首次调用时从 load_zhua_config() 创建。

    Returns:
        ZhuaClient 实例
    """
    global _global_client
    if _global_client is None:
        with _global_client_lock:
            if _global_client is None:
                cfg = load_zhua_config()
                _global_client = ZhuaClient(**cfg.to_client_kwargs())
    return _global_client  # type: ignore[return-value]


def _set_global_client(client: ZhuaClient | None) -> None:
    """设置全局单例 client(register_zhua_tools 传入时调用)。"""
    global _global_client
    with _global_client_lock:
        _global_client = client


def _error_dict(operation: str, e: Exception, **context: Any) -> dict[str, Any]:
    """构造统一的错误返回 dict(含 request_id 便于排查)。"""
    err: dict[str, Any] = {
        "success": False,
        "operation": operation,
        "error": str(e),
        "error_type": type(e).__name__,
    }
    # ZhuaError 携带 status_code / request_id(便于服务端排查)
    if isinstance(e, ZhuaError):
        if e.status_code is not None:
            err["status_code"] = e.status_code
        if e.request_id:
            err["request_id"] = e.request_id
    err.update(context)
    return err


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


def _tool_scrape(
    url: str,
    adapter: str = "auto",
    output: str = "markdown",
    fit: bool = False,
    screenshot: bool = False,
    wait_for: str | None = None,
    timeout: float = 60.0,
    impersonate: str | None = None,
    proxy: str | None = None,
) -> dict:
    """zhua_scrape 工具实现 —— 单页抓取。

    Args:
        url:         目标 URL(非空)
        adapter:     适配器:auto/http/browser/agent/mobile
        output:      输出格式:markdown/html/raw
        fit:         是否启用 BM25 去噪
        screenshot:  是否截图(返回 base64)
        wait_for:    等待 CSS 选择器(可选)
        timeout:     抓取超时(秒,1-600)
        impersonate: curl_cffi 指纹目标(可选)
        proxy:       代理 URL(可选)

    Returns:
        抓取结果 dict(成功含 markdown/html/raw/elapsed/screenshots 等,
        失败含 error / status_code / request_id)
    """
    try:
        client = _get_client()
        return client.scrape(
            url,
            adapter=adapter,
            output=output,
            fit=fit,
            screenshot=screenshot,
            wait_for=wait_for,
            timeout=int(timeout),
            impersonate=impersonate,
            proxy=proxy,
        )
    except ZhuaError as e:
        _logger.warning("zhua_scrape failed: %s", e)
        return _error_dict("scrape", e, url=url)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_scrape unexpected error: %s", e)
        return _error_dict("scrape", e, url=url)


def _tool_extract(
    url: str,
    schema: dict | None = None,
    selector: str | None = None,
    html_mode: str = "markdown",
) -> dict:
    """zhua_extract 工具实现 —— LLM 结构化提取。

    Args:
        url:       目标 URL(非空)
        schema:    JSON Schema(描述要提取的字段;None 时提取通用结构)
        selector:  CSS 选择器(可选,限定提取范围)
        html_mode: HTML 处理模式:markdown/html/fit

    Returns:
        提取结果 dict(成功含 extracted_data/model/tokens/elapsed,
        失败含 error)
    """
    try:
        client = _get_client()
        return client.extract(
            url,
            schema=schema,
            selector=selector,
            html_mode=html_mode,
        )
    except ZhuaError as e:
        _logger.warning("zhua_extract failed: %s", e)
        return _error_dict("extract", e, url=url)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_extract unexpected error: %s", e)
        return _error_dict("extract", e, url=url)


def _tool_agent(
    url: str,
    task: str,
    max_steps: int = 10,
) -> dict:
    """zhua_agent 工具实现 —— Agent 多步任务(浏览器自动化)。

    Args:
        url:       目标 URL(非空,Agent 的起点)
        task:      Agent 任务描述(自然语言,如"登录后导出 12 月报表")
        max_steps: 最大步数(1-100,默认 10)

    Returns:
        Agent 结果 dict(成功含 success/actions/final_text/elapsed,
        失败含 error)
    """
    try:
        client = _get_client()
        return client.agent(url, task=task, max_steps=max_steps)
    except ZhuaError as e:
        _logger.warning("zhua_agent failed: %s", e)
        return _error_dict("agent", e, url=url, task=task)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_agent unexpected error: %s", e)
        return _error_dict("agent", e, url=url, task=task)


def _tool_task_create(
    urls: list[str],
    adapter: str = "auto",
    priority: int = 5,
    webhook: str | None = None,
) -> dict:
    """zhua_task_create 工具实现 —— 批量任务创建(异步)。

    Args:
        urls:     URL 列表(非空,至少 1 个)
        adapter:  适配器(默认 auto)
        priority: 优先级(0-10,默认 5)
        webhook:  完成回调 URL(可选)

    Returns:
        任务创建 dict(成功含 task_id/accepted/status,失败含 error)
        后续可用 zhua_task_status / zhua_task_result 查询。
    """
    try:
        client = _get_client()
        return client.task_create(
            urls,
            adapter=adapter,
            priority=priority,
            webhook=webhook,
        )
    except ZhuaError as e:
        _logger.warning("zhua_task_create failed: %s", e)
        return _error_dict("task_create", e, urls=urls)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_task_create unexpected error: %s", e)
        return _error_dict("task_create", e, urls=urls)


def _tool_task_status(task_id: str) -> dict:
    """zhua_task_status 工具实现 —— 查询任务状态。

    Args:
        task_id: 任务 ID(非空,由 zhua_task_create 返回)

    Returns:
        状态 dict(含 task_id/status/total/succeeded/failed/pending 等)
    """
    try:
        client = _get_client()
        return client.task_status(task_id)
    except ZhuaError as e:
        _logger.warning("zhua_task_status failed: %s", e)
        return _error_dict("task_status", e, task_id=task_id)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_task_status unexpected error: %s", e)
        return _error_dict("task_status", e, task_id=task_id)


def _tool_task_result(task_id: str) -> dict:
    """zhua_task_result 工具实现 —— 取任务结果。

    Args:
        task_id: 任务 ID(非空)

    Returns:
        结果 dict(含 task_id/results 列表;任务未完成时 results 可能为空)
    """
    try:
        client = _get_client()
        return client.task_result(task_id)
    except ZhuaError as e:
        _logger.warning("zhua_task_result failed: %s", e)
        return _error_dict("task_result", e, task_id=task_id)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_task_result unexpected error: %s", e)
        return _error_dict("task_result", e, task_id=task_id)


def _tool_task_cancel(task_id: str) -> dict:
    """zhua_task_cancel 工具实现 —— 取消任务。

    Args:
        task_id: 任务 ID(非空)

    Returns:
        取消结果 dict(含 task_id/cancelled)
    """
    try:
        client = _get_client()
        return client.task_cancel(task_id)
    except ZhuaError as e:
        _logger.warning("zhua_task_cancel failed: %s", e)
        return _error_dict("task_cancel", e, task_id=task_id)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_task_cancel unexpected error: %s", e)
        return _error_dict("task_cancel", e, task_id=task_id)


def _tool_reverse_api(
    url: str,
    probe: bool = False,
    discover: bool = False,
    capture: bool = False,
    max_requests: int = 100,
) -> dict:
    """zhua_reverse_api 工具实现 —— API 嗅探(逆向工程)。

    Args:
        url:          目标 API URL(非空)
        probe:        枚举候选参数探测
        discover:     只返回成功组合
        capture:      浏览器嗅探 XHR/Fetch
        max_requests: 最大请求数(1-10000,默认 100)

    Returns:
        嗅探结果 dict(含 api_catalog/probe_results)
    """
    try:
        client = _get_client()
        return client.reverse_api(
            url,
            probe=probe,
            discover=discover,
            capture=capture,
            max_requests=max_requests,
        )
    except ZhuaError as e:
        _logger.warning("zhua_reverse_api failed: %s", e)
        return _error_dict("reverse_api", e, url=url)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_reverse_api unexpected error: %s", e)
        return _error_dict("reverse_api", e, url=url)


def _tool_health() -> dict:
    """zhua_health 工具实现 —— 健康检查。

    Returns:
        健康 dict(含 status/version/uptime)
    """
    try:
        client = _get_client()
        return client.health()
    except ZhuaError as e:
        _logger.warning("zhua_health failed: %s", e)
        return _error_dict("health", e)
    except Exception as e:  # pragma: no cover
        _logger.exception("zhua_health unexpected error: %s", e)
        return _error_dict("health", e)


# ---------------------------------------------------------------------------
# 工具元数据
# ---------------------------------------------------------------------------

# 公共元数据字段(与 crawler_* 工具一致:网络调用,中等成本)
_COMMON_META: dict[str, Any] = {
    "category": "crawler",
    "layer": ToolLayer.L2_ECOSYSTEM,
    "permission_level": ToolPermission.MIDDLE,  # 调用外部 API
    "cost_score": 0.5,
    "timeout_ms": 60000,
    "is_concurrency_safe": True,
}


def _make_metadata(
    name: str,
    description: str,
    input_schema: dict,
) -> ToolMetadata:
    """构造工具元数据(合并公共字段)。

    Args:
        name:         工具名
        description:  功能描述
        input_schema: JSON Schema 入参

    Returns:
        ToolMetadata 实例
    """
    return ToolMetadata(
        name=name,
        description=description,
        input_schema=input_schema,
        **_COMMON_META,
    )


# 工具元数据定义(input_schema 用于 LLM function-calling)
TOOL_METADATA: dict[str, ToolMetadata] = {
    "zhua_scrape": _make_metadata(
        "zhua_scrape",
        "zhua-crawler 单页抓取(支持 http/browser/agent 适配器,"
        "返回 markdown/html/raw,可选截图与去噪)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL"},
                "adapter": {
                    "type": "string",
                    "default": "auto",
                    "enum": ["auto", "http", "browser", "agent", "mobile"],
                    "description": "适配器:auto/http/browser/agent/mobile",
                },
                "output": {
                    "type": "string",
                    "default": "markdown",
                    "enum": ["markdown", "html", "raw"],
                    "description": "输出格式",
                },
                "fit": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否启用 BM25 去噪",
                },
                "screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否截图(返回 base64)",
                },
                "wait_for": {
                    "type": "string",
                    "description": "等待 CSS 选择器(可选)",
                },
                "timeout": {
                    "type": "number",
                    "default": 60.0,
                    "description": "抓取超时(秒,1-600)",
                },
                "impersonate": {
                    "type": "string",
                    "description": "curl_cffi 指纹目标(可选)",
                },
                "proxy": {
                    "type": "string",
                    "description": "代理 URL(可选)",
                },
            },
            "required": ["url"],
        },
    ),
    "zhua_extract": _make_metadata(
        "zhua_extract",
        "zhua-crawler LLM 结构化提取(按 JSON Schema 从网页提取字段)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL"},
                "schema": {
                    "type": "object",
                    "description": "JSON Schema(描述要提取的字段)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS 选择器(可选,限定提取范围)",
                },
                "html_mode": {
                    "type": "string",
                    "default": "markdown",
                    "enum": ["markdown", "html", "fit"],
                    "description": "HTML 处理模式",
                },
            },
            "required": ["url"],
        },
    ),
    "zhua_agent": _make_metadata(
        "zhua_agent",
        "zhua-crawler Agent 多步任务(浏览器自动化,自然语言描述任务,自动规划与执行多步操作)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 URL(Agent 起点)"},
                "task": {
                    "type": "string",
                    "description": "Agent 任务描述(自然语言)",
                },
                "max_steps": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "最大步数",
                },
            },
            "required": ["url", "task"],
        },
    ),
    "zhua_task_create": _make_metadata(
        "zhua_task_create",
        "zhua-crawler 批量任务创建(异步,返回 task_id,"
        "后续用 zhua_task_status/zhua_task_result 查询)",
        {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "URL 列表(至少 1 个)",
                },
                "adapter": {
                    "type": "string",
                    "default": "auto",
                    "description": "适配器",
                },
                "priority": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 0,
                    "maximum": 10,
                    "description": "优先级(0-10)",
                },
                "webhook": {
                    "type": "string",
                    "description": "完成回调 URL(可选)",
                },
            },
            "required": ["urls"],
        },
    ),
    "zhua_task_status": _make_metadata(
        "zhua_task_status",
        "查询 zhua-crawler 批量任务状态",
        {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "任务 ID(由 zhua_task_create 返回)",
                },
            },
            "required": ["task_id"],
        },
    ),
    "zhua_task_result": _make_metadata(
        "zhua_task_result",
        "取 zhua-crawler 批量任务结果(任务完成后调用)",
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
            },
            "required": ["task_id"],
        },
    ),
    "zhua_task_cancel": _make_metadata(
        "zhua_task_cancel",
        "取消 zhua-crawler 批量任务",
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
            },
            "required": ["task_id"],
        },
    ),
    "zhua_reverse_api": _make_metadata(
        "zhua_reverse_api",
        "zhua-crawler API 嗅探(逆向工程:枚举参数探测 / 浏览器嗅探 XHR/Fetch)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标 API URL"},
                "probe": {
                    "type": "boolean",
                    "default": False,
                    "description": "枚举候选参数探测",
                },
                "discover": {
                    "type": "boolean",
                    "default": False,
                    "description": "只返回成功组合",
                },
                "capture": {
                    "type": "boolean",
                    "default": False,
                    "description": "浏览器嗅探 XHR/Fetch",
                },
                "max_requests": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 10000,
                    "description": "最大请求数",
                },
            },
            "required": ["url"],
        },
    ),
    "zhua_health": _make_metadata(
        "zhua_health",
        "zhua-crawler 健康检查(返回服务状态/版本/运行时长)",
        {
            "type": "object",
            "properties": {},
        },
    ),
}


# 工具名 → 实现函数映射
TOOL_FUNCS: dict[str, Any] = {
    "zhua_scrape": _tool_scrape,
    "zhua_extract": _tool_extract,
    "zhua_agent": _tool_agent,
    "zhua_task_create": _tool_task_create,
    "zhua_task_status": _tool_task_status,
    "zhua_task_result": _tool_task_result,
    "zhua_task_cancel": _tool_task_cancel,
    "zhua_reverse_api": _tool_reverse_api,
    "zhua_health": _tool_health,
}


def register_zhua_tools(
    registry: Any,
    client: ZhuaClient | None = None,
) -> None:
    """注册 zhua-crawler 工具到 ToolRegistry。

    Args:
        registry: ToolRegistry 实例(需实现 register(metadata, func) 方法)
        client:   可选 ZhuaClient(默认从配置创建全局单例)

    Note:
        - 若 client 提供,设为全局单例(后续 _tool_* 调用复用)
        - 工具元数据:layer=L2_ECOSYSTEM, category="crawler", cost_score=0.5,
          timeout_ms=60000
        - 单工具注册失败不影响其他工具(记录 warning 后继续)
        - 与 register_crawler_tools 互不影响,两套工具可同时注册
    """
    if client is not None:
        _set_global_client(client)

    for name, metadata in TOOL_METADATA.items():
        func = TOOL_FUNCS[name]
        try:
            registry.register(metadata, func)
        except Exception as e:  # pragma: no cover
            _logger.warning("注册 zhua 工具 %s 失败: %s", name, e)
