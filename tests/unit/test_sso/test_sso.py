"""Phase 2.3 SSO 单点登录测试。

覆盖:
    1. SSO 配置存储 CRUD(InMemorySSOConfigStore)
    2. SSO 绑定存储 CRUD(InMemorySSOBindingStore)
    3. OAuth 客户端(mock requests,覆盖 GitHub/Google/通用)
    4. SAML 客户端(mock python3-saml)
    5. OAuth 用户同步(按 provider_user_id / email 绑定)
    6. SAML 用户同步
    7. API 端点(/auth/sso/* + /admin/sso/*)
    8. requests / python3-saml 未安装时的降级处理
"""
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置存储,确保隔离。"""
    from fnixagent.services.storage_sso import (
        reset_sso_binding_store,
        reset_sso_config_store,
    )
    from fnixagent.services.storage import reset_stores

    reset_sso_config_store()
    reset_sso_binding_store()
    reset_stores()
    yield
    reset_sso_config_store()
    reset_sso_binding_store()
    reset_stores()


# ---------------------------------------------------------------------------
# Mock requests 模块(测试环境可能未安装,或需要拦截 HTTP 调用)
# ---------------------------------------------------------------------------


def _make_mock_requests():
    """创建一个 mock requests 模块。"""
    mock = types.ModuleType("requests")

    # 类级变量:测试可设置来控制响应
    class _MockResponse:
        def __init__(self, status_code=200, json_data=None, text=""):
            self.status_code = status_code
            self._json = json_data or {}
            self.text = text or ""

        def json(self):
            return self._json

    class _Requests:
        _post_callback = None    # function(url, data, headers) -> _MockResponse
        _get_callback = None     # function(url, headers) -> _MockResponse

        def post(self, url, data=None, headers=None, timeout=None, **kw):
            if _Requests._post_callback:
                return _Requests._post_callback(url, data, headers)
            return _MockResponse(200, {"access_token": "mock-token"})

        def get(self, url, headers=None, timeout=None, **kw):
            if _Requests._get_callback:
                return _Requests._get_callback(url, headers)
            return _MockResponse(200, {})

    mock._MockResponse = _MockResponse
    mock._Requests = _Requests
    mock.post = _Requests().post
    mock.get = _Requests().get
    return mock


@pytest.fixture
def mock_requests():
    """注入 mock requests 模块。"""
    mock = _make_mock_requests()
    old = sys.modules.get("requests")
    sys.modules["requests"] = mock
    yield mock
    if old is not None:
        sys.modules["requests"] = old
    else:
        sys.modules.pop("requests", None)


# ---------------------------------------------------------------------------
# Mock python3-saml 模块
# ---------------------------------------------------------------------------


def _make_mock_saml():
    """创建一个 mock onelogin.saml2 模块树。"""
    onelogin = types.ModuleType("onelogin")
    saml2 = types.ModuleType("onelogin.saml2")
    auth_mod = types.ModuleType("onelogin.saml2.auth")
    utils_mod = types.ModuleType("onelogin.saml2.utils")

    class _MockUtils:
        @staticmethod
        def generate_unique_id():
            return "mock-id-123"

    class _MockAuth:
        """Mock OneLogin_Saml2_Auth。"""
        _authenticated = True
        _nameid = "alice@company.com"
        _attributes = {
            "email": ["alice@company.com"],
            "name": ["Alice Wang"],
        }
        _errors = []
        _last_error_reason = ""

        def __init__(self, request_dict, old_settings=None):
            self.request_dict = request_dict
            self.settings = old_settings

        def login(self, return_to=None):
            return f"https://idp.example.com/sso?SAMLRequest=mock&RelayState={return_to}"

        def process_response(self):
            pass

        def is_authenticated(self):
            return _MockAuth._authenticated

        def get_errors(self):
            return _MockAuth._errors

        def get_last_error_reason(self):
            return _MockAuth._last_error_reason

        def get_nameid(self):
            return _MockAuth._nameid

        def get_attributes(self):
            return _MockAuth._attributes

    auth_mod.OneLogin_Saml2_Auth = _MockAuth
    utils_mod.OneLogin_Saml2_Utils = _MockUtils

    onelogin.saml2 = saml2
    saml2.auth = auth_mod
    saml2.utils = utils_mod
    auth_mod.OneLogin_Saml2_Auth = _MockAuth
    utils_mod.OneLogin_Saml2_Utils = _MockUtils

    return onelogin, _MockAuth


@pytest.fixture
def mock_saml():
    """注入 mock onelogin.saml2 模块树。"""
    onelogin, mock_auth_cls = _make_mock_saml()
    old_onelogin = sys.modules.get("onelogin")
    old_auth = sys.modules.get("onelogin.saml2.auth")
    old_utils = sys.modules.get("onelogin.saml2.utils")

    sys.modules["onelogin"] = onelogin
    sys.modules["onelogin.saml2"] = onelogin.saml2
    sys.modules["onelogin.saml2.auth"] = onelogin.saml2.auth
    sys.modules["onelogin.saml2.utils"] = onelogin.saml2.utils

    yield mock_auth_cls

    # 恢复
    for name, mod in [("onelogin", old_onelogin),
                      ("onelogin.saml2.auth", old_auth),
                      ("onelogin.saml2.utils", old_utils)]:
        if mod is not None:
            sys.modules[name] = mod
        else:
            sys.modules.pop(name, None)


# ===========================================================================
# 1. SSO 配置存储
# ===========================================================================


class TestSSOConfigStore:
    def test_create_oauth_config(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        cfg = store.create_config(
            provider_type="oauth",
            provider_code="github",
            name="GitHub",
            client_id="gh_id",
            client_secret="gh_secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
        )
        assert cfg.id > 0
        assert cfg.provider_type == "oauth"
        assert cfg.provider_code == "github"
        assert cfg.is_active is True

        # 读取
        got = store.get_config(cfg.id)
        assert got is not None
        assert got.client_secret == "gh_secret"

    def test_create_saml_config(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        cfg = store.create_config(
            provider_type="saml",
            provider_code="azure_ad",
            name="Azure AD",
            sp_entity_id="https://admin.example.com/saml/metadata",
            acs_url="https://admin.example.com/sso/saml/acs",
            idp_entity_id="https://sts.windows.net/tenant/",
            idp_sso_url="https://login.microsoftonline.com/tenant/saml2",
            idp_x509_cert="-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
        )
        assert cfg.id > 0
        assert cfg.provider_type == "saml"
        assert cfg.idp_x509_cert.startswith("-----BEGIN")

    def test_list_configs_filter_by_type(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        store.create_config(provider_type="oauth", provider_code="github",
                            name="GitHub", client_id="i", client_secret="s",
                            redirect_uri="https://r")
        store.create_config(provider_type="saml", provider_code="azure_ad",
                            name="Azure AD", sp_entity_id="x", acs_url="y",
                            idp_entity_id="z", idp_sso_url="u", idp_x509_cert="c")

        all_configs = store.list_configs()
        assert len(all_configs) == 2

        oauth_only = store.list_configs(provider_type="oauth")
        assert len(oauth_only) == 1
        assert oauth_only[0].provider_type == "oauth"

        saml_only = store.list_configs(provider_type="saml")
        assert len(saml_only) == 1

    def test_get_by_code(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        store.create_config(provider_type="oauth", provider_code="github",
                            name="GitHub", client_id="i", client_secret="s",
                            redirect_uri="https://r")

        cfg = store.get_by_code("github", provider_type="oauth")
        assert cfg is not None
        assert cfg.provider_code == "github"

        # 不存在的 provider
        assert store.get_by_code("nonexistent") is None

    def test_update_config(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        cfg = store.create_config(provider_type="oauth", provider_code="github",
                                  name="GitHub", client_id="i", client_secret="s",
                                  redirect_uri="https://r")
        updated = store.update_config(cfg.id, name="新名称", client_secret="new_secret")
        assert updated.name == "新名称"
        assert updated.client_secret == "new_secret"

    def test_delete_config(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        cfg = store.create_config(provider_type="oauth", provider_code="github",
                                  name="GitHub", client_id="i", client_secret="s",
                                  redirect_uri="https://r")
        assert store.delete_config(cfg.id) is True
        assert store.get_config(cfg.id) is None
        assert store.delete_config(999) is False

    def test_to_dict_hides_secret_by_default(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        cfg = store.create_config(provider_type="oauth", provider_code="github",
                                  name="GitHub", client_id="i", client_secret="secret",
                                  redirect_uri="https://r")
        d = cfg.to_dict(include_secret=False)
        assert "client_secret" not in d
        assert d["client_id"] == "i"

        d_with_secret = cfg.to_dict(include_secret=True)
        assert d_with_secret["client_secret"] == "secret"

    def test_to_oauth_config_conversion(self):
        from fnixagent.services.storage_sso import get_sso_config_store

        store = get_sso_config_store()
        cfg = store.create_config(provider_type="oauth", provider_code="github",
                                  name="GitHub", client_id="i", client_secret="s",
                                  redirect_uri="https://r")
        oauth_cfg = cfg.to_oauth_config()
        assert oauth_cfg.client_id == "i"
        assert oauth_cfg.client_secret == "s"
        assert oauth_cfg.provider_code == "github"


# ===========================================================================
# 2. SSO 绑定存储
# ===========================================================================


class TestSSOBindingStore:
    def test_create_and_get_by_provider(self):
        from fnixagent.services.storage_sso import get_sso_binding_store

        store = get_sso_binding_store()
        binding = store.create(user_id=1, provider_code="github",
                               provider_user_id="12345")
        assert binding.id > 0
        assert binding.user_id == 1

        got = store.get_by_provider("github", "12345")
        assert got is not None
        assert got.user_id == 1

    def test_create_idempotent(self):
        """同 (provider, provider_user_id) 重复创建返回已有绑定。"""
        from fnixagent.services.storage_sso import get_sso_binding_store

        store = get_sso_binding_store()
        b1 = store.create(user_id=1, provider_code="github",
                          provider_user_id="12345")
        b2 = store.create(user_id=1, provider_code="github",
                          provider_user_id="12345")
        assert b1.id == b2.id

    def test_list_by_user(self):
        from fnixagent.services.storage_sso import get_sso_binding_store

        store = get_sso_binding_store()
        store.create(user_id=1, provider_code="github", provider_user_id="123")
        store.create(user_id=1, provider_code="google", provider_user_id="abc")
        store.create(user_id=2, provider_code="github", provider_user_id="456")

        binds = store.list_by_user(1)
        assert len(binds) == 2
        assert {b.provider_code for b in binds} == {"github", "google"}

    def test_delete_binding(self):
        from fnixagent.services.storage_sso import get_sso_binding_store

        store = get_sso_binding_store()
        binding = store.create(user_id=1, provider_code="github",
                               provider_user_id="123")
        assert store.delete(binding.id) is True
        assert store.get_by_provider("github", "123") is None
        assert store.delete(999) is False

    def test_delete_by_user(self):
        from fnixagent.services.storage_sso import get_sso_binding_store

        store = get_sso_binding_store()
        store.create(user_id=1, provider_code="github", provider_user_id="123")
        store.create(user_id=1, provider_code="google", provider_user_id="abc")
        count = store.delete_by_user(1)
        assert count == 2
        assert len(store.list_by_user(1)) == 0


# ===========================================================================
# 3. OAuth 客户端
# ===========================================================================


class TestOAuthClient:
    def test_build_authorization_url_github(self, mock_requests):
        from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfig

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="gh_id", client_secret="gh_secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
        )
        client = OAuthClient(cfg)
        url = client.build_authorization_url(state="random-state")
        assert "github.com/login/oauth/authorize" in url
        assert "client_id=gh_id" in url
        assert "state=random-state" in url
        assert "scope=read" in url  # GitHub 默认 scope

    def test_build_authorization_url_generic_provider(self, mock_requests):
        from fnixagent.core.security.auth.oauth import OAuthConfig, OAuthClient

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="custom",
            name="Custom", client_id="cid", client_secret="secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
            authorize_url="https://idp.example.com/authorize",
            token_url="https://idp.example.com/token",
            userinfo_url="https://idp.example.com/userinfo",
            scopes=["openid", "profile"],
        )
        client = OAuthClient(cfg)
        url = client.build_authorization_url(state="state-123")
        assert "idp.example.com/authorize" in url
        assert "scope=openid+profile" in url  # 空格被 urlencode 为 +

    def test_exchange_code_success(self, mock_requests):
        from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfig

        # 配置 mock 响应
        mock_requests._Requests._post_callback = lambda url, data, headers: (
            mock_requests._MockResponse(200, {
                "access_token": "gh-token",
                "token_type": "bearer",
                "scope": "read:user",
            })
        )

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="gh_id", client_secret="gh_secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
        )
        client = OAuthClient(cfg)
        token = client.exchange_code("auth-code-123")
        assert token["access_token"] == "gh-token"

    def test_exchange_code_failure(self, mock_requests):
        from fnixagent.core.security.auth.oauth import (
            OAuthAuthenticationError, OAuthClient, OAuthConfig,
        )

        mock_requests._Requests._post_callback = lambda url, data, headers: (
            mock_requests._MockResponse(401, {"error": "bad_verification_code"})
        )

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="gh_id", client_secret="gh_secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
        )
        client = OAuthClient(cfg)
        with pytest.raises(OAuthAuthenticationError):
            client.exchange_code("invalid-code")

    def test_fetch_userinfo_github(self, mock_requests):
        from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfig

        mock_requests._Requests._get_callback = lambda url, headers: (
            mock_requests._MockResponse(200, {
                "id": 12345,
                "login": "alice",
                "email": "alice@company.com",
                "name": "Alice Wang",
                "avatar_url": "https://github.com/avatars/alice.png",
            })
        )

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="gh_id", client_secret="gh_secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
        )
        client = OAuthClient(cfg)
        raw = client.fetch_userinfo("access-token")
        assert raw["login"] == "alice"

        # 测试标准化
        user_info = client.normalize_userinfo(raw)
        assert user_info.provider_user_id == "12345"
        assert user_info.username == "alice"
        assert user_info.email == "alice@company.com"
        assert user_info.display_name == "Alice Wang"

    def test_authenticate_end_to_end(self, mock_requests):
        from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfig

        # 配置 mock:换 token + 拉用户信息
        def post_cb(url, data, headers):
            return mock_requests._MockResponse(200, {"access_token": "tok"})

        def get_cb(url, headers):
            return mock_requests._MockResponse(200, {
                "id": 67890,
                "login": "bob",
                "email": "bob@company.com",
                "name": "Bob Li",
            })

        mock_requests._Requests._post_callback = post_cb
        mock_requests._Requests._get_callback = get_cb

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="gh_id", client_secret="gh_secret",
            redirect_uri="https://admin.example.com/sso/oauth/callback",
        )
        client = OAuthClient(cfg)
        user_info = client.authenticate("auth-code", state="state")
        assert user_info.provider_user_id == "67890"
        assert user_info.email == "bob@company.com"

    def test_not_installed_raises(self):
        """requests 库未安装时抛 OAuthNotInstalledError。"""
        from fnixagent.core.security.auth.oauth import (
            OAuthClient, OAuthConfig, OAuthNotInstalledError,
        )

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="gh_id", client_secret="gh_secret",
            redirect_uri="https://r",
        )
        client = OAuthClient(cfg)

        # 直接 mock _import_requests 方法抛 OAuthNotInstalledError
        with patch.object(client, "_import_requests",
                          side_effect=OAuthNotInstalledError("mock: 未安装")):
            with pytest.raises(OAuthNotInstalledError):
                client.exchange_code("code")

    def test_normalize_userinfo_uses_email_as_username(self, mock_requests):
        from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfig

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="google",
            name="Google", client_id="g_id", client_secret="g_secret",
            redirect_uri="https://r",
        )
        client = OAuthClient(cfg)
        # Google 用户信息(无 username 字段)
        raw = {
            "sub": "google-123",
            "email": "user@gmail.com",
            "name": "Gmail User",
            "picture": "https://google.com/avatar.png",
        }
        info = client.normalize_userinfo(raw)
        assert info.provider_user_id == "google-123"
        assert info.username == "user"  # email 前缀
        assert info.email == "user@gmail.com"


# ===========================================================================
# 4. OAuth 用户同步
# ===========================================================================


class TestOAuthUserSync:
    def test_sync_creates_new_user(self, mock_requests):
        from fnixagent.core.security.auth.oauth import (
            OAuthClient, OAuthConfig, OAuthUserInfo,
        )
        from fnixagent.services.storage import get_user_store

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="i", client_secret="s",
            redirect_uri="https://r",
        )
        client = OAuthClient(cfg)
        oauth_user = OAuthUserInfo(
            provider_code="github",
            provider_user_id="12345",
            username="alice",
            email="alice@company.com",
            display_name="Alice Wang",
        )

        local = client.sync_user_to_local(oauth_user)
        assert local is not None
        assert local.email == "alice@company.com"
        assert local.profile.get("source") == "oauth"
        assert local.profile.get("oauth_provider") == "github"

    def test_sync_binds_existing_user_by_email(self, mock_requests):
        from fnixagent.core.security.auth.oauth import (
            OAuthClient, OAuthConfig, OAuthUserInfo,
        )
        from fnixagent.services.storage import get_user_store
        from fnixagent.services.storage_sso import get_sso_binding_store

        # 先创建本地用户(已有邮箱)
        store = get_user_store()
        local_user, _ = store.create(
            username="bob_local", email="bob@company.com", password="Pass1234"
        )

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="i", client_secret="s",
            redirect_uri="https://r",
        )
        client = OAuthClient(cfg)
        oauth_user = OAuthUserInfo(
            provider_code="github",
            provider_user_id="67890",
            username="bob",
            email="bob@company.com",
            display_name="Bob Li",
        )

        local = client.sync_user_to_local(oauth_user)
        assert local.id == local_user.id  # 复用已有用户

        # 绑定应已创建
        binding_store = get_sso_binding_store()
        binding = binding_store.get_by_provider("github", "67890")
        assert binding is not None
        assert binding.user_id == local_user.id

    def test_sync_returns_existing_binding(self, mock_requests):
        from fnixagent.core.security.auth.oauth import (
            OAuthClient, OAuthConfig, OAuthUserInfo,
        )
        from fnixagent.services.storage_sso import get_sso_binding_store

        # 预创建绑定
        binding_store = get_sso_binding_store()
        from fnixagent.services.storage import get_user_store
        store = get_user_store()
        local_user, _ = store.create(
            username="carol", email="carol@co.com", password="Pass1234"
        )
        binding_store.create(user_id=local_user.id, provider_code="github",
                             provider_user_id="99999")

        cfg = OAuthConfig(
            id=1, provider_type="oauth", provider_code="github",
            name="GitHub", client_id="i", client_secret="s",
            redirect_uri="https://r",
        )
        client = OAuthClient(cfg)
        oauth_user = OAuthUserInfo(
            provider_code="github",
            provider_user_id="99999",
            username="carol_gh",
            email="carol@github.com",
            display_name="Carol",
        )

        local = client.sync_user_to_local(oauth_user)
        assert local.id == local_user.id


# ===========================================================================
# 5. SAML 客户端
# ===========================================================================


class TestSAMLClient:
    def test_build_authn_request(self, mock_saml):
        from fnixagent.core.security.auth.saml import SAMLClient, SAMLConfig

        cfg = SAMLConfig(
            id=1, provider_type="saml", provider_code="azure_ad",
            name="Azure AD",
            sp_entity_id="https://admin.example.com/saml/metadata",
            acs_url="https://admin.example.com/sso/saml/acs",
            idp_entity_id="https://sts.windows.net/tenant/",
            idp_sso_url="https://login.microsoftonline.com/tenant/saml2",
            idp_x509_cert="-----BEGIN CERTIFICATE-----\nMIID...\n-----END CERTIFICATE-----",
        )
        client = SAMLClient(cfg)
        result = client.build_authn_request(state="relay-state-123")
        assert "idp.example.com" in result["redirect_url"] or \
               "login.microsoftonline.com" in result["redirect_url"] or \
               "SAMLRequest" in result["redirect_url"]
        assert result["state"] == "relay-state-123"

    def test_parse_response_success(self, mock_saml):
        from fnixagent.core.security.auth.saml import SAMLClient, SAMLConfig

        # 配置 mock:已认证 + 返回 alice 信息
        mock_saml._authenticated = True
        mock_saml._nameid = "alice@company.com"
        mock_saml._attributes = {
            "email": ["alice@company.com"],
            "name": ["Alice Wang"],
        }

        cfg = SAMLConfig(
            id=1, provider_type="saml", provider_code="azure_ad",
            name="Azure AD",
            sp_entity_id="https://sp",
            acs_url="https://sp/acs",
            idp_entity_id="https://idp",
            idp_sso_url="https://idp/sso",
            idp_x509_cert="cert",
        )
        client = SAMLClient(cfg)
        user_info = client.parse_response("base64-saml-response")
        assert user_info.name_id == "alice@company.com"
        assert user_info.email == "alice@company.com"
        assert user_info.display_name == "Alice Wang"

    def test_parse_response_auth_failure(self, mock_saml):
        from fnixagent.core.security.auth.saml import (
            SAMLClient, SAMLConfig, SAMLResponseError,
        )

        mock_saml._authenticated = False
        mock_saml._errors = ["invalid_response"]
        mock_saml._last_error_reason = "Signature validation failed"

        cfg = SAMLConfig(
            id=1, provider_type="saml", provider_code="azure_ad",
            name="Azure AD",
            sp_entity_id="https://sp",
            acs_url="https://sp/acs",
            idp_entity_id="https://idp",
            idp_sso_url="https://idp/sso",
            idp_x509_cert="cert",
        )
        client = SAMLClient(cfg)
        with pytest.raises(SAMLResponseError):
            client.parse_response("invalid-response")

    def test_not_installed_raises(self):
        from fnixagent.core.security.auth.saml import (
            SAMLClient, SAMLConfig, SAMLNotInstalledError,
        )

        # 确保 onelogin 模块未加载
        for mod in list(sys.modules):
            if mod.startswith("onelogin"):
                old = sys.modules.pop(mod)
                break
        else:
            old = None

        try:
            cfg = SAMLConfig(
                id=1, provider_type="saml", provider_code="x",
                name="X", sp_entity_id="https://sp", acs_url="https://sp/acs",
                idp_entity_id="https://idp", idp_sso_url="https://idp/sso",
                idp_x509_cert="cert",
            )
            client = SAMLClient(cfg)
            with pytest.raises(SAMLNotInstalledError):
                client._import_saml()
        finally:
            # 恢复(若需要)
            pass


# ===========================================================================
# 6. SAML 用户同步
# ===========================================================================


class TestSAMLUserSync:
    def test_sync_creates_new_user(self, mock_saml):
        from fnixagent.core.security.auth.saml import (
            SAMLClient, SAMLConfig, SAMLUserInfo,
        )

        cfg = SAMLConfig(
            id=1, provider_type="saml", provider_code="azure_ad",
            name="Azure AD",
            sp_entity_id="https://sp", acs_url="https://sp/acs",
            idp_entity_id="https://idp", idp_sso_url="https://idp/sso",
            idp_x509_cert="cert",
        )
        client = SAMLClient(cfg)
        saml_user = SAMLUserInfo(
            provider_code="azure_ad",
            name_id="dave@company.com",
            username="dave",
            email="dave@company.com",
            display_name="Dave Zhao",
        )

        local = client.sync_user_to_local(saml_user)
        assert local is not None
        assert local.email == "dave@company.com"
        assert local.profile.get("source") == "saml"
        assert local.profile.get("saml_provider") == "azure_ad"

    def test_sync_binds_existing_by_email(self, mock_saml):
        from fnixagent.core.security.auth.saml import (
            SAMLClient, SAMLConfig, SAMLUserInfo,
        )
        from fnixagent.services.storage import get_user_store
        from fnixagent.services.storage_sso import get_sso_binding_store

        store = get_user_store()
        local_user, _ = store.create(
            username="eve_local", email="eve@company.com", password="Pass1234"
        )

        cfg = SAMLConfig(
            id=1, provider_type="saml", provider_code="okta",
            name="Okta",
            sp_entity_id="https://sp", acs_url="https://sp/acs",
            idp_entity_id="https://idp", idp_sso_url="https://idp/sso",
            idp_x509_cert="cert",
        )
        client = SAMLClient(cfg)
        saml_user = SAMLUserInfo(
            provider_code="okta",
            name_id="eve@company.com",
            username="eve",
            email="eve@company.com",
            display_name="Eve Chen",
        )

        local = client.sync_user_to_local(saml_user)
        assert local.id == local_user.id

        binding_store = get_sso_binding_store()
        binding = binding_store.get_by_provider("okta", "eve@company.com")
        assert binding is not None
        assert binding.user_id == local_user.id


# ===========================================================================
# 7. API 端点测试
# ===========================================================================


class TestSSOAPIEndpoints:
    @pytest.fixture
    def client(self):
        """构建带 SSO 路由的 TestClient。"""
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
            username="admin_sso", email="admin@e.com",
            password="Pass1234", role="admin",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    def test_list_providers_empty(self, client):
        """无配置时返回空列表。"""
        resp = client.get("/api/v1/auth/sso/providers")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    def test_list_providers_with_configs(self, client, admin_token):
        token, _ = admin_token
        # 创建 OAuth 配置
        client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth",
            "provider_code": "github",
            "name": "GitHub",
            "client_id": "i", "client_secret": "s",
            "redirect_uri": "https://r",
        }, headers={"Authorization": f"Bearer {token}"})

        resp = client.get("/api/v1/auth/sso/providers")
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["provider_code"] == "github"

    def test_oauth_authorize_no_config_404(self, client):
        """未配置 OAuth provider 时返回 404。"""
        resp = client.post("/api/v1/auth/sso/oauth/authorize", json={
            "provider_code": "github",
        })
        assert resp.status_code == 404

    def test_oauth_authorize_returns_url(self, client, admin_token, mock_requests):
        token, _ = admin_token
        # 创建 GitHub OAuth 配置
        client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth",
            "provider_code": "github",
            "name": "GitHub",
            "client_id": "gh_id", "client_secret": "gh_secret",
            "redirect_uri": "https://admin.example.com/sso/oauth/callback",
        }, headers={"Authorization": f"Bearer {token}"})

        resp = client.post("/api/v1/auth/sso/oauth/authorize", json={
            "provider_code": "github",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "authorization_url" in data
        assert "state" in data
        assert "github.com/login/oauth/authorize" in data["authorization_url"]

    def test_oauth_callback_success(self, client, admin_token, mock_requests):
        token, _ = admin_token
        # 创建 OAuth 配置
        client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth",
            "provider_code": "github",
            "name": "GitHub",
            "client_id": "gh_id", "client_secret": "gh_secret",
            "redirect_uri": "https://admin.example.com/sso/oauth/callback",
        }, headers={"Authorization": f"Bearer {token}"})

        # 配置 mock:换 token + 拉用户信息
        mock_requests._Requests._post_callback = lambda url, data, headers: (
            mock_requests._MockResponse(200, {"access_token": "tok"})
        )
        mock_requests._Requests._get_callback = lambda url, headers: (
            mock_requests._MockResponse(200, {
                "id": 12345, "login": "alice", "email": "alice@co.com",
                "name": "Alice",
            })
        )

        resp = client.post("/api/v1/auth/sso/oauth/callback", json={
            "provider_code": "github",
            "code": "auth-code-123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_oauth_callback_invalid_code(self, client, admin_token, mock_requests):
        token, _ = admin_token
        client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth", "provider_code": "github",
            "name": "GitHub", "client_id": "i", "client_secret": "s",
            "redirect_uri": "https://r",
        }, headers={"Authorization": f"Bearer {token}"})

        # mock 返回 401
        mock_requests._Requests._post_callback = lambda url, data, headers: (
            mock_requests._MockResponse(401, {"error": "bad_code"})
        )

        resp = client.post("/api/v1/auth/sso/oauth/callback", json={
            "provider_code": "github",
            "code": "invalid-code",
        })
        assert resp.status_code == 401

    def test_sso_config_crud_full_flow(self, client, admin_token):
        token, _ = admin_token
        headers = {"Authorization": f"Bearer {token}"}

        # 1. 创建 OAuth 配置
        resp = client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth", "provider_code": "github",
            "name": "GitHub", "client_id": "i", "client_secret": "s",
            "redirect_uri": "https://r",
        }, headers=headers)
        assert resp.status_code == 200
        cfg = resp.json()["data"]
        assert cfg["provider_code"] == "github"
        assert "client_secret" not in cfg  # 不回显 secret
        config_id = cfg["id"]

        # 2. 列表
        resp = client.get("/api/v1/admin/sso/configs", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1

        # 3. 更新
        resp = client.put(f"/api/v1/admin/sso/configs/{config_id}", json={
            "name": "GitHub (新)",
        }, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "GitHub (新)"

        # 4. 删除
        resp = client.delete(f"/api/v1/admin/sso/configs/{config_id}", headers=headers)
        assert resp.status_code == 200

        # 5. 确认已删除
        resp = client.get("/api/v1/admin/sso/configs", headers=headers)
        assert resp.json()["data"]["total"] == 0

    def test_sso_config_requires_admin(self, client):
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(username="normal_sso", email="n@e.com",
                               password="Pass1234", role="user")
        token = create_jwt_token(user_id=user.id, username=user.username)

        resp = client.get("/api/v1/admin/sso/configs", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 403

    def test_sso_config_create_validation(self, client, admin_token):
        token, _ = admin_token
        # 缺少 provider_type
        resp = client.post("/api/v1/admin/sso/configs", json={
            "provider_code": "github", "name": "GitHub",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

        # 非法 provider_type
        resp = client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "invalid", "provider_code": "x", "name": "X",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

        # OAuth 缺少必填字段
        resp = client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth", "provider_code": "github", "name": "GitHub",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 400

    def test_sso_bindings_list_by_user(self, client, admin_token):
        token, admin_id = admin_token
        headers = {"Authorization": f"Bearer {token}"}

        # 不传 user_id
        resp = client.get("/api/v1/admin/sso/bindings", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

        # 创建绑定
        from fnixagent.services.storage_sso import get_sso_binding_store
        binding_store = get_sso_binding_store()
        binding_store.create(user_id=admin_id, provider_code="github",
                             provider_user_id="123")

        resp = client.get(f"/api/v1/admin/sso/bindings?user_id={admin_id}",
                          headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["provider_code"] == "github"

    def test_sso_config_test_oauth(self, client, admin_token, mock_requests):
        token, _ = admin_token
        headers = {"Authorization": f"Bearer {token}"}

        # 创建 OAuth 配置
        resp = client.post("/api/v1/admin/sso/configs", json={
            "provider_type": "oauth", "provider_code": "github",
            "name": "GitHub", "client_id": "i", "client_secret": "s",
            "redirect_uri": "https://r",
        }, headers=headers)
        config_id = resp.json()["data"]["id"]

        # 测试
        resp = client.post(f"/api/v1/admin/sso/configs/{config_id}/test",
                           headers=headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_saml_login_no_config_404(self, client):
        """未配置 SAML provider 时调用 SP 发起登录返回 404。"""
        resp = client.post("/api/v1/auth/sso/saml/azure_ad/login", json={})
        assert resp.status_code == 404
