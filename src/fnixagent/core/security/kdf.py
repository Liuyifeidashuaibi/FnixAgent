"""
密钥派生 (KDF Manager)。

目标: 主密钥(KDK)仅用于派生子密钥,不直接加密业务数据。
     每个租户/每个文档类型使用独立派生密钥(HKDF-SHA256)。

设计:
  - HKDF-SHA256: 用 cryptography.hazmat.primitives.kdf.hkdf
  - 主密钥来源: 从 SecretManager 读取 fnixagent_KDK(缺失时启动生成并警告)
  - 缓存: functools.lru_cache(maxsize=100),key=(context, length)
  - 轮换: rotate_kdk() 设置新 KDK 并清空缓存
  - 安全: DerivedKey.key 在 __del__ 时尝试 zero out(ctypes memset)

可选项依赖: cryptography(已在 requirements.txt 中)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import ctypes
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 审计钩子(失败不影响主流程)
# ---------------------------------------------------------------------------


def _audit_kdf(action: str, detail: dict | None = None) -> None:
    """将密钥派生操作写入审计日志(不记录密钥本身,仅记录元信息)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class DerivedKey:
    """派生密钥。

    Attributes:
        key: 派生密钥字节(AES-256 用 32 字节)
        context: 派生上下文(如 "tenant:123:doc:word")
        derived_at: 派生时间(ISO 字符串)
        kdk_id: 主密钥 ID(不暴露主密钥本身)
    """

    key: bytes
    context: str
    derived_at: str
    kdk_id: str

    def __del__(self) -> None:
        """析构时尝试 zero out key 内存(尽力而为)。"""
        try:
            if self.key:
                # ctypes.memset 直接清零底层缓冲区
                buf = (ctypes.c_char * len(self.key)).from_buffer_copy(self.key)
                ctypes.memset(buf, 0, len(self.key))
                # bytes 是不可变对象,无法原地修改,只能确保临时副本被清零
        except Exception:
            pass


# ---------------------------------------------------------------------------
# KDFManager
# ---------------------------------------------------------------------------


