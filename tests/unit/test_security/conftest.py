"""
core/security/auth 子包单元测试公共夹具。

提供以下 fixtures:
    - argon2_available: 是否安装 argon2-cffi(用于 skip 装饰)
    - crypto_available: 是否安装 cryptography(用于 skip 装饰)
    - fresh_keypair:    每个测试用例独立的 RSAKeyPair(避免共享状态)
    - fresh_blacklist:  每个测试用例独立的 TokenBlacklist(内存模式)
    - reset_keystore:   每个测试用例前重置 keystore 单例
"""

import os
import sys

# 确保 src 在路径中(与其它 conftest 一致)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest

from fnixagent.core.security.auth.blacklist import TokenBlacklist, reset_blacklist
from fnixagent.core.security.auth.keystore import reset_server_keypair
from fnixagent.core.security.auth.password import is_argon2_available
from fnixagent.core.security.auth.rsa_crypto import generate_keypair, is_rsa_available

# ---------------------------------------------------------------------------
# 可用性检查(供 skipif 使用)
# ---------------------------------------------------------------------------


@pytest.fixture
def argon2_available() -> bool:
    """返回 argon2-cffi 是否可用。"""
    return is_argon2_available()


@pytest.fixture
def crypto_available() -> bool:
    """返回 cryptography 库是否可用。"""
    return is_rsa_available()


# ---------------------------------------------------------------------------
# 每个用例独立 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_keypair():
    """每个测试生成全新的 RSA-2048 密钥对(隔离)。"""
    return generate_keypair(key_size=2048)


@pytest.fixture
def fresh_blacklist():
    """每个测试用例独立的内存 TokenBlacklist。

    不连接 Redis(测试环境无 Redis),强制内存模式。
    """
    bl = TokenBlacklist(redis_host=None)  # None → 内存模式
    yield bl
    bl.clear()


@pytest.fixture(autouse=True)
def reset_keystore_and_blacklist():
    """每个测试前后重置全局单例(避免用例间相互污染)。"""
    reset_server_keypair()
    reset_blacklist()
    yield
    reset_server_keypair()
    reset_blacklist()
