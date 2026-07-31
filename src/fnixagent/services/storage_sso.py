"""
SSO 配置 + 用户绑定存储层(Phase 2.3)。

提供两类存储:
    1. SSOConfigStore:管理 OAuth / SAML provider 配置(CRUD)
    2. SSOBindingStore:管理 provider_user_id ↔ local_user_id 绑定关系

设计要点:
    - 同 LDAP 一样,统一使用内存实现(SSO 配置不常变,重启后可通过 admin API 重建)
    - client_secret 在 to_dict() 时默认隐藏(避免泄露)
    - 绑定关系按 (provider_code, provider_user_id) 唯一索引
    - 一个本地用户可绑定多个 SSO provider(如同时绑定 GitHub + Google)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# SSO 配置 DTO
# ---------------------------------------------------------------------------


@dataclass
class SSOConfigDTO:
    """SSO provider 配置(支持 OAuth / SAML)。"""

    id: int
    provider_type: str  # "oauth" / "saml"
    provider_code: str  # "github" / "google" / "azure_ad" / 自定义
    name: str  # 显示名
    # OAuth 字段
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    scopes: list[str] = field(default_factory=list)
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    field_mapping: dict[str, str] = field(default_factory=dict)
    # SAML 字段
    sp_entity_id: str = ""
    acs_url: str = ""
    idp_entity_id: str = ""
    idp_sso_url: str = ""
    idp_x509_cert: str = ""
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    # 通用
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self, include_secret: bool = False) -> dict:
        """转换为 dict。

        Args:
            include_secret: 是否包含 client_secret / idp_x509_cert(敏感字段)
        """
        d = {
            "id": self.id,
            "provider_type": self.provider_type,
            "provider_code": self.provider_code,
            "name": self.name,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.provider_type == "oauth":
            d.update(
                {
                    "client_id": self.client_id,
                    "redirect_uri": self.redirect_uri,
                    "scopes": list(self.scopes),
                    "authorize_url": self.authorize_url,
                    "token_url": self.token_url,
                    "userinfo_url": self.userinfo_url,
                    "field_mapping": dict(self.field_mapping),
                }
            )
            if include_secret:
                d["client_secret"] = self.client_secret
        elif self.provider_type == "saml":
            d.update(
                {
                    "sp_entity_id": self.sp_entity_id,
                    "acs_url": self.acs_url,
                    "idp_entity_id": self.idp_entity_id,
                    "idp_sso_url": self.idp_sso_url,
                    "name_id_format": self.name_id_format,
                    "field_mapping": dict(self.field_mapping),
                }
            )
            if include_secret:
                d["idp_x509_cert"] = self.idp_x509_cert
        return d

    def to_oauth_config(self):
        """转换为 OAuthConfig(供 OAuthClient 使用)。"""
        from fnixagent.core.security.auth.oauth import OAuthConfig

        return OAuthConfig(
            id=self.id,
            provider_type=self.provider_type,
            provider_code=self.provider_code,
            name=self.name,
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scopes=list(self.scopes),
            authorize_url=self.authorize_url,
            token_url=self.token_url,
            userinfo_url=self.userinfo_url,
            field_mapping=dict(self.field_mapping),
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_saml_config(self):
        """转换为 SAMLConfig(供 SAMLClient 使用)。"""
        from fnixagent.core.security.auth.saml import SAMLConfig

        return SAMLConfig(
            id=self.id,
            provider_type=self.provider_type,
            provider_code=self.provider_code,
            name=self.name,
            sp_entity_id=self.sp_entity_id,
            acs_url=self.acs_url,
            idp_entity_id=self.idp_entity_id,
            idp_sso_url=self.idp_sso_url,
            idp_x509_cert=self.idp_x509_cert,
            name_id_format=self.name_id_format,
            field_mapping=dict(self.field_mapping),
            is_active=self.is_active,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# ---------------------------------------------------------------------------
# SSO 绑定 DTO
# ---------------------------------------------------------------------------


@dataclass
class SSOBindingDTO:
    """SSO 用户绑定关系(provider_user_id ↔ local_user_id)。"""

    id: int
    user_id: int
    provider_code: str  # github / google / azure_ad / 自定义
    provider_user_id: str  # OAuth id 或 SAML name_id
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "provider_code": self.provider_code,
            "provider_user_id": self.provider_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# 内存 SSO 配置存储
# ---------------------------------------------------------------------------


class InMemorySSOConfigStore:
    """内存 SSO 配置存储。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._configs: dict[int, SSOConfigDTO] = {}
        self._next_id = 1

    def list_configs(
        self, include_inactive: bool = True, provider_type: str | None = None
    ) -> list[SSOConfigDTO]:
        with self._lock:
            result = list(self._configs.values())
            if not include_inactive:
                result = [c for c in result if c.is_active]
            if provider_type:
                result = [c for c in result if c.provider_type == provider_type]
            return sorted(result, key=lambda x: (x.is_active, -x.id), reverse=True)

    def get_config(self, config_id: int) -> SSOConfigDTO | None:
        with self._lock:
            return self._configs.get(config_id)

    def get_by_code(
        self, provider_code: str, provider_type: str | None = None
    ) -> SSOConfigDTO | None:
        """按 provider_code 查找 active 配置。"""
        with self._lock:
            for c in self._configs.values():
                if c.provider_code == provider_code and c.is_active:
                    if provider_type is None or c.provider_type == provider_type:
                        return c
            return None

    def create_config(self, **kwargs) -> SSOConfigDTO:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
            now = datetime.utcnow()
            cfg = SSOConfigDTO(
                id=cid,
                provider_type=kwargs["provider_type"],
                provider_code=kwargs["provider_code"],
                name=kwargs["name"],
                client_id=kwargs.get("client_id", ""),
                client_secret=kwargs.get("client_secret", ""),
                redirect_uri=kwargs.get("redirect_uri", ""),
                scopes=list(kwargs.get("scopes", [])),
                authorize_url=kwargs.get("authorize_url", ""),
                token_url=kwargs.get("token_url", ""),
                userinfo_url=kwargs.get("userinfo_url", ""),
                field_mapping=dict(kwargs.get("field_mapping", {})),
                sp_entity_id=kwargs.get("sp_entity_id", ""),
                acs_url=kwargs.get("acs_url", ""),
                idp_entity_id=kwargs.get("idp_entity_id", ""),
                idp_sso_url=kwargs.get("idp_sso_url", ""),
                idp_x509_cert=kwargs.get("idp_x509_cert", ""),
                name_id_format=kwargs.get(
                    "name_id_format",
                    "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
                ),
                is_active=kwargs.get("is_active", True),
                created_at=now,
                updated_at=now,
            )
            self._configs[cid] = cfg
            return cfg

    def update_config(self, config_id: int, **kwargs) -> SSOConfigDTO | None:
        with self._lock:
            cfg = self._configs.get(config_id)
            if not cfg:
                return None
            for k in (
                "provider_type",
                "provider_code",
                "name",
                "client_id",
                "client_secret",
                "redirect_uri",
                "scopes",
                "authorize_url",
                "token_url",
                "userinfo_url",
                "field_mapping",
                "sp_entity_id",
                "acs_url",
                "idp_entity_id",
                "idp_sso_url",
                "idp_x509_cert",
                "name_id_format",
                "is_active",
            ):
                if k in kwargs and kwargs[k] is not None:
                    if k == "scopes":
                        setattr(cfg, k, list(kwargs[k]))
                    elif k == "field_mapping":
                        setattr(cfg, k, dict(kwargs[k]))
                    else:
                        setattr(cfg, k, kwargs[k])
            cfg.updated_at = datetime.utcnow()
            return cfg

    def delete_config(self, config_id: int) -> bool:
        with self._lock:
            if config_id not in self._configs:
                return False
            del self._configs[config_id]
            return True


