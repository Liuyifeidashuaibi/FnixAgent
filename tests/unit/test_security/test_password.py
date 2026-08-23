"""
password 模块单元测试(验收标准 ① 单元测试覆盖 Argon2id 哈希/校验)。

覆盖:
    - Argon2id 哈希返回 PHC 格式字符串
    - 哈希结果不可逆(不含明文)
    - 相同密码每次哈希结果不同(随机 salt)
    - 正确密码校验通过
    - 错误密码校验失败
    - PBKDF2 旧哈希向后兼容
    - verify_password 自动识别两种格式
    - needs_rehash 检测旧哈希需升级
    - 空哈希 / 未知格式拒绝
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest

from fnixagent.core.security.auth.password import (
    _pbkdf2_hash,
    _pbkdf2_verify,
    argon2_hash_password,
    argon2_verify_password,
    hash_password,
    is_argon2_available,
    needs_rehash,
    verify_password,
)

# ---------------------------------------------------------------------------
# 前置条件:argon2-cffi 必须可用(Phase 0.2 已加入 requirements)
# ---------------------------------------------------------------------------

_SKIP_REASON = "argon2-cffi 不可用,跳过 Argon2id 真实哈希测试"


# ---------------------------------------------------------------------------
# Argon2id 哈希格式
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_argon2_available(), reason=_SKIP_REASON)
class TestArgon2HashFormat:
    """Argon2id 哈希输出格式。"""

    def test_hash_returns_phc_string(self):
        """哈希结果应为 PHC 格式($argon2id$v=...$...)。"""
        h = argon2_hash_password("mypassword")
        assert isinstance(h, str)
        assert h.startswith("$argon2id$")

    def test_hash_contains_required_params(self):
        """PHC 字符串必须包含 v/m/t/p 参数。"""
        h = argon2_hash_password("mypassword")
        # $argon2id$v=19$m=65536,t=3,p=1$<salt>$<hash>
        assert "$v=" in h
        assert "$m=" in h
        assert ",t=" in h
        assert ",p=" in h

    def test_hash_does_not_contain_plaintext(self):
        """哈希结果不应包含明文密码。"""
        password = "super_secret_123"
        h = argon2_hash_password(password)
        assert password not in h

    def test_each_hash_differs_due_to_random_salt(self):
        """相同密码每次哈希结果不同(随机 salt)。"""
        h1 = argon2_hash_password("same")
        h2 = argon2_hash_password("same")
        assert h1 != h2
        # 但都能正确校验
        assert argon2_verify_password("same", h1) is True
        assert argon2_verify_password("same", h2) is True

    def test_hash_length_within_reasonable_range(self):
        """Argon2id PHC 字符串长度合理(< 200 字符)。"""
        h = argon2_hash_password("x" * 64)
        assert 50 < len(h) < 200


# ---------------------------------------------------------------------------
# Argon2id 校验
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_argon2_available(), reason=_SKIP_REASON)
class TestArgon2Verify:
    """Argon2id 校验逻辑。"""

    def test_verify_correct_password(self):
        """正确密码校验通过。"""
        h = argon2_hash_password("correct_password")
        assert argon2_verify_password("correct_password", h) is True

    def test_verify_wrong_password(self):
        """错误密码校验失败。"""
        h = argon2_hash_password("correct_password")
        assert argon2_verify_password("wrong_password", h) is False

    def test_verify_empty_password_against_real_hash(self):
        """空密码也能哈希/校验(不应崩溃)。"""
        h = argon2_hash_password("")
        assert argon2_verify_password("", h) is True
        assert argon2_verify_password("nonempty", h) is False

    def test_verify_unicode_password(self):
        """Unicode 密码(中文/emoji)支持。"""
        password = "密码🔐123"
        h = argon2_hash_password(password)
        assert argon2_verify_password(password, h) is True
        assert argon2_verify_password("密码🔐124", h) is False

    def test_verify_returns_false_on_corrupted_hash(self):
        """损坏的 Argon2 哈希返回 False(不抛异常)。"""
        h = argon2_hash_password("mypassword")
        # 篡改哈希末尾
        tampered = h[:-4] + "XXXX"
        assert argon2_verify_password("mypassword", tampered) is False


# ---------------------------------------------------------------------------
# PBKDF2 向后兼容
# ---------------------------------------------------------------------------


class TestPbkdf2BackwardCompat:
    """PBKDF2 旧哈希向后兼容(不依赖 argon2-cffi)。"""

    def test_pbkdf2_hash_format(self):
        """PBKDF2 哈希格式:pbkdf2_sha256$<iter>$<salt>$<hash>。"""
        h = _pbkdf2_hash("mypassword")
        assert h.startswith("pbkdf2_sha256$")
        parts = h.split("$")
        assert len(parts) == 4
        assert parts[0] == "pbkdf2_sha256"
        assert int(parts[1]) == 100000  # 默认迭代次数

    def test_pbkdf2_verify_correct(self):
        """PBKDF2 正确密码校验通过。"""
        h = _pbkdf2_hash("mypassword")
        assert _pbkdf2_verify("mypassword", h) is True

    def test_pbkdf2_verify_wrong(self):
        """PBKDF2 错误密码校验失败。"""
        h = _pbkdf2_hash("mypassword")
        assert _pbkdf2_verify("wrong", h) is False

    def test_pbkdf2_each_hash_differs(self):
        """相同密码每次 PBKDF2 哈希结果不同(随机 salt)。"""
        h1 = _pbkdf2_hash("same")
        h2 = _pbkdf2_hash("same")
        assert h1 != h2

    def test_pbkdf2_verify_corrupted_returns_false(self):
        """损坏的 PBKDF2 哈希返回 False(不抛异常)。"""
        assert _pbkdf2_verify("x", "garbage") is False
        assert _pbkdf2_verify("x", "pbkdf2_sha256$bad") is False
        assert _pbkdf2_verify("x", "pbkdf2_sha256$abc$def$ghi$extra") is False


# ---------------------------------------------------------------------------
# 统一入口(自动识别哈希格式)
# ---------------------------------------------------------------------------


class TestUnifiedEntry:
    """hash_password / verify_password 统一入口。"""

    def test_hash_password_uses_argon2_when_available(self):
        """argon2-cffi 可用时,hash_password 返回 Argon2id 哈希。"""
        h = hash_password("test")
        if is_argon2_available():
            assert h.startswith("$argon2id$")
        else:
            # 降级到 PBKDF2
            assert h.startswith("pbkdf2_sha256$")

    def test_verify_password_detects_argon2_format(self):
        """verify_password 自动识别 Argon2id 哈希。"""
        if not is_argon2_available():
            pytest.skip(_SKIP_REASON)
        h = argon2_hash_password("mypassword")
        assert verify_password("mypassword", h) is True
        assert verify_password("wrong", h) is False

    def test_verify_password_detects_pbkdf2_format(self):
        """verify_password 自动识别 PBKDF2 哈希(向后兼容)。"""
        h = _pbkdf2_hash("mypassword")
        assert verify_password("mypassword", h) is True
        assert verify_password("wrong", h) is False

    def test_verify_password_empty_stored_returns_false(self):
        """空哈希返回 False。"""
        assert verify_password("x", "") is False
        assert verify_password("x", None) is False

    def test_verify_password_unknown_format_returns_false(self):
        """未知哈希格式返回 False。"""
        assert verify_password("x", "bcrypt$some$hash") is False
        assert verify_password("x", "plain_text_no_prefix") is False


# ---------------------------------------------------------------------------
# needs_rehash 升级检测
# ---------------------------------------------------------------------------


class TestNeedsRehash:
    """needs_rehash 检测哈希是否需要升级到 Argon2id。"""

    def test_pbkdf2_hash_needs_rehash_when_argon2_available(self):
        """PBKDF2 哈希在 argon2-cffi 可用时需要升级。"""
        h = _pbkdf2_hash("x")
        if is_argon2_available():
            assert needs_rehash(h) is True
        else:
            # argon2-cffi 不可用时不升级
            assert needs_rehash(h) is False

    def test_argon2_hash_does_not_need_rehash(self):
        """已经是 Argon2id 的哈希不需要升级。"""
        if not is_argon2_available():
            pytest.skip(_SKIP_REASON)
        h = argon2_hash_password("x")
        assert needs_rehash(h) is False

    def test_unknown_format_does_not_need_rehash(self):
        """未知格式不触发升级(避免误升级非密码哈希)。"""
        assert needs_rehash("bcrypt$xxx") is False
        assert needs_rehash("") is False
