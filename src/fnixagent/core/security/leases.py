"""
密钥租约与 Cubbyhole(Lease Manager)- P2 安全模块。

参考 HashiCorp Vault 的 Lease + Cubbyhole 机制:
  - Secret 带租约,到期自动失效(惰性清理 + 主动清理)
  - Cubbyhole:为每次任务签发单次 token,绑定 task_id,任务结束撤销
  - 租约可续期(renew),可主动撤销(revoke)
  - 续期限制:总 TTL 不超过 max_ttl(默认 24 小时)

核心概念:
  - LeasedSecret:带过期时间的凭证副本,bound_to 绑定 task_id
  - CubbyholeToken:单次使用 token,用后立即失效(use_cubbyhole 后 used=True)
  - LeaseManager:统一管理租约生命周期,线程安全(threading.Lock)

与 SecretManager 集成:
  - lease(name) 时从 SecretManager 取值并包装为 LeasedSecret
  - 若未配置 SecretManager,lease() 抛 ValueError
  - Cubbyhole 不依赖 SecretManager,直接接收 secrets dict
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import os
import secrets as _secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fnixagent.core.security.secrets import SecretManager

logger = logging.getLogger(__name__)

# 默认持久化文件(可选)
_DEFAULT_LEASES_FILE = ".leases.json"
# 默认最大 TTL(24 小时)
_DEFAULT_MAX_TTL = 86400

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class LeaseExpiredError(Exception):
    """租约已过期或已撤销。"""

    pass

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class LeasedSecret:
    """带租约的凭证。

    Attributes:
        name:       凭证名
        value:      凭证值
        lease_id:   租约 ID(用于 read/renew/revoke)
        issued_at:  签发时间(unix timestamp)
        expires_at: 过期时间(unix timestamp)
        renewable:  是否可续期(默认 True)
        max_ttl:    最大 TTL(秒,默认 86400=24h)
        bound_to:   绑定的 task_id / user_id(None 表示不绑定)
    """

    name: str
    value: str
    lease_id: str
    issued_at: float
    expires_at: float
    renewable: bool = True
    max_ttl: int = _DEFAULT_MAX_TTL
    bound_to: str | None = None

@dataclass
class CubbyholeToken:
    """Cubbyhole 单次使用 token(参考 Vault Cubbyhole)。

    Attributes:
        token:      单次 token(secrets.token_urlsafe(32))
        task_id:    绑定的任务 ID
        secrets:    该 token 可访问的凭证集合
        expires_at: 过期时间(unix timestamp)
        used:       是否已使用(用后立即置 True)
    """

    token: str
    task_id: str
    secrets: dict[str, str] = field(default_factory=dict)
    expires_at: float = 0.0
    used: bool = False

# ---------------------------------------------------------------------------
# LeaseManager
# ---------------------------------------------------------------------------

class LeaseManager:
    """密钥租约管理器(线程安全)。

    用法:
        from fnixagent.core.security.secrets import get_secret_manager
        mgr = LeaseManager(secret_manager=get_secret_manager())
        # 签发租约
        ls = mgr.lease("JWT_SECRET", ttl_seconds=3600, bound_to="task-001")
        # 读取(过期抛 LeaseExpiredError)
        value = mgr.read(ls.lease_id)
        # 续期
        mgr.renew(ls.lease_id, ttl_seconds=1800)
        # 撤销某 task 的所有租约
        mgr.revoke_all("task-001")
        # Cubbyhole:单次 token
        ct = mgr.create_cubbyhole("task-002", {"API_KEY": "xxx"}, ttl=600)
        secrets_dict = mgr.use_cubbyhole(ct.token)  # 用后失效
    """

    def __init__(
        self,
        secret_manager: SecretManager | None = None,
        persist_path: str | None = None,
    ) -> None:
        self._secret_manager = secret_manager
        self._lock = threading.Lock()
        self._leases: dict[str, LeasedSecret] = {}
        self._cubbyholes: dict[str, CubbyholeToken] = {}
        self._persist_path = persist_path  # None 表示不持久化

    # -- 租约接口 ----------------------------------------------------------

    def lease(
        self,
        name: str,
        ttl_seconds: int = 3600,
        bound_to: str | None = None,
    ) -> LeasedSecret:
        """签发凭证租约(从 SecretManager 取值并包装)。

        Args:
            name:        凭证名(需在 SecretManager 中注册)
            ttl_seconds: 租约 TTL(秒,不超过 max_ttl)
            bound_to:    绑定的 task_id / user_id

        Returns:
            LeasedSecret(含 lease_id,用于后续 read/renew/revoke)

        Raises:
            ValueError: secret_manager 未配置或凭证不存在
        """
        if self._secret_manager is None:
            raise ValueError("secret_manager 未配置,无法签发租约")
        # 从 SecretManager 取值
        sv = self._secret_manager.get(name)
        if not sv.value:
            raise ValueError(f"凭证 {name} 不存在或为空")

        # 限制 TTL 不超过 max_ttl
        max_ttl = _DEFAULT_MAX_TTL
        actual_ttl = min(ttl_seconds, max_ttl)
        now = time.time()
        lease_id = _secrets.token_urlsafe(16)

        leased = LeasedSecret(
            name=name,
            value=sv.value,
            lease_id=lease_id,
            issued_at=now,
            expires_at=now + actual_ttl,
            renewable=True,
            max_ttl=max_ttl,
            bound_to=bound_to,
        )
        with self._lock:
            self._leases[lease_id] = leased
        logger.debug(
            "[leases] 签发租约 %s (name=%s, bound_to=%s, ttl=%ds)",
            lease_id,
            name,
            bound_to,
            actual_ttl,
        )
        return leased

    def read(self, lease_id: str) -> str:
        """读取租约对应的凭证值(过期抛 LeaseExpiredError)。"""
        with self._lock:
            leased = self._leases.get(lease_id)
        if leased is None:
            raise LeaseExpiredError(f"租约 {lease_id} 不存在或已撤销")
        now = time.time()
        if leased.expires_at <= now:
            # 惰性清理
            self._lazy_remove(lease_id)
            raise LeaseExpiredError(
                f"租约 {lease_id} 已过期(expires_at={leased.expires_at})",
            )
        return leased.value

    def renew(self, lease_id: str, ttl_seconds: int = 3600) -> LeasedSecret:
        """续期租约(总存活时间不超过 max_ttl)。

        Args:
            lease_id:    租约 ID
            ttl_seconds: 续期 TTL(秒)

        Returns:
            更新后的 LeasedSecret

        Raises:
            LeaseExpiredError: 租约已过期或不可续期
        """
        with self._lock:
            leased = self._leases.get(lease_id)
            if leased is None:
                raise LeaseExpiredError(f"租约 {lease_id} 不存在或已撤销")
            now = time.time()
            if leased.expires_at <= now:
                self._lazy_remove(lease_id)
                raise LeaseExpiredError(f"租约 {lease_id} 已过期,无法续期")
            if not leased.renewable:
                raise LeaseExpiredError(f"租约 {lease_id} 不可续期")
            # 计算续期后的过期时间:不超过 issued_at + max_ttl
            new_expires = now + ttl_seconds
            hard_limit = leased.issued_at + leased.max_ttl
            if new_expires > hard_limit:
                new_expires = hard_limit
            leased.expires_at = new_expires
            return leased

    def revoke(self, lease_id: str) -> bool:
        """主动撤销指定租约。"""
        with self._lock:
            if lease_id in self._leases:
                del self._leases[lease_id]
                logger.debug("[leases] 撤销租约 %s", lease_id)
                return True
            return False

    def revoke_all(self, bound_to: str) -> int:
        """撤销绑定到指定 task_id / user_id 的所有租约,返回撤销数。"""
        count = 0
        with self._lock:
            to_remove = [lid for lid, ls in self._leases.items() if ls.bound_to == bound_to]
            for lid in to_remove:
                del self._leases[lid]
                count += 1
        if count > 0:
            logger.info(
                "[leases] 批量撤销 %d 个租约(bound_to=%s)",
                count,
                bound_to,
            )
        return count

    def list_leases(self, bound_to: str | None = None) -> list[LeasedSecret]:
        """列出租约(bound_to 过滤;已过期的惰性清理)。"""
        now = time.time()
        with self._lock:
            # 惰性清理过期租约
            expired = [lid for lid, ls in self._leases.items() if ls.expires_at <= now]
            for lid in expired:
                del self._leases[lid]
            # 过滤返回
            result = [
                ls for ls in self._leases.values() if bound_to is None or ls.bound_to == bound_to
            ]
            return result

    def cleanup_expired(self) -> int:
        """主动清理所有过期租约,返回清理数。"""
        now = time.time()
        with self._lock:
            expired = [lid for lid, ls in self._leases.items() if ls.expires_at <= now]
            for lid in expired:
                del self._leases[lid]
            # 同时清理过期 cubbyhole
            expired_cb = [tok for tok, ct in self._cubbyholes.items() if ct.expires_at <= now]
            for tok in expired_cb:
                del self._cubbyholes[tok]
        total = len(expired) + len(expired_cb)
        if total > 0:
            logger.info(
                "[leases] 清理 %d 个过期租约 + %d 个过期 cubbyhole",
                len(expired),
                len(expired_cb),
            )
        return total

    # -- Cubbyhole 接口 ----------------------------------------------------

    def create_cubbyhole(
        self,
        task_id: str,
        secrets: dict[str, str],
        ttl: int = 3600,
    ) -> CubbyholeToken:
        """为指定任务创建 Cubbyhole(单次 token,绑定 task_id)。

        Args:
            task_id:  任务 ID
            secrets:  该 token 可访问的凭证集合
            ttl:      token 有效期(秒)

        Returns:
            CubbyholeToken(含 token,用于 use_cubbyhole)
        """
        token = _secrets.token_urlsafe(32)
        now = time.time()
        ct = CubbyholeToken(
            token=token,
            task_id=task_id,
            secrets=dict(secrets),  # 拷贝避免外部修改
            expires_at=now + ttl,
            used=False,
        )
        with self._lock:
            self._cubbyholes[token] = ct
        logger.debug(
            "[leases] 创建 Cubbyhole(task=%s, ttl=%ds, keys=%s)",
            task_id,
            ttl,
            list(secrets.keys()),
        )
        return ct

    def use_cubbyhole(self, token: str) -> dict[str, str]:
        """使用 Cubbyhole token 获取 secrets(单次使用,用后失效)。

        Raises:
            LeaseExpiredError: token 不存在/已使用/已过期
        """
        with self._lock:
            ct = self._cubbyholes.get(token)
            if ct is None:
                raise LeaseExpiredError("Cubbyhole token 不存在或已撤销")
            now = time.time()
            if ct.expires_at <= now:
                del self._cubbyholes[token]
                raise LeaseExpiredError("Cubbyhole token 已过期")
            if ct.used:
                raise LeaseExpiredError("Cubbyhole token 已被使用(单次有效)")
            # 标记已使用
            ct.used = True
            # 立即删除(单次使用)
            result = dict(ct.secrets)
            del self._cubbyholes[token]
            return result

    def revoke_cubbyhole(self, token: str) -> bool:
        """主动撤销 Cubbyhole token。"""
        with self._lock:
            if token in self._cubbyholes:
                del self._cubbyholes[token]
                logger.debug("[leases] 撤销 Cubbyhole token")
                return True
            return False

    # -- 持久化(可选) ----------------------------------------------------

    def save(self) -> bool:
        """持久化租约到 .leases.json(仅当 persist_path 已配置)。

        注意:Cubbyhole token 不持久化(单次使用,重启即失效)。
        """
        if self._persist_path is None:
            return False
        try:
            with self._lock:
                data = [asdict(ls) for ls in self._leases.values()]
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump({"leases": data}, f, ensure_ascii=False, indent=2)
            return True
        except OSError as exc:
            logger.warning("[leases] 持久化失败: %s", exc)
            return False

    def load(self) -> int:
        """从 .leases.json 恢复租约,返回恢复数量。"""
        if self._persist_path is None or not os.path.exists(self._persist_path):
            return 0
        try:
            with open(self._persist_path, encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            count = 0
            with self._lock:
                for item in data.get("leases", []):
                    ls = LeasedSecret(**item)
                    # 跳过已过期的
                    if ls.expires_at > now:
                        self._leases[ls.lease_id] = ls
                        count += 1
            logger.info("[leases] 恢复 %d 个租约", count)
            return count
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("[leases] 加载持久化文件失败: %s", exc)
            return 0

    # -- 内部辅助 ----------------------------------------------------------

    def _lazy_remove(self, lease_id: str) -> None:
        """惰性删除过期租约(调用方需持锁)。"""
        self._leases.pop(lease_id, None)

# ---------------------------------------------------------------------------
# 后台定时清理(可选,需调用方启动线程)
# ---------------------------------------------------------------------------

class LeaseCleaner:
    """租约后台清理器(定时调用 cleanup_expired)。

    用法:
        cleaner = LeaseCleaner(manager, interval=300)
        cleaner.start()  # 启动后台线程
        # ...
        cleaner.stop()   # 停止
    """

    def __init__(
        self,
        manager: LeaseManager,
        interval: int = 300,
    ) -> None:
        self._manager = manager
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """启动后台清理线程。"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="lease-cleaner",
        )
        self._thread.start()
        logger.info("[leases] 后台清理线程已启动(interval=%ds)", self._interval)

    def stop(self) -> None:
        """停止后台清理线程。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        """清理循环(异常吞掉,避免线程退出)。"""
        while not self._stop_event.wait(self._interval):
            try:
                self._manager.cleanup_expired()
            except Exception as exc:
                logger.warning("[leases] 后台清理异常: %s", exc)
