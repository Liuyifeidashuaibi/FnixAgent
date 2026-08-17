"""Phase 4.4 Dashboard API 测试。

覆盖:
  1. GET /dashboard/overview       — 总览
  2. GET /dashboard/users          — 用户统计
  3. GET /dashboard/audit          — 审计统计
  4. GET /dashboard/moderation     — 审核统计
  5. PATCH /dashboard/moderation/config — 更新审核配置
  6. GET /dashboard/system         — 系统信息
  7. GET /dashboard/trends         — 趋势
  8. 鉴权:非 admin 403,未登录 401
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置存储。"""
    from fnixagent.core.security import rbac
    from fnixagent.services.moderation_service import reset_moderation_service
    from fnixagent.services.storage import reset_stores
    from fnixagent.services.storage_audit import reset_audit_store
    from fnixagent.services.storage_rbac import reset_rbac_store

    reset_audit_store()
    reset_stores()
    reset_rbac_store()
    reset_moderation_service()
    rbac.invalidate_all_permission_cache()
    yield
    reset_audit_store()
    reset_stores()
    reset_rbac_store()
    reset_moderation_service()
    rbac.invalidate_all_permission_cache()


def _create_app():
    """创建带 dashboard + auth 路由的测试 app。"""
    from fnixagent.api.routers import auth, dashboard

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    return app


def _register_admin_and_login(client, username="admin1"):
    """注册管理员并登录。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Pass1234"},
    )
    assert resp.status_code == 200, resp.text
    user_id = resp.json()["id"]

    # 提升为 admin
    from fnixagent.services.storage import get_user_store

    get_user_store().update_role(user_id, "admin")

    # 登录
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Pass1234"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"], user_id


def _register_normal_user_and_login(client, username="user1"):
    """注册普通用户并登录。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": "Pass1234"},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Pass1234"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ===========================================================================
# 鉴权测试
# ===========================================================================


class TestDashboardAuth:
    """Dashboard API 鉴权。"""

    def test_unauthenticated_401(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.get("/api/v1/dashboard/overview")
        assert resp.status_code == 401

    def test_normal_user_403(self):
        app = _create_app()
        client = TestClient(app)
        token = _register_normal_user_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_admin_200(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# ===========================================================================
# Overview API
# ===========================================================================


class TestDashboardOverview:
    """总览 API。"""

    def test_overview_returns_user_stats(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        # 多注册几个用户(用户名 >= 3 字符,符合 schema 约束)
        for i in range(3):
            resp = client.post(
                "/api/v1/auth/register",
                json={"username": f"user{i}", "email": f"user{i}@e.com", "password": "Pass1234"},
            )
            assert resp.status_code == 200, f"注册 user{i} 失败: {resp.text}"
        resp = client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["users"]["total"] >= 4, f"期望 >=4,实际 {data['users']['total']}"
        assert data["users"]["active"] >= 4
        assert data["users"]["disabled"] == 0
        assert "system" in data
        assert "version" in data["system"]
        assert "uptime_seconds" in data["system"]
        assert data["system"]["storage_mode"] in ("memory", "postgres")

    def test_overview_includes_moderation_stats(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "moderation" in data
        assert "total_input" in data["moderation"]

    def test_overview_includes_audit_stats(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "audit" in data
        assert "last_24h_count" in data["audit"]

    def test_overview_counts_pending_deletion(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        # 注册用户并软删除
        client.post(
            "/api/v1/auth/register",
            json={"username": "todelete", "email": "td@e.com", "password": "Pass1234"},
        )
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user = store.get_by_username("todelete")
        store.soft_delete_user(user.id)

        resp = client.get(
            "/api/v1/dashboard/overview",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()["data"]
        assert data["users"]["pending_deletion"] >= 1


# ===========================================================================
# Users API
# ===========================================================================


class TestDashboardUsers:
    """用户统计 API。"""

    def test_users_returns_by_role(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        # 用户名 >= 3 字符,符合 schema 约束
        for i in range(5):
            resp = client.post(
                "/api/v1/auth/register",
                json={"username": f"role{i}", "email": f"role{i}@e.com", "password": "Pass1234"},
            )
            assert resp.status_code == 200, f"注册 role{i} 失败: {resp.text}"
        resp = client.get(
            "/api/v1/dashboard/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "by_role" in data
        assert data["by_role"].get("user", 0) >= 5
        assert data["by_role"].get("admin", 0) >= 1
        assert "daily_new_7d" in data
        assert len(data["daily_new_7d"]) == 7


# ===========================================================================
# Audit API
# ===========================================================================


class TestDashboardAudit:
    """审计统计 API。"""

    def test_audit_returns_action_distribution(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        # 触发一些审计事件(登录失败)
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin1", "password": "wrong"},
        )
        resp = client.get(
            "/api/v1/dashboard/audit?hours=24",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "action_distribution" in data
        assert data["total_events"] >= 1

    def test_audit_with_custom_hours(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/audit?hours=48",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["window_hours"] == 48


# ===========================================================================
# Moderation API
# ===========================================================================


class TestDashboardModeration:
    """审核统计 + 配置 API。"""

    def test_moderation_returns_config(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/moderation",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["enabled"] is True
        assert data["input_enabled"] is True
        assert data["output_enabled"] is True

    def test_update_moderation_config(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.patch(
            "/api/v1/dashboard/moderation/config",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"block_high_risk_only": True, "high_risk_threshold": 50},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "block_high_risk_only" in data["updated"]
        assert data["current_config"]["block_high_risk_only"] is True
        assert data["current_config"]["high_risk_threshold"] == 50

    def test_update_moderation_config_ignores_unknown_keys(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.patch(
            "/api/v1/dashboard/moderation/config",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"unknown_key": "value", "enabled": False},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "unknown_key" not in data["updated"]
        assert "enabled" in data["updated"]
        assert data["current_config"]["enabled"] is False


# ===========================================================================
# System API
# ===========================================================================


class TestDashboardSystem:
    """系统信息 API。"""

    def test_system_returns_info(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/system",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "version" in data
        assert "uptime_seconds" in data
        assert "uptime_human" in data
        assert "storage_mode" in data
        assert "python_version" in data

    def test_system_uptime_human_readable(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/system",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()["data"]
        # 格式应为 "Xd Yh Zm" 或 "Yh Zm" 或 "Zm"
        assert "m" in data["uptime_human"]


# ===========================================================================
# Trends API
# ===========================================================================


class TestDashboardTrends:
    """趋势 API。"""

    def test_trends_returns_7_days(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/trends?days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["days"] == 7
        assert len(data["trends"]) == 7
        for item in data["trends"]:
            assert "date" in item
            assert "new_users" in item
            assert "audit_events" in item

    def test_trends_with_custom_days(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        resp = client.get(
            "/api/v1/dashboard/trends?days=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["days"] == 3
        assert len(data["trends"]) == 3

    def test_trends_today_has_new_user(self):
        app = _create_app()
        client = TestClient(app)
        token, _ = _register_admin_and_login(client)
        # 注册一个新用户(今天)
        client.post(
            "/api/v1/auth/register",
            json={"username": "trenduser", "email": "tu@e.com", "password": "Pass1234"},
        )
        resp = client.get(
            "/api/v1/dashboard/trends?days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()["data"]
        # 最后一项是今天
        today = data["trends"][-1]
        assert today["new_users"] >= 1
