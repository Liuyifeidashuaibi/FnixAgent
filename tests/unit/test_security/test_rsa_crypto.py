"""
rsa_crypto 模块单元测试(验收标准 ② RSA 加解密往返测试)。

覆盖:
    - 生成 RSA-2048 密钥对(PEM 格式)
    - 公钥加密 → 私钥解密 往返一致
    - 模拟客户端加密密码 → 服务端解密
    - 错误密文解密抛 ValueError
    - 篡改密文解密失败(OAEP 认证)
    - 密钥对从文件加载
    - rsa_decrypt_password 统一入口
"""

import base64

import pytest

from fnixagent.core.security.auth.rsa_crypto import (
    RSAKeyPair,
    generate_keypair,
    is_rsa_available,
    load_keypair_from_file,
    rsa_decrypt_password,
)

# ---------------------------------------------------------------------------
# 前置条件:cryptography 必须可用
# ---------------------------------------------------------------------------

_SKIP_REASON = "cryptography 库不可用,跳过 RSA 真实加解密测试"


# ---------------------------------------------------------------------------
# 客户端加密辅助函数(模拟前端行为)
# ---------------------------------------------------------------------------


def _client_encrypt(public_pem: str, plaintext: str) -> str:
    """模拟客户端用服务端公钥加密密码(OAEP+SHA256),返回 Base64 密文。"""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding

    public_key = serialization.load_pem_public_key(
        public_pem.encode("utf-8"),
        backend=default_backend(),
    )
    ciphertext = public_key.encrypt(
        plaintext.encode("utf-8"),
        rsa_padding.OAEP(
            mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("ascii")


# ---------------------------------------------------------------------------
# 密钥对生成与格式
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestKeypairGeneration:
    """RSA 密钥对生成。"""

    def test_generate_returns_rsa_keypair(self, fresh_keypair):
        """generate_keypair 返回 RSAKeyPair 实例。"""
        assert isinstance(fresh_keypair, RSAKeyPair)

    def test_keypair_has_private_and_public_pem(self, fresh_keypair):
        """密钥对包含 PEM 格式的私钥和公钥。"""
        assert "BEGIN PRIVATE KEY" in fresh_keypair.private_pem
        assert "END PRIVATE KEY" in fresh_keypair.private_pem
        assert "BEGIN PUBLIC KEY" in fresh_keypair.public_pem
        assert "END PUBLIC KEY" in fresh_keypair.public_pem

    def test_default_key_size_is_2048(self, fresh_keypair):
        """默认密钥长度 2048 位。"""
        assert fresh_keypair.key_size == 2048

    def test_each_keypair_differs(self):
        """每次生成的密钥对不同(随机性)。"""
        kp1 = generate_keypair()
        kp2 = generate_keypair()
        assert kp1.private_pem != kp2.private_pem
        assert kp1.public_pem != kp2.public_pem


# ---------------------------------------------------------------------------
# 加解密往返(验收标准 ②)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestRsaRoundTrip:
    """RSA 加解密往返一致性。"""

    def test_client_encrypt_server_decrypt_round_trip(self, fresh_keypair):
        """模拟客户端加密 → 服务端解密的完整链路。"""
        password = "my_super_secret_password_123"
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        # 服务端用私钥解密
        plaintext = fresh_keypair.decrypt(ciphertext_b64)
        assert plaintext == password

    def test_round_trip_with_unicode_password(self, fresh_keypair):
        """Unicode 密码(中文/emoji)加解密往返一致。"""
        password = "密码🔐123"
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        assert fresh_keypair.decrypt(ciphertext_b64) == password

    def test_round_trip_with_empty_password(self, fresh_keypair):
        """空密码也能加密解密。"""
        password = ""
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        assert fresh_keypair.decrypt(ciphertext_b64) == password

    def test_round_trip_with_max_length_password(self, fresh_keypair):
        """接近 RSA-2048 OAEP 最大长度的密码(190 字节)。"""
        # RSA-2048 + OAEP-SHA256: 最大明文 = 256 - 2*32 - 2 = 190 字节
        password = "a" * 190
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        assert fresh_keypair.decrypt(ciphertext_b64) == password

    def test_each_encryption_differs(self, fresh_keypair):
        """OAEP padding 引入随机性,相同明文每次密文不同。"""
        password = "same"
        c1 = _client_encrypt(fresh_keypair.public_pem, password)
        c2 = _client_encrypt(fresh_keypair.public_pem, password)
        assert c1 != c2
        # 都能正确解密
        assert fresh_keypair.decrypt(c1) == password
        assert fresh_keypair.decrypt(c2) == password


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestRsaDecryptionErrors:
    """RSA 解密错误处理。"""

    def test_tampered_ciphertext_raises_value_error(self, fresh_keypair):
        """篡改密文后解密失败(OAEP 认证)。"""
        password = "original"
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        # 翻转最后一字节(篡改)
        raw = bytearray(base64.b64decode(ciphertext_b64))
        raw[-1] ^= 0xFF
        tampered_b64 = base64.b64encode(bytes(raw)).decode("ascii")
        with pytest.raises(Exception):
            fresh_keypair.decrypt(tampered_b64)

    def test_decrypt_invalid_base64_raises(self, fresh_keypair):
        """非法 Base64 抛异常。"""
        with pytest.raises(Exception):
            fresh_keypair.decrypt("not_base64!!!")

    def test_decrypt_wrong_keypair_raises(self):
        """用错误的私钥解密另一公钥加密的密文失败。"""
        kp1 = generate_keypair()
        kp2 = generate_keypair()
        ciphertext_b64 = _client_encrypt(kp1.public_pem, "secret")
        with pytest.raises(Exception):
            kp2.decrypt(ciphertext_b64)


# ---------------------------------------------------------------------------
# rsa_decrypt_password 统一入口
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestRsaDecryptPasswordEntry:
    """rsa_decrypt_password 统一入口。"""

    def test_rsa_decrypt_password_success(self, fresh_keypair):
        """rsa_decrypt_password 解密客户端加密的密码。"""
        password = "login_password_456"
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        assert rsa_decrypt_password(ciphertext_b64, fresh_keypair) == password

    def test_rsa_decrypt_password_empty_ciphertext_raises(self, fresh_keypair):
        """空密文抛 ValueError。"""
        with pytest.raises(ValueError, match="密文为空"):
            rsa_decrypt_password("", fresh_keypair)

    def test_rsa_decrypt_password_failure_wraps_as_value_error(self, fresh_keypair):
        """解密失败统一包装为 ValueError。"""
        with pytest.raises(ValueError, match="RSA 解密失败"):
            rsa_decrypt_password("!!!invalid_base64!!!", fresh_keypair)


# ---------------------------------------------------------------------------
# 从文件加载密钥对
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not is_rsa_available(), reason=_SKIP_REASON)
class TestLoadKeypairFromFile:
    """从 PEM 文件加载密钥对(生产环境持久化)。"""

    def test_load_keypair_from_file_round_trip(self, fresh_keypair, tmp_path):
        """保存私钥到文件,加载后公钥应一致。"""
        key_file = tmp_path / "private.pem"
        # 用二进制写入,避免 Windows 文本模式把 \n 转成 \r\n
        key_file.write_bytes(fresh_keypair.private_pem.encode("utf-8"))

        loaded = load_keypair_from_file(str(key_file))
        assert loaded.public_pem == fresh_keypair.public_pem
        assert loaded.private_pem == fresh_keypair.private_pem

    def test_loaded_keypair_can_decrypt(self, fresh_keypair, tmp_path):
        """加载的密钥对可正常解密。"""
        key_file = tmp_path / "private.pem"
        key_file.write_bytes(fresh_keypair.private_pem.encode("utf-8"))

        loaded = load_keypair_from_file(str(key_file))
        password = "loaded_key_test"
        ciphertext_b64 = _client_encrypt(fresh_keypair.public_pem, password)
        assert rsa_decrypt_password(ciphertext_b64, loaded) == password

    def test_load_nonexistent_file_raises(self):
        """加载不存在的文件抛 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError):
            load_keypair_from_file("/nonexistent/path/key.pem")
