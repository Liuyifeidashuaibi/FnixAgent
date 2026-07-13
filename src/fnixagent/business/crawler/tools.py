"""爬虫工具注册 —— 将爬虫系统 API 暴露为 fnixagent 工具。

注册工具:
  crawler_fetch    抓取 URL
  crawler_render   浏览器渲染
  crawler_extract  内容提取
  crawler_search   搜索
  crawler_summary  摘要
  crawler_batch    批量任务

核心约束(瘦客户端):
  - 工具函数返回 dict(便于序列化,不返回 dataclass)
  - 全局单例 CrawlerClient(首次调用时从配置创建)
  - 工具内部捕获 CrawlerError,返回 {"success": False, "error": ...}(单工具失败不影响其他)
  - 不缓存/不落盘/不本地存储

工具元数据:
  - layer:      ToolLayer.L2_ECOSYSTEM(办公生态层)
  - category:   "crawler"(注:ToolMetadata 无 tags 字段,用 category 表达分类)
  - cost_score: 0.5(网络调用,中等成本)
  - timeout_ms: 60000
"""
from __future__ import annotations

import dataclasses
import logging
import threading
from typing import Any, Optional

from fnixagent.business.crawler.client import CrawlerClient, CrawlerError
from fnixagent.business.crawler.config import CrawlerConfig, load_config
from fnixagent.business.crawler.schema import (
    BatchRequest,
    ExtractRequest,
    FetchRequest,
    RenderRequest,
    SearchRequest,
    SummaryRequest,
)
from fnixagent.core.tools.protocol import ToolLayer, ToolMetadata, ToolPermission

_logger = logging.getLogger(__name__)

# 全局单例 CrawlerClient(首次调用时从配置创建)
_global_client: Optional[CrawlerClient] = None
_global_client_lock = threading.Lock()


def _get_client() -> CrawlerClient:
    """获取全局单例 CrawlerClient(线程安全懒初始化)。

    若 register_crawler_tools 传入 client,则使用传入的;
    否则首次调用时从 load_config() 创建。

    Returns:
        CrawlerClient 实例
    """
    global _global_client
    if _global_client is None:
        with _global_client_lock:
            if _global_client is None:
                _global_client = CrawlerClient(load_config())
    return _global_client  # type: ignore[return-value]


def _set_global_client(client: Optional[CrawlerClient]) -> None:
    """设置全局单例 client(register_crawler_tools 传入时调用)。"""
    global _global_client
    with _global_client_lock:
        _global_client = client


def _to_dict(obj: Any) -> dict:
    """dataclass → dict(递归,便于序列化)。"""
    return dataclasses.asdict(obj)


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


def _tool_fetch(
    url: str,
    extract_text: bool = False,
    use_browser: bool = False,
    timeout: float = 30.0,
) -> dict:
    """crawler_fetch 工具实现。

    Args:
        url:          待抓取的 URL(非空)
        extract_text: 是否同时提取正文文本
        use_browser:  强制使用浏览器渲染
        timeout:      抓取超时(秒,必须 > 0)

    Returns:
        抓取结果 dict(成功含 html/text/title 等,失败含 error)
    """
    try:
        client = _get_client()
        resp = client.fetch(
            FetchRequest(
                url=url,
                extract_text=extract_text,
                use_browser=use_browser,
                timeout=timeout,
            )
        )
        return _to_dict(resp)
    except CrawlerError as e:
        _logger.warning("crawler_fetch failed: %s", e)
        return {"success": False, "error": str(e), "url": url}
    except Exception as e:  # pragma: no cover
        _logger.exception("crawler_fetch unexpected error: %s", e)
        return {"success": False, "error": f"{type(e).__name__}: {e}", "url": url}


def _tool_render(
    url: str,
    wait_for: Optional[str] = None,
    screenshot: bool = False,
) -> dict:
    """crawler_render 工具实现。

    Args:
        url:        待渲染的 URL(非空)
        wait_for:   CSS 选择器等待(可选)
        screenshot: 是否返回截图

    Returns:
        渲染结果 dict(成功含 html/title/screenshot 等,失败含 error)
    """
    try:
        client = _get_client()
        resp = client.render(
            RenderRequest(url=url, wait_for=wait_for, screenshot=screenshot)
        )
        return _to_dict(resp)
    except CrawlerError as e:
        _logger.warning("crawler_render failed: %s", e)
        return {"success": False, "error": str(e), "url": url}
    except Exception as e:  # pragma: no cover
        _logger.exception("crawler_render unexpected error: %s", e)
        return {"success": False, "error": f"{type(e).__name__}: {e}", "url": url}


def _tool_extract(
    url: Optional[str] = None,
    html: Optional[str] = None,
) -> dict:
    """crawler_extract 工具实现。

    Args:
        url:  提供 URL(爬虫系统抓取后提取)
        html: 直接提供 HTML(url 与 html 至少一个非空)

    Returns:
        提取结果 dict(成功含 text/tables/links/metadata 等,失败含 error)
    """
    try:
        client = _get_client()
        resp = client.extract(ExtractRequest(url=url, html=html))
        return _to_dict(resp)
    except CrawlerError as e:
        _logger.warning("crawler_extract failed: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:  # pragma: no cover
        _logger.exception("crawler_extract unexpected error: %s", e)
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def _tool_search(query: str, num_results: int = 10) -> dict:
    """crawler_search 工具实现。

    Args:
        query:       搜索关键词(非空)
        num_results: 返回结果数

    Returns:
        搜索结果 dict(成功含 results 列表,失败含 error)
    """
    try:
        client = _get_client()
        resp = client.search(
            SearchRequest(query=query, num_results=num_results)
        )
        return _to_dict(resp)
    except CrawlerError as e:
        _logger.warning("crawler_search failed: %s", e)
        return {"success": False, "error": str(e), "query": query, "results": []}
    except Exception as e:  # pragma: no cover
        _logger.exception("crawler_search unexpected error: %s", e)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "query": query,
            "results": [],
        }


