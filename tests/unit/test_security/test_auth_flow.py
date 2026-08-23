"""
端到端鉴权流程测试(覆盖验收标准 ③④⑤⑥)。

通过 FastAPI TestClient 模拟完整客户端链路:
    ③ 双 Token 刷新流程测试
    ④ 设备指纹不匹配时拒绝 Refresh
    ⑤ 登出后 Access Token 在 1s 内失效
    ⑥ 全链路仅见密文(模拟客户端用公钥加密密码 → 服务端解密)

测试用例独立于 tests/unit/test_api/test_auth.py,聚焦 Phase 0.4 新增的安全流程。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import base64
import os
import sys
import time

# 确保 src 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fnixagent.api.routers import auth as auth_router
from fnixagent.core.security.auth.blacklist import reset_blacklist
from fnixagent.core.security.auth.keystore import reset_server_keypair
from fnixagent.core.security.auth.rsa_crypto import is_rsa_available
from fnixagent.services.storage import reset_stores

# ---------------------------------------------------------------------------
# 公共夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """构建只含 auth 路由的 FastAPI 应用。"""
    application = FastAPI()
    application.include_router(auth_router.router, prefix="/api/v1")
    return application


@pytest.fixture
def client(app):
    """TestClient,每个测试自动重置 stores / keystore / blacklist。"""
    reset_stores()
    reset_server_keypair()
    reset_blacklist()
    with TestClient(app) as c:
        yield c
    reset_stores()
    reset_server_keypair()
    reset_blacklist()


def _client_encrypt_password(public_pem: str, password: str) -> str:
    """模拟客户端用服务端公钥加密密码(OAEP+SHA256),返回 Base64。"""
    public_key = serialization.load_pem_public_key(
        public_pem.encode("utf-8"),
        backend=default_backend(),
    )
    ciphertext = public_key.encrypt(
        password.encode("utf-8"),
        rsa_padding.OAEP(
            mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def _register_user(client, username="alice", password="Secret123!"):
    """注册一个测试用户。"""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "role": "user",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 验收标准 ⑥:全链路加密密码登录
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason="cryptography 不可用")
class TestEncryptedLoginFlow:
    """全链路加密密码登录(模拟客户端 → 服务端)。"""

    def test_get_pubkey_returns_rsa_public_key(self, client):
        """GET /auth/pubkey 返回 PEM 格式 RSA-2048 公钥。"""
        resp = client.get("/api/v1/auth/pubkey")
        assert resp.status_code == 200
        data = resp.json()
        assert "BEGIN PUBLIC KEY" in data["public_key"]
        assert data["algorithm"] == "RSA-2048-OAEP-SHA256"
        assert data["key_id"]  # 16 字符指纹
        assert len(data["key_id"]) == 16

    def test_login_with_encrypted_password_succeeds(self, client):
        """客户端加密密码登录:6 步全链路。"""
        _register_user(client, "alice", "Secret123!")

        # 1. 客户端获取公钥
        pubkey_resp = client.get("/api/v1/auth/pubkey")
        public_pem = pubkey_resp.json()["public_key"]

        # 2. 客户端用公钥加密密码
        encrypted_pwd = _client_encrypt_password(public_pem, "Secret123!")

        # 3. 客户端提交加密密码
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": encrypted_pwd,
                "is_password_encrypted": True,
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # 4. 返回双 Token
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["expires_in"] == 2 * 3600
        assert data["refresh_expires_in"] == 7 * 24 * 3600

    def test_login_with_encrypted_password_wrong_decryption_fails(self, client):
        """加密密码但密文损坏 → 401(不暴露具体原因)。"""
        _register_user(client, "bob", "Secret123!")
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "bob",
                "password": "!!!invalid_base64_ciphertext!!!",
                "is_password_encrypted": True,
            },
        )
        assert resp.status_code == 401
        assert "解密失败" in resp.json()["detail"]

    def test_login_plaintext_backward_compat(self, client):
        """旧客户端明文密码登录仍可用(向后兼容)。"""
        _register_user(client, "carol", "Secret123!")
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "carol", "password": "Secret123!"},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"]


# ---------------------------------------------------------------------------
# 验收标准 ③:双 Token 刷新流程
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason="cryptography 不可用")
class TestRefreshTokenFlow:
    """双 Token 刷新流程。"""

    def test_refresh_succeeds_returns_new_pair(self, client):
        """合法 Refresh Token 换发新的双 Token。"""
        _register_user(client, "alice", "Secret123!")
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        old_refresh = resp.json()["refresh_token"]
        old_access = resp.json()["access_token"]

        # 用 Refresh Token 换新
        resp2 = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp2.status_code == 200, resp2.text
        new_data = resp2.json()
        assert new_data["access_token"]
        assert new_data["refresh_token"]
        # 新 Token 与旧 Token 不同
        assert new_data["access_token"] != old_access
        assert new_data["refresh_token"] != old_refresh

    def test_refresh_token_one_time_use(self, client):
        """Refresh Token 一次性,用过立即作废。"""
        _register_user(client, "alice", "Secret123!")
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        refresh = resp.json()["refresh_token"]

        # 第一次使用:成功
        r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert r1.status_code == 200

        # 第二次使用:失败(已加入黑名单)
        r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert r2.status_code == 401
        assert "已被使用" in r2.json()["detail"]

    def test_refresh_with_access_token_rejected(self, client):
        """用 Access Token 当 Refresh Token 用 → 401(类型不匹配)。"""
        _register_user(client, "alice", "Secret123!")
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        access_token = resp.json()["access_token"]

        r = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
        assert r.status_code == 401
        assert "Refresh Token 无效" in r.json()["detail"]

    def test_refresh_with_invalid_token_rejected(self, client):
        """非法 Refresh Token → 401。"""
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        assert r.status_code == 401

    def test_refresh_for_nonexistent_user_rejected(self, client):
        """Refresh Token 中 user_id 对应用户不存在 → 401。"""
        # 直接构造一个 Refresh Token(用户不存在)
        from fnixagent.core.security.auth.token import create_refresh_token

        refresh = create_refresh_token(user_id=99999, username="ghost", role="user")
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 401
        assert "用户不存在" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 验收标准 ④:设备指纹不匹配时拒绝 Refresh
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason="cryptography 不可用")
class TestDeviceFingerprintOnRefresh:
    """设备指纹不匹配时拒绝 Refresh Token。"""

    def test_refresh_with_matching_device_fp_succeeds(self, client):
        """登录带 client_uuid,Refresh 时同 UUID → 成功。"""
        _register_user(client, "alice", "Secret123!")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "Secret123!",
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
            headers={"User-Agent": "Electron/1.0"},
        )
        assert login_resp.status_code == 200
        refresh = login_resp.json()["refresh_token"]

        # Refresh 时带相同 UUID + 相同 UA
        r = client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": refresh,
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
            headers={"User-Agent": "Electron/1.0"},
        )
        assert r.status_code == 200, r.text

    def test_refresh_with_mismatched_uuid_rejected(self, client):
        """登录带 UUID-A,Refresh 时换成 UUID-B → 401(验收标准 ④)。"""
        _register_user(client, "alice", "Secret123!")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "Secret123!",
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
            headers={"User-Agent": "Electron/1.0"},
        )
        refresh = login_resp.json()["refresh_token"]

        # 攻击者用不同 UUID 尝试 Refresh
        r = client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": refresh,
                "client_uuid": "660e8400-e29b-41d4-a716-446655440000",  # 不同 UUID
            },
            headers={"User-Agent": "Electron/1.0"},
        )
        assert r.status_code == 401
        assert "设备指纹不匹配" in r.json()["detail"]

    def test_refresh_with_mismatched_user_agent_rejected(self, client):
        """登录 UA=A,Refresh 时 UA=B → 401。"""
        _register_user(client, "alice", "Secret123!")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "Secret123!",
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
            headers={"User-Agent": "Electron/1.0"},
        )
        refresh = login_resp.json()["refresh_token"]

        # 不同 UA
        r = client.post(
            "/api/v1/auth/refresh",
            json={
                "refresh_token": refresh,
                "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            },
            headers={"User-Agent": "Attacker-Browser/9.9"},
        )
        assert r.status_code == 401
        assert "设备指纹不匹配" in r.json()["detail"]

    def test_refresh_without_client_uuid_skips_fp_check(self, client):
        """登录时不带 client_uuid,Refresh 时不校验设备指纹(向后兼容)。"""
        _register_user(client, "alice", "Secret123!")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        refresh = login_resp.json()["refresh_token"]

        # Refresh 时不带 client_uuid
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# 验收标准 ⑤:登出后 Access Token 在 1s 内失效
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason="cryptography 不可用")
class TestLogoutInvalidatesToken:
    """登出后 Access Token 立即失效。"""

    def test_logout_then_access_token_rejected_within_1s(self, client):
        """登出后用同一 Access Token 访问 /me → 401(验收标准 ⑤)。"""
        _register_user(client, "alice", "Secret123!")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        access_token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # 登出前:/me 可访问
        before = client.get("/api/v1/auth/me", headers=headers)
        assert before.status_code == 200

        # 登出
        logout_resp = client.post("/api/v1/auth/logout", headers=headers)
        assert logout_resp.status_code == 200

        # 登出后:立即(0 延迟)用同一 Token → 401
        t0 = time.time()
        after = client.get("/api/v1/auth/me", headers=headers)
        elapsed = time.time() - t0
        assert after.status_code == 401
        assert "已被撤销" in after.json()["detail"]
        # 确认在 1s 内完成
        assert elapsed < 1.0, f"登出失效应在 1s 内,实际 {elapsed:.3f}s"

    def test_logout_does_not_affect_other_tokens(self, client):
        """登出 Token-A 不影响 Token-B(黑名单按 jti 隔离)。"""
        # 用户 A 登录
        _register_user(client, "alice", "Secret123!")
        a_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        a_token = a_resp.json()["access_token"]
        a_headers = {"Authorization": f"Bearer {a_token}"}

        # 用户 B 登录
        _register_user(client, "bob", "Secret456!")
        b_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": "Secret456!"},
        )
        b_token = b_resp.json()["access_token"]
        b_headers = {"Authorization": f"Bearer {b_token}"}

        # 用户 A 登出
        client.post("/api/v1/auth/logout", headers=a_headers)

        # 用户 A 的 Token 失效
        assert client.get("/api/v1/auth/me", headers=a_headers).status_code == 401
        # 用户 B 的 Token 仍可用
        assert client.get("/api/v1/auth/me", headers=b_headers).status_code == 200

    def test_logout_idempotent(self, client):
        """重复登出同一 Token:第一次 200,第二次 401(Token 已撤销)。"""
        _register_user(client, "alice", "Secret123!")
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Secret123!"},
        )
        headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        # 第一次登出
        r1 = client.post("/api/v1/auth/logout", headers=headers)
        assert r1.status_code == 200

        # 第二次登出:Token 已在黑名单,verify_jwt_token 直接 401
        r2 = client.post("/api/v1/auth/logout", headers=headers)
        assert r2.status_code == 401


# ---------------------------------------------------------------------------
# 验收标准:自动哈希升级(PBKDF2 → Argon2id)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason="cryptography 不可用")
class TestAutoHashUpgrade:
    """登录成功后自动把 PBKDF2 哈希升级为 Argon2id。"""

    def test_pbkdf2_user_upgraded_on_login(self, client):
        """老用户(PBKDF2 哈希)登录后,哈希自动升级为 Argon2id。"""
        from fnixagent.core.security.auth.password import (
            _pbkdf2_hash,
            is_argon2_available,
        )

        if not is_argon2_available():
            pytest.skip("argon2-cffi 不可用")

        # 直接用 PBKDF2 哈希创建一个"老用户"
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        with store._lock:
            uid = store._next_id
            store._next_id += 1
            from fnixagent.services.storage import StoredUser

            user = StoredUser(
                id=uid,
                username="legacy_user",
                email="legacy@example.com",
                password_hash=_pbkdf2_hash("OldPass123!"),  # PBKDF2 哈希
                role="user",
            )
            store._users[uid] = user
            store._username_idx["legacy_user"] = uid
            store._email_idx["legacy@example.com"] = uid

        # 登录(明文密码,触发自动升级)
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "legacy_user", "password": "OldPass123!"},
        )
        assert resp.status_code == 200

        # 验证哈希已升级为 Argon2id
        updated_user = store.get_by_username("legacy_user")
        assert updated_user.password_hash.startswith("$argon2id$"), (
            "老用户登录后哈希应升级为 Argon2id"
        )

    def test_argon2_user_not_rehashed_on_login(self, client):
        """新用户(Argon2id 哈希)登录不会触发重新哈希。"""
        _register_user(client, "new_user", "Secret123!")
        from fnixagent.services.storage import get_user_store

        # 注册后已经是 Argon2id
        user_before = get_user_store().get_by_username("new_user")
        hash_before = user_before.password_hash

        # 登录
        client.post(
            "/api/v1/auth/login",
            json={"username": "new_user", "password": "Secret123!"},
        )

        # 哈希未变
        user_after = get_user_store().get_by_username("new_user")
        assert user_after.password_hash == hash_before
