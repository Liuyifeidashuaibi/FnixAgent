"""
OfficeAgent Prometheus 指标模块 — Phase 2.10

覆盖 4 大监控维度:
  1. 业务监控:用户活跃度 / 功能使用率
  2. 系统监控:HTTP QPS / 延迟 / P99
  3. 应用监控:LangGraph 节点耗时 / 飞轮触发 / 拓扑增长 / 工具执行
  4. 安全监控:登录异常 / 高危操作 / 限流触发 / 权限拒绝

用法:
  from officeagent.core.observability.metrics import setup_metrics

  # 在 FastAPI app 中注册
  setup_metrics(app)

  # 在业务代码中记录指标
  from officeagent.core.observability.metrics import record_login, record_chat_message
  record_login(success=True, method="password")
  record_chat_message(mode="evolve")
"""
from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        REGISTRY,
    )
    from prometheus_client.exposition import make_asgi_app
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    REGISTRY = None  # type: ignore

# ============================================================================
# 指标定义
# ============================================================================

# 使用全局 REGISTRY(避免重复注册)
_registry: "CollectorRegistry | None" = REGISTRY

# 初始化锁:保证 _init_metrics 在多线程下只执行一次(线程安全的单例初始化)
_init_lock = threading.Lock()

# ---------------------------------------------------------------------------
# 1. 系统监控(HTTP / 进程)
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = None  # type: ignore
HTTP_REQUEST_DURATION_SECONDS = None  # type: ignore
HTTP_REQUESTS_IN_PROGRESS = None  # type: ignore

# ---------------------------------------------------------------------------
# 2. 业务监控(用户 / 功能使用)
# ---------------------------------------------------------------------------

USER_ACTIVE_TOTAL = None  # type: ignore
USER_REGISTRATIONS_TOTAL = None  # type: ignore
CHAT_MESSAGES_TOTAL = None  # type: ignore
DOCUMENT_OPERATIONS_TOTAL = None  # type: ignore
TASKS_CREATED_TOTAL = None  # type: ignore

# ---------------------------------------------------------------------------
# 3. 应用监控(LangGraph / 飞轮 / 拓扑 / 工具)
# ---------------------------------------------------------------------------

LANGGRAPH_NODE_DURATION_SECONDS = None  # type: ignore
LANGGRAPH_NODE_EXECUTIONS_TOTAL = None  # type: ignore
FLYWHEEL_TRIGGER_TOTAL = None  # type: ignore
TOPOLOGY_NODE_COUNT = None  # type: ignore
TOPOLOGY_EDGE_COUNT = None  # type: ignore
TOOL_EXECUTIONS_TOTAL = None  # type: ignore
TOOL_EXECUTION_DURATION_SECONDS = None  # type: ignore
TOOL_ERRORS_TOTAL = None  # type: ignore

# ---------------------------------------------------------------------------
# 4. 安全监控(登录 / 权限 / 限流 / 注入)
# ---------------------------------------------------------------------------

LOGIN_ATTEMPTS_TOTAL = None  # type: ignore
PERMISSION_DENIED_TOTAL = None  # type: ignore
RATE_LIMIT_TRIGGERED_TOTAL = None  # type: ignore
INJECTION_BLOCKED_TOTAL = None  # type: ignore
SENSITIVE_HIT_TOTAL = None  # type: ignore
MFA_CHALLENGE_TOTAL = None  # type: ignore
AUDIT_LOG_ENTRIES_TOTAL = None  # type: ignore

# ---------------------------------------------------------------------------
# 5. LLM 监控
# ---------------------------------------------------------------------------

LLM_CALLS_TOTAL = None  # type: ignore
LLM_TOKENS_USED_TOTAL = None  # type: ignore
LLM_CALL_DURATION_SECONDS = None  # type: ignore
LLM_ERRORS_TOTAL = None  # type: ignore


# ============================================================================
# 初始化指标(仅当 prometheus_client 可用时)
# ============================================================================


