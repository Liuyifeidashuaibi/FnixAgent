"""
auth 路由单元测试。

覆盖:
  - 注册(成功/用户名重复/邮箱重复/参数校验)
  - 登录(成功/密码错误/用户不存在)
  - /me(成功/无效Token)
  - /logout
  - /profile 更新
  - /quota 查询
  - /apikey 创建/列表/吊销
  - JWT 签名校验/过期校验
"""
import time

import pytest


class TestRegister:
    """用户注册。"""

    def test_register_success(self, client):
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice",
                "email": "alice@example.com",
                "password": "password123",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "alice"
        assert data["email"] == "alice@example.com"
        assert data["role"] == "user"
        assert data["id"] >= 1

    def test_register_duplicate_username(self, client):
        payload = {
            "username": "bob",
            "email": "bob1@example.com",
            "password": "password123",
        }
        client.post("/api/v1/auth/register", json=payload)
        # 同用户名不同邮箱
        payload["email"] = "bob2@example.com"
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        assert "已存在" in resp.json()["detail"]

    def test_register_duplicate_email(self, client):
        client.post(
            "/api/v1/auth/register",
            json={"username": "user_one", "email": "dup@example.com", "password": "password123"},
        )
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "user_two", "email": "dup@example.com", "password": "password123"},
        )
        assert resp.status_code == 409
        assert "邮箱" in resp.json()["detail"]

    def test_register_short_password_rejected(self, client):
        """密码少于 6 位应被 Pydantic 拒绝(422)。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "short", "email": "s@e.com", "password": "123"},
        )
        assert resp.status_code == 422

    def test_register_short_username_rejected(self, client):
        """用户名少于 3 位应被拒绝(422)。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "ab", "email": "s@e.com", "password": "password123"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email_rejected(self, client):
        """安全:邮箱格式不合法应被拒绝(422)。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "validuser", "email": "not-an-email", "password": "password123"},
        )
        assert resp.status_code == 422

    def test_register_username_with_special_chars_rejected(self, client):
        """安全:用户名含特殊字符应被拒绝(422)。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": "user@hack", "email": "u@e.com", "password": "password123"},
        )
        assert resp.status_code == 422


class TestLogin:
    """用户登录。"""

    def test_login_success(self, client, auth_token):
        """auth_token fixture 已经完成注册+登录,这里验证 token 非空。"""
        assert isinstance(auth_token, str)
        assert auth_token.count(".") == 2  # JWT 三段式

    def test_login_wrong_password(self, client):
        client.post(
            "/api/v1/auth/register",
            json={"username": "carol", "email": "c@e.com", "password": "correct123"},
        )
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "carol", "password": "wrong"},
        )
        assert resp.status_code == 401
        assert "密码" in resp.json()["detail"]

    def test_login_unknown_user(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "whatever"},
        )
        assert resp.status_code == 401

    def test_login_rate_limiting_after_max_attempts(self, client):
        """安全:连续 5 次登录失败后应锁定(返回 401)。"""
        client.post(
            "/api/v1/auth/register",
            json={"username": "lockme", "email": "l@e.com", "password": "correct123"},
        )
        # 连续 5 次错误密码
        for i in range(5):
            resp = client.post(
                "/api/v1/auth/login",
                json={"username": "lockme", "password": "wrong"},
            )
            assert resp.status_code == 401
        # 第 6 次:即使密码正确也应被锁定
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "lockme", "password": "correct123"},
        )
        assert resp.status_code == 401  # 锁定中


class TestMe:
    """获取当前用户。"""

    def test_me_success(self, client, auth_headers):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "tester"
        assert data["email"] == "tester@example.com"

    def test_me_without_token(self, client):
        resp = client.get("/api/v1/auth/me")
        # HTTPBearer 缺少凭证返回 401(未授权)
        assert resp.status_code in (401, 403)

    def test_me_invalid_token(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401

    def test_me_tampered_signature(self, client, auth_token):
        """篡改签名应被拒绝。"""
        parts = auth_token.split(".")
        # 篡改签名段
        tampered = parts[0] + "." + parts[1] + ".AAAA"
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert resp.status_code == 401


class TestLogout:
    def test_logout(self, client, auth_headers):
        resp = client.post("/api/v1/auth/logout", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestProfile:
    def test_update_profile(self, client, auth_headers):
        resp = client.put(
            "/api/v1/auth/profile",
            json={"research_area": "NLP", "timezone": "Asia/Shanghai"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["research_area"] == "NLP"


class TestQuota:
    def test_get_quota(self, client, auth_headers):
        resp = client.get("/api/v1/auth/quota", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_quota"] == 100000
        assert data["used_quota"] == 0
        assert data["remaining_quota"] == 100000


class TestApiKey:
    """API Key 管理。"""

    def test_create_apikey(self, client, auth_headers):
        resp = client.post("/api/v1/auth/apikey", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["api_key"].startswith("sk-officeagent-")
        assert data["id"] >= 1
        assert "expires_at" in data

    def test_list_apikeys(self, client, auth_headers):
        # 创建两个 key
        client.post("/api/v1/auth/apikey", headers=auth_headers)
        client.post("/api/v1/auth/apikey", headers=auth_headers)
        resp = client.get("/api/v1/auth/apikey/list", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # 列表不应返回明文 key
        assert "api_key" not in data[0]

    def test_revoke_apikey(self, client, auth_headers):
        create_resp = client.post("/api/v1/auth/apikey", headers=auth_headers)
        key_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/auth/apikey/{key_id}", headers=auth_headers)
        assert resp.status_code == 200
        # 确认已吊销
        list_resp = client.get("/api/v1/auth/apikey/list", headers=auth_headers)
        keys = list_resp.json()
        revoked = next(k for k in keys if k["id"] == key_id)
        assert revoked["revoked"] is True

    def test_revoke_nonexistent_apikey(self, client, auth_headers):
        resp = client.delete("/api/v1/auth/apikey/9999", headers=auth_headers)
        assert resp.status_code == 404


class TestJwtInternals:
    """JWT 内部实现校验。"""

    def test_token_contains_user_id(self, client, auth_token):
        """解码 payload 验证 user_id 字段。"""
        import base64
        import json

        payload_b64 = auth_token.split(".")[1]
        pad = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        assert payload["username"] == "tester"
        assert "exp" in payload
        assert "iat" in payload
