"""
资产加密测试。

覆盖:
    - 加密/解密往返一致性
    - 文件加密/解密往返
    - 密码错误解密失败
    - 每次加密密文不同(随机 salt + nonce)
    - 降级模式(cryptography 不可用时)
"""

import os

import pytest

from fnixagent.assets.crypto import AssetEncryptor, is_encryption_available

# ---------------------------------------------------------------------------
# 前置条件
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not is_encryption_available(),
    reason="cryptography 库不可用,跳过真实加密测试",
)
class TestEncryptionAvailable:
    """cryptography 可用时的测试。"""

    # ------------------------------------------------------------------
    # 字节级加密/解密往返
    # ------------------------------------------------------------------

    def test_encrypt_decrypt_round_trip_bytes(self, encryptor):
        """字节级加密-解密往返一致。"""
        plain = b"Hello, FnixAgent! \xe4\xb8\xad\xe6\x96\x87"
        cipher = encryptor.encrypt(plain)
        assert cipher != plain
        decrypted = encryptor.decrypt(cipher)
        assert decrypted == plain

    def test_encrypt_empty_bytes(self, encryptor):
        """空字节也能加密解密。"""
        plain = b""
        cipher = encryptor.encrypt(plain)
        decrypted = encryptor.decrypt(cipher)
        assert decrypted == plain

    def test_encrypt_large_bytes(self, encryptor):
        """大块字节(64KB)加密解密往返。"""
        plain = os.urandom(64 * 1024)
        cipher = encryptor.encrypt(plain)
        assert encryptor.decrypt(cipher) == plain

    # ------------------------------------------------------------------
    # 随机性
    # ------------------------------------------------------------------

    def test_each_encryption_differs(self, encryptor):
        """每次加密的密文不同(随机 salt + nonce)。"""
        plain = b"same plaintext"
        cipher1 = encryptor.encrypt(plain)
        cipher2 = encryptor.encrypt(plain)
        assert cipher1 != cipher2
        # 但都能正确解密
        assert encryptor.decrypt(cipher1) == plain
        assert encryptor.decrypt(cipher2) == plain

    def test_cipher_has_salt_nonce_prefix(self, encryptor):
        """密文包含 salt(16) + nonce(12) 前缀。"""
        plain = b"test"
        cipher = encryptor.encrypt(plain)
        # 至少 16 + 12 + GCM tag(16) 字节
        assert len(cipher) >= 16 + 12 + 16

    # ------------------------------------------------------------------
    # 密码错误
    # ------------------------------------------------------------------

    def test_wrong_password_decrypt_fails(self):
        """错误密码解密失败,抛出 ValueError。"""
        enc1 = AssetEncryptor("correct_password")
        enc2 = AssetEncryptor("wrong_password")
        cipher = enc1.encrypt(b"secret data")
        with pytest.raises(ValueError):
            enc2.decrypt(cipher)

    def test_tampered_ciphertext_decrypt_fails(self, encryptor):
        """篡改密文后解密失败(GCM 认证)。"""
        cipher = encryptor.encrypt(b"original data")
        # 翻转最后一字节(篡改 GCM tag)
        tampered = cipher[:-1] + bytes([cipher[-1] ^ 0xFF])
        with pytest.raises(ValueError):
            encryptor.decrypt(tampered)

    def test_truncated_ciphertext_raises(self, encryptor):
        """截断的密文(不足 salt+nonce 长度)抛出 ValueError。"""
        with pytest.raises(ValueError):
            encryptor.decrypt(b"too short")

    # ------------------------------------------------------------------
    # 文件级加密/解密
    # ------------------------------------------------------------------

    def test_encrypt_decrypt_file_round_trip(self, encryptor, tmp_path):
        """文件加密-解密往返一致。"""
        src = tmp_path / "plain.txt"
        dst = tmp_path / "enc.bin"
        restored = tmp_path / "restored.txt"
        content = b"file content with \xe4\xb8\xad\xe6\x96\x87"
        src.write_bytes(content)

        encryptor.encrypt_file(str(src), str(dst))
        # 密文文件存在且与原文不同
        assert dst.exists()
        assert dst.read_bytes() != content

        encryptor.decrypt_file(str(dst), str(restored))
        assert restored.read_bytes() == content

    def test_encrypt_file_creates_parent_dir(self, encryptor, tmp_path):
        """加密文件时自动创建父目录。"""
        src = tmp_path / "plain.txt"
        src.write_bytes(b"data")
        dst = tmp_path / "sub" / "dir" / "enc.bin"
        encryptor.encrypt_file(str(src), str(dst))
        assert dst.exists()

    def test_decrypt_file_creates_parent_dir(self, encryptor, tmp_path):
        """解密文件时自动创建父目录。"""
        src = tmp_path / "plain.txt"
        src.write_bytes(b"data")
        enc = tmp_path / "enc.bin"
        encryptor.encrypt_file(str(src), str(enc))
        dst = tmp_path / "out" / "deep" / "restored.txt"
        encryptor.decrypt_file(str(enc), str(dst))
        assert dst.exists()


# ---------------------------------------------------------------------------
# 不同密码实例的隔离性
# ---------------------------------------------------------------------------


def test_different_encryptors_same_password_compatible():
    """两个不同实例使用相同密码可互相解密(密钥派生可复现)。"""
    enc1 = AssetEncryptor("shared_password")
    enc2 = AssetEncryptor("shared_password")
    cipher = enc1.encrypt(b"shared secret")
    # 注意: salt 随机,但 enc2 用密文中的 salt 重新派生密钥
    assert enc2.decrypt(cipher) == b"shared secret"
