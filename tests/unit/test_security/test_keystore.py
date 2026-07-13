"""
keystore 模块单元测试。

覆盖:
    - get_server_keypair 单例懒加载
    - 多次调用返回同一实例
    - reset_server_keypair 后返回新实例
    - 默认生成 RSA-2048 密钥对(开发环境)
    - 从 RSA_PRIVATE_KEY_PATH 环境变量加载持久化密钥
    - 加载失败时回退到生成新密钥对
"""
import os

import pytest

from officeagent.core.security.auth.keystore import (
    _keypair_instance,
    get_server_keypair,
    reset_server_keypair,
)
from officeagent.core.security.auth.rsa_crypto import (
    RSAKeyPair,
    generate_keypair,
    is_rsa_available,
)


_SKIP_REASON = "cryptography 库不可用,跳过 keystore 真实密钥测试"


# ---------------------------------------------------------------------------
# 单例行为
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestKeystoreSingleton:
    """keystore 单例行为。"""

    def test_get_server_keypair_returns_rsa_keypair(self):
        """get_server_keypair 返回 RSAKeyPair 实例。"""
        kp = get_server_keypair()
        assert isinstance(kp, RSAKeyPair)

    def test_get_server_keypair_returns_singleton(self):
        """多次调用返回同一实例。"""
        kp1 = get_server_keypair()
        kp2 = get_server_keypair()
        assert kp1 is kp2

    def test_reset_then_get_returns_new_instance(self):
        """reset 后再次 get 返回新实例。"""
        kp1 = get_server_keypair()
        reset_server_keypair()
        kp2 = get_server_keypair()
        assert kp1 is not kp2
        # 公钥也不同(重新生成)
        assert kp1.public_pem != kp2.public_pem

    def test_default_keypair_is_2048_bits(self):
        """默认生成的密钥对为 2048 位。"""
        kp = get_server_keypair()
        assert kp.key_size == 2048


# ---------------------------------------------------------------------------
# 从环境变量加载持久化密钥
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestKeystoreLoadFromEnv:
    """从 RSA_PRIVATE_KEY_PATH 加载持久化密钥。"""

    def test_load_from_env_path(self, tmp_path, monkeypatch):
        """设置 RSA_PRIVATE_KEY_PATH 时从文件加载密钥。"""
        # 生成一个持久化密钥对并保存
        original_kp = generate_keypair()
        key_file = tmp_path / "server.pem"
        # 用二进制写入,避免 Windows 文本模式把 \n 转成 \r\n
        key_file.write_bytes(original_kp.private_pem.encode("utf-8"))

        # 设置环境变量
        monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", str(key_file))
        reset_server_keypair()

        loaded = get_server_keypair()
        assert loaded.public_pem == original_kp.public_pem
        assert loaded.private_pem == original_kp.private_pem

    def test_load_nonexistent_file_falls_back_to_generate(self, monkeypatch):
        """RSA_PRIVATE_KEY_PATH 指向不存在的文件时回退到生成。"""
        monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", "/nonexistent/key.pem")
        reset_server_keypair()

        kp = get_server_keypair()
        assert isinstance(kp, RSAKeyPair)
        assert kp.key_size == 2048

    def test_load_corrupted_file_falls_back_to_generate(self, tmp_path, monkeypatch):
        """RSA_PRIVATE_KEY_PATH 指向损坏文件时回退到生成。"""
        bad_file = tmp_path / "corrupt.pem"
        bad_file.write_text("not a valid PEM file", encoding="utf-8")

        monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", str(bad_file))
        reset_server_keypair()

        kp = get_server_keypair()
        assert isinstance(kp, RSAKeyPair)
        # 应该是新生成的(PEM 格式正确)
        assert "BEGIN PRIVATE KEY" in kp.private_pem

    def test_empty_env_var_falls_back_to_generate(self, monkeypatch):
        """RSA_PRIVATE_KEY_PATH 为空时回退到生成。"""
        monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", "")
        reset_server_keypair()

        kp = get_server_keypair()
        assert isinstance(kp, RSAKeyPair)

    def test_unset_env_var_falls_back_to_generate(self, monkeypatch):
        """未设置 RSA_PRIVATE_KEY_PATH 时回退到生成。"""
        monkeypatch.delenv("RSA_PRIVATE_KEY_PATH", raising=False)
        reset_server_keypair()

        kp = get_server_keypair()
        assert isinstance(kp, RSAKeyPair)


# ---------------------------------------------------------------------------
# 集成:keystore 加载的密钥可解密客户端加密的密码
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
def test_keystore_keypair_can_decrypt_client_encrypted_password():
    """从 keystore 获取的密钥对可解密客户端用其公钥加密的密码。"""
    import base64
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding

    reset_server_keypair()
    kp = get_server_keypair()

    password = "integration_test_password"

    # 模拟客户端用公钥加密
    public_key = serialization.load_pem_public_key(
        kp.public_pem.encode("utf-8"),
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
    ciphertext_b64 = base64.b64encode(ciphertext).decode("ascii")

    # 服务端解密
    assert kp.decrypt(ciphertext_b64) == password
