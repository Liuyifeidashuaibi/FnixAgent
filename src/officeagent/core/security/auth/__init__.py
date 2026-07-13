"""
鉴权安全模块(Phase 0.4 安全规范对齐)。

子模块:
    - password:  Argon2id 密码哈希(替代 PBKDF2)
    - rsa_crypto: RSA-2048 密码传输加密
    - token:     双 Token 体系(Access 2h + Refresh 7d)
    - device:    设备指纹生成与校验
    - blacklist: Token 黑名单(Redis + 内存降级)
    - keystore:  服务端 RSA 密钥对单例

设计原则:
    - 所有模块支持「无 Redis / 无外部服务」降级运行(开发环境零依赖)
    - 密码哈希向后兼容 PBKDF2(老用户首次登录后自动升级到 Argon2id)
    - 接口签名稳定,不破坏现有 API 路由
"""
from officeagent.core.security.auth.password import (
    argon2_hash_password,
    argon2_verify_password,
    hash_password,           # 兼容入口(默认 Argon2id)
    verify_password,         # 兼容入口(自动识别 Argon2id / PBKDF2)
    needs_rehash,            # 检测旧哈希是否需升级
)
from officeagent.core.security.auth.rsa_crypto import (
    RSAKeyPair,
    rsa_decrypt_password,
)
from officeagent.core.security.auth.token import (
    TokenPair,
    create_token_pair,
    create_access_token,
    create_refresh_token,
    verify_token,
    decode_token_unsafe,
)
from officeagent.core.security.auth.device import (
    compute_device_fingerprint,
    verify_device_fingerprint,
)
from officeagent.core.security.auth.blacklist import (
    TokenBlacklist,
    get_blacklist,
)
from officeagent.core.security.auth.keystore import (
    get_server_keypair,
)

__all__ = [
    # password
    "argon2_hash_password",
    "argon2_verify_password",
    "hash_password",
    "verify_password",
    "needs_rehash",
    # rsa
    "RSAKeyPair",
    "rsa_decrypt_password",
    # token
    "TokenPair",
    "create_token_pair",
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "decode_token_unsafe",
    # device
    "compute_device_fingerprint",
    "verify_device_fingerprint",
    # blacklist
    "TokenBlacklist",
    "get_blacklist",
    # keystore
    "get_server_keypair",
]
