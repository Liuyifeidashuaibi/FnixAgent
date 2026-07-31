"""
RSA-2048 密码传输加密(Phase 0.4)。

实现「客户端用服务端公钥加密密码 → 服务端私钥解密」的传输链路,
确保即使 HTTPS 被中间人解密(如企业代理)也无法获取密码明文。

设计:
    - 服务端启动时生成 RSA-2048 密钥对(或从持久化加载)
    - 客户端通过 GET /auth/pubkey 获取公钥(PEM 格式)
    - 客户端用公钥加密密码(OAEP padding,防选择性密文攻击)
    - 服务端用私钥解密

密钥管理:
    - 开发环境:进程内生成,重启失效(用户需重新登录)
    - 生产环境:从环境变量 RSA_PRIVATE_KEY_PATH 加载持久化密钥
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

# cryptography 在 Phase 0.2 已加入 requirements.txt
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
    from cryptography.hazmat.primitives.asymmetric import rsa

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False


# ---------------------------------------------------------------------------
# RSA 密钥对容器
# ---------------------------------------------------------------------------


@dataclass
class RSAKeyPair:
    """RSA-2048 密钥对(PEM 编码)。"""

    private_pem: str  # PKCS#8 PEM(含头尾)
    public_pem: str  # SubjectPublicKeyInfo PEM
    key_size: int = 2048

    def decrypt(self, ciphertext_b64: str) -> str:
        """用私钥解密客户端发来的 Base64 密文,返回密码明文。

        Args:
            ciphertext_b64: Base64 编码的密文(客户端用公钥 + OAEP 加密)

        Returns:
            密码明文

        Raises:
            ValueError: 解密失败
        """
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography 库不可用")

        private_key = serialization.load_pem_private_key(
            self.private_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )

        ciphertext = base64.b64decode(ciphertext_b64)

        plaintext = private_key.decrypt(
            ciphertext,
            rsa_padding.OAEP(
                mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# 密钥对生成
# ---------------------------------------------------------------------------


def generate_keypair(key_size: int = 2048) -> RSAKeyPair:
    """生成新的 RSA 密钥对。"""
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography 库不可用,无法生成 RSA 密钥对")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend(),
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    return RSAKeyPair(
        private_pem=private_pem,
        public_pem=public_pem,
        key_size=key_size,
    )


def load_keypair_from_file(path: str) -> RSAKeyPair:
    """从 PEM 文件加载密钥对(生产环境持久化)。"""
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography 库不可用")

    with open(path, "rb") as f:
        private_pem = f.read().decode("utf-8")

    private_key = serialization.load_pem_private_key(
        private_pem.encode("utf-8"),
        password=None,
        backend=default_backend(),
    )

    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    return RSAKeyPair(
        private_pem=private_pem,
        public_pem=public_pem,
        key_size=private_key.key_size,
    )


# ---------------------------------------------------------------------------
# 密码解密(统一入口,供 auth router 调用)
# ---------------------------------------------------------------------------


def rsa_decrypt_password(ciphertext_b64: str, keypair: RSAKeyPair) -> str:
    """解密客户端发来的 RSA 加密密码。

    Args:
        ciphertext_b64: Base64 编码的密文
        keypair: 服务端 RSA 密钥对

    Returns:
        密码明文

    Raises:
        ValueError: 解密失败(密文损坏 / 私钥不匹配 / 库不可用)
    """
    if not ciphertext_b64:
        raise ValueError("密文为空")

    try:
        return keypair.decrypt(ciphertext_b64)
    except Exception as e:
        raise ValueError(f"RSA 解密失败: {e}") from e


def is_rsa_available() -> bool:
    """返回 cryptography 库是否可用。"""
    return _HAS_CRYPTO