def _init_metrics() -> None:
    """初始化所有 Prometheus 指标。幂等,可多次调用。

    线程安全:内部使用 _init_lock 保证多线程下只注册一次,
    避免重复注册导致的 ValueError。
    """
    global HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_IN_PROGRESS
    global USER_ACTIVE_TOTAL, USER_REGISTRATIONS_TOTAL, CHAT_MESSAGES_TOTAL
    global DOCUMENT_OPERATIONS_TOTAL, TASKS_CREATED_TOTAL
    global LANGGRAPH_NODE_DURATION_SECONDS, LANGGRAPH_NODE_EXECUTIONS_TOTAL
    global FLYWHEEL_TRIGGER_TOTAL, TOPOLOGY_NODE_COUNT, TOPOLOGY_EDGE_COUNT
    global TOOL_EXECUTIONS_TOTAL, TOOL_EXECUTION_DURATION_SECONDS, TOOL_ERRORS_TOTAL
    global LOGIN_ATTEMPTS_TOTAL, PERMISSION_DENIED_TOTAL, RATE_LIMIT_TRIGGERED_TOTAL
    global INJECTION_BLOCKED_TOTAL, SENSITIVE_HIT_TOTAL, MFA_CHALLENGE_TOTAL
    global AUDIT_LOG_ENTRIES_TOTAL
    global LLM_CALLS_TOTAL, LLM_TOKENS_USED_TOTAL, LLM_CALL_DURATION_SECONDS, LLM_ERRORS_TOTAL

    if not _PROMETHEUS_AVAILABLE or _registry is None:
        return

    # 快速路径:已初始化则直接返回(无锁)
    if HTTP_REQUESTS_TOTAL is not None:
        return

    # 加锁后再次检查(double-checked locking),防止多线程重复注册
    with _init_lock:
        if HTTP_REQUESTS_TOTAL is not None:
            return

        # --- 系统监控 ---
        HTTP_REQUESTS_TOTAL = Counter(
            "officeagent_http_requests_total",
            "Total HTTP requests",
            ["method", "path", "status"],
            registry=_registry,
        )
        HTTP_REQUEST_DURATION_SECONDS = Histogram(
            "officeagent_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "path"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=_registry,
        )
        HTTP_REQUESTS_IN_PROGRESS = Gauge(
            "officeagent_http_requests_in_progress",
            "HTTP requests currently in progress",
            ["method"],
            registry=_registry,
        )

        # --- 业务监控 ---
        USER_ACTIVE_TOTAL = Counter(
            "officeagent_user_active_total",
            "Total active user events (login / API call)",
            ["user_id"],
            registry=_registry,
        )
        USER_REGISTRATIONS_TOTAL = Counter(
            "officeagent_user_registrations_total",
            "Total user registrations",
            ["source"],  # local / ldap / sso
            registry=_registry,
        )
        CHAT_MESSAGES_TOTAL = Counter(
            "officeagent_chat_messages_total",
            "Total chat messages processed",
            ["mode"],  # legacy / evolve
            registry=_registry,
        )
        DOCUMENT_OPERATIONS_TOTAL = Counter(
            "officeagent_document_operations_total",
            "Total document operations",
            ["operation"],  # upload / download / delete / convert
            registry=_registry,
        )
        TASKS_CREATED_TOTAL = Counter(
            "officeagent_tasks_created_total",
            "Total tasks created",
            ["task_type"],
            registry=_registry,
        )

        # --- 应用监控 ---
        LANGGRAPH_NODE_DURATION_SECONDS = Histogram(
            "officeagent_langgraph_node_duration_seconds",
            "LangGraph node execution duration in seconds",
            ["node_name"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
            registry=_registry,
        )
        LANGGRAPH_NODE_EXECUTIONS_TOTAL = Counter(
            "officeagent_langgraph_node_executions_total",
            "Total LangGraph node executions",
            ["node_name", "status"],  # success / error
            registry=_registry,
        )
        FLYWHEEL_TRIGGER_TOTAL = Counter(
            "officeagent_flywheel_trigger_total",
            "Total flywheel (self-evolution) triggers",
            ["stage"],  # perception / knowledge / reflection / climbing
            registry=_registry,
        )
        TOPOLOGY_NODE_COUNT = Gauge(
            "officeagent_topology_node_count",
            "Total nodes in topology graph",
            registry=_registry,
        )
        TOPOLOGY_EDGE_COUNT = Gauge(
            "officeagent_topology_edge_count",
            "Total edges in topology graph",
            registry=_registry,
        )
        TOOL_EXECUTIONS_TOTAL = Counter(
            "officeagent_tool_executions_total",
            "Total tool executions",
            ["tool_name", "status"],
            registry=_registry,
        )
        TOOL_EXECUTION_DURATION_SECONDS = Histogram(
            "officeagent_tool_execution_duration_seconds",
            "Tool execution duration in seconds",
            ["tool_name"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=_registry,
        )
        TOOL_ERRORS_TOTAL = Counter(
            "officeagent_tool_errors_total",
            "Total tool execution errors",
            ["tool_name", "error_type"],
            registry=_registry,
        )

        # --- 安全监控 ---
        LOGIN_ATTEMPTS_TOTAL = Counter(
            "officeagent_login_attempts_total",
            "Total login attempts",
            ["method", "result"],  # method: password/ldap/sso; result: success/failure
            registry=_registry,
        )
        PERMISSION_DENIED_TOTAL = Counter(
            "officeagent_permission_denied_total",
            "Total permission denied events",
            ["permission", "endpoint"],
            registry=_registry,
        )
        RATE_LIMIT_TRIGGERED_TOTAL = Counter(
            "officeagent_rate_limit_triggered_total",
            "Total rate limit triggered events",
            ["limiter_type"],  # api / llm / login
            registry=_registry,
        )
        INJECTION_BLOCKED_TOTAL = Counter(
            "officeagent_injection_blocked_total",
            "Total injection attempts blocked",
            ["injection_type"],  # sql / xss / prompt_injection / command
            registry=_registry,
        )
        SENSITIVE_HIT_TOTAL = Counter(
            "officeagent_sensitive_hit_total",
            "Total sensitive content hits",
            ["category"],
            registry=_registry,
        )
        MFA_CHALLENGE_TOTAL = Counter(
            "officeagent_mfa_challenge_total",
            "Total MFA challenge events",
            ["factor_type", "result"],  # totp/sms/email/recovery; success/failure
            registry=_registry,
        )
        AUDIT_LOG_ENTRIES_TOTAL = Counter(
            "officeagent_audit_log_entries_total",
            "Total audit log entries written",
            ["action"],
            registry=_registry,
        )

        # --- LLM 监控 ---
        LLM_CALLS_TOTAL = Counter(
            "officeagent_llm_calls_total",
            "Total LLM API calls",
            ["provider", "model"],
            registry=_registry,
        )
        LLM_TOKENS_USED_TOTAL = Counter(
            "officeagent_llm_tokens_used_total",
            "Total LLM tokens used",
            ["provider", "model", "type"],  # type: prompt / completion
            registry=_registry,
        )
        LLM_CALL_DURATION_SECONDS = Histogram(
            "officeagent_llm_call_duration_seconds",
            "LLM call duration in seconds",
            ["provider", "model"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=_registry,
        )
        LLM_ERRORS_TOTAL = Counter(
            "officeagent_llm_errors_total",
            "Total LLM call errors",
            ["provider", "error_type"],
            registry=_registry,
        )


# ============================================================================
# FastAPI 集成
# ============================================================================


async def _http_middleware(request: "Request", call_next) -> Any:
    """HTTP 请求指标中间件(异步)。

    自动记录请求 QPS / 延迟 / 状态码 / 在途数,异常时记 500。
    Prometheus Counter.inc() 内部为原子操作,线程安全。
    """
    if not _PROMETHEUS_AVAILABLE or HTTP_REQUESTS_TOTAL is None:
        return await call_next(request)

    method = request.method
    # 标准化路径(避免高基数,如 /api/v1/users/{id} → /api/v1/users/:id)
    path = _normalize_path(request.url.path)

    HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        status = response.status_code
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
        return response
    except Exception:
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=500).inc()
        raise
    finally:
        elapsed = time.perf_counter() - start_time
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(elapsed)
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()


# 高基数路径模式(需归一化)
_PATH_PATTERNS = [
    ("/api/v1/users/", "/api/v1/users/:id"),
    ("/api/v1/documents/", "/api/v1/documents/:id"),
    ("/api/v1/tasks/", "/api/v1/tasks/:id"),
    ("/api/v1/rbac/users/", "/api/v1/rbac/users/:id"),
    ("/api/v1/rbac/roles/", "/api/v1/rbac/roles/:id"),
    ("/api/v1/rbac/departments/", "/api/v1/rbac/departments/:id"),
    ("/api/v1/rbac/positions/", "/api/v1/rbac/positions/:id"),
    ("/api/v1/admin/users/", "/api/v1/admin/users/:id"),
    ("/api/v1/admin/audit/", "/api/v1/admin/audit/:id"),
    ("/api/v1/auth/sso/saml/", "/api/v1/auth/sso/saml/:provider"),
    ("/api/v1/auth/sso/oauth/", "/api/v1/auth/sso/oauth/:provider"),
]


def _normalize_path(path: str) -> str:
    """将动态路径参数归一化,避免 Prometheus 指标高基数。"""
    for prefix, replacement in _PATH_PATTERNS:
        if path.startswith(prefix):
            # 截断到前缀长度 + 替换
            return replacement
    return path


def setup_metrics(app: "FastAPI") -> None:
    """在 FastAPI 应用中注册 Prometheus 指标。

    功能:
      1. 初始化所有指标定义
      2. 添加 HTTP 请求中间件(自动记录 QPS / 延迟 / 状态码)
      3. 挂载 /metrics 端点(Prometheus scrape target)

    受环境变量 PROMETHEUS_ENABLED 控制(默认 true)。
    """
    enabled = os.getenv("PROMETHEUS_ENABLED", "true").lower() in ("true", "1", "yes", "on")

    if not enabled:
        return

    if not _PROMETHEUS_AVAILABLE:
        return

    _init_metrics()

    # 添加 HTTP 中间件
    from starlette.middleware.base import BaseHTTPMiddleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=_http_middleware)

    # 挂载 /metrics 端点
    metrics_app = make_asgi_app(registry=_registry)
    app.mount("/metrics", metrics_app)


# ============================================================================
# 业务指标记录函数(供业务代码调用)
# ============================================================================


def record_login(success: bool, method: str = "password") -> None:
    """记录登录尝试。"""
    if LOGIN_ATTEMPTS_TOTAL is not None:
        result = "success" if success else "failure"
        LOGIN_ATTEMPTS_TOTAL.labels(method=method, result=result).inc()


def record_user_active(user_id: str) -> None:
    """记录用户活跃事件。"""
    if USER_ACTIVE_TOTAL is not None:
        USER_ACTIVE_TOTAL.labels(user_id=user_id).inc()


def record_user_registration(source: str = "local") -> None:
    """记录用户注册。"""
    if USER_REGISTRATIONS_TOTAL is not None:
        USER_REGISTRATIONS_TOTAL.labels(source=source).inc()


def record_chat_message(mode: str = "evolve") -> None:
    """记录聊天消息。"""
    if CHAT_MESSAGES_TOTAL is not None:
        CHAT_MESSAGES_TOTAL.labels(mode=mode).inc()


def record_document_operation(operation: str) -> None:
    """记录文档操作。"""
    if DOCUMENT_OPERATIONS_TOTAL is not None:
        DOCUMENT_OPERATIONS_TOTAL.labels(operation=operation).inc()


def record_task_created(task_type: str) -> None:
    """记录任务创建。"""
    if TASKS_CREATED_TOTAL is not None:
        TASKS_CREATED_TOTAL.labels(task_type=task_type).inc()


def record_langgraph_node(node_name: str, duration_seconds: float, success: bool = True) -> None:
    """记录 LangGraph 节点执行。"""
    if LANGGRAPH_NODE_DURATION_SECONDS is not None:
        LANGGRAPH_NODE_DURATION_SECONDS.labels(node_name=node_name).observe(duration_seconds)
    if LANGGRAPH_NODE_EXECUTIONS_TOTAL is not None:
        status = "success" if success else "error"
        LANGGRAPH_NODE_EXECUTIONS_TOTAL.labels(node_name=node_name, status=status).inc()


def record_flywheel_trigger(stage: str) -> None:
    """记录飞轮触发。"""
    if FLYWHEEL_TRIGGER_TOTAL is not None:
        FLYWHEEL_TRIGGER_TOTAL.labels(stage=stage).inc()


def update_topology_stats(node_count: int, edge_count: int) -> None:
    """更新拓扑图统计(Gauge)。"""
    if TOPOLOGY_NODE_COUNT is not None:
        TOPOLOGY_NODE_COUNT.set(node_count)
    if TOPOLOGY_EDGE_COUNT is not None:
        TOPOLOGY_EDGE_COUNT.set(edge_count)


def record_tool_execution(tool_name: str, duration_seconds: float, success: bool = True) -> None:
    """记录工具执行。"""
    if TOOL_EXECUTION_DURATION_SECONDS is not None:
        TOOL_EXECUTION_DURATION_SECONDS.labels(tool_name=tool_name).observe(duration_seconds)
    if TOOL_EXECUTIONS_TOTAL is not None:
        status = "success" if success else "error"
        TOOL_EXECUTIONS_TOTAL.labels(tool_name=tool_name, status=status).inc()


def record_tool_error(tool_name: str, error_type: str) -> None:
    """记录工具执行错误。"""
    if TOOL_ERRORS_TOTAL is not None:
        TOOL_ERRORS_TOTAL.labels(tool_name=tool_name, error_type=error_type).inc()


def record_permission_denied(permission: str, endpoint: str) -> None:
    """记录权限拒绝。"""
    if PERMISSION_DENIED_TOTAL is not None:
        PERMISSION_DENIED_TOTAL.labels(permission=permission, endpoint=endpoint).inc()


def record_rate_limit_triggered(limiter_type: str = "api") -> None:
    """记录限流触发。"""
    if RATE_LIMIT_TRIGGERED_TOTAL is not None:
        RATE_LIMIT_TRIGGERED_TOTAL.labels(limiter_type=limiter_type).inc()


def record_injection_blocked(injection_type: str) -> None:
    """记录注入拦截。"""
    if INJECTION_BLOCKED_TOTAL is not None:
        INJECTION_BLOCKED_TOTAL.labels(injection_type=injection_type).inc()


def record_sensitive_hit(category: str) -> None:
    """记录敏感词命中。"""
    if SENSITIVE_HIT_TOTAL is not None:
        SENSITIVE_HIT_TOTAL.labels(category=category).inc()


def record_mfa_challenge(factor_type: str, success: bool) -> None:
    """记录 MFA 挑战。"""
    if MFA_CHALLENGE_TOTAL is not None:
        result = "success" if success else "failure"
        MFA_CHALLENGE_TOTAL.labels(factor_type=factor_type, result=result).inc()


def record_audit_log(action: str) -> None:
    """记录审计日志写入。"""
    if AUDIT_LOG_ENTRIES_TOTAL is not None:
        AUDIT_LOG_ENTRIES_TOTAL.labels(action=action).inc()


def record_llm_call(provider: str, model: str, duration_seconds: float) -> None:
    """记录 LLM 调用。"""
    if LLM_CALL_DURATION_SECONDS is not None:
        LLM_CALL_DURATION_SECONDS.labels(provider=provider, model=model).observe(duration_seconds)
    if LLM_CALLS_TOTAL is not None:
        LLM_CALLS_TOTAL.labels(provider=provider, model=model).inc()


def record_llm_tokens(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """记录 LLM token 用量。

    Args:
        provider:          LLM 供应方(如 openai/glm/anthropic)
        model:             模型名
        prompt_tokens:     输入 token 数(必须 >= 0)
        completion_tokens: 输出 token 数(必须 >= 0)

    负值将被截断为 0(防御性处理,避免外部传入异常值污染指标)。
    """
    if prompt_tokens < 0 or completion_tokens < 0:
        prompt_tokens = max(0, prompt_tokens)
        completion_tokens = max(0, completion_tokens)
    if LLM_TOKENS_USED_TOTAL is not None:
        LLM_TOKENS_USED_TOTAL.labels(
            provider=provider, model=model, type="prompt"
        ).inc(prompt_tokens)
        LLM_TOKENS_USED_TOTAL.labels(
            provider=provider, model=model, type="completion"
        ).inc(completion_tokens)


def record_llm_error(provider: str, error_type: str) -> None:
    """记录 LLM 调用错误。"""
    if LLM_ERRORS_TOTAL is not None:
        LLM_ERRORS_TOTAL.labels(provider=provider, error_type=error_type).inc()


def is_enabled() -> bool:
    """检查 Prometheus 指标是否已启用。"""
    return _PROMETHEUS_AVAILABLE and HTTP_REQUESTS_TOTAL is not None
