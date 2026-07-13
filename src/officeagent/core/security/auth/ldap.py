"""
LDAP/AD 域集成(Phase 2.2)。

提供:
    1. LDAP 服务器连接管理(支持 SSL/TLS)
    2. 用户认证(bind with user credentials)
    3. 用户/组搜索(可配置 filter 与属性映射)
    4. LDAP 用户同步到本地(按邮箱映射,不存在则创建)
    5. LDAP 组同步到部门(可选)

设计要点:
    - ldap3 为延迟导入,未安装时返回明确错误(不阻断启动)
    - LDAP 配置由 storage_ldap 管理,此处只负责协议交互
    - 认证失败/连接错误统一抛 LDAPError,由调用方决定 HTTP 响应
    - 用户同步幂等:按邮箱查找本地用户,存在则更新,不存在则创建
    - 同步时为 LDAP 用户打上 profile.source=ldap 标记,便于追溯

依赖:ldap3>=2.9
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from officeagent.services.storage import get_user_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class LDAPError(Exception):
    """LDAP 操作异常基类。"""


class LDAPConnectionError(LDAPError):
    """连接 LDAP 服务器失败。"""


class LDAPAuthenticationError(LDAPError):
    """LDAP 认证失败(用户名/密码错误)。"""


class LDAPNotInstalledError(LDAPError):
    """ldap3 库未安装。"""


# ---------------------------------------------------------------------------
# 配置 DTO
# ---------------------------------------------------------------------------


@dataclass
class LDAPConfig:
    """LDAP 服务器配置(与 storage_ldap.LDAPConfigDTO 对应)。"""
    id: int
    name: str
    server_url: str                      # ldap://host:389 或 ldaps://host:636
    bind_dn: str                         # 服务账号 DN(用于搜索用户)
    bind_password: str                   # 服务账号密码
    user_search_base: str                # 用户搜索基准 DN
    user_filter: str = "(objectClass=person)"  # 用户过滤器
    group_search_base: str = ""          # 组搜索基准 DN(可选)
    group_filter: str = "(objectClass=group)"  # 组过滤器
    username_attribute: str = "sAMAccountName"  # AD 默认;OpenLDAP 可为 uid
    email_attribute: str = "mail"
    display_name_attribute: str = "displayName"
    use_ssl: bool = False                # ldaps://
    use_tls: bool = True                 # STARTTLS
    is_active: bool = True
    sync_interval_hours: int = 24
    last_sync_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, d: dict) -> "LDAPConfig":
        return cls(
            id=d["id"],
            name=d["name"],
            server_url=d["server_url"],
            bind_dn=d["bind_dn"],
            bind_password=d["bind_password"],
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
            last_sync_at=d.get("last_sync_at"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


@dataclass
class LDAPUser:
    """LDAP 用户查询结果。"""
    dn: str
    username: str
    email: str
    display_name: str
    attributes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LDAP 客户端
# ---------------------------------------------------------------------------


class LDAPClient:
    """LDAP 客户端(封装 ldap3)。

    用法:
        client = LDAPClient(config)
        if client.test_connection():
            user = client.authenticate("alice", "password")
            local_user = client.sync_user_to_local(user)
    """

    def __init__(self, config: LDAPConfig):
        self.config = config
        self._server = None
        self._connection = None

    def _import_ldap3(self):
        """延迟导入 ldap3,未安装时抛 LDAPNotInstalledError。"""
        try:
            import ldap3
            return ldap3
        except ImportError as e:
            raise LDAPNotInstalledError(
                "ldap3 库未安装,请运行 pip install ldap3"
            ) from e

    def _build_server(self):
        """构建 ldap3 Server 对象。"""
        ldap3 = self._import_ldap3()
        cfg = self.config
        return ldap3.Server(
            cfg.server_url,
            use_ssl=cfg.use_ssl,
            tls=ldap3.Tls() if cfg.use_tls else None,
            get_info=ldap3.ALL,
        )

    def _bind(self, username: str, password: str) -> Any:
        """建立绑定连接,返回 Connection。"""
        ldap3 = self._import_ldap3()
        server = self._build_server()
        conn = ldap3.Connection(
            server,
            user=username,
            password=password,
            auto_bind=ldap3.AUTO_BIND_TLS_BEFORE_BIND if self.config.use_tls else ldap3.AUTO_BIND_NO_TLS,
            read_only=True,
        )
        if not conn.bind():
            raise LDAPAuthenticationError(f"LDAP bind 失败: {conn.result}")
        return conn

    def test_connection(self) -> bool:
        """测试连接 + 服务账号绑定。返回 True/False。

        注:LDAPNotInstalledError 会抛出(库未安装是配置问题,不应静默)。
        """
        try:
            conn = self._bind(self.config.bind_dn, self.config.bind_password)
            conn.unbind()
            return True
        except LDAPNotInstalledError:
            raise  # 库未安装是配置问题,应该抛出
        except LDAPError as e:
            logger.warning("LDAP 连接测试失败: %s", e)
            return False
        except Exception as e:
            logger.warning("LDAP 连接测试异常: %s", e)
            return False

    def authenticate(self, username: str, password: str) -> Optional[LDAPUser]:
        """用用户凭据绑定 LDAP,成功则返回 LDAPUser。

        流程:
            1. 用服务账号 bind,搜索用户 DN
            2. 用找到的 DN + 用户密码重新 bind
            3. 返回用户属性
        """
        if not password:
            raise LDAPAuthenticationError("密码不能为空")

        # 1. 服务账号 bind 搜索用户
        admin_conn = self._bind(self.config.bind_dn, self.config.bind_password)
        try:
            cfg = self.config
            search_filter = cfg.user_filter
            # 兼容 AD:在 filter 中加入 username 条件
            if "sAMAccountName" in cfg.username_attribute:
                search_filter = f"(&{cfg.user_filter}({cfg.username_attribute}={username}))"
            else:
                search_filter = f"(&{cfg.user_filter}({cfg.username_attribute}={username}))"

            admin_conn.search(
                search_base=cfg.user_search_base,
                search_filter=search_filter,
                attributes=[cfg.username_attribute, cfg.email_attribute,
                            cfg.display_name_attribute, "dn"],
            )

            if not admin_conn.entries:
                return None

            entry = admin_conn.entries[0]
            user_dn = entry.entry_dn
            email = str(entry[cfg.email_attribute].value) if cfg.email_attribute in entry else ""
            display_name = str(entry[cfg.display_name_attribute].value) if cfg.display_name_attribute in entry else username
        finally:
            admin_conn.unbind()

        # 2. 用用户 DN + 密码重新 bind 验证
        try:
            user_conn = self._bind(user_dn, password)
            user_conn.unbind()
        except LDAPAuthenticationError:
            return None

        return LDAPUser(
            dn=user_dn,
            username=username,
            email=email,
            display_name=display_name,
        )

    def search_users(self) -> list[LDAPUser]:
        """搜索所有 LDAP 用户(用于定时同步)。"""
        conn = self._bind(self.config.bind_dn, self.config.bind_password)
        try:
            cfg = self.config
            conn.search(
                search_base=cfg.user_search_base,
                search_filter=cfg.user_filter,
                attributes=[cfg.username_attribute, cfg.email_attribute,
                            cfg.display_name_attribute],
            )
            result = []
            for entry in conn.entries:
                username = str(entry[cfg.username_attribute].value) if cfg.username_attribute in entry else ""
                email = str(entry[cfg.email_attribute].value) if cfg.email_attribute in entry else ""
                display_name = str(entry[cfg.display_name_attribute].value) if cfg.display_name_attribute in entry else username
                result.append(LDAPUser(
                    dn=entry.entry_dn,
                    username=username,
                    email=email,
                    display_name=display_name,
                ))
            return result
        finally:
            conn.unbind()

    def sync_users_to_local(self) -> dict:
        """同步 LDAP 用户到本地,返回统计。

        映射规则:按邮箱查找本地用户
            - 存在:更新 username/display_name(若变化)
            - 不存在:创建新用户(随机密码,role=user)
        """
        ldap_users = self.search_users()
        store = get_user_store()
        created = 0
        updated = 0
        skipped = 0

        for lu in ldap_users:
            if not lu.email:
                skipped += 1
                continue

            local = store.get_by_email(lu.email)
            if local is None:
                # 创建新用户(随机密码,LDAP 用户不需要本地密码)
                import secrets
                import string
                random_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
                user, err = store.create(
                    username=lu.username or lu.email.split("@")[0],
                    email=lu.email,
                    password=random_pw,
                    role="user",
                )
                if user:
                    # 打上 LDAP 来源标记
                    store.update_profile(user.id, {
                        **(user.profile or {}),
                        "source": "ldap",
                        "ldap_dn": lu.dn,
                        "display_name": lu.display_name,
                    })
                    created += 1
                else:
                    logger.warning("LDAP 用户同步创建失败: %s (%s)", lu.email, err)
                    skipped += 1
            else:
                # 已存在:更新 profile(若需要)
                profile = local.profile or {}
                needs_update = (
                    profile.get("source") != "ldap"
                    or profile.get("ldap_dn") != lu.dn
                    or profile.get("display_name") != lu.display_name
                )
                if needs_update:
                    store.update_profile(local.id, {
                        **profile,
                        "source": "ldap",
                        "ldap_dn": lu.dn,
                        "display_name": lu.display_name,
                    })
                    updated += 1
                else:
                    skipped += 1

        return {
            "total_ldap_users": len(ldap_users),
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }

    def sync_user_to_local(self, ldap_user: LDAPUser):
        """单个 LDAP 用户同步到本地(登录时调用)。

        返回本地 StoredUser。
        """
        store = get_user_store()

        if ldap_user.email:
            local = store.get_by_email(ldap_user.email)
            if local is not None:
                # 更新 DN 标记
                profile = local.profile or {}
                if profile.get("ldap_dn") != ldap_user.dn:
                    store.update_profile(local.id, {
                        **profile,
                        "source": "ldap",
                        "ldap_dn": ldap_user.dn,
                        "display_name": ldap_user.display_name,
                    })
                return local

        # 不存在 → 创建
        import secrets
        import string
        random_pw = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
        username = ldap_user.username or (ldap_user.email.split("@")[0] if ldap_user.email else f"ldap_{secrets.token_hex(4)}")
        user, err = store.create(
            username=username,
            email=ldap_user.email,
            password=random_pw,
            role="user",
        )
        if user:
            store.update_profile(user.id, {
                "source": "ldap",
                "ldap_dn": ldap_user.dn,
                "display_name": ldap_user.display_name,
            })
        return user
