"""
服务端 RSA 密钥对单例(Phase 0.4)。

管理服务端 RSA-2048 密钥对的生命周期:
    - 开发环境:进程启动时生成,重启失效(用户需重新获取公钥)
    - 生产环境:从 RSA_PRIVATE_KEY_PATH 环境变量加载持久化密钥

密钥对在首次访问时懒加载,后续全局复用(线程安全)。
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from officeagent.core.security.auth.rsa_crypto import (
    RSAKeyPair,
    generate_keypair,
    load_keypair_from_file,
)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------


_keypair_instance: Optional[RSAKeyPair] = None
_keypair_lock = threading.Lock()


def get_server_keypair() -> RSAKeyPair:
    """获取服务端 RSA 密钥对单例(懒加载)。

    优先级:
        1. 环境变量 RSA_PRIVATE_KEY_PATH 指向的 PEM 文件(生产环境持久化)
        2. 进程内生成(开发环境,重启失效)

    Returns:
        RSAKeyPair 实例
    """
    global _keypair_instance
    if _keypair_instance is None:
        with _keypair_lock:
            if _keypair_instance is None:
                _keypair_instance = _load_or_generate()

    return _keypair_instance


def reset_server_keypair() -> None:
    """重置密钥对单例(用于测试)。

    重置后,下次调用 get_server_keypair() 会重新加载/生成。
    """
    global _keypair_instance
    with _keypair_lock:
        _keypair_instance = None


def _load_or_generate() -> RSAKeyPair:
    """从文件加载或生成新密钥对。"""
    # 1. 尝试从环境变量加载持久化密钥
    key_path = os.getenv("RSA_PRIVATE_KEY_PATH", "")
    if key_path and os.path.exists(key_path):
        try:
            return load_keypair_from_file(key_path)
        except Exception as e:
            print(f"[keystore] 从 {key_path} 加载密钥对失败,改为生成新密钥: {e}")

    # 2. 生成新密钥对(开发环境默认路径)
    print("[keystore] 生成新的 RSA-2048 密钥对(重启后失效)")
    return generate_keypair(key_size=2048)
