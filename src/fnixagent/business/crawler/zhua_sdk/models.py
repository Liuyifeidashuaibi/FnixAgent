"""zhua_client Pydantic 模型

与 HTTP API 的请求/响应 schemas 对应,提供类型友好的数据模型。
所有模型均为 Pydantic v2 BaseModel,可直接 .model_dump() / .model_validate()。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #
class OutputFormat(str, Enum):
    """scrape 输出格式"""

    MARKDOWN = "markdown"
    HTML = "html"
    RAW = "raw"


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #
class ScrapeRequest(BaseModel):
    """POST /v1/scrape 请求体"""

    url: str = Field(..., description="目标 URL")
    adapter: str = Field("auto", description="适配器:auto/http/browser/agent/mobile")
    output: OutputFormat = Field(OutputFormat.MARKDOWN, description="输出格式")
    fit: bool = Field(False, description="是否启用 BM25 去噪")
    screenshot: bool = Field(False, description="是否截图")
    wait_for: str | None = Field(None, description="等待 CSS 选择器")
    timeout: int = Field(60, ge=1, le=600, description="超时(秒)")
    impersonate: str | None = Field(None, description="curl_cffi 指纹目标")
    proxy: str | None = Field(None, description="代理 URL")


class ExtractRequest(BaseModel):
    """POST /v1/extract 请求体"""

    url: str = Field(..., description="目标 URL")
    schema: dict[str, Any] | None = Field(None, description="JSON Schema")
    selector: str | None = Field(None, description="CSS 选择器")
    html_mode: str = Field("markdown", description="HTML 处理模式:markdown/html/fit")


class AgentRequest(BaseModel):
    """POST /v1/agent 请求体"""

    url: str = Field(..., description="目标 URL")
    task: str = Field(..., description="Agent 任务描述")
    max_steps: int = Field(10, ge=1, le=100, description="最大步数")


class TaskCreateRequest(BaseModel):
    """POST /v1/task 请求体"""

    urls: list[str] = Field(..., min_length=1, description="URL 列表")
    adapter: str = Field("auto", description="适配器")
    priority: int = Field(5, ge=0, le=10, description="优先级")
    webhook: str | None = Field(None, description="完成回调 URL")


class ReverseApiRequest(BaseModel):
    """POST /v1/reverse-api 请求体"""

    url: str = Field(..., description="目标 API URL")
    probe: bool = Field(False, description="枚举候选参数探测")
    discover: bool = Field(False, description="只返回成功组合")
    capture: bool = Field(False, description="浏览器嗅探 XHR/Fetch")
    max_requests: int = Field(100, ge=1, le=10000, description="最大请求数")


class TokenRequest(BaseModel):
    """POST /v1/token 请求体"""

    operator_token: str = Field(..., description="运维静态令牌")
    principal: str | None = Field(None, description="主体标识")
    scopes: list[str] | None = Field(None, description="作用域列表")
    ttl: int | None = Field(None, description="有效期(秒)")


# --------------------------------------------------------------------------- #
# 响应模型
# --------------------------------------------------------------------------- #
class TokenResponse(BaseModel):
    """POST /v1/token 响应"""

    access_token: str = Field(..., description="JWT")
    token_type: str = Field("Bearer", description="令牌类型")
    expires_in: int = Field(..., description="有效期(秒)")


class ScrapeResponse(BaseModel):
    """POST /v1/scrape 响应"""

    url: str
    status_code: int = 200
    markdown: str | None = None
    html: str | None = None
    raw: str | None = None
    elapsed: float = 0.0
    screenshots: list[str] = Field(default_factory=list, description="截图(base64)")
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ExtractResponse(BaseModel):
    """POST /v1/extract 响应"""

    url: str
    extracted_data: Any = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    elapsed: float = 0.0
    request_id: str | None = None


class AgentResponse(BaseModel):
    """POST /v1/agent 响应"""

    url: str
    success: bool = True
    actions: list[dict[str, Any]] = Field(default_factory=list)
    final_text: str | None = None
    elapsed: float = 0.0
    request_id: str | None = None


class TaskCreateResponse(BaseModel):
    """POST /v1/task 响应"""

    task_id: str
    accepted: int = Field(..., description="成功入队数")
    status: TaskStatus = TaskStatus.PENDING
    request_id: str | None = None


class TaskStatusResponse(BaseModel):
    """GET /v1/task/{task_id} 响应"""

    task_id: str
    status: TaskStatus
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    pending: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    request_id: str | None = None


class TaskResultResponse(BaseModel):
    """GET /v1/task/{task_id}/result 响应"""

    task_id: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str | None = None


class TaskCancelResponse(BaseModel):
    """DELETE /v1/task/{task_id} 响应"""

    task_id: str
    cancelled: bool = True
    request_id: str | None = None


class ReverseApiResponse(BaseModel):
    """POST /v1/reverse-api 响应"""

    url: str
    api_catalog: list[dict[str, Any]] = Field(default_factory=list)
    probe_results: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str | None = None


class HealthResponse(BaseModel):
    """GET /v1/health 响应"""

    status: str = "ok"
    version: str | None = None
    uptime: float | None = None
    request_id: str | None = None


__all__ = [
    # 枚举
    "OutputFormat",
    "TaskStatus",
    # 请求
    "ScrapeRequest",
    "ExtractRequest",
    "AgentRequest",
    "TaskCreateRequest",
    "ReverseApiRequest",
    "TokenRequest",
    # 响应
    "TokenResponse",
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
