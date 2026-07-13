"""
token 模块单元测试(验收标准 ③ 双 Token 刷新流程测试 - 单元层)。

覆盖:
    - Access Token 创建(包含 token_type=access + jti + exp)
    - Refresh Token 创建(包含 token_type=refresh)
    - 双 Token 配对创建(TokenPair)
    - verify_token 校验签名/过期/类型
    - Access Token 不能用作 Refresh Token(类型不匹配拒绝)
    - Refresh Token 不能用作 Access Token
    - 篡改签名被拒绝
    - 过期 Token 被拒绝
    - decode_token_unsafe 不校验签名
    - Access Token 默认 TTL 2h,Refresh Token 默认 TTL 7d
"""
import time

import pytest

from fnixagent.core.security.auth.token import (
    ACCESS_TOKEN_TTL,
    JWT_ALGORITHM,
    REFRESH_TOKEN_TTL,
    TokenPair,
    _b64url_decode,
    _b64url_encode,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token_unsafe,
    verify_token,
)


# ---------------------------------------------------------------------------
# Token 创建
# ---------------------------------------------------------------------------

class TestTokenCreation:
    """Token 创建与字段。"""

    def test_create_access_token_returns_jwt_string(self):
        """create_access_token 返回 JWT 字符串(3 段)。"""
        token = create_access_token(user_id=1, username="alice", role="user")
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_create_refresh_token_returns_jwt_string(self):
        """create_refresh_token 返回 JWT 字符串。"""
        token = create_refresh_token(user_id=1, username="alice", role="user")
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_access_token_payload_contains_required_fields(self):
        """Access Token payload 必须包含必需字段。"""
        token = create_access_token(user_id=42, username="bob", role="admin")
        payload = verify_token(token, expected_type="access")
        assert payload["user_id"] == 42
        assert payload["username"] == "bob"
        assert payload["role"] == "admin"
        assert payload["token_type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_refresh_token_payload_contains_required_fields(self):
        """Refresh Token payload 必须包含必需字段。"""
        token = create_refresh_token(user_id=42, username="bob", role="admin")
        payload = verify_token(token, expected_type="refresh")
        assert payload["user_id"] == 42
        assert payload["token_type"] == "refresh"
        assert "jti" in payload

    def test_access_token_default_ttl_is_2_hours(self):
        """Access Token 默认 TTL = 2*3600 秒。"""
        assert ACCESS_TOKEN_TTL == 2 * 3600

    def test_refresh_token_default_ttl_is_7_days(self):
        """Refresh Token 默认 TTL = 7*24*3600 秒。"""
        assert REFRESH_TOKEN_TTL == 7 * 24 * 3600

    def test_access_token_exp_is_iat_plus_ttl(self):
        """Access Token 的 exp = iat + ACCESS_TOKEN_TTL。"""
        before = int(time.time())
        token = create_access_token(user_id=1, username="u", role="user")
        after = int(time.time())
        payload = verify_token(token)
        assert payload["exp"] == payload["iat"] + ACCESS_TOKEN_TTL
        # iat 落在 [before, after] 区间
        assert before <= payload["iat"] <= after

    def test_each_token_has_unique_jti(self):
        """每个 Token 的 jti 唯一。"""
        t1 = create_access_token(user_id=1, username="u", role="user")
        t2 = create_access_token(user_id=1, username="u", role="user")
        p1 = verify_token(t1)
        p2 = verify_token(t2)
        assert p1["jti"] != p2["jti"]


# ---------------------------------------------------------------------------
# TokenPair 双 Token
# ---------------------------------------------------------------------------

class TestTokenPair:
    """双 Token 配对创建。"""

    def test_create_token_pair_returns_token_pair_instance(self):
        """create_token_pair 返回 TokenPair 实例。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        assert isinstance(pair, TokenPair)

    def test_token_pair_contains_both_tokens(self):
        """TokenPair 包含 access_token 与 refresh_token。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        assert pair.access_token
        assert pair.refresh_token
        assert pair.access_token != pair.refresh_token

    def test_token_pair_token_types_correct(self):
        """TokenPair 中 Access Token 类型为 access,Refresh Token 类型为 refresh。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        access_payload = verify_token(pair.access_token, expected_type="access")
        refresh_payload = verify_token(pair.refresh_token, expected_type="refresh")
        assert access_payload["token_type"] == "access"
        assert refresh_payload["token_type"] == "refresh"

    def test_token_pair_expires_in_matches_ttl(self):
        """TokenPair 的 expires_in / refresh_expires_in 与 TTL 一致。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        assert pair.expires_in == ACCESS_TOKEN_TTL
        assert pair.refresh_expires_in == REFRESH_TOKEN_TTL
        assert pair.token_type == "bearer"

    def test_token_pair_jti_differ(self):
        """Access Token 与 Refresh Token 的 jti 不同。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        access_p = verify_token(pair.access_token)
        refresh_p = verify_token(pair.refresh_token)
        assert access_p["jti"] != refresh_p["jti"]

    def test_token_pair_carries_device_fp_when_provided(self):
        """传入 device_fp 时,Access Token 携带设备指纹。"""
        fp = "a" * 64
        pair = create_token_pair(user_id=1, username="u", role="user", device_fp=fp)
        access_p = verify_token(pair.access_token, expected_type="access")
        assert access_p["device_fp"] == fp

    def test_token_pair_no_device_fp_when_not_provided(self):
        """未传 device_fp 时,Access Token 不含该字段。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        access_p = verify_token(pair.access_token, expected_type="access")
        assert "device_fp" not in access_p

    def test_refresh_token_carries_device_fp_when_provided(self):
        """传入 device_fp 时,Refresh Token 也携带(用于 /auth/refresh 校验)。"""
        fp = "b" * 64
        pair = create_token_pair(user_id=1, username="u", role="user", device_fp=fp)
        refresh_p = verify_token(pair.refresh_token, expected_type="refresh")
        assert refresh_p["device_fp"] == fp

    def test_refresh_token_no_device_fp_when_not_provided(self):
        """未传 device_fp 时,Refresh Token 不含该字段。"""
        pair = create_token_pair(user_id=1, username="u", role="user")
        refresh_p = verify_token(pair.refresh_token, expected_type="refresh")
        assert "device_fp" not in refresh_p


# ---------------------------------------------------------------------------
# Token 校验
# ---------------------------------------------------------------------------

class TestTokenVerification:
    """verify_token 校验逻辑。"""

    def test_verify_token_success(self):
        """合法 Token 校验通过,返回 payload。"""
        token = create_access_token(user_id=1, username="u", role="user")
        payload = verify_token(token)
        assert payload["user_id"] == 1

    def test_verify_token_with_expected_type_access(self):
        """期望 access 类型,传入 access Token 校验通过。"""
        token = create_access_token(user_id=1, username="u", role="user")
        payload = verify_token(token, expected_type="access")
        assert payload["token_type"] == "access"

    def test_verify_token_rejects_access_as_refresh(self):
        """Access Token 不能用作 Refresh Token(类型不匹配)。"""
        token = create_access_token(user_id=1, username="u", role="user")
        with pytest.raises(ValueError, match="Token 类型不匹配"):
            verify_token(token, expected_type="refresh")

    def test_verify_token_rejects_refresh_as_access(self):
        """Refresh Token 不能用作 Access Token。"""
        token = create_refresh_token(user_id=1, username="u", role="user")
        with pytest.raises(ValueError, match="Token 类型不匹配"):
            verify_token(token, expected_type="access")

    def test_verify_token_rejects_tampered_signature(self):
        """篡改签名段被拒绝。"""
        token = create_access_token(user_id=1, username="u", role="user")
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".AAAA"
        with pytest.raises(ValueError, match="签名无效"):
            verify_token(tampered)

    def test_verify_token_rejects_tampered_payload(self):
        """篡改 payload 段被拒绝(签名失效)。"""
        token = create_access_token(user_id=1, username="u", role="user")
        parts = token.split(".")
        # 篡改 payload:把 user_id 从 1 改成 99
        import json
        payload = json.loads(_b64url_decode(parts[1]))
        payload["user_id"] = 99
        tampered_payload_b64 = _b64url_encode(
            json.dumps(payload, separators=(",", ":")).encode()
        )
        tampered = parts[0] + "." + tampered_payload_b64 + "." + parts[2]
        with pytest.raises(ValueError, match="签名无效"):
            verify_token(tampered)

    def test_verify_token_rejects_malformed_token(self):
        """格式错误的 Token 被拒绝。"""
        with pytest.raises(ValueError, match="3 段"):
            verify_token("only.two")
        with pytest.raises(ValueError, match="3 段"):
            verify_token("single")

    def test_verify_token_rejects_expired_token(self, monkeypatch):
        """过期 Token 被拒绝。"""
        # 创建一个已经过期的 Token:把 TTL 设为负数
        # 通过直接构造过期 payload
        import json
        import hmac
        import hashlib

        header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
        now = int(time.time())
        payload = {
            "user_id": 1,
            "username": "u",
            "role": "user",
            "token_type": "access",
            "jti": "expired_jti",
            "iat": now - 100,
            "exp": now - 10,  # 10 秒前过期
        }
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"
        sig = hmac.new(
            "fnixagent-dev-secret-change-me".encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
        sig_b64 = _b64url_encode(sig)
        expired_token = f"{signing_input}.{sig_b64}"

        with pytest.raises(ValueError, match="已过期"):
            verify_token(expired_token)

    def test_verify_token_rejects_wrong_algorithm(self):
        """非 HS256 算法的 Token 被拒绝(签名校验先于算法校验,故报签名无效)。"""
        import json
        header = {"alg": "none", "typ": "JWT"}
        payload = {"user_id": 1, "token_type": "access"}
        header_b64 = _b64url_encode(json.dumps(header).encode())
        payload_b64 = _b64url_encode(json.dumps(payload).encode())
        token = f"{header_b64}.{payload_b64}."
        # 签名校验先于算法校验,空签名无法通过 → "签名无效"
        with pytest.raises(ValueError, match="签名无效"):
            verify_token(token)


# ---------------------------------------------------------------------------
# decode_token_unsafe(不校验签名)
# ---------------------------------------------------------------------------

class TestDecodeUnsafe:
    """decode_token_unsafe 仅解码,不校验签名。"""

    def test_decode_unsafe_returns_payload(self):
        """decode_token_unsafe 返回 payload(不校验签名)。"""
        token = create_access_token(user_id=42, username="u", role="user")
        payload = decode_token_unsafe(token)
        assert payload["user_id"] == 42

    def test_decode_unsafe_returns_empty_for_malformed(self):
        """格式错误返回空字典。"""
        assert decode_token_unsafe("malformed") == {}
        assert decode_token_unsafe("a.b") == {}

    def test_decode_unsafe_does_not_verify_signature(self):
        """decode_token_unsafe 不校验签名(可解码任意 payload)。"""
        import json
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {"user_id": 999, "fake": True}
        header_b64 = _b64url_encode(json.dumps(header).encode())
        payload_b64 = _b64url_encode(json.dumps(payload).encode())
        fake_token = f"{header_b64}.{payload_b64}.fakesignature"
        decoded = decode_token_unsafe(fake_token)
        assert decoded["user_id"] == 999
        assert decoded["fake"] is True
