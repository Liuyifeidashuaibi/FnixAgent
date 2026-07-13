"""
OfficeAgent Prometheus 指标模块测试 — Phase 2.10

覆盖:
  1. 指标初始化(幂等)
  2. HTTP 中间件(请求计数 / 延迟 / 在途)
  3. 路径归一化(避免高基数)
  4. 业务指标记录(login / chat / document / task)
  5. 应用指标记录(langgraph / flywheel / topology / tool / llm)
  6. 安全指标记录(permission_denied / injection / sensitive / rate_limit / mfa / audit)
  7. setup_metrics 集成(/metrics 端点)
  8. PROMETHEUS_ENABLED 环境变量控制
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock
from prometheus_client import REGISTRY, generate_latest

from officeagent.core.observability.metrics import (
    _init_metrics,
    _normalize_path,
    setup_metrics,
    is_enabled,
    record_login,
    record_user_active,
    record_user_registration,
    record_chat_message,
    record_document_operation,
    record_task_created,
    record_langgraph_node,
    record_flywheel_trigger,
    update_topology_stats,
    record_tool_execution,
    record_tool_error,
    record_permission_denied,
    record_rate_limit_triggered,
    record_injection_blocked,
    record_sensitive_hit,
    record_mfa_challenge,
    record_audit_log,
    record_llm_call,
    record_llm_tokens,
    record_llm_error,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_metrics():
    """每个测试前初始化指标(幂等)。"""
    _init_metrics()
    yield


# ============================================================================
# 1. 指标初始化
# ============================================================================


class TestMetricsInit:
    def test_init_metrics_is_idempotent(self):
        """多次调用 _init_metrics 不应报错。"""
        _init_metrics()
        _init_metrics()
        _init_metrics()
        assert is_enabled()

    def test_all_metric_families_registered(self):
        """验证所有指标族已注册到 REGISTRY。"""
        latest = generate_latest().decode("utf-8")
        # 系统监控
        assert "officeagent_http_requests_total" in latest
        assert "officeagent_http_request_duration_seconds" in latest
        assert "officeagent_http_requests_in_progress" in latest
        # 业务监控
        assert "officeagent_user_active_total" in latest
        assert "officeagent_chat_messages_total" in latest
        # 应用监控
        assert "officeagent_langgraph_node_duration_seconds" in latest
        assert "officeagent_tool_executions_total" in latest
        assert "officeagent_llm_calls_total" in latest
        # 安全监控
        assert "officeagent_login_attempts_total" in latest
        assert "officeagent_permission_denied_total" in latest
        assert "officeagent_injection_blocked_total" in latest


# ============================================================================
# 2. 路径归一化
# ============================================================================


class TestNormalizePath:
    def test_static_path_unchanged(self):
        assert _normalize_path("/api/v1/auth/login") == "/api/v1/auth/login"

    def test_dynamic_user_path_normalized(self):
        assert _normalize_path("/api/v1/users/42") == "/api/v1/users/:id"

    def test_dynamic_document_path_normalized(self):
        assert _normalize_path("/api/v1/documents/abc-123") == "/api/v1/documents/:id"

    def test_dynamic_task_path_normalized(self):
        assert _normalize_path("/api/v1/tasks/999") == "/api/v1/tasks/:id"

    def test_dynamic_rbac_role_path_normalized(self):
        assert _normalize_path("/api/v1/rbac/roles/5") == "/api/v1/rbac/roles/:id"

    def test_dynamic_saml_path_normalized(self):
        assert _normalize_path("/api/v1/auth/sso/saml/github") == "/api/v1/auth/sso/saml/:provider"

    def test_dynamic_oauth_path_normalized(self):
        assert _normalize_path("/api/v1/auth/sso/oauth/google") == "/api/v1/auth/sso/oauth/:provider"

    def test_root_path_unchanged(self):
        assert _normalize_path("/") == "/"

    def test_metrics_path_unchanged(self):
        assert _normalize_path("/metrics") == "/metrics"


# ============================================================================
# 3. 业务指标
# ============================================================================


class TestBusinessMetrics:
    def test_record_login_success(self):
        record_login(success=True, method="password")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_login_attempts_total{method="password",result="success"}' in latest

    def test_record_login_failure(self):
        record_login(success=False, method="ldap")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_login_attempts_total{method="ldap",result="failure"}' in latest

    def test_record_user_active(self):
        record_user_active(user_id="user_123")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_user_active_total{user_id="user_123"}' in latest

    def test_record_user_registration(self):
        record_user_registration(source="ldap")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_user_registrations_total{source="ldap"}' in latest

    def test_record_chat_message(self):
        record_chat_message(mode="evolve")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_chat_messages_total{mode="evolve"}' in latest

    def test_record_document_operation(self):
        record_document_operation(operation="upload")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_document_operations_total{operation="upload"}' in latest

    def test_record_task_created(self):
        record_task_created(task_type="research")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_tasks_created_total{task_type="research"}' in latest


# ============================================================================
# 4. 应用指标
# ============================================================================


class TestApplicationMetrics:
    def test_record_langgraph_node(self):
        record_langgraph_node(node_name="planner", duration_seconds=0.5, success=True)
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_langgraph_node_executions_total{node_name="planner",status="success"}' in latest

    def test_record_langgraph_node_failure(self):
        record_langgraph_node(node_name="executor", duration_seconds=1.2, success=False)
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_langgraph_node_executions_total{node_name="executor",status="error"}' in latest

    def test_record_flywheel_trigger(self):
        record_flywheel_trigger(stage="perception")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_flywheel_trigger_total{stage="perception"}' in latest

    def test_update_topology_stats(self):
        update_topology_stats(node_count=100, edge_count=500)
        latest = generate_latest().decode("utf-8")
        assert "officeagent_topology_node_count 100.0" in latest
        assert "officeagent_topology_edge_count 500.0" in latest

    def test_record_tool_execution(self):
        record_tool_execution(tool_name="web_search", duration_seconds=2.5, success=True)
        latest = generate_latest().decode("utf-8")
        # Prometheus 按字母序输出 label(status 在 tool_name 之前)
        assert 'officeagent_tool_executions_total{status="success",tool_name="web_search"}' in latest

    def test_record_tool_error(self):
        record_tool_error(tool_name="pdf_gen", error_type="TimeoutError")
        latest = generate_latest().decode("utf-8")
        # Prometheus 按字母序输出 label(error_type 在 tool_name 之前)
        assert 'officeagent_tool_errors_total{error_type="TimeoutError",tool_name="pdf_gen"}' in latest

    def test_record_llm_call(self):
        record_llm_call(provider="openai", model="gpt-4", duration_seconds=3.2)
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_llm_calls_total{model="gpt-4",provider="openai"}' in latest

    def test_record_llm_tokens(self):
        record_llm_tokens(
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=500,
            completion_tokens=200,
        )
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_llm_tokens_used_total{model="deepseek-chat",provider="deepseek",type="prompt"}' in latest
        assert 'officeagent_llm_tokens_used_total{model="deepseek-chat",provider="deepseek",type="completion"}' in latest

    def test_record_llm_error(self):
        record_llm_error(provider="qwen", error_type="RateLimitError")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_llm_errors_total{error_type="RateLimitError",provider="qwen"}' in latest


# ============================================================================
# 5. 安全指标
# ============================================================================


class TestSecurityMetrics:
    def test_record_permission_denied(self):
        record_permission_denied(permission="user:read", endpoint="/api/v1/users")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_permission_denied_total{endpoint="/api/v1/users",permission="user:read"}' in latest

    def test_record_rate_limit_triggered(self):
        record_rate_limit_triggered(limiter_type="llm")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_rate_limit_triggered_total{limiter_type="llm"}' in latest

    def test_record_injection_blocked(self):
        record_injection_blocked(injection_type="prompt_injection")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_injection_blocked_total{injection_type="prompt_injection"}' in latest

    def test_record_sensitive_hit(self):
        record_sensitive_hit(category="secret_key")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_sensitive_hit_total{category="secret_key"}' in latest

    def test_record_mfa_challenge_success(self):
        record_mfa_challenge(factor_type="totp", success=True)
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_mfa_challenge_total{factor_type="totp",result="success"}' in latest

    def test_record_mfa_challenge_failure(self):
        record_mfa_challenge(factor_type="sms", success=False)
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_mfa_challenge_total{factor_type="sms",result="failure"}' in latest

    def test_record_audit_log(self):
        record_audit_log(action="login.success")
        latest = generate_latest().decode("utf-8")
        assert 'officeagent_audit_log_entries_total{action="login.success"}' in latest


# ============================================================================
# 6. setup_metrics 集成
# ============================================================================


class TestSetupMetrics:
    def test_setup_metrics_adds_endpoint(self):
        """验证 setup_metrics 在 FastAPI 上挂载 /metrics 端点。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        setup_metrics(app)

        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "officeagent_http_requests_total" in response.text

    def test_setup_metrics_disabled_when_env_false(self):
        """PROMETHEUS_ENABLED=false 时不挂载 /metrics。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        with patch.dict(os.environ, {"PROMETHEUS_ENABLED": "false"}):
            setup_metrics(app)

        client = TestClient(app)
        response = client.get("/metrics")
        # 未挂载 /metrics,应返回 404
        assert response.status_code == 404

    def test_http_middleware_records_requests(self):
        """HTTP 中间件应自动记录请求指标。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        setup_metrics(app)

        client = TestClient(app)
        # 发送请求
        response = client.get("/test")
        assert response.status_code == 200

        # 检查 /metrics 是否记录了请求
        metrics_response = client.get("/metrics")
        assert "officeagent_http_requests_total" in metrics_response.text
        assert 'path="/test"' in metrics_response.text
        assert 'status="200"' in metrics_response.text

    def test_http_middleware_records_404(self):
        """404 请求也应被记录。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        setup_metrics(app)

        client = TestClient(app)
        client.get("/nonexistent")

        metrics_response = client.get("/metrics")
        assert 'status="404"' in metrics_response.text

    def test_http_middleware_records_500(self):
        """500 错误请求也应被记录。"""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/error")
        def error_endpoint():
            raise RuntimeError("test error")

        # 覆盖全局异常处理,让 500 真正返回
        @app.exception_handler(Exception)
        async def handler(request, exc):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=500, content={"error": "internal"})

        setup_metrics(app)

        client = TestClient(app, raise_server_exceptions=False)
        client.get("/error")

        metrics_response = client.get("/metrics")
        assert 'status="500"' in metrics_response.text


# ============================================================================
# 7. 边界情况
# ============================================================================


class TestEdgeCases:
    def test_record_functions_safe_when_metrics_not_initialized(self):
        """指标未初始化时,record 函数应安全跳过(不抛异常)。"""
        # 通过 mock 使所有指标为 None
        with patch("officeagent.core.observability.metrics.HTTP_REQUESTS_TOTAL", None), \
             patch("officeagent.core.observability.metrics.LOGIN_ATTEMPTS_TOTAL", None), \
             patch("officeagent.core.observability.metrics.CHAT_MESSAGES_TOTAL", None):
            # 这些调用不应抛异常
            record_login(success=True)
            record_chat_message()
            record_langgraph_node(node_name="test", duration_seconds=0.1)

    def test_is_enabled_returns_true_after_init(self):
        _init_metrics()
        assert is_enabled() is True

    def test_multiple_record_calls_accumulate(self):
        """多次调用应累加,而非覆盖。"""
        # 先记录当前值
        record_login(success=True, method="password")
        record_login(success=True, method="password")
        record_login(success=True, method="password")

        latest = generate_latest().decode("utf-8")
        # 应该看到计数 >= 3(可能包含其他测试的调用)
        lines = [l for l in latest.split("\n") if 'officeagent_login_attempts_total{method="password",result="success"}' in l]
        assert len(lines) == 1
        value = float(lines[0].split()[-1])
        assert value >= 3
