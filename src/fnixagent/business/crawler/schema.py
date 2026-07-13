"""爬虫系统接口契约。

本模块定义 fnixagent 调用爬虫系统的请求/响应 schema。
爬虫系统必须按此契约实现 API,fnixagent 端不做任何数据存储。

核心约束(瘦客户端):
  - 无状态:不维护 session/cookie,每次调用独立请求
  - 无缓存:不缓存任何响应
  - 无落盘:不写任何文件
  - 无本地存储:不存任何抓取内容

接口清单:
  POST /api/v1/fetch          抓取单个 URL(返回 HTML)
  POST /api/v1/render         浏览器渲染(JS 执行后返回 HTML)
  POST /api/v1/extract        内容提取(返回结构化数据)
  POST /api/v1/search         搜索(返回结果列表)
  POST /api/v1/summary        摘要(LLM 摘要,可选)
  POST /api/v1/batch          批量任务(异步,返回 task_id)
  GET  /api/v1/task/{task_id} 查询异步任务状态
  GET  /api/v1/health         健康检查
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FetchRequest:
    """抓取请求。

    Attributes:
        url:          待抓取的 URL(非空)
        method:       HTTP 方法(GET/POST),默认 GET
        headers:      请求头
        body:         POST 请求体
        timeout:      抓取超时(秒),必须 > 0
        wait_for:     CSS 选择器等待(渲染场景使用)
        use_browser:  强制使用浏览器渲染
        extract_text: 是否同时提取正文文本
        max_chars:    截断到最大字符数
    """

    url: str
    method: str = "GET"
    headers: Optional[dict[str, str]] = None
    body: Optional[str] = None
    timeout: float = 30.0
    wait_for: Optional[str] = None
    use_browser: bool = False
    extract_text: bool = False
    max_chars: Optional[int] = None


@dataclass
class FetchResponse:
    """抓取响应。

    Attributes:
        success:     是否成功
        url:         原始请求 URL
        final_url:   重定向后最终 URL
        status_code: HTTP 状态码
        html:        原始/渲染后 HTML
        text:        提取的正文(extract_text=True 时填充)
        title:       页面标题
        elapsed_ms:  耗时(毫秒)
        error:       错误信息(success=False 时填充)
    """

    success: bool
    url: str
    final_url: str
    status_code: int
    html: str
    text: Optional[str] = None
    title: Optional[str] = None
    elapsed_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class RenderRequest:
    """浏览器渲染请求。

    Attributes:
        url:            待渲染的 URL(非空)
        wait_for:       CSS 选择器等待
        wait_until:     等待条件(load/domcontentloaded/networkidle)
        timeout:        渲染超时(秒)
        screenshot:     是否返回截图(base64 PNG)
        execute_js:     渲染后执行的 JS
        block_resources: 拦截的资源类型(image/font/media)
    """

    url: str
    wait_for: Optional[str] = None
    wait_until: str = "networkidle"
    timeout: float = 60.0
    screenshot: bool = False
    execute_js: Optional[str] = None
    block_resources: Optional[list[str]] = None


@dataclass
class RenderResponse:
    """渲染响应。

    Attributes:
        success:    是否成功
        url:        原始请求 URL
        final_url:  重定向后最终 URL
        title:      页面标题
        html:       渲染后 HTML
        text:       提取的正文(可选)
        screenshot: base64 编码 PNG 截图(可选)
        elapsed_ms: 耗时(毫秒)
        error:      错误信息
    """

    success: bool
    url: str
    final_url: str
    title: str
    html: str
    text: Optional[str] = None
    screenshot: Optional[str] = None
    elapsed_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class ExtractRequest:
    """内容提取请求。

    Attributes:
        html:              直接提供 HTML(与 url 二选一)
        url:               提供 URL(爬虫系统抓取后提取)
        extract_tables:    是否提取表格
        extract_links:     是否提取链接
        extract_metadata:  是否提取元数据
    """

    html: Optional[str] = None
    url: Optional[str] = None
    extract_tables: bool = True
    extract_links: bool = True
    extract_metadata: bool = True


@dataclass
class ExtractResponse:
    """提取响应。

    Attributes:
        success:    是否成功
        title:      页面标题
        text:       正文文本
        tables:     表格列表(三维:表格 → 行 → 单元格)
        links:      链接列表([{"url":..., "text":..., "rel":...}])
        metadata:   元数据
        language:   语言(可选)
        word_count: 词数
        error:      错误信息
    """

    success: bool
    title: str
    text: str
    tables: list[list[list[str]]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    language: Optional[str] = None
    word_count: int = 0
    error: Optional[str] = None


@dataclass
class SearchRequest:
    """搜索请求。

    Attributes:
        query:       搜索关键词(非空)
        num_results: 返回结果数
        language:    语言
        time_range:  时间范围(day/week/month/year)
        safe_search: 安全搜索
    """

    query: str
    num_results: int = 10
    language: str = "zh-CN"
    time_range: Optional[str] = None
    safe_search: bool = True


@dataclass
class SearchResult:
    """单条搜索结果。

    Attributes:
        title:        标题
        url:          URL
        snippet:      摘要片段
        published_at: 发布时间(可选)
    """

    title: str
    url: str
    snippet: str
    published_at: Optional[str] = None


@dataclass
class SearchResponse:
    """搜索响应。

    Attributes:
        success:    是否成功
        query:      原始查询
        results:    结果列表
        total:      总结果数
        elapsed_ms: 耗时(毫秒)
        error:      错误信息
    """

    success: bool
    query: str
    results: list[SearchResult] = field(default_factory=list)
    total: int = 0
    elapsed_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class SummaryRequest:
    """摘要请求(若爬虫系统提供 LLM 摘要能力)。

    Attributes:
        url:              提供 URL(爬虫系统抓取+摘要)
        html:             提供 HTML
        text:             提供纯文本
        summary_style:    摘要风格(concise/detailed/bullet)
        summary_language: 摘要语言
        max_key_points:   最大要点数
    """

    url: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    summary_style: str = "concise"
    summary_language: str = "zh-CN"
    max_key_points: int = 10


@dataclass
class SummaryResponse:
    """摘要响应。

    Attributes:
        success:    是否成功
        title:      标题
        summary:    摘要正文
        key_points: 要点列表
        keywords:   关键词列表
        language:   摘要语言
        elapsed_ms: 耗时(毫秒)
        error:      错误信息
    """

    success: bool
    title: str
    summary: str
    key_points: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    language: str = "zh-CN"
    elapsed_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class BatchRequest:
    """批量任务请求(异步)。

    Attributes:
        urls:      URL 列表(非空)
        task_type: 任务类型(fetch/render/extract/summary)
        config:    任务特定配置
    """

    urls: list[str]
    task_type: str = "fetch"
    config: Optional[dict] = None


@dataclass
class BatchResponse:
    """批量任务响应。

    Attributes:
        success: 是否成功
        task_id: 任务 ID(用于查询状态)
        total:   总任务数
        status:  任务状态(pending/running/completed/failed)
        error:   错误信息
    """

    success: bool
    task_id: str
    total: int
    status: str
    error: Optional[str] = None


@dataclass
class TaskStatus:
    """异步任务状态。

    Attributes:
        task_id:      任务 ID
        status:       状态(pending/running/completed/failed)
        progress:     进度(0.0-1.0)
        results:      完成后的结果(每项是响应 dict)
        error:        错误信息
        created_at:   创建时间
        completed_at: 完成时间
    """

    task_id: str
    status: str
    progress: float = 0.0
    results: Optional[list[dict]] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class HealthStatus:
    """健康检查响应。

    Attributes:
        healthy:         是否健康
        version:         爬虫系统版本
        uptime_seconds:  运行时长(秒)
        active_tasks:    活跃任务数
    """

    healthy: bool
    version: Optional[str] = None
    uptime_seconds: Optional[float] = None
    active_tasks: int = 0
