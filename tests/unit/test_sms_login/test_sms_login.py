"""Phase 3.0 手机号验证码登录测试。

覆盖:
    1. POST /auth/sms/send-code
       - 成功发送(返回 challenge_id)
       - 手机号格式校验(422)
       - 60s 重发冷却(429)
    2. POST /auth/sms/login
       - 成功登录(返回双 Token)
       - 验证码错误(401)
       - 验证码已使用(401,一次性消费)
       - 验证码已过期(401)
       - 手机号未注册(404,防用户枚举)
       - 账号已禁用(403)
       - 错误次数过多(401,5 次后消费)
    3. 存储层
       - UserStore.get_by_phone(内存实现)
"""
import sys
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 确保 src 在路径中
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置所有存储,确保隔离。"""
    from fnixagent.services.storage_mfa import reset_all_mfa_stores
    from fnixagent.services.storage import reset_stores

    reset_all_mfa_stores()
    reset_stores()
    yield
    reset_all_mfa_stores()
    reset_stores()


@pytest.fixture
def app():
    """构建只含 auth 路由的 FastAPI 应用。"""
    from fnixagent.api.routers import auth
    application = FastAPI()
    application.include_router(auth.router, prefix="/api/v1")
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# 用于捕获 mock SMS 发送的验证码
_CAPTCHA = {"code": None}


def _capture_send_sms(self, phone: str, code: str) -> bool:
    """替换 OTPClient.send_sms,捕获验证码而非实际发送。"""
    _CAPTCHA["code"] = code
    return True


def _register_user_with_phone(client, username="smsuser", phone="13800138000"):
    """注册一个用户并为其设置 profile.phone。"""
    # 1. 通过 API 注册
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "password123",
            "role": "user",
        },
    )
    assert resp.status_code == 200, resp.text
    user_data = resp.json()

    # 2. 直接通过 store 设置 phone(避免依赖 profile 更新 API)
    from fnixagent.services.storage import get_user_store
    store = get_user_store()
    store.update_profile(user_data["id"], {"phone": phone})
    return user_data


# ===========================================================================
# 1. POST /auth/sms/send-code
# ===========================================================================


class TestSmsSendCode:
    """发送短信验证码端点。"""

    def test_send_code_success(self, client):
        """成功发送验证码,返回 challenge_id 与 expires_in。"""
        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            resp = client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138000"},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "challenge_id" in data
        assert data["expires_in"] == 300
        assert data["message"] == "验证码已发送"
        # 验证码已被捕获
        assert _CAPTCHA["code"] is not None
        assert len(_CAPTCHA["code"]) == 6
        assert _CAPTCHA["code"].isdigit()

    def test_send_code_invalid_phone_format(self, client):
        """手机号格式不合法应被 Pydantic 拒绝(422)。"""
        # 少于 11 位
        resp = client.post(
            "/api/v1/auth/sms/send-code",
            json={"phone": "1380013800"},
        )
        assert resp.status_code == 422

        # 不以 1 开头
        resp = client.post(
            "/api/v1/auth/sms/send-code",
            json={"phone": "23800138000"},
        )
        assert resp.status_code == 422

        # 第二位不在 3-9 范围
        resp = client.post(
            "/api/v1/auth/sms/send-code",
            json={"phone": "12800138000"},
        )
        assert resp.status_code == 422

    def test_send_code_resend_cooldown(self, client):
        """同一手机号 60s 内不可重发(429)。"""
        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            # 第一次发送成功
            resp1 = client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13900139000"},
            )
            assert resp1.status_code == 200

            # 第二次立即重发应被拒绝
            resp2 = client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13900139000"},
            )
            assert resp2.status_code == 429
            assert "频繁" in resp2.json()["detail"]

    def test_send_code_different_phones_no_cooldown(self, client):
        """不同手机号不受同一冷却限制。"""
        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            resp1 = client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138000"},
            )
            assert resp1.status_code == 200

            resp2 = client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13900139000"},
            )
            assert resp2.status_code == 200


# ===========================================================================
# 2. POST /auth/sms/login
# ===========================================================================


class TestSmsLogin:
    """手机号验证码登录端点。"""

    def test_login_success(self, client):
        """已注册手机号 + 正确验证码 → 登录成功,返回双 Token。"""
        _register_user_with_phone(client, username="smsuser1", phone="13800138000")

        # 发送验证码(捕获 code)
        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            resp = client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138000"},
            )
            assert resp.status_code == 200

        code = _CAPTCHA["code"]

        # 用验证码登录
        resp = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138000", "code": code},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_wrong_code(self, client):
        """验证码错误 → 401。"""
        _register_user_with_phone(client, username="smsuser2", phone="13800138001")

        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138001"},
            )

        resp = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138001", "code": "000000"},
        )
        # 000000 几乎不可能匹配,应返回 401
        assert resp.status_code == 401
        assert "验证码错误" in resp.json()["detail"]

    def test_login_code_reuse_rejected(self, client):
        """验证码一次性:成功登录后再次使用应失败(401)。"""
        _register_user_with_phone(client, username="smsuser3", phone="13800138002")

        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138002"},
            )
        code = _CAPTCHA["code"]

        # 第一次登录成功
        resp1 = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138002", "code": code},
        )
        assert resp1.status_code == 200

        # 第二次使用同一验证码应失败
        resp2 = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138002", "code": code},
        )
        assert resp2.status_code == 401
        assert "已使用" in resp2.json()["detail"] or "已过期" in resp2.json()["detail"]

    def test_login_unregistered_phone(self, client):
        """手机号未注册 → 404(明确告知未注册,引导注册)。"""
        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13700137000"},
            )
        code = _CAPTCHA["code"]

        resp = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13700137000", "code": code},
        )
        assert resp.status_code == 404
        assert "未注册" in resp.json()["detail"]

    def test_login_without_sending_code(self, client):
        """未发送验证码直接登录 → 401(验证码已过期)。"""
        _register_user_with_phone(client, username="smsuser4", phone="13800138003")

        resp = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138003", "code": "123456"},
        )
        assert resp.status_code == 401
        assert "过期" in resp.json()["detail"] or "重新获取" in resp.json()["detail"]

    def test_login_expired_code(self, client):
        """验证码过期 → 401。"""
        _register_user_with_phone(client, username="smsuser5", phone="13800138004")

        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138004"},
            )
        code = _CAPTCHA["code"]

        # 手动将 challenge 的过期时间设为过去
        from fnixagent.services.storage_mfa import get_otp_challenge_store
        import hashlib
        phone_hash = int(hashlib.sha256("13800138004".encode()).hexdigest()[:8], 16)
        store = get_otp_challenge_store()
        challenge = store.get_active_by_user(phone_hash, "sms_login")
        assert challenge is not None
        # 直接修改内部 challenge 的过期时间
        with store._lock:
            c = store._challenges[challenge.challenge_id]
            c.expires_at = time.time() - 1

        resp = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138004", "code": code},
        )
        # 过期校验在 code 校验之后,但 challenge 仍可被查到(get_active_by_user 已经过滤了过期)
        # 实际上 get_active_by_user 检查 expires_at > now,所以过期后查不到 → 401 已过期
        assert resp.status_code == 401

    def test_login_too_many_attempts(self, client):
        """连续 5 次错误验证码后 challenge 被消费(401 错误次数过多)。"""
        _register_user_with_phone(client, username="smsuser6", phone="13800138005")

        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138005"},
            )

        # 连续 5 次错误(第 5 次触发消费)
        for i in range(5):
            resp = client.post(
                "/api/v1/auth/sms/login",
                json={"phone": "13800138005", "code": "111111"},
            )
            if i < 4:
                assert resp.status_code == 401
                assert "验证码错误" in resp.json()["detail"]
            else:
                # 第 5 次:错误次数过多
                assert resp.status_code == 401
                assert "过多" in resp.json()["detail"] or "重新获取" in resp.json()["detail"]

    def test_login_disabled_user(self, client):
        """被禁用账号 → 403。"""
        user_data = _register_user_with_phone(
            client, username="smsuser7", phone="13800138006"
        )

        # 禁用用户
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        store.set_user_disabled(user_data["id"], True)

        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138006"},
            )
        code = _CAPTCHA["code"]

        resp = client.post(
            "/api/v1/auth/sms/login",
            json={"phone": "13800138006", "code": code},
        )
        assert resp.status_code == 403
        assert "禁用" in resp.json()["detail"]

    def test_login_with_client_uuid(self, client):
        """携带 client_uuid 时,Token 中应包含设备指纹。"""
        _register_user_with_phone(client, username="smsuser8", phone="13800138007")

        with patch(
            "fnixagent.core.security.auth.mfa.OTPClient.send_sms",
            _capture_send_sms,
        ):
            client.post(
                "/api/v1/auth/sms/send-code",
                json={"phone": "13800138007"},
            )
        code = _CAPTCHA["code"]

        resp = client.post(
            "/api/v1/auth/sms/login",
            json={
                "phone": "13800138007",
                "code": code,
                "client_uuid": "test-uuid-1234",
            },
        )
        assert resp.status_code == 200
        # Token 中包含 device_fp(解码 JWT 验证)
        import base64
        import json as _json
        token = resp.json()["access_token"]
        payload_b64 = token.split(".")[1]
        # 补 padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        assert "device_fp" in payload
        assert payload["device_fp"] is not None


# ===========================================================================
# 3. 存储层 — UserStore.get_by_phone
# ===========================================================================


class TestUserStoreGetByPhone:
    """UserStore.get_by_phone 内存实现。"""

    def test_get_by_phone_found(self):
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        user, _ = store.create("phoneuser1", "phone1@e.com", "pass", "user")
        store.update_profile(user.id, {"phone": "13600136000"})
        found = store.get_by_phone("13600136000")
        assert found is not None
        assert found.id == user.id
        assert found.username == "phoneuser1"

    def test_get_by_phone_not_found(self):
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        assert store.get_by_phone("19999999999") is None

    def test_get_by_phone_empty_input(self):
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        assert store.get_by_phone("") is None
        assert store.get_by_phone(None) is None  # type: ignore[arg-type]

    def test_get_by_phone_no_phone_in_profile(self):
        """用户未设置 phone 时不应被找到。"""
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        store.create("nophoneuser", "np@e.com", "pass", "user")
        assert store.get_by_phone("13800138000") is None

    def test_get_by_phone_multiple_users(self):
        """多个用户,通过 phone 精确匹配目标用户。"""
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        u1, _ = store.create("multi1", "m1@e.com", "pass", "user")
        u2, _ = store.create("multi2", "m2@e.com", "pass", "user")
        store.update_profile(u1.id, {"phone": "13100131001"})
        store.update_profile(u2.id, {"phone": "13100131002"})

        assert store.get_by_phone("13100131001").id == u1.id
        assert store.get_by_phone("13100131002").id == u2.id
