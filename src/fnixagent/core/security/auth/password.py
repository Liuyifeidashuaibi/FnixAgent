"""
Argon2id 密码哈希(Phase 0.4)。

替代 services/storage.py 中的 PBKDF2-HMAC-SHA256 实现。
Argon2id 是 OWASP 推荐的密码哈希算法(抗 GPU/ASIC 攻击)。

参数选择(基于 OWASP 2024 推荐):
    - time_cost:        3        (迭代次数)
    - memory_cost:      65536    (64 MB,抗 GPU 并行破解)
    - parallelism:      1        (单线程,避免 DoS)
    - hash_len:         32       (256 bits)
    - salt_len:         16       (128 bits)

向后兼容:
    verify_password 同时识别 pbkdf2_sha256$... 与 $argon2id$... 两种格式。
    检测到 PBKDF2 哈希时按旧算法校验,通过后调用 needs_rehash 提示需升级。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import secrets

# argon2-cffi 在 Phase 0.2 已加入 requirements.txt
try:
    from argon2 import PasswordHasher, Type
    from argon2.exceptions import InvalidHashError, VerifyMismatchError

    _HAS_ARGON2 = True
    _argon2_hasher = PasswordHasher(
        time_cost=3,
        memory_cost=65536,  # 64 MB
        parallelism=1,
        hash_len=32,
        salt_len=16,
        type=Type.ID,  # Argon2id(混合版,推荐)
    )
except ImportError:  # pragma: no cover
    _HAS_ARGON2 = False
    _argon2_hasher = None

# ---------------------------------------------------------------------------
# Argon2id 哈希
# ---------------------------------------------------------------------------


def argon2_hash_password(password: str) -> str:
    """对密码做 Argon2id 哈希,返回 PHC 字符串。

    返回格式: $argon2id$v=19$m=65536,t=3,p=1$<salt>$<hash>
    """
    if not _HAS_ARGON2:
        # argon2-cffi 不可用时回退到 PBKDF2(开发环境降级,生产必须装 argon2-cffi)
        return _pbkdf2_hash(password)
    return _argon2_hasher.hash(password)


def argon2_verify_password(password: str, stored: str) -> bool:
    """校验密码是否匹配 Argon2id 哈希。"""
    if not _HAS_ARGON2:
        return False
    try:
        return _argon2_hasher.verify(stored, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PBKDF2(向后兼容,仅当 argon2-cffi 不可用或老用户哈希仍是 PBKDF2 时使用)
# ---------------------------------------------------------------------------


def _pbkdf2_hash(password: str, salt: str | None = None) -> str:
    """PBKDF2-HMAC-SHA256, 100000 轮(向后兼容)。"""
    iterations = 100000
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def _pbkdf2_verify(password: str, stored: str) -> bool:
    """校验 PBKDF2 哈希。"""
    try:
        parts = stored.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected = parts[3]
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
        )
        return secrets.compare_digest(dk.hex(), expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 统一入口(自动识别哈希格式)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """对密码做哈希(默认 Argon2id)。

    统一入口,与 services/storage.py 中的旧函数同名,便于无缝替换。
    """
    return argon2_hash_password(password)


def verify_password(password: str, stored: str) -> bool:
    """校验密码(自动识别 Argon2id / PBKDF2 格式)。

    统一入口,与 services/storage.py 中的旧函数同名。
    """
    if not stored:
        return False

    # 1. Argon2id 哈希(优先)
    if stored.startswith("$argon2"):
        return argon2_verify_password(password, stored)

    # 2. PBKDF2 哈希(向后兼容老用户)
    if stored.startswith("pbkdf2_sha256$"):
        return _pbkdf2_verify(password, stored)

    # 3. 未知格式
    return False


def needs_rehash(stored: str) -> bool:
    """检测哈希是否需要升级(老 PBKDF2 哈希需升级到 Argon2id)。

    用于登录成功后判断是否需要调用 hash_password 重新哈希。
    """
    if not _HAS_ARGON2:
        return False  # argon2-cffi 不可用时不升级
    return stored.startswith("pbkdf2_sha256$")


# ---------------------------------------------------------------------------
# Argon2id 可用性检查
# ---------------------------------------------------------------------------


def is_argon2_available() -> bool:
    """返回 argon2-cffi 是否可用。"""
    return _HAS_ARGON2
