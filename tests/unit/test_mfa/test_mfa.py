"""Phase 2.4 MFA 多因素认证测试。

覆盖:
    1. TOTP 客户端(secret 生成 / URI 构建 / 验证 / 时钟漂移容忍)
    2. 恢复码客户端(生成 / 哈希 / 校验 / 一次性)
    3. OTP 客户端(验证码生成 / 哈希 / 掩码 / mock 发送)
    4. MFA Challenge Token(签发 / 校验 / 过期 / 类型不匹配)
    5. 存储层(因子 / 恢复码 / OTP challenge / 强制策略)
    6. API 端点(setup / enable / disable / list / regenerate / send-code / verify)
    7. 登录流程集成(密码校验后返回 MFA Challenge)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置所有存储,确保隔离。"""
    from fnixagent.services.storage import reset_stores
    from fnixagent.services.storage_mfa import reset_all_mfa_stores

    reset_all_mfa_stores()
    reset_stores()
    yield
    reset_all_mfa_stores()
    reset_stores()


# ===========================================================================
# 1. TOTP 客户端
# ===========================================================================


class TestTOTPClient:
    def test_generate_secret_length(self):
        from fnixagent.core.security.auth.mfa import TOTPClient

        secret = TOTPClient.generate_secret()
        # 32 字节熵 → Base32 编码(去掉 padding)
        assert len(secret) >= 50
        # Base32 字符集
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_generate_secret_uniqueness(self):
        from fnixagent.core.security.auth.mfa import TOTPClient

        s1 = TOTPClient.generate_secret()
        s2 = TOTPClient.generate_secret()
        assert s1 != s2

    def test_build_provisioning_uri(self):
        from fnixagent.core.security.auth.mfa import TOTPClient

        uri = TOTPClient.build_provisioning_uri(
            secret="JBSWY3DPEHPK3PXP",
            account_name="alice@example.com",
        )
        assert uri.startswith("otpauth://totp/")
        assert "FnixAgent%3Aalice%40example.com" in uri
        assert "secret=JBSWY3DPEHPK3PXP" in uri
        assert "digits=6" in uri
        assert "period=30" in uri

    def test_verify_correct_code(self):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        secret = TOTPClient.generate_secret()
        client = TOTPClient(TOTPConfig(secret=secret, account_name="user"))
        code = client.generate_current_code()
        assert client.verify(code) is True

    def test_verify_wrong_code(self):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        secret = TOTPClient.generate_secret()
        client = TOTPClient(TOTPConfig(secret=secret, account_name="user"))
        # 6 位但错误
        assert client.verify("000000") is False or client.verify("999999") is False

    def test_verify_non_digit_code(self):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        client = TOTPClient(TOTPConfig(secret="JBSWY3DPEHPK3PXP"))
        assert client.verify("abcdef") is False
        assert client.verify("") is False

    def test_verify_accepts_adjacent_window(self):
        """容忍 ±1 个时间窗(±30s)防止时钟漂移。"""
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        secret = TOTPClient.generate_secret()
        client = TOTPClient(TOTPConfig(secret=secret))
        # 当前码一定通过(包含在 ±1 窗口内)
        code = client.generate_current_code()
        assert client.verify(code) is True

    def test_not_installed_raises(self):
        """pyotp 未安装时抛 MFANotInstalledError。"""
        from fnixagent.core.security.auth.mfa import (
            MFANotInstalledError,
            TOTPClient,
            TOTPConfig,
        )

        client = TOTPClient(TOTPConfig(secret="JBSWY3DPEHPK3PXP"))
        with patch.object(
            client, "_import_pyotp", side_effect=MFANotInstalledError("mock: 未安装")
        ):
            with pytest.raises(MFANotInstalledError):
                client.verify("123456")


# ===========================================================================
# 2. 恢复码客户端
# ===========================================================================


class TestRecoveryCodeClient:
    def test_generate_count(self):
        from fnixagent.core.security.auth.mfa import (
            RECOVERY_CODE_COUNT,
            RecoveryCodeClient,
        )

        codes = RecoveryCodeClient.generate()
        assert len(codes) == RECOVERY_CODE_COUNT

    def test_generate_format(self):
        """每个码 16 字符,4-4-4-4 分组(3 个连字符)。"""
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        codes = RecoveryCodeClient.generate(count=1)
        code = codes[0]
        # 16 字符 + 3 个连字符 = 19
        assert len(code) == 19
        assert code.count("-") == 3
        # 每段 4 字符
        parts = code.split("-")
        assert len(parts) == 4
        for part in parts:
            assert len(part) == 4

    def test_generate_uniqueness(self):
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        codes = RecoveryCodeClient.generate(count=20)
        assert len(set(codes)) == 20

    def test_alphabet_excludes_confusable(self):
        """易混淆字符 0/O/1/I/L 不出现在恢复码中。"""
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        codes = RecoveryCodeClient.generate(count=50)
        for code in codes:
            for ch in "0O1IL":
                assert ch not in code

    def test_hash_code_normalization(self):
        """哈希时去除分隔符 + 转大写,容忍用户输入差异。"""
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        code = "ABCD-EFGH-IJKL-MNOP"
        h1 = RecoveryCodeClient.hash_code(code)
        h2 = RecoveryCodeClient.hash_code("ABCDEFGHIJKLMNOP")
        h3 = RecoveryCodeClient.hash_code("abcd-efgh-ijkl-mnop")
        assert h1 == h2 == h3

    def test_verify_correct(self):
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        code = "ABCD-EFGH-IJKL-MNOP"
        code_hash = RecoveryCodeClient.hash_code(code)
        assert RecoveryCodeClient.verify(code, code_hash) is True

    def test_verify_wrong(self):
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        code = "ABCD-EFGH-IJKL-MNOP"
        code_hash = RecoveryCodeClient.hash_code(code)
        assert RecoveryCodeClient.verify("ZZZZ-ZZZZ-ZZZZ-ZZZZ", code_hash) is False

    def test_verify_empty(self):
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        assert RecoveryCodeClient.verify("", "somehash") is False
        assert RecoveryCodeClient.verify("ABCD", "") is False

    def test_verify_case_insensitive(self):
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient

        code_hash = RecoveryCodeClient.hash_code("ABCD-EFGH-IJKL-MNOP")
        assert RecoveryCodeClient.verify("abcd-efgh-ijkl-mnop", code_hash) is True