class KDFManager:
    """HKDF-SHA256 密钥派生管理器。

    用法:
        mgr = KDFManager()  # 自动从 SecretManager 读取 fnixagent_KDK
        dk = mgr.derive_for_tenant("tenant-123", "doc:word")
        # 用 dk.key 做 AES-256-GCM 加密
        # 轮换主密钥
        mgr.rotate_kdk(new_kdk_bytes, new_kdk_id="v2")
    """

    # 默认 KDK 长度(32 字节 = 256 位)
    _DEFAULT_KDK_LENGTH = 32

    def __init__(
        self,
        kdk: bytes | None = None,
        kdk_id: str = "default",
    ) -> None:
        self._lock = threading.Lock()
        if kdk is not None:
            self._kdk = kdk
            self._kdk_id = kdk_id
        else:
            # 从 SecretManager 读取
            self._kdk, self._kdk_id = self._load_kdk_from_secrets()
        # 派生审计计数(用于监控)
        self._derive_count: int = 0

    # -- 公开接口 ----------------------------------------------------------

    def derive(
        self,
        context: str,
        length: int = 32,
    ) -> DerivedKey:
        """按上下文派生子密钥(同一 context+length 命中缓存)。

        Args:
            context: 派生上下文(如 "tenant:123:doc:word")
            length: 子密钥字节数(默认 32 = AES-256)

        Returns:
            DerivedKey(含 key/context/derived_at/kdk_id)
        """
        key = self._derive_cached(context, length)
        return DerivedKey(
            key=key,
            context=context,
            derived_at=datetime.utcnow().isoformat(),
            kdk_id=self._kdk_id,
        )

    def derive_for_tenant(
        self,
        tenant_id: str,
        purpose: str,
        length: int = 32,
    ) -> DerivedKey:
        """为租户派生专用密钥(context=f"tenant:{tenant_id}:{purpose}")。"""
        context = f"tenant:{tenant_id}:{purpose}"
        return self.derive(context, length=length)

    def rotate_kdk(self, new_kdk: bytes, new_kdk_id: str) -> bool:
        """轮换主密钥(清空缓存,旧派生密钥失效)。

        Args:
            new_kdk: 新主密钥(>= 32 字节)
            new_kdk_id: 新主密钥 ID(如 "v2")

        Returns:
            True=成功,False=新密钥不合法
        """
        if not new_kdk or len(new_kdk) < self._DEFAULT_KDK_LENGTH:
            logger.warning(
                "[kdf] 轮换失败: 新 KDK 长度 %d < %d",
                len(new_kdk) if new_kdk else 0,
                self._DEFAULT_KDK_LENGTH,
            )
            return False
        with self._lock:
            self._kdk = new_kdk
            self._kdk_id = new_kdk_id
            self._derive_count = 0
            # 清空 lru_cache
            self._derive_cached.cache_clear()
        _audit_kdf(
            "kdk.rotate",
            detail={
                "new_kdk_id": new_kdk_id,
                "kdk_length": len(new_kdk),
            },
        )
        logger.info("[kdf] 主密钥已轮换到 %s", new_kdk_id)
        return True

    def clear_cache(self) -> None:
        """清空派生缓存(不轮换主密钥)。"""
        with self._lock:
            self._derive_cached.cache_clear()

    def get_kdk_id(self) -> str:
        """返回当前主密钥 ID(不暴露主密钥本身)。"""
        return self._kdk_id

    # -- 内部:HKDF 派生 --------------------------------------------------

    @lru_cache(maxsize=100)
    def _derive_cached(self, context: str, length: int) -> bytes:
        """HKDF-SHA256 派生(lru_cache 缓存 100 条)。

        注意: 此方法是实例方法 + lru_cache,cache 绑定到实例。
        lru_cache 装饰器对实例方法的标准用法,Python 3.8+ 正常工作。
        """
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        except ImportError as exc:
            logger.error("[kdf] cryptography 未安装: %s", exc)
            # 降级: 用 hashlib 的 hkdf 实现(标准库,无第三方依赖)
            return self._hkdf_fallback(context, length)

        try:
            # HKDF-SHA256:salt=None(用零字节 salt),info=context
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=length,
                salt=None,
                info=context.encode("utf-8"),
            )
            key = hkdf.derive(self._kdk)
            with self._lock:
                self._derive_count += 1
            _audit_kdf(
                "kdk.derive",
                detail={
                    "context": context,
                    "length": length,
                    "kdk_id": self._kdk_id,
                },
            )
            return key
        except Exception:
            logger.exception("[kdf] HKDF 派生失败,使用 fallback")
            return self._hkdf_fallback(context, length)

    def _hkdf_fallback(self, context: str, length: int) -> bytes:
        """标准库 HKDF-SHA256 实现(cryptography 缺失时降级)。

        参考 RFC 5869:
          - Extract: PRK = HMAC-SHA256(salt, IKM)
          - Expand:  OKM = T(1) | T(2) | ... 截断到 length
        """
        import hashlib
        import hmac

        kdk = self._kdk
        salt = b"\x00" * 32  # HKDF salt 默认为零字节串,长度=哈希输出

        # Extract
        prk = hmac.new(salt, kdk, hashlib.sha256).digest()

        # Expand
        okm = b""
        t = b""
        info = context.encode("utf-8")
        while len(okm) < length:
            t = hmac.new(prk, t + info + bytes([len(okm) // 32 + 1]), hashlib.sha256).digest()
            okm += t
        with self._lock:
            self._derive_count += 1
        return okm[:length]

    # -- 内部:KDK 加载 ---------------------------------------------------

    def _load_kdk_from_secrets(self) -> tuple[bytes, str]:
        """从 SecretManager 读取 fnixagent_KDK。

        - 存在且合法: 返回 (kdk_bytes, "env")
        - 不存在:    生成 32 字节随机 KDK,记录 warning,返回 (kdk, "generated")
        """
        try:
            from fnixagent.core.security.secrets import get_secret_manager

            mgr = get_secret_manager()
            sv = mgr.get("KDK")
            if sv.value and len(sv.value) >= self._DEFAULT_KDK_LENGTH:
                # 优先按 hex 解码,失败则按 utf-8 编码
                try:
                    kdk = bytes.fromhex(sv.value)
                    if len(kdk) >= self._DEFAULT_KDK_LENGTH:
                        return kdk, "env"
                except ValueError:
                    pass
                kdk = sv.value.encode("utf-8")[:64]
                # 不足 32 字节则哈希派生
                if len(kdk) < self._DEFAULT_KDK_LENGTH:
                    import hashlib

                    kdk = hashlib.sha256(kdk).digest()
                return kdk, "env"
        except Exception as exc:
            logger.warning("[kdf] 从 SecretManager 加载 KDK 失败: %s", exc)

        # 生成随机 KDK(开发环境)
        kdk = os.urandom(self._DEFAULT_KDK_LENGTH)
        logger.warning("[kdf] fnixagent_KDK 未配置,生成临时 KDK(重启后失效,生产环境必须配置)")
        _audit_kdf(
            "kdk.generated",
            detail={
                "reason": "KDK not configured, generated ephemeral key",
            },
        )
        return kdk, "generated"


# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------


_manager_instance: KDFManager | None = None
_manager_lock = threading.Lock()


def get_kdf_manager() -> KDFManager:
    """获取全局 KDFManager 单例。"""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = KDFManager()
    return _manager_instance


def reset_kdf_manager() -> None:
    """重置单例(主要用于测试)。"""
    global _manager_instance
    with _manager_lock:
        _manager_instance = None
