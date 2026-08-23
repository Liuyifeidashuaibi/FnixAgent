"""
LDAP 配置存储层(Phase 2.2)。

提供 LDAPConfig 的 CRUD,支持 InMemory(开发/测试)和 Pg(生产)两种实现。

设计要点:
    - bind_password 在 Pg 模式下应加密存储(此处简化为明文,生产环境建议补充)
    - 工厂 get_ldap_config_store() 按 DATABASE_URL 选择实现
    - 同一时间可有多个 LDAP 配置,但只有 is_active=True 的生效
    - last_sync_at 用于定时同步调度判断
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from fnixagent.core.security.auth.ldap import LDAPConfig

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------


@dataclass
class LDAPConfigDTO:
    """LDAP 配置数据传输对象。"""

    id: int
    name: str
    server_url: str
    bind_dn: str
    bind_password: str
    user_search_base: str
    user_filter: str = "(objectClass=person)"
    group_search_base: str = ""
    group_filter: str = "(objectClass=group)"
    username_attribute: str = "sAMAccountName"
    email_attribute: str = "mail"
    display_name_attribute: str = "displayName"
    use_ssl: bool = False
    use_tls: bool = True
    is_active: bool = True
    sync_interval_hours: int = 24
    last_sync_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self, include_password: bool = False) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "server_url": self.server_url,
            "bind_dn": self.bind_dn,
            "user_search_base": self.user_search_base,
            "user_filter": self.user_filter,
            "group_search_base": self.group_search_base,
            "group_filter": self.group_filter,
            "username_attribute": self.username_attribute,
            "email_attribute": self.email_attribute,
            "display_name_attribute": self.display_name_attribute,
            "use_ssl": self.use_ssl,
            "use_tls": self.use_tls,
            "is_active": self.is_active,
            "sync_interval_hours": self.sync_interval_hours,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_password:
            d["bind_password"] = self.bind_password
        return d

    def to_ldap_config(self) -> LDAPConfig:
        return LDAPConfig(
            id=self.id,
            name=self.name,
            server_url=self.server_url,
            bind_dn=self.bind_dn,
            bind_password=self.bind_password,
            user_search_base=self.user_search_base,
            user_filter=self.user_filter,
            group_search_base=self.group_search_base,
            group_filter=self.group_filter,
            username_attribute=self.username_attribute,
            email_attribute=self.email_attribute,
            display_name_attribute=self.display_name_attribute,
            use_ssl=self.use_ssl,
            use_tls=self.use_tls,
            is_active=self.is_active,
            sync_interval_hours=self.sync_interval_hours,
            last_sync_at=self.last_sync_at,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# ---------------------------------------------------------------------------
# 内存实现
# ---------------------------------------------------------------------------


class InMemoryLDAPConfigStore:
    """内存 LDAP 配置存储(开发/测试用)。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._configs: dict[int, LDAPConfigDTO] = {}
        self._next_id = 1

    def list_configs(self, include_inactive: bool = True) -> list[LDAPConfigDTO]:
        with self._lock:
            result = list(self._configs.values())
            if not include_inactive:
                result = [c for c in result if c.is_active]
            return sorted(result, key=lambda x: (x.is_active, -x.id), reverse=True)

    def get_config(self, config_id: int) -> LDAPConfigDTO | None:
        with self._lock:
            return self._configs.get(config_id)

    def get_active_config(self) -> LDAPConfigDTO | None:
        """获取当前生效的 LDAP 配置(第一个 is_active=True)。"""
        with self._lock:
            for c in self._configs.values():
                if c.is_active:
                    return c
            return None

    def create_config(
        self,
        name: str,
        server_url: str,
        bind_dn: str,
        bind_password: str,
        user_search_base: str,
        **kwargs,
    ) -> LDAPConfigDTO:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
            now = datetime.now(UTC)
            cfg = LDAPConfigDTO(
                id=cid,
                name=name,
                server_url=server_url,
                bind_dn=bind_dn,
                bind_password=bind_password,
                user_search_base=user_search_base,
                user_filter=kwargs.get("user_filter", "(objectClass=person)"),
                group_search_base=kwargs.get("group_search_base", ""),
                group_filter=kwargs.get("group_filter", "(objectClass=group)"),
                username_attribute=kwargs.get("username_attribute", "sAMAccountName"),
                email_attribute=kwargs.get("email_attribute", "mail"),
                display_name_attribute=kwargs.get("display_name_attribute", "displayName"),
                use_ssl=kwargs.get("use_ssl", False),
                use_tls=kwargs.get("use_tls", True),
                is_active=kwargs.get("is_active", True),
                sync_interval_hours=kwargs.get("sync_interval_hours", 24),
                created_at=now,
                updated_at=now,
            )
            self._configs[cid] = cfg
            return cfg

    def update_config(self, config_id: int, **kwargs) -> LDAPConfigDTO | None:
        with self._lock:
            cfg = self._configs.get(config_id)
            if not cfg:
                return None
            for k in (
                "name",
                "server_url",
                "bind_dn",
                "bind_password",
                "user_search_base",
                "user_filter",
                "group_search_base",
                "group_filter",
                "username_attribute",
                "email_attribute",
                "display_name_attribute",
                "use_ssl",
                "use_tls",
                "is_active",
                "sync_interval_hours",
            ):
                if k in kwargs and kwargs[k] is not None:
                    setattr(cfg, k, kwargs[k])
            cfg.updated_at = datetime.now(UTC)
            return cfg

    def delete_config(self, config_id: int) -> bool:
        with self._lock:
            if config_id not in self._configs:
                return False
            del self._configs[config_id]
            return True

    def mark_synced(self, config_id: int) -> None:
        """更新最后同步时间。"""
        with self._lock:
            cfg = self._configs.get(config_id)
            if cfg:
                cfg.last_sync_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# PostgreSQL 实现