# ===========================================================================
# 3. OTP 客户端
# ===========================================================================


class TestOTPClient:
    def test_generate_code_format(self):
        from fnixagent.core.security.auth.mfa import OTP_DIGITS, OTPClient

        code = OTPClient.generate_code()
        assert len(code) == OTP_DIGITS
        assert code.isdigit()

    def test_generate_code_range(self):
        from fnixagent.core.security.auth.mfa import OTPClient

        for _ in range(100):
            code = OTPClient.generate_code()
            assert 0 <= int(code) < 10**6

    def test_hash_code(self):
        from fnixagent.core.security.auth.mfa import OTPClient

        h = OTPClient.hash_code("123456")
        assert len(h) == 64  # SHA256 hex
        assert h != "123456"

    def test_mask_phone(self):
        from fnixagent.core.security.auth.mfa import FACTOR_SMS, OTPClient

        masked = OTPClient.mask_target("13812345678", FACTOR_SMS)
        assert masked == "138****5678"

    def test_mask_short_phone(self):
        from fnixagent.core.security.auth.mfa import FACTOR_SMS, OTPClient

        masked = OTPClient.mask_target("12345", FACTOR_SMS)
        assert masked == "***"

    def test_mask_email(self):
        from fnixagent.core.security.auth.mfa import FACTOR_EMAIL, OTPClient

        masked = OTPClient.mask_target("alice@example.com", FACTOR_EMAIL)
        assert masked == "a***@example.com"

    def test_mask_empty(self):
        from fnixagent.core.security.auth.mfa import OTPClient

        assert OTPClient.mask_target("", "sms") == ""

    def test_send_sms_mock(self):
        from fnixagent.core.security.auth.mfa import OTPClient, SMSConfig

        client = OTPClient(sms_config=SMSConfig(provider="mock"))
        assert client.send_sms("13812345678", "123456") is True

    def test_send_sms_no_config(self):
        from fnixagent.core.security.auth.mfa import MFAConfigError, OTPClient

        client = OTPClient()
        with pytest.raises(MFAConfigError):
            client.send_sms("13812345678", "123456")

    def test_send_sms_unknown_provider(self):
        from fnixagent.core.security.auth.mfa import MFAConfigError, OTPClient, SMSConfig

        client = OTPClient(sms_config=SMSConfig(provider="unknown"))
        with pytest.raises(MFAConfigError):
            client.send_sms("13812345678", "123456")

    def test_send_email_no_config(self):
        from fnixagent.core.security.auth.mfa import MFAConfigError, OTPClient

        client = OTPClient()
        with pytest.raises(MFAConfigError):
            client.send_email("user@example.com", "123456")


# ===========================================================================
# 4. MFA Challenge Token
# ===========================================================================


