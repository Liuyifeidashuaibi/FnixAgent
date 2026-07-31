"""
资产加密 (Asset Encryptor)。

使用 AES-256-GCM 对资产文件进行加密存储:
    - 密钥从用户密码派生(PBKDF2-HMAC-SHA256, salt 随机, 100000 轮迭代)
    - 每次加密生成新的随机 salt + nonce,保证语义安全
    - 密钥仅内存持有,不落盘
    - cryptography 不可用时优雅降级(明文 + DeprecationWarning)

加密数据格式(字节布局):
    +----------+-----------+-----------------------+
    | salt(16) | nonce(12) | ciphertext(variable)  |
    +----------+-----------+-----------------------+
其中 ciphertext 末尾 16 字节为 GCM 认证标签(cryptography 库默认)。

设计原则:
    - 密钥派生参数(salt/iterations)与密文一同存储,解密时自洽
    - 文件加密使用二进制模式,避免编码污染
    - 降级模式仅用于无 cryptography 的环境,生产环境必须安装
"""

from __future__ import annotations

import os
import warnings

# ---------------------------------------------------------------------------
# 尝试导入 cryptography
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTO_AVAILABLE: bool = True
except ImportError:  # pragma: no cover - 降级路径,测试环境通常有 cryptography
    _CRYPTO_AVAILABLE = False


# 加密参数
_SALT_LEN: int = 16  # PBKDF2 salt 长度(字节)
_NONCE_LEN: int = 12  # AES-GCM nonce 长度(字节)
_KEY_LEN: int = 32  # AES-256 密钥长度(字节)
_ITERATIONS: int = 100_000  # PBKDF2 迭代次数


class AssetEncryptor:
    """资产加密器:基于 AES-256-GCM 的对称加密。

    Args:
        password: 用户密码(用于派生密钥,不落盘)

    Note:
        - 每次 encrypt 生成新 salt + nonce,密文每次不同
        - decrypt 复用密文头部携带的 salt/nonce 重新派生密钥
        - cryptography 不可用时降级为明文 + DeprecationWarning
    """

    def __init__(self, password: str) -> None:
        self._password: str = password
        if not _CRYPTO_AVAILABLE:
            warnings.warn(
                "cryptography 库不可用,AssetEncryptor 降级为明文模式,"
                "敏感资产未加密存储。生产环境请安装 cryptography。",
                DeprecationWarning,
                stacklevel=2,
            )

    # ------------------------------------------------------------------
    # 密钥派生
    # ------------------------------------------------------------------

    def _derive_key(self, salt: bytes) -> bytes:
        """从密码 + salt 派生 32 字节 AES 密钥(PBKDF2-HMAC-SHA256)。"""
        if not _CRYPTO_AVAILABLE:
            # 降级模式:返回固定长度占位(不会真正用于加密)
            return b"\x00" * _KEY_LEN
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LEN,
            salt=salt,
            iterations=_ITERATIONS,
        )
        return kdf.derive(self._password.encode("utf-8"))

    # ------------------------------------------------------------------
    # 字节级加密/解密
    # ------------------------------------------------------------------

    def encrypt(self, data: bytes) -> bytes:
        """加密字节数据。

        格式: salt(16) + nonce(12) + ciphertext(含 GCM tag)

        Args:
            data: 明文字节

        Returns:
            密文字节(含 salt + nonce 前缀)
        """
        if not _CRYPTO_AVAILABLE:
            # 降级:前缀标记位 + 原文
            return b"PLAIN:" + data
        salt = os.urandom(_SALT_LEN)
        nonce = os.urandom(_NONCE_LEN)
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return salt + nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        """解密字节数据。

        Args:
            data: 密文字节(salt + nonce + ciphertext)

        Returns:
            明文字节

        Raises:
            ValueError: 密码错误或数据被篡改(GCM 认证失败)
        """
        if not _CRYPTO_AVAILABLE:
            # 降级:剥离前缀返回原文
            if data.startswith(b"PLAIN:"):
                return data[len(b"PLAIN:") :]
            return data
        if len(data) < _SALT_LEN + _NONCE_LEN:
            raise ValueError("密文长度不足,数据可能已损坏")
        salt = data[:_SALT_LEN]
        nonce = data[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
        ciphertext = data[_SALT_LEN + _NONCE_LEN :]
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        try:
            return aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise ValueError(f"解密失败(密码错误或数据被篡改): {e}") from e

    # ------------------------------------------------------------------
    # 文件级加密/解密
    # ------------------------------------------------------------------

    def encrypt_file(self, src_path: str, dst_path: str) -> None:
        """加密文件。

        Args:
            src_path: 明文源文件路径
            dst_path: 密文目标文件路径(自动创建父目录)
        """
        with open(src_path, "rb") as f:
            plain = f.read()
        cipher = self.encrypt(plain)
        os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
        with open(dst_path, "wb") as f:
            f.write(cipher)

    def decrypt_file(self, src_path: str, dst_path: str) -> None:
        """解密文件。

        Args:
            src_path: 密文源文件路径
            dst_path: 明文目标文件路径(自动创建父目录)
        """
        with open(src_path, "rb") as f:
            cipher = f.read()
        plain = self.decrypt(cipher)
        os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
        with open(dst_path, "wb") as f:
            f.write(plain)


def is_encryption_available() -> bool:
    """返回 cryptography 库是否可用。"""
    return _CRYPTO_AVAILABLE