# ---------------------------------------------------------------------------
# 内存 SSO 绑定存储
# ---------------------------------------------------------------------------


class InMemorySSOBindingStore:
    """内存 SSO 绑定关系存储。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._bindings: dict[int, SSOBindingDTO] = {}
        self._next_id = 1
        # 索引:(provider_code, provider_user_id) -> binding_id
        self._provider_idx: dict[tuple[str, str], int] = {}
        # 索引:user_id -> [binding_id, ...]
        self._user_idx: dict[int, list[int]] = {}

    def create(self, user_id: int, provider_code: str, provider_user_id: str) -> SSOBindingDTO:
        """创建绑定。若已存在(provider + provider_user_id),返回已有绑定。"""
        with self._lock:
            key = (provider_code, provider_user_id)
            existing_id = self._provider_idx.get(key)
            if existing_id is not None:
                return self._bindings[existing_id]

            bid = self._next_id
            self._next_id += 1
            binding = SSOBindingDTO(
                id=bid,
                user_id=user_id,
                provider_code=provider_code,
                provider_user_id=provider_user_id,
                created_at=datetime.utcnow(),
            )
            self._bindings[bid] = binding
            self._provider_idx[key] = bid
            self._user_idx.setdefault(user_id, []).append(bid)
            return binding

    def get_by_provider(self, provider_code: str, provider_user_id: str) -> SSOBindingDTO | None:
        with self._lock:
            bid = self._provider_idx.get((provider_code, provider_user_id))
            return self._bindings.get(bid) if bid else None

    def list_by_user(self, user_id: int) -> list[SSOBindingDTO]:
        with self._lock:
            bids = self._user_idx.get(user_id, [])
            return [self._bindings[bid] for bid in bids if bid in self._bindings]

    def delete(self, binding_id: int) -> bool:
        with self._lock:
            binding = self._bindings.get(binding_id)
            if not binding:
                return False
            key = (binding.provider_code, binding.provider_user_id)
            self._provider_idx.pop(key, None)
            user_binds = self._user_idx.get(binding.user_id, [])
            if binding_id in user_binds:
                user_binds.remove(binding_id)
            del self._bindings[binding_id]
            return True

    def delete_by_user(self, user_id: int) -> int:
        """删除用户的所有绑定,返回删除条数。"""
        with self._lock:
            bids = self._user_idx.get(user_id, [])
            count = 0
            for bid in list(bids):
                binding = self._bindings.get(bid)
                if binding:
                    self._provider_idx.pop((binding.provider_code, binding.provider_user_id), None)
                    del self._bindings[bid]
                    count += 1
            self._user_idx.pop(user_id, None)
            return count


# ---------------------------------------------------------------------------
# 工厂单例
# ---------------------------------------------------------------------------


_sso_config_store: InMemorySSOConfigStore | None = None
_sso_config_store_lock = threading.Lock()

_sso_binding_store: InMemorySSOBindingStore | None = None
_sso_binding_store_lock = threading.Lock()


def get_sso_config_store() -> InMemorySSOConfigStore:
    """获取 SSO 配置存储单例(内存实现)。"""
    global _sso_config_store
    if _sso_config_store is None:
        with _sso_config_store_lock:
            if _sso_config_store is None:
                _sso_config_store = InMemorySSOConfigStore()
    return _sso_config_store


def reset_sso_config_store() -> None:
    """重置配置存储单例(测试用)。"""
    global _sso_config_store
    with _sso_config_store_lock:
        _sso_config_store = None


def get_sso_binding_store() -> InMemorySSOBindingStore:
    """获取 SSO 绑定存储单例(内存实现)。"""
    global _sso_binding_store
    if _sso_binding_store is None:
        with _sso_binding_store_lock:
            if _sso_binding_store is None:
                _sso_binding_store = InMemorySSOBindingStore()
    return _sso_binding_store


def reset_sso_binding_store() -> None:
    """重置绑定存储单例(测试用)。"""
    global _sso_binding_store
    with _sso_binding_store_lock:
        _sso_binding_store = None