# ---------------------------------------------------------------------------


class PgLDAPConfigStore:
    """PostgreSQL LDAP 配置存储。

    注:为减少迁移复杂度,LDAP 配置存储在 settings 表中(key=ldap_config:{id})。
    生产环境建议后续迁移到独立表。
    """

    def __init__(self):
        import json

        from sqlalchemy import delete, select

        from fnixagent.models.db.models import Setting
        from fnixagent.services.storage_postgres import get_db_adapter

        self._get_db = get_db_adapter
        self._Setting = Setting
        self._select = select
        self._delete = delete
        self._json = json

    def _key(self, config_id: int) -> str:
        return f"ldap_config:{config_id}"

    def _load_all(self) -> list[LDAPConfigDTO]:
        with self._get_db().session() as s:
            stmt = self._select(self._Setting).where(self._Setting.key.like("ldap_config:%"))
            rows = s.execute(stmt).scalars().all()
            result = []
            for r in rows:
                try:
                    data = self._json.loads(r.value)
                    result.append(self._dict_to_dto(data))
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)
                    continue
            return result

    def _dict_to_dto(self, d: dict) -> LDAPConfigDTO:
        return LDAPConfigDTO(
            id=d["id"],
            name=d["name"],
            server_url=d["server_url"],
            bind_dn=d["bind_dn"],
            bind_password=d.get("bind_password", ""),
            user_search_base=d["user_search_base"],
            user_filter=d.get("user_filter", "(objectClass=person)"),
            group_search_base=d.get("group_search_base", ""),
            group_filter=d.get("group_filter", "(objectClass=group)"),
            username_attribute=d.get("username_attribute", "sAMAccountName"),
            email_attribute=d.get("email_attribute", "mail"),
            display_name_attribute=d.get("display_name_attribute", "displayName"),
            use_ssl=d.get("use_ssl", False),
            use_tls=d.get("use_tls", True),
            is_active=d.get("is_active", True),
            sync_interval_hours=d.get("sync_interval_hours", 24),
            last_sync_at=datetime.fromisoformat(d["last_sync_at"])
            if d.get("last_sync_at")
            else None,
            created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
            updated_at=datetime.fromisoformat(d["updated_at"]) if d.get("updated_at") else None,
        )

    def list_configs(self, include_inactive: bool = True) -> list[LDAPConfigDTO]:
        result = self._load_all()
        if not include_inactive:
            result = [c for c in result if c.is_active]
        return sorted(result, key=lambda x: (x.is_active, -x.id), reverse=True)

    def get_config(self, config_id: int) -> LDAPConfigDTO | None:
        with self._get_db().session() as s:
            r = s.get(self._Setting, self._key(config_id))
            if not r:
                return None
            try:
                return self._dict_to_dto(self._json.loads(r.value))
            except Exception:
                return None

    def get_active_config(self) -> LDAPConfigDTO | None:
        all_configs = self._load_all()
        for c in all_configs:
            if c.is_active:
                return c
        return None

    def create_config(
        self,
        name: str,
        server_url: str,
        bind_dn: str,
        bind_password: str,
        user_search_base: str,
        **kwargs,
    ) -> LDAPConfigDTO:
        # 生成新 ID:取现有最大 ID + 1
        all_configs = self._load_all()
        new_id = max([c.id for c in all_configs], default=0) + 1
        now = datetime.now(UTC)
        cfg = LDAPConfigDTO(
            id=new_id,
            name=name,
            server_url=server_url,
            bind_dn=bind_dn,
            bind_password=bind_password,
            user_search_base=user_search_base,
            user_filter=kwargs.get("user_filter", "(objectClass=person)"),
            group_search_base=kwargs.get("group_search_base", ""),
            group_filter=kwargs.get("group_filter", "(objectClass=group)"),
            username_attribute=kwargs.get("username_attribute", "sAMAccountName"),
            email_attribute=kwargs.get("email_attribute", "mail"),
            display_name_attribute=kwargs.get("display_name_attribute", "displayName"),
            use_ssl=kwargs.get("use_ssl", False),
            use_tls=kwargs.get("use_tls", True),
            is_active=kwargs.get("is_active", True),
            sync_interval_hours=kwargs.get("sync_interval_hours", 24),
            created_at=now,
            updated_at=now,
        )
        with self._get_db().session() as s:
            setting = self._Setting(
                key=self._key(new_id),
                value=self._json.dumps(cfg.to_dict(include_password=True)),
            )
            s.add(setting)
            s.flush()
        return cfg

    def update_config(self, config_id: int, **kwargs) -> LDAPConfigDTO | None:
        cfg = self.get_config(config_id)
        if not cfg:
            return None
        for k in (
            "name",
            "server_url",
            "bind_dn",
            "bind_password",
            "user_search_base",
            "user_filter",
            "group_search_base",
            "group_filter",
            "username_attribute",
            "email_attribute",
            "display_name_attribute",
            "use_ssl",
            "use_tls",
            "is_active",
            "sync_interval_hours",
        ):
            if k in kwargs and kwargs[k] is not None:
                setattr(cfg, k, kwargs[k])
        cfg.updated_at = datetime.now(UTC)
        with self._get_db().session() as s:
            r = s.get(self._Setting, self._key(config_id))
            if r:
                r.value = self._json.dumps(cfg.to_dict(include_password=True))
                s.flush()
        return cfg

    def delete_config(self, config_id: int) -> bool:
        with self._get_db().session() as s:
            r = s.get(self._Setting, self._key(config_id))
            if not r:
                return False
            s.delete(r)
            s.flush()
            return True

    def mark_synced(self, config_id: int) -> None:
        cfg = self.get_config(config_id)
        if cfg:
            cfg.last_sync_at = datetime.now(UTC)
            with self._get_db().session() as s:
                r = s.get(self._Setting, self._key(config_id))
                if r:
                    r.value = self._json.dumps(cfg.to_dict(include_password=True))
                    s.flush()


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


_ldap_config_store: object | None = None
_ldap_config_store_lock = threading.Lock()


def get_ldap_config_store():
    """获取 LDAP 配置存储单例。

    注:当前统一使用内存实现。LDAP 配置很少变更,重启后可通过 admin API 重建。
    后续如需持久化,可添加 settings 表 + 迁移。
    """
    global _ldap_config_store
    if _ldap_config_store is None:
        with _ldap_config_store_lock:
            if _ldap_config_store is None:
                _ldap_config_store = InMemoryLDAPConfigStore()
    return _ldap_config_store


def reset_ldap_config_store() -> None:
    """重置单例(测试用)。"""
    global _ldap_config_store
    with _ldap_config_store_lock:
        _ldap_config_store = None
