"""
双 Token 体系(Phase 0.4)。

实现「Access Token 2h + Refresh Token 7d」:
    - Access Token:  短有效期,每次请求携带,过期后用 Refresh Token 换新
    - Refresh Token: 长有效期,仅用于换新 Access Token,服务端持久化 jti

Token 格式: JWT HS256(保持与旧实现一致,便于无缝替换)
    - payload.user_id:    用户 ID
    - payload.username:   用户名
    - payload.role:       角色
    - payload.token_type: "access" / "refresh"
    - payload.jti:        Token 唯一 ID(用于黑名单)
    - payload.device_fp:  设备指纹(Access Token 绑定设备)
    - payload.iat:        签发时间
    - payload.exp:        过期时间

设计:
    - 默认有效期通过环境变量可调
    - Refresh Token 的 jti 写入 Redis(或内存),换发时校验
    - 黑名单通过 blacklist 模块实现
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# 配置(从环境变量读取,带安全默认)
# ---------------------------------------------------------------------------

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "officeagent-dev-secret-change-me")
JWT_ALGORITHM = "HS256"

# Access Token 有效期:2 小时
ACCESS_TOKEN_TTL = int(os.getenv("ACCESS_TOKEN_TTL", str(2 * 3600)))

# Refresh Token 有效期:7 天
REFRESH_TOKEN_TTL = int(os.getenv("REFRESH_TOKEN_TTL", str(7 * 24 * 3600)))


# ---------------------------------------------------------------------------
# Base64url 工具
# ---------------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """Base64url 编码(无填充)。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Base64url 解码(自动补齐填充)。"""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _jwt_sign(message: str) -> str:
    """HMAC-SHA256 签名。"""
    sig = hmac.new(
        JWT_SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).digest()
    return _b64url_encode(sig)


# ---------------------------------------------------------------------------
# Token 容器
# ---------------------------------------------------------------------------


@dataclass
class TokenPair:
    """双 Token 响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_TTL      # Access Token 剩余有效期(秒)
    refresh_expires_in: int = REFRESH_TOKEN_TTL  # Refresh Token 剩余有效期(秒)


# ---------------------------------------------------------------------------
# Token 创建
# ---------------------------------------------------------------------------


def _create_token(
    user_id: int,
    username: str,
    role: str,
    token_type: str,
    ttl: int,
    device_fp: Optional[str] = None,
    extra_payload: Optional[dict] = None,
) -> str:
    """创建 JWT Token。"""
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "token_type": token_type,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + ttl,
    }
    if device_fp:
        payload["device_fp"] = device_fp
    if extra_payload:
        payload.update(extra_payload)

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"
    signature = _jwt_sign(signing_input)
    return f"{signing_input}.{signature}"


def create_access_token(
    user_id: int,
    username: str,
    role: str = "user",
    device_fp: Optional[str] = None,
) -> str:
    """创建 Access Token(2h)。"""
    return _create_token(
        user_id=user_id,
        username=username,
        role=role,
        token_type="access",
        ttl=ACCESS_TOKEN_TTL,
        device_fp=device_fp,
    )


def create_refresh_token(
    user_id: int,
    username: str,
    role: str = "user",
    device_fp: Optional[str] = None,
) -> str:
    """创建 Refresh Token(7d)。

    Phase 0.4:device_fp 也写入 Refresh Token,以便 /auth/refresh
    接口能校验设备指纹(防止 Refresh Token 被盗后在不同设备换发)。
    """
    return _create_token(
        user_id=user_id,
        username=username,
        role=role,
        token_type="refresh",
        ttl=REFRESH_TOKEN_TTL,
        device_fp=device_fp,
    )


def create_token_pair(
    user_id: int,
    username: str,
    role: str = "user",
    device_fp: Optional[str] = None,
) -> TokenPair:
    """创建双 Token(Access + Refresh)。

    两个 Token 都携带 device_fp(Access Token 用于业务接口校验,
    Refresh Token 用于换发时校验)。
    """
    return TokenPair(
        access_token=create_access_token(user_id, username, role, device_fp),
        refresh_token=create_refresh_token(user_id, username, role, device_fp),
        expires_in=ACCESS_TOKEN_TTL,
        refresh_expires_in=REFRESH_TOKEN_TTL,
    )


# ---------------------------------------------------------------------------
# Token 校验
# ---------------------------------------------------------------------------


def verify_token(token: str, expected_type: Optional[str] = None) -> dict:
    """校验 JWT Token 签名 + 过期 + 类型,返回 payload。

    Args:
        token: JWT 字符串
        expected_type: 期望的 token_type("access" / "refresh"),None 则不校验

    Returns:
        payload dict

    Raises:
        ValueError: 校验失败
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Token 必须由 3 段组成")

    header_b64, payload_b64, signature = parts

    # 1. 校验签名(常量时间比较防侧信道)
    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = _jwt_sign(signing_input)
    if not hmac.compare_digest(expected_sig, signature):
        raise ValueError("签名无效")

    # 2. 解析 header,校验算法
    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != JWT_ALGORITHM:
        raise ValueError(f"不支持的算法: {header.get('alg')}")

    # 3. 解析 payload
    payload = json.loads(_b64url_decode(payload_b64))

    # 4. 校验过期
    exp = payload.get("exp")
    if exp is not None and int(time.time()) > int(exp):
        raise ValueError("Token 已过期")

    if "user_id" not in payload:
        raise ValueError("Token 缺少 user_id")

    # 5. 校验类型
    if expected_type and payload.get("token_type") != expected_type:
        raise ValueError(
            f"Token 类型不匹配: 期望 {expected_type}, 实际 {payload.get('token_type')}"
        )

    return payload


def decode_token_unsafe(token: str) -> dict:
    """仅解码 payload,不校验签名(用于调试/日志)。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        return json.loads(_b64url_decode(parts[1]))
    except Exception:
        return {}
