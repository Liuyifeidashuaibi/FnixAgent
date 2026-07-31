"""Phase 2.2 LDAP/AD 域集成测试。

覆盖:
    1. LDAP 配置存储 CRUD(InMemoryLDAPConfigStore)
    2. LDAP 客户端(mock ldap3 库)
    3. LDAP 登录端点(/auth/ldap/login)
    4. LDAP 配置管理端点(/admin/ldap/*)
    5. 用户同步逻辑(按邮箱映射)
    6. ldap3 未安装时的降级处理
"""

import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置存储,确保隔离。"""
    from fnixagent.services.storage import reset_stores
    from fnixagent.services.storage_ldap import reset_ldap_config_store

    reset_ldap_config_store()
    reset_stores()
    yield
    reset_ldap_config_store()
    reset_stores()


# ---------------------------------------------------------------------------
# Mock ldap3 模块(测试环境可能未安装)
# ---------------------------------------------------------------------------


class MockLDAPEntry:
    """模拟 ldap3 的搜索结果条目。"""

    def __init__(self, dn: str, attrs: dict):
        self.entry_dn = dn
        self._attrs = attrs

    def __contains__(self, key):
        return key in self._attrs

    def __getitem__(self, key):
        # 返回带 .value 属性的对象(模拟 ldap3 Attribute)
        m = MagicMock()
        m.value = self._attrs.get(key, "")
        return m


def _make_mock_ldap3():
    """创建一个 mock ldap3 模块。"""
    mock = types.ModuleType("ldap3")

    # 常量
    mock.AUTO_BIND_NO_TLS = 0
    mock.AUTO_BIND_TLS_BEFORE_BIND = 1
    mock.ALL = 0

    # Tls 类
    class Tls:
        def __init__(self, *a, **kw):
            pass

    mock.Tls = Tls

    # Server 类
    class Server:
        def __init__(self, host, use_ssl=False, tls=None, get_info=None):
            self.host = host
            self.use_ssl = use_ssl
            self.tls = tls

    mock.Server = Server

    # Connection 类
    class Connection:
        # 类级变量:测试可设置来控制搜索结果
        _search_callback = None  # function(search_base, search_filter) -> list[MockLDAPEntry]
        _bind_should_succeed = True

        def __init__(self, server, user=None, password=None, auto_bind=None, read_only=False):
            self.server = server
            self.user = user
            self.password = password
            self.auto_bind = auto_bind
            self.read_only = read_only
            self.bound = False
            self.result = {}
            self.entries: list = []

        def bind(self):
            if Connection._bind_should_succeed:
                self.bound = True
                return True
            self.result = {"description": "invalidCredentials"}
            return False

        def unbind(self):
            self.bound = False

        def search(self, search_base, search_filter, attributes=None):
            if Connection._search_callback:
                self.entries = Connection._search_callback(search_base, search_filter)
            else:
                self.entries = []

    mock.Connection = Connection
    return mock


# ---------------------------------------------------------------------------
# 1. LDAP 配置存储
# ---------------------------------------------------------------------------


class TestLDAPConfigStore:
    def test_create_and_get(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        cfg = store.create_config(
            name="企业AD",
            server_url="ldap://dc.company.com:389",
            bind_dn="CN=svc,DC=company,DC=com",
            bind_password="secret",
            user_search_base="OU=Users,DC=company,DC=com",
        )
        assert cfg.id > 0
        assert cfg.name == "企业AD"
        assert cfg.is_active is True

        # 读取
        got = store.get_config(cfg.id)
        assert got is not None
        assert got.bind_dn == "CN=svc,DC=company,DC=com"
        assert got.bind_password == "secret"

    def test_list_configs(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        store.create_config("AD1", "ldap://a", "dn1", "pw", "base1")
        store.create_config("AD2", "ldap://b", "dn2", "pw", "base2", is_active=False)

        all_configs = store.list_configs()
        assert len(all_configs) == 2

        active_only = store.list_configs(include_inactive=False)
        assert len(active_only) == 1
        assert active_only[0].name == "AD1"

    def test_get_active_config(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        assert store.get_active_config() is None

        store.create_config("AD1", "ldap://a", "dn1", "pw", "base1")
        active = store.get_active_config()
        assert active is not None
        assert active.name == "AD1"

    def test_update_config(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        cfg = store.create_config("AD", "ldap://a", "dn", "pw", "base")
        updated = store.update_config(cfg.id, name="新名称", server_url="ldap://new")
        assert updated.name == "新名称"
        assert updated.server_url == "ldap://new"

    def test_delete_config(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        cfg = store.create_config("AD", "ldap://a", "dn", "pw", "base")
        assert store.delete_config(cfg.id) is True
        assert store.get_config(cfg.id) is None
        assert store.delete_config(999) is False

    def test_mark_synced(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        cfg = store.create_config("AD", "ldap://a", "dn", "pw", "base")
        assert cfg.last_sync_at is None
        store.mark_synced(cfg.id)
        got = store.get_config(cfg.id)
        assert got.last_sync_at is not None

    def test_to_dict_hides_password_by_default(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        cfg = store.create_config("AD", "ldap://a", "dn", "secret", "base")
        d = cfg.to_dict(include_password=False)
        assert "bind_password" not in d

        d2 = cfg.to_dict(include_password=True)
        assert d2["bind_password"] == "secret"

    def test_to_ldap_config(self):
        from fnixagent.services.storage_ldap import get_ldap_config_store

        store = get_ldap_config_store()
        cfg = store.create_config("AD", "ldap://a", "dn", "pw", "base")
        ldap_cfg = cfg.to_ldap_config()
        assert ldap_cfg.name == "AD"
        assert ldap_cfg.server_url == "ldap://a"


# ---------------------------------------------------------------------------
# 2. LDAP 客户端(mock ldap3)
# ---------------------------------------------------------------------------


class TestLDAPClient:
    @pytest.fixture
    def mock_ldap3(self):
        """注入 mock ldap3 模块到 sys.modules。"""
        mock = _make_mock_ldap3()
        old = sys.modules.get("ldap3")
        sys.modules["ldap3"] = mock
        yield mock
        if old is not None:
            sys.modules["ldap3"] = old
        else:
            sys.modules.pop("ldap3", None)

    def test_test_connection_success(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)
        assert client.test_connection() is True

    def test_test_connection_failure(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="wrong",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)

        # 让 bind 失败
        mock_ldap3.Connection._bind_should_succeed = False
        assert client.test_connection() is False
        # 恢复
        mock_ldap3.Connection._bind_should_succeed = True

    def test_authenticate_success(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
            username_attribute="sAMAccountName",
            email_attribute="mail",
            display_name_attribute="displayName",
        )
        client = LDAPClient(config)

        # 预设搜索回调:返回 alice 用户
        def _search_cb(search_base, search_filter):
            return [
                MockLDAPEntry(
                    dn="CN=alice,OU=Users,DC=co,DC=com",
                    attrs={
                        "sAMAccountName": "alice",
                        "mail": "alice@company.com",
                        "displayName": "Alice Wang",
                    },
                )
            ]

        mock_ldap3.Connection._search_callback = _search_cb

        user = client.authenticate("alice", "password123")
        assert user is not None
        assert user.username == "alice"
        assert user.email == "alice@company.com"
        assert user.display_name == "Alice Wang"

    def test_authenticate_user_not_found(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)

        # 搜索返回空
        mock_ldap3.Connection._search_callback = lambda *a: []

        user = client.authenticate("nobody", "password")
        assert user is None

    def test_authenticate_empty_password_raises(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import (
            LDAPAuthenticationError,
            LDAPClient,
            LDAPConfig,
        )

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)
        with pytest.raises(LDAPAuthenticationError):
            client.authenticate("alice", "")

    def test_not_installed_raises(self):
        """ldap3 未安装时应抛 LDAPNotInstalledError。"""
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig, LDAPNotInstalledError

        # 确保 ldap3 未导入
        old = sys.modules.pop("ldap3", None)
        try:
            config = LDAPConfig(
                id=1,
                name="AD",
                server_url="ldap://dc:389",
                bind_dn="CN=svc,DC=co,DC=com",
                bind_password="pw",
                user_search_base="OU=Users,DC=co,DC=com",
            )
            client = LDAPClient(config)
            with pytest.raises(LDAPNotInstalledError):
                client.test_connection()
        finally:
            if old is not None:
                sys.modules["ldap3"] = old


# ---------------------------------------------------------------------------
# 3. 用户同步
# ---------------------------------------------------------------------------


class TestLDAPUserSync:
    @pytest.fixture
    def mock_ldap3(self):
        mock = _make_mock_ldap3()
        old = sys.modules.get("ldap3")
        sys.modules["ldap3"] = mock
        yield mock
        if old is not None:
            sys.modules["ldap3"] = old
        else:
            sys.modules.pop("ldap3", None)

    def test_sync_user_to_local_creates_new(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig, LDAPUser

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)

        ldap_user = LDAPUser(
            dn="CN=bob,OU=Users,DC=co,DC=com",
            username="bob",
            email="bob@company.com",
            display_name="Bob Li",
        )

        local = client.sync_user_to_local(ldap_user)
        assert local is not None
        assert local.email == "bob@company.com"
        assert local.profile.get("source") == "ldap"
        assert local.profile.get("ldap_dn") == "CN=bob,OU=Users,DC=co,DC=com"

    def test_sync_user_to_local_updates_existing(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig, LDAPUser
        from fnixagent.services.storage import get_user_store

        # 先创建本地用户(已有邮箱)
        store = get_user_store()
        store.create(username="bob", email="bob@company.com", password="Pass1234")

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)

        ldap_user = LDAPUser(
            dn="CN=bob,OU=Users,DC=co,DC=com",
            username="bob",
            email="bob@company.com",
            display_name="Bob Li (Updated)",
        )

        local = client.sync_user_to_local(ldap_user)
        assert local is not None
        assert local.username == "bob"
        # profile 应被更新
        assert local.profile.get("source") == "ldap"
        assert local.profile.get("ldap_dn") == "CN=bob,OU=Users,DC=co,DC=com"
        assert local.profile.get("display_name") == "Bob Li (Updated)"

    def test_sync_users_batch(self, mock_ldap3):
        from fnixagent.core.security.auth.ldap import LDAPClient, LDAPConfig

        config = LDAPConfig(
            id=1,
            name="AD",
            server_url="ldap://dc:389",
            bind_dn="CN=svc,DC=co,DC=com",
            bind_password="pw",
            user_search_base="OU=Users,DC=co,DC=com",
        )
        client = LDAPClient(config)

        # 预设搜索回调:返回 alice 和 bob
        def _search_cb(search_base, search_filter):
            return [
                MockLDAPEntry(
                    "CN=alice",
                    {
                        "sAMAccountName": "alice",
                        "mail": "alice@co.com",
                        "displayName": "Alice",
                    },
                ),
                MockLDAPEntry(
                    "CN=bob",
                    {
                        "sAMAccountName": "bob",
                        "mail": "bob@co.com",
                        "displayName": "Bob",
                    },
                ),
            ]

        mock_ldap3.Connection._search_callback = _search_cb

        stats = client.sync_users_to_local()
        assert stats["total_ldap_users"] == 2
        assert stats["created"] == 2
        assert stats["updated"] == 0

        # 再次同步 → 应全部命中已存在
        stats2 = client.sync_users_to_local()
        assert stats2["created"] == 0
        assert stats2["updated"] == 0  # 无变化
        assert stats2["skipped"] == 2


# ---------------------------------------------------------------------------
# 4. API 端点测试
# ---------------------------------------------------------------------------


class TestLDAPAPIEndpoints:
    @pytest.fixture
    def client(self):
        """构建带 LDAP 路由的 TestClient。"""
        from fnixagent.api.routers import admin, auth

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(admin.router, prefix="/api/v1")
        return TestClient(app)

    @pytest.fixture
    def admin_token(self):
        """创建管理员 Token。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="admin_ldap", email="admin@e.com", password="Pass1234", role="admin"
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    def test_ldap_login_no_config_returns_503(self, client):
        """未配置 LDAP 时返回 503。"""
        resp = client.post(
            "/api/v1/auth/ldap/login",
            json={
                "username": "alice",
                "password": "pass",
            },
        )
        assert resp.status_code == 503

    def test_ldap_config_crud(self, client, admin_token):
        """测试 LDAP 配置 CRUD 全流程。"""
        token, _ = admin_token
        headers = {"Authorization": f"Bearer {token}"}

        # 1. 创建
        resp = client.post(
            "/api/v1/admin/ldap/configs",
            json={
                "name": "企业AD",
                "server_url": "ldap://dc.company.com:389",
                "bind_dn": "CN=svc,DC=company,DC=com",
                "bind_password": "secret",
                "user_search_base": "OU=Users,DC=company,DC=com",
                "use_tls": False,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        cfg = resp.json()["data"]
        assert cfg["name"] == "企业AD"
        assert "bind_password" not in cfg  # 不回显密码
        config_id = cfg["id"]

        # 2. 列表
        resp = client.get("/api/v1/admin/ldap/configs", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]["items"]) == 1

        # 3. 更新
        resp = client.put(
            f"/api/v1/admin/ldap/configs/{config_id}",
            json={
                "name": "新名称",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "新名称"

        # 4. 删除
        resp = client.delete(f"/api/v1/admin/ldap/configs/{config_id}", headers=headers)
        assert resp.status_code == 200

        # 5. 确认已删除
        resp = client.get("/api/v1/admin/ldap/configs", headers=headers)
        assert len(resp.json()["data"]["items"]) == 0

    def test_ldap_config_requires_admin(self, client):
        """非 admin 用户不能访问 LDAP 配置。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(username="normal", email="n@e.com", password="Pass1234", role="user")
        token = create_jwt_token(user_id=user.id, username=user.username)

        resp = client.get(
            "/api/v1/admin/ldap/configs",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert resp.status_code == 403

    def test_ldap_config_create_validation(self, client, admin_token):
        """缺少必填字段返回 400。"""
        token, _ = admin_token
        resp = client.post(
            "/api/v1/admin/ldap/configs",
            json={
                "name": "AD",
                # 缺少 server_url, bind_dn, bind_password, user_search_base
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_ldap_sync_no_configs_returns_404(self, client, admin_token):
        """无 LDAP 配置时触发同步返回 404。"""
        token, _ = admin_token
        resp = client.post(
            "/api/v1/admin/ldap/sync",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )
        assert resp.status_code == 404