def _tool_summary(
    url: Optional[str] = None,
    text: Optional[str] = None,
    style: str = "concise",
) -> dict:
    """crawler_summary 工具实现。

    Args:
        url:   提供 URL(url 与 text 至少一个非空)
        text:  提供纯文本
        style: 摘要风格(concise/detailed/bullet)

    Returns:
        摘要结果 dict(成功含 summary/key_points/keywords 等,失败含 error)
    """
    try:
        client = _get_client()
        resp = client.summary(
            SummaryRequest(url=url, text=text, summary_style=style)
        )
        return _to_dict(resp)
    except CrawlerError as e:
        _logger.warning("crawler_summary failed: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:  # pragma: no cover
        _logger.exception("crawler_summary unexpected error: %s", e)
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


def _tool_batch(urls: list[str], task_type: str = "fetch") -> dict:
    """crawler_batch 工具实现(返回 task_id,异步)。

    Args:
        urls:      URL 列表(非空)
        task_type: 任务类型(fetch/render/extract/summary)

    Returns:
        批量任务 dict(成功含 task_id,失败含 error)
    """
    try:
        client = _get_client()
        resp = client.submit_batch(
            BatchRequest(urls=urls, task_type=task_type)
        )
        return _to_dict(resp)
    except CrawlerError as e:
        _logger.warning("crawler_batch failed: %s", e)
        return {"success": False, "error": str(e)}
    except Exception as e:  # pragma: no cover
        _logger.exception("crawler_batch unexpected error: %s", e)
        return {"success": False, "error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# 工具元数据
# ---------------------------------------------------------------------------

# 公共元数据字段(网络调用,中等成本)
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
        name:        工具名
        description: 功能描述
        input_schema:JSON Schema 入参

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
    "crawler_fetch": _make_metadata(
        "crawler_fetch",
        "抓取 URL,返回 HTML(可选提取正文文本 / 浏览器渲染)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "待抓取的 URL"},
                "extract_text": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否同时提取正文文本",
                },
                "use_browser": {
                    "type": "boolean",
                    "default": False,
                    "description": "强制使用浏览器渲染",
                },
                "timeout": {
                    "type": "number",
                    "default": 30.0,
                    "description": "抓取超时(秒)",
                },
            },
            "required": ["url"],
        },
    ),
    "crawler_render": _make_metadata(
        "crawler_render",
        "浏览器渲染 URL(JS 执行后返回 HTML,可选截图)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "待渲染的 URL"},
                "wait_for": {
                    "type": "string",
                    "description": "CSS 选择器等待(可选)",
                },
                "screenshot": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否返回截图(base64 PNG)",
                },
            },
            "required": ["url"],
        },
    ),
    "crawler_extract": _make_metadata(
        "crawler_extract",
        "内容提取(返回正文/表格/链接/元数据等结构化数据)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "提供 URL(抓取后提取)"},
                "html": {"type": "string", "description": "直接提供 HTML"},
            },
        },
    ),
    "crawler_search": _make_metadata(
        "crawler_search",
        "Web 搜索(返回结果列表,含标题/URL/摘要)",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "num_results": {
                    "type": "integer",
                    "default": 10,
                    "description": "返回结果数",
                },
            },
            "required": ["query"],
        },
    ),
    "crawler_summary": _make_metadata(
        "crawler_summary",
        "网页/文本摘要(LLM 摘要,返回摘要/要点/关键词)",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "提供 URL(抓取+摘要)"},
                "text": {"type": "string", "description": "提供纯文本"},
                "style": {
                    "type": "string",
                    "default": "concise",
                    "enum": ["concise", "detailed", "bullet"],
                    "description": "摘要风格",
                },
            },
        },
    ),
    "crawler_batch": _make_metadata(
        "crawler_batch",
        "批量任务(异步,返回 task_id 用于查询状态)",
        {
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URL 列表",
                },
                "task_type": {
                    "type": "string",
                    "default": "fetch",
                    "enum": ["fetch", "render", "extract", "summary"],
                    "description": "任务类型",
                },
            },
            "required": ["urls"],
        },
    ),
}


# 工具名 → 实现函数映射
TOOL_FUNCS: dict[str, Any] = {
    "crawler_fetch": _tool_fetch,
    "crawler_render": _tool_render,
    "crawler_extract": _tool_extract,
    "crawler_search": _tool_search,
    "crawler_summary": _tool_summary,
    "crawler_batch": _tool_batch,
}


def register_crawler_tools(
    registry: Any,
    client: Optional[CrawlerClient] = None,
) -> None:
    """注册爬虫工具到 ToolRegistry。

    Args:
        registry: ToolRegistry 实例(需实现 register(metadata, func) 方法)
        client:   可选 CrawlerClient(默认从配置创建全局单例)

    Note:
        - 若 client 提供,设为全局单例(后续 _tool_* 调用复用)
        - 工具元数据:layer=L2_ECOSYSTEM, category="crawler", cost_score=0.5,
          timeout_ms=60000
        - 单工具注册失败不影响其他工具(记录 warning 后继续)
    """
    if client is not None:
        _set_global_client(client)

    for name, metadata in TOOL_METADATA.items():
        func = TOOL_FUNCS[name]
        try:
            registry.register(metadata, func)
        except Exception as e:  # pragma: no cover
            _logger.warning("注册爬虫工具 %s 失败: %s", name, e)