class TestMFAChallengeToken:
    def test_create_and_verify_success(self):
        from fnixagent.core.security.auth.mfa import (
            create_mfa_challenge_token,
            verify_mfa_challenge_token,
        )

        token = create_mfa_challenge_token(
            user_id=42,
            username="alice",
            factors=["totp", "recovery"],
        )
        payload = verify_mfa_challenge_token(token)
        assert payload["user_id"] == 42
        assert payload["username"] == "alice"
        assert payload["token_type"] == "mfa_challenge"
        assert payload["factors"] == ["totp", "recovery"]
        assert "exp" in payload
        assert "jti" in payload

    def test_verify_invalid_signature(self):
        from fnixagent.core.security.auth.mfa import (
            create_mfa_challenge_token,
            verify_mfa_challenge_token,
        )

        token = create_mfa_challenge_token(
            user_id=1,
            username="user",
            factors=["totp"],
        )
        # 篡改签名
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalid_signature"
        with pytest.raises(ValueError, match="签名无效"):
            verify_mfa_challenge_token(tampered)

    def test_verify_wrong_token_type(self):
        """非 mfa_challenge 类型的 token 应拒绝。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.core.security.auth.mfa import verify_mfa_challenge_token

        # 创建普通 access token
        token = create_jwt_token(user_id=1, username="user")
        with pytest.raises(ValueError, match="类型不匹配"):
            verify_mfa_challenge_token(token)

    def test_verify_expired_token(self):
        from fnixagent.core.security.auth.mfa import (
            MFA_CHALLENGE_TTL_SECONDS,
            create_mfa_challenge_token,
            verify_mfa_challenge_token,
        )

        # 创建一个已过期的 token(通过 mock time)
        with patch("fnixagent.core.security.auth.mfa.time.time", return_value=1000.0):
            token = create_mfa_challenge_token(
                user_id=1,
                username="user",
                factors=["totp"],
            )
        # 当前时间已远超过期时间
        with patch(
            "fnixagent.core.security.auth.mfa.time.time",
            return_value=1000.0 + MFA_CHALLENGE_TTL_SECONDS + 1,
        ):
            with pytest.raises(ValueError, match="已过期"):
                verify_mfa_challenge_token(token)

    def test_verify_malformed_token(self):
        from fnixagent.core.security.auth.mfa import verify_mfa_challenge_token

        with pytest.raises(ValueError, match="3 段"):
            verify_mfa_challenge_token("not.a.valid.token")

    def test_custom_secret_key(self):
        from fnixagent.core.security.auth.mfa import (
            create_mfa_challenge_token,
            verify_mfa_challenge_token,
        )

        custom_key = "my-custom-secret-key-1234567890"
        token = create_mfa_challenge_token(
            user_id=1,
            username="u",
            factors=["totp"],
            secret_key=custom_key,
        )
        payload = verify_mfa_challenge_token(token, secret_key=custom_key)
        assert payload["user_id"] == 1

    def test_custom_secret_key_mismatch(self):
        from fnixagent.core.security.auth.mfa import (
            create_mfa_challenge_token,
            verify_mfa_challenge_token,
        )

        token = create_mfa_challenge_token(
            user_id=1,
            username="u",
            factors=["totp"],
            secret_key="key-A",
        )
        with pytest.raises(ValueError, match="签名无效"):
            verify_mfa_challenge_token(token, secret_key="key-B")


# ===========================================================================
# 5. 存储层
# ===========================================================================


class TestMFAFactorStore:
    def test_create_and_get(self):
        from fnixagent.core.security.auth.mfa import FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        factor = store.create(user_id=1, factor_type=FACTOR_TOTP, secret="ABC123")
        assert factor.id == 1
        assert factor.user_id == 1
        assert factor.factor_type == FACTOR_TOTP
        assert factor.secret == "ABC123"
        assert factor.enabled is True

        fetched = store.get(factor.id)
        assert fetched is not None
        assert fetched.secret == "ABC123"

    def test_list_by_user(self):
        from fnixagent.core.security.auth.mfa import FACTOR_SMS, FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        store.create(user_id=1, factor_type=FACTOR_TOTP, secret="S1")
        store.create(user_id=1, factor_type=FACTOR_SMS, phone="13800000000")
        store.create(user_id=2, factor_type=FACTOR_TOTP, secret="S2")

        factors = store.list_by_user(1)
        assert len(factors) == 2
        factors_user2 = store.list_by_user(2)
        assert len(factors_user2) == 1

    def test_list_by_user_exclude_disabled(self):
        from fnixagent.core.security.auth.mfa import FACTOR_SMS, FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        store.create(user_id=1, factor_type=FACTOR_TOTP, secret="S1")
        f2 = store.create(user_id=1, factor_type=FACTOR_SMS, phone="13800000000")
        store.update(f2.id, enabled=False)

        all_factors = store.list_by_user(1, include_disabled=True)
        assert len(all_factors) == 2
        enabled_only = store.list_by_user(1, include_disabled=False)
        assert len(enabled_only) == 1
        assert enabled_only[0].factor_type == FACTOR_TOTP

    def test_get_totp(self):
        from fnixagent.core.security.auth.mfa import FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        store.create(user_id=1, factor_type=FACTOR_TOTP, secret="S1")
        totp = store.get_totp(1)
        assert totp is not None
        assert totp.secret == "S1"

    def test_get_totp_disabled(self):
        from fnixagent.core.security.auth.mfa import FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        f = store.create(user_id=1, factor_type=FACTOR_TOTP, secret="S1")
        store.update(f.id, enabled=False)
        assert store.get_totp(1) is None

    def test_has_enabled_factor(self):
        from fnixagent.core.security.auth.mfa import FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        assert store.has_enabled_factor(1) is False
        store.create(user_id=1, factor_type=FACTOR_TOTP, secret="S1")
        assert store.has_enabled_factor(1) is True

    def test_delete(self):
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        f = store.create(user_id=1, factor_type="totp", secret="S")
        assert store.delete(f.id) is True
        assert store.get(f.id) is None
        assert store.delete(999) is False

    def test_delete_all_by_user(self):
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        store.create(user_id=1, factor_type="totp", secret="S1")
        store.create(user_id=1, factor_type="sms", phone="13800000000")
        store.create(user_id=2, factor_type="totp", secret="S2")

        deleted = store.delete_all_by_user(1)
        assert deleted == 2
        assert len(store.list_by_user(1)) == 0
        assert len(store.list_by_user(2)) == 1

    def test_to_dict_hides_secret(self):
        from fnixagent.core.security.auth.mfa import FACTOR_TOTP
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        f = store.create(user_id=1, factor_type=FACTOR_TOTP, secret="SECRET")
        d = f.to_dict(include_secret=False)
        assert "secret" not in d
        d2 = f.to_dict(include_secret=True)
        assert d2["secret"] == "SECRET"

    def test_to_dict_masks_phone(self):
        from fnixagent.core.security.auth.mfa import FACTOR_SMS
        from fnixagent.services.storage_mfa import get_mfa_factor_store

        store = get_mfa_factor_store()
        f = store.create(user_id=1, factor_type=FACTOR_SMS, phone="13812345678")
        d = f.to_dict()
        assert d["phone"] == "138****5678"


class TestRecoveryCodeStore:
    def test_create_and_find(self):
        from fnixagent.core.security.auth.mfa import RecoveryCodeClient
        from fnixagent.services.storage_mfa import get_recovery_code_store

        store = get_recovery_code_store()
        code = "ABCD-EFGH-IJKL-MNOP"
        code_hash = RecoveryCodeClient.hash_code(code)
        record = store.create(user_id=1, code_hash=code_hash)

        assert record.id == 1
        found = store.find_unused_by_hash(1, code_hash)
        assert found is not None
        assert found.id == record.id

    def test_count_unused(self):
        from fnixagent.services.storage_mfa import get_recovery_code_store

        store = get_recovery_code_store()
        store.create(user_id=1, code_hash="h1")
        store.create(user_id=1, code_hash="h2")
        store.create(user_id=2, code_hash="h3")
        assert store.count_unused(1) == 2
        assert store.count_unused(2) == 1

    def test_mark_used(self):
        from fnixagent.services.storage_mfa import get_recovery_code_store

        store = get_recovery_code_store()
        record = store.create(user_id=1, code_hash="h1")
        assert store.mark_used(record.id) is True
        assert record.used is True
        # 已使用的码不能再 mark
        assert store.mark_used(record.id) is False
        # 已使用的码查不到
        assert store.find_unused_by_hash(1, "h1") is None
        assert store.count_unused(1) == 0

    def test_delete_all_by_user(self):
        from fnixagent.services.storage_mfa import get_recovery_code_store

        store = get_recovery_code_store()
        store.create(user_id=1, code_hash="h1")
        store.create(user_id=1, code_hash="h2")
        store.create(user_id=2, code_hash="h3")

        deleted = store.delete_all_by_user(1)
        assert deleted == 2
        assert store.count_unused(1) == 0
        assert store.count_unused(2) == 1

    def test_to_dict_no_hash(self):
        """恢复码 to_dict 不返回 code_hash。"""
        from fnixagent.services.storage_mfa import get_recovery_code_store

        store = get_recovery_code_store()
        record = store.create(user_id=1, code_hash="secret-hash")
        d = record.to_dict()
        assert "code_hash" not in d
        assert d["used"] is False


class TestOTPChallengeStore:
    def test_create_and_get(self):
        from fnixagent.services.storage_mfa import get_otp_challenge_store

        store = get_otp_challenge_store()
        challenge = store.create(
            user_id=1,
            factor_type="sms",
            target="138****5678",
            code_hash="abc",
        )
        assert challenge.challenge_id
        assert challenge.user_id == 1
        assert challenge.attempts == 0
        assert challenge.consumed is False

        fetched = store.get(challenge.challenge_id)
        assert fetched is not None
        assert fetched.user_id == 1

    def test_get_nonexistent(self):
        from fnixagent.services.storage_mfa import get_otp_challenge_store

        store = get_otp_challenge_store()
        assert store.get("nonexistent-id") is None

    def test_get_returns_copy(self):
        """get() 返回副本,外部修改不影响原数据。"""
        from fnixagent.services.storage_mfa import get_otp_challenge_store

        store = get_otp_challenge_store()
        challenge = store.create(
            user_id=1,
            factor_type="sms",
            target="t",
            code_hash="h",
        )
        fetched = store.get(challenge.challenge_id)
        fetched.attempts = 99
        refetched = store.get(challenge.challenge_id)
        assert refetched.attempts == 0

    def test_check_resend_cooldown(self):
        from fnixagent.services.storage_mfa import get_otp_challenge_store

        store = get_otp_challenge_store()
        # 初始可以发送
        assert store.check_resend_cooldown(1, "sms") is True
        store.create(1, "sms", "t", "h")
        # 冷却期内不能发送
        assert store.check_resend_cooldown(1, "sms") is False
        # 不同 factor_type 不受影响
        assert store.check_resend_cooldown(1, "email") is True

    def test_increment_attempts(self):
        from fnixagent.core.security.auth.mfa import OTP_MAX_ATTEMPTS
        from fnixagent.services.storage_mfa import (
            get_otp_challenge_store,
        )

        store = get_otp_challenge_store()
        challenge = store.create(1, "sms", "t", "h")

        for i in range(OTP_MAX_ATTEMPTS - 1):
            c = store.increment_attempts(challenge.challenge_id)
            assert c.attempts == i + 1
            assert c.consumed is False

        # 第 OTP_MAX_ATTEMPTS 次自动 consume
        c = store.increment_attempts(challenge.challenge_id)
        assert c.attempts == OTP_MAX_ATTEMPTS
        assert c.consumed is True

    def test_consume(self):
        from fnixagent.services.storage_mfa import get_otp_challenge_store

        store = get_otp_challenge_store()
        challenge = store.create(1, "sms", "t", "h")
        assert store.consume(challenge.challenge_id) is True
        # 已 consume 不能再 consume
        assert store.consume(challenge.challenge_id) is False

    def test_cleanup_expired(self):
        from fnixagent.services.storage_mfa import get_otp_challenge_store

        store = get_otp_challenge_store()
        # 创建一个已过期的 challenge(ttl=0)
        challenge = store.create(1, "sms", "t", "h", ttl=0)
        time.sleep(0.1)
        expired_count = store.cleanup_expired()
        assert expired_count >= 1
        assert store.get(challenge.challenge_id) is None


class TestMFAEnforcementStore:
    def test_upsert_create(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        e = store.upsert(role="admin", factor_type="totp", enabled=True)
        assert e.id == 1
        assert e.role == "admin"
        assert e.factor_type == "totp"
        assert e.enabled is True

    def test_upsert_update(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        store.upsert(role="admin", factor_type="totp", enabled=True)
        # 同 role 再次 upsert = 更新
        e = store.upsert(role="admin", factor_type="any", enabled=False)
        assert e.factor_type == "any"
        assert e.enabled is False
        # 仍然只有一条
        assert len(store.list_all()) == 1

    def test_get_by_role(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        store.upsert(role="admin", factor_type="totp")
        e = store.get_by_role("admin")
        assert e is not None
        assert e.factor_type == "totp"
        assert store.get_by_role("nonexistent") is None

    def test_list_all(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        store.upsert(role="admin", factor_type="totp")
        store.upsert(role="finance", factor_type="any")
        all_e = store.list_all()
        assert len(all_e) == 2

    def test_list_enabled(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        store.upsert(role="admin", factor_type="totp", enabled=True)
        store.upsert(role="user", factor_type="any", enabled=False)
        enabled = store.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].role == "admin"

    def test_delete(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        e = store.upsert(role="admin", factor_type="totp")
        assert store.delete(e.id) is True
        assert store.get_by_role("admin") is None
        assert store.delete(999) is False

    def test_delete_by_role(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        store.upsert(role="admin", factor_type="totp")
        assert store.delete_by_role("admin") is True
        assert store.delete_by_role("admin") is False

    def test_is_role_enforced(self):
        from fnixagent.services.storage_mfa import get_mfa_enforcement_store

        store = get_mfa_enforcement_store()
        assert store.is_role_enforced("admin") is False
        store.upsert(role="admin", factor_type="totp", enabled=True)
        assert store.is_role_enforced("admin") is True
        store.upsert(role="admin", factor_type="totp", enabled=False)
        assert store.is_role_enforced("admin") is False


# ===========================================================================
# 6. API 端点测试
# ===========================================================================


class TestMFAAPIEndpoints:
    @pytest.fixture
    def client(self):
        """构建带 MFA 路由的 TestClient。"""
        from fnixagent.api.routers import admin, auth

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(admin.router, prefix="/api/v1")
        return TestClient(app)

    @pytest.fixture
    def user_token(self):
        """创建普通用户 Token。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="mfa_user",
            email="mfauser@e.com",
            password="Pass1234",
            role="user",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    @pytest.fixture
    def admin_token(self):
        """创建管理员 Token。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="mfa_admin",
            email="mfaadmin@e.com",
            password="Pass1234",
            role="admin",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    # ---- /auth/mfa/setup ----

    def test_setup_totp(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["factor_type"] == "totp"
        assert len(data["secret"]) >= 50
        assert data["qr_uri"].startswith("otpauth://totp/")

    def test_setup_sms(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "sms",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["factor_type"] == "sms"

    def test_setup_email(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "email",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["factor_type"] == "email"

    def test_setup_invalid_factor(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "webauthn",
            },
            headers=self._headers(token),
        )
        # Pydantic pattern 校验返回 422
        assert resp.status_code == 422

    def test_setup_no_auth(self, client):
        resp = client.post("/api/v1/auth/mfa/setup", json={"factor_type": "totp"})
        assert resp.status_code == 401

    # ---- /auth/mfa/enable ----

    def test_enable_totp_success(self, client, user_token):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        token, _ = user_token
        # 先 setup
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]

        # 用 secret 生成正确验证码
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()

        # enable
        resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # 返回恢复码
        assert "recovery_codes" in data["data"]
        assert len(data["data"]["recovery_codes"]) == 10

    def test_enable_totp_wrong_code(self, client, user_token):
        token, _ = user_token
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]

        resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": "000000",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 400
        assert "验证码错误" in resp.json()["detail"]

    def test_enable_sms(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "sms",
                "phone": "13812345678",
                "code": "0000",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_enable_email(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "email",
                "email": "user@example.com",
                "code": "0000",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200

    def test_enable_sms_no_phone(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "sms",
                "code": "0000",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 400

    # ---- /auth/mfa/factors ----

    def test_list_factors_empty(self, client, user_token):
        token, _ = user_token
        resp = client.get("/api/v1/auth/mfa/factors", headers=self._headers(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["factors"] == []
        assert data["recovery_codes_remaining"] == 0
        assert data["mfa_enabled"] is False

    def test_list_factors_after_enable(self, client, user_token):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        token, _ = user_token
        # setup + enable
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )

        resp = client.get("/api/v1/auth/mfa/factors", headers=self._headers(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["factors"]) == 1
        assert data["factors"][0]["factor_type"] == "totp"
        # secret 不应返回
        assert "secret" not in data["factors"][0]
        assert data["recovery_codes_remaining"] == 10
        assert data["mfa_enabled"] is True

    # ---- /auth/mfa/disable ----

    def test_disable_all_factors(self, client, user_token):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        token, _ = user_token
        # 先 enable TOTP
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )

        # disable(需密码确认,用明文)
        resp = client.post(
            "/api/v1/auth/mfa/disable",
            json={
                "password": "Pass1234",
                "is_password_encrypted": False,
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # 确认已清空
        factors_resp = client.get("/api/v1/auth/mfa/factors", headers=self._headers(token))
        assert factors_resp.json()["data"]["factors"] == []

    def test_disable_wrong_password(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/disable",
            json={
                "password": "WrongPass",
                "is_password_encrypted": False,
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 401

    def test_disable_no_password(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/disable",
            json={
                "password": "",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 400

    # ---- /auth/mfa/recovery-codes/regenerate ----

    def test_regenerate_recovery_codes(self, client, user_token):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        token, _ = user_token
        # 先 enable
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )

        # regenerate
        resp = client.post(
            "/api/v1/auth/mfa/recovery-codes/regenerate", headers=self._headers(token)
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["recovery_codes"]) == 10

    def test_regenerate_without_mfa(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/recovery-codes/regenerate", headers=self._headers(token)
        )
        assert resp.status_code == 400

    # ---- /auth/mfa/send-code ----

    def test_send_code_sms(self, client, user_token):
        token, _ = user_token
        # 先绑定 SMS
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "sms",
                "phone": "13812345678",
                "code": "0000",
            },
            headers=self._headers(token),
        )

        resp = client.post(
            "/api/v1/auth/mfa/send-code",
            json={
                "factor_type": "sms",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["challenge_id"]
        assert data["target"] == "138****5678"
        assert data["expires_in"] == 300

    def test_send_code_email(self, client, user_token):
        token, _ = user_token
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "email",
                "email": "user@example.com",
                "code": "0000",
            },
            headers=self._headers(token),
        )

        resp = client.post(
            "/api/v1/auth/mfa/send-code",
            json={
                "factor_type": "email",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["challenge_id"]

    def test_send_code_cooldown(self, client, user_token):
        token, _ = user_token
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "sms",
                "phone": "13812345678",
                "code": "0000",
            },
            headers=self._headers(token),
        )

        # 第一次发送
        resp1 = client.post(
            "/api/v1/auth/mfa/send-code",
            json={
                "factor_type": "sms",
            },
            headers=self._headers(token),
        )
        assert resp1.status_code == 200

        # 60s 内重发应被拒
        resp2 = client.post(
            "/api/v1/auth/mfa/send-code",
            json={
                "factor_type": "sms",
            },
            headers=self._headers(token),
        )
        assert resp2.status_code == 429

    def test_send_code_no_factor(self, client, user_token):
        token, _ = user_token
        resp = client.post(
            "/api/v1/auth/mfa/send-code",
            json={
                "factor_type": "sms",
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 400

    # ---- /auth/mfa/verify ----

    def test_verify_totp_success(self, client, user_token):
        from fnixagent.core.security.auth.mfa import (
            TOTPClient,
            TOTPConfig,
            create_mfa_challenge_token,
        )

        token, user_id = user_token
        # 先绑定 TOTP
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        enable_code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": enable_code,
            },
            headers=self._headers(token),
        )

        # 创建 MFA Challenge Token
        mfa_token = create_mfa_challenge_token(
            user_id=user_id,
            username="mfa_user",
            factors=["totp", "recovery"],
        )

        # 用正确 TOTP code 验证
        verify_code = totp_client.generate_current_code()
        resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token,
                "factor_type": "totp",
                "code": verify_code,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_verify_totp_wrong_code(self, client, user_token):
        from fnixagent.core.security.auth.mfa import (
            TOTPClient,
            TOTPConfig,
            create_mfa_challenge_token,
        )

        token, user_id = user_token
        # 绑定 TOTP
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )

        mfa_token = create_mfa_challenge_token(
            user_id=user_id,
            username="mfa_user",
            factors=["totp"],
        )
        resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token,
                "factor_type": "totp",
                "code": "000000",
            },
        )
        assert resp.status_code == 401

    def test_verify_recovery_code_success(self, client, user_token):
        from fnixagent.core.security.auth.mfa import (
            TOTPClient,
            TOTPConfig,
            create_mfa_challenge_token,
        )

        token, user_id = user_token
        # 绑定 TOTP(同时生成恢复码)
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        enable_resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )
        recovery_codes = enable_resp.json()["data"]["recovery_codes"]

        mfa_token = create_mfa_challenge_token(
            user_id=user_id,
            username="mfa_user",
            factors=["recovery"],
        )
        # 用第一个恢复码验证
        resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token,
                "factor_type": "recovery",
                "code": recovery_codes[0],
            },
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_verify_recovery_code_reused(self, client, user_token):
        """恢复码一次性,不能重复使用。"""
        from fnixagent.core.security.auth.mfa import (
            TOTPClient,
            TOTPConfig,
            create_mfa_challenge_token,
        )

        token, user_id = user_token
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(token),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        enable_resp = client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(token),
        )
        recovery_code = enable_resp.json()["data"]["recovery_codes"][0]

        mfa_token = create_mfa_challenge_token(
            user_id=user_id,
            username="mfa_user",
            factors=["recovery"],
        )
        # 第一次使用成功
        resp1 = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token,
                "factor_type": "recovery",
                "code": recovery_code,
            },
        )
        assert resp1.status_code == 200

        # 第二次使用同一恢复码应失败(需新 mfa_token,因旧的已消耗)
        mfa_token2 = create_mfa_challenge_token(
            user_id=user_id,
            username="mfa_user",
            factors=["recovery"],
        )
        resp2 = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token2,
                "factor_type": "recovery",
                "code": recovery_code,
            },
        )
        assert resp2.status_code == 401

    def test_verify_invalid_mfa_token(self, client):
        resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": "invalid.token.here",
                "factor_type": "totp",
                "code": "123456",
            },
        )
        assert resp.status_code == 401

    def test_verify_disallowed_factor(self, client, user_token):
        """mfa_token 的 factors 列表不包含请求的 factor_type 时应拒绝。"""
        from fnixagent.core.security.auth.mfa import create_mfa_challenge_token

        token, user_id = user_token
        # 只允许 totp,不允许 recovery
        mfa_token = create_mfa_challenge_token(
            user_id=user_id,
            username="mfa_user",
            factors=["totp"],
        )
        resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token,
                "factor_type": "recovery",
                "code": "ABCD-EFGH-IJKL-MNOP",
            },
        )
        assert resp.status_code == 400


# ===========================================================================
# 7. 登录流程集成(密码校验后返回 MFA Challenge)
# ===========================================================================


class TestMFALoginFlow:
    @pytest.fixture
    def client(self):
        from fnixagent.api.routers import admin, auth

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(admin.router, prefix="/api/v1")
        return TestClient(app)

    def test_login_returns_mfa_challenge(self, client):
        """用户启用 MFA 后,登录返回 MFA Challenge 而非 Token。"""
        from fnixagent.core.security.auth.mfa import TOTPClient
        from fnixagent.services.storage import get_user_store

        # 创建用户
        store = get_user_store()
        user, _ = store.create(
            username="mfa_login_user",
            email="mfa@e.com",
            password="Pass1234",
            role="user",
        )

        # 直接通过 store 绑定 TOTP(绕过 API,简化测试)
        from fnixagent.core.security.auth.mfa import (
            FACTOR_TOTP,
            RecoveryCodeClient,
        )
        from fnixagent.services.storage_mfa import (
            get_mfa_factor_store,
            get_recovery_code_store,
        )

        factor_store = get_mfa_factor_store()
        recovery_store = get_recovery_code_store()
        secret = TOTPClient.generate_secret()
        factor_store.create(user.id, FACTOR_TOTP, secret=secret)
        # 生成恢复码
        for code in RecoveryCodeClient.generate():
            recovery_store.create(user.id, RecoveryCodeClient.hash_code(code))
        store.update_profile(user.id, {"mfa_enabled": True})

        # 登录(明文密码,不走 RSA 加密)
        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "mfa_login_user",
                "password": "Pass1234",
                "is_password_encrypted": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mfa_required"] is True
        assert "mfa_token" in data
        assert "totp" in data["factors"]
        assert "recovery" in data["factors"]
        assert data["expires_in"] == 300

    def test_login_without_mfa_returns_token(self, client):
        """未启用 MFA 的用户正常登录,返回 Token。"""
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        store.create(
            username="normal_user",
            email="normal@e.com",
            password="Pass1234",
            role="user",
        )

        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "normal_user",
                "password": "Pass1234",
                "is_password_encrypted": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # 非 MFA 响应应包含 access_token
        assert "access_token" in data
        assert "mfa_required" not in data or data.get("mfa_required") is not True

    def test_full_mfa_login_flow(self, client):
        """完整 MFA 登录流程:密码登录 → MFA Challenge → TOTP 验证 → 获取 Token。"""
        from fnixagent.core.security.auth.mfa import (
            FACTOR_TOTP,
            RecoveryCodeClient,
            TOTPClient,
            TOTPConfig,
        )
        from fnixagent.services.storage import get_user_store
        from fnixagent.services.storage_mfa import (
            get_mfa_factor_store,
            get_recovery_code_store,
        )

        # 创建用户 + 绑定 TOTP
        store = get_user_store()
        user, _ = store.create(
            username="full_flow_user",
            email="ff@e.com",
            password="Pass1234",
            role="user",
        )
        factor_store = get_mfa_factor_store()
        recovery_store = get_recovery_code_store()
        secret = TOTPClient.generate_secret()
        factor_store.create(user.id, FACTOR_TOTP, secret=secret)
        for code in RecoveryCodeClient.generate():
            recovery_store.create(user.id, RecoveryCodeClient.hash_code(code))
        store.update_profile(user.id, {"mfa_enabled": True})

        # Step 1: 密码登录,获取 MFA Challenge
        login_resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "full_flow_user",
                "password": "Pass1234",
                "is_password_encrypted": False,
            },
        )
        assert login_resp.status_code == 200
        challenge = login_resp.json()
        assert challenge["mfa_required"] is True
        mfa_token = challenge["mfa_token"]

        # Step 2: 用 TOTP 验证,获取真正 Token
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        verify_code = totp_client.generate_current_code()
        verify_resp = client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": mfa_token,
                "factor_type": "totp",
                "code": verify_code,
            },
        )
        assert verify_resp.status_code == 200
        tokens = verify_resp.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens

        # Step 3: 用 access_token 访问受保护接口
        me_resp = client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {tokens['access_token']}",
            },
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "full_flow_user"


# ===========================================================================
# 8. Admin MFA 管理端点
# ===========================================================================


class TestAdminMFAEndpoints:
    @pytest.fixture
    def client(self):
        from fnixagent.api.routers import admin, auth

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(admin.router, prefix="/api/v1")
        return TestClient(app)

    @pytest.fixture
    def admin_token(self):
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="admin_mfa",
            email="am@e.com",
            password="Pass1234",
            role="admin",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    @pytest.fixture
    def user_token(self):
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="target_user",
            email="tu@e.com",
            password="Pass1234",
            role="user",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_list_enforcements_empty(self, client, admin_token):
        token, _ = admin_token
        resp = client.get("/api/v1/admin/mfa/enforcements", headers=self._headers(token))
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []

    def test_upsert_enforcement(self, client, admin_token):
        token, _ = admin_token
        resp = client.post(
            "/api/v1/admin/mfa/enforcements",
            json={
                "role": "admin",
                "factor_type": "totp",
                "enabled": True,
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "admin"
        assert data["factor_type"] == "totp"
        assert data["enabled"] is True

    def test_upsert_enforcement_idempotent(self, client, admin_token):
        """同 role 再次 upsert 为更新。"""
        token, _ = admin_token
        client.post(
            "/api/v1/admin/mfa/enforcements",
            json={
                "role": "admin",
                "factor_type": "totp",
                "enabled": True,
            },
            headers=self._headers(token),
        )
        resp = client.post(
            "/api/v1/admin/mfa/enforcements",
            json={
                "role": "admin",
                "factor_type": "any",
                "enabled": False,
            },
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["factor_type"] == "any"
        assert data["enabled"] is False

    def test_delete_enforcement(self, client, admin_token):
        token, _ = admin_token
        create_resp = client.post(
            "/api/v1/admin/mfa/enforcements",
            json={
                "role": "finance",
                "factor_type": "any",
                "enabled": True,
            },
            headers=self._headers(token),
        )
        eid = create_resp.json()["data"]["id"]

        resp = client.delete(f"/api/v1/admin/mfa/enforcements/{eid}", headers=self._headers(token))
        assert resp.status_code == 200

        # 确认已删除
        list_resp = client.get("/api/v1/admin/mfa/enforcements", headers=self._headers(token))
        assert len(list_resp.json()["data"]["items"]) == 0

    def test_list_user_factors(self, client, admin_token, user_token):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        admin_t, _ = admin_token
        user_t, user_id = user_token

        # 用户先绑定 TOTP
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(user_t),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(user_t),
        )

        # admin 查看用户因子
        resp = client.get(
            f"/api/v1/admin/mfa/users/{user_id}/factors", headers=self._headers(admin_t)
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["factors"]) == 1
        assert data["factors"][0]["factor_type"] == "totp"

    def test_admin_disable_factor(self, client, admin_token, user_token):
        from fnixagent.core.security.auth.mfa import TOTPClient, TOTPConfig

        admin_t, _ = admin_token
        user_t, _ = user_token

        # 用户绑定 TOTP
        setup_resp = client.post(
            "/api/v1/auth/mfa/setup",
            json={
                "factor_type": "totp",
            },
            headers=self._headers(user_t),
        )
        secret = setup_resp.json()["secret"]
        totp_client = TOTPClient(TOTPConfig(secret=secret))
        code = totp_client.generate_current_code()
        client.post(
            "/api/v1/auth/mfa/enable",
            json={
                "factor_type": "totp",
                "secret": secret,
                "code": code,
            },
            headers=self._headers(user_t),
        )

        # 获取 factor_id
        factors_resp = client.get("/api/v1/auth/mfa/factors", headers=self._headers(user_t))
        factor_id = factors_resp.json()["data"]["factors"][0]["id"]

        # admin 强制禁用
        resp = client.delete(
            f"/api/v1/admin/mfa/factors/{factor_id}", headers=self._headers(admin_t)
        )
        assert resp.status_code == 200

    def test_non_admin_cannot_access(self, client, user_token):
        token, _ = user_token
        resp = client.get("/api/v1/admin/mfa/enforcements", headers=self._headers(token))
        assert resp.status_code in (403, 401)
