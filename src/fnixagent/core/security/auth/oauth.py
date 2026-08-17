"""
OAuth2.0 单点登录客户端(Phase 2.3)。

支持:
    1. GitHub OAuth(开箱即用 preset)
    2. Google OAuth(开箱即用 preset)
    3. 通用 OAuth2.0 Authorization Code Flow(企业 IdP)
    4. 用户信息按 provider_user_id 或 email 绑定到本地

设计要点:
    - requests 为延迟导入(若未安装时抛 OAuthNotInstalledError)
    - 所有 provider 配置由 storage_sso 管理,此处只负责协议交互
    - state 参数用于 CSRF 防护(调用方需自行校验)
    - 用户信息字段映射可配置(GitHub/Google 字段不同)
    - 认证失败统一抛 OAuthError,由调用方决定 HTTP 响应

依赖:requests>=2.28
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from fnixagent.services.storage import get_user_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class OAuthError(Exception):
    """OAuth 操作异常基类。"""


class OAuthConnectionError(OAuthError):
    """连接 OAuth 服务失败(网络/HTTP 错误)。"""


class OAuthAuthenticationError(OAuthError):
    """OAuth 认证失败(code 无效 / token 拒绝)。"""


class OAuthNotInstalledError(OAuthError):
    """requests 库未安装。"""


class OAuthConfigError(OAuthError):
    """OAuth 配置错误(缺字段 / provider 未知)。"""


# ---------------------------------------------------------------------------
# 内置 Provider 预设
# ---------------------------------------------------------------------------


@dataclass
class OAuthProviderPreset:
    """OAuth provider 预设(端点 URL + 字段映射)。"""

    code: str
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    default_scopes: list[str]
    # 字段映射:userinfo JSON 字段 → 标准字段
    field_mapping: dict[str, str] = field(default_factory=dict)


# 内置 Provider 预设表
BUILTIN_PRESETS: dict[str, OAuthProviderPreset] = {
    "github": OAuthProviderPreset(
        code="github",
        name="GitHub",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        userinfo_url="https://api.github.com/user",
        default_scopes=["read:user", "user:email"],
        field_mapping={
            "id": "id",  # provider_user_id
            "login": "username",
            "email": "email",
            "name": "display_name",
            "avatar_url": "avatar_url",
        },
    ),
    "google": OAuthProviderPreset(
        code="google",
        name="Google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v3/userinfo",
        default_scopes=["openid", "email", "profile"],
        field_mapping={
            "sub": "id",  # provider_user_id
            "email": "email",
            "name": "display_name",
            "picture": "avatar_url",
            # Google 用 email 前缀作用户名
        },
    ),
    # 通用 OAuth2(企业 IdP 自填端点)
    "generic": OAuthProviderPreset(
        code="generic",
        name="Generic OAuth2",
        authorize_url="",
        token_url="",
        userinfo_url="",
        default_scopes=[],
        field_mapping={
            "id": "id",
            "username": "username",
            "email": "email",
            "name": "display_name",
        },
    ),
}


# ---------------------------------------------------------------------------
# 配置 DTO
# ---------------------------------------------------------------------------


@dataclass
class OAuthConfig:
    """OAuth provider 配置(与 storage_sso.SSOConfigDTO 对应)。"""

    id: int
    provider_type: str  # "oauth"
    provider_code: str  # "github" / "google" / 自定义
    name: str  # 显示名
    client_id: str
    client_secret: str
    redirect_uri: str  # 回调地址
    scopes: list[str] = field(default_factory=list)
    # 通用 IdP 必填端点(provider_code 为 generic 时使用)
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    # 字段映射覆盖(可选):provider 原始字段 → 标准字段
    field_mapping: dict[str, str] = field(default_factory=dict)
    is_active: bool = True
    created_at: Any | None = None
    updated_at: Any | None = None

    def get_preset(self) -> OAuthProviderPreset:
        """获取内置 preset(若 provider_code 在 BUILTIN_PRESETS 中)。"""
        return BUILTIN_PRESETS.get(self.provider_code, BUILTIN_PRESETS["generic"])

    def get_authorize_url(self) -> str:
        return self.authorize_url or self.get_preset().authorize_url

    def get_token_url(self) -> str:
        return self.token_url or self.get_preset().token_url

    def get_userinfo_url(self) -> str:
        return self.userinfo_url or self.get_preset().userinfo_url

    def get_scopes(self) -> list[str]:
        return self.scopes or self.get_preset().default_scopes

    def get_field_mapping(self) -> dict[str, str]:
        """合并 preset 默认映射 + 用户自定义覆盖。"""
        merged = dict(self.get_preset().field_mapping)
        merged.update(self.field_mapping or {})
        return merged


@dataclass
class OAuthUserInfo:
    """OAuth 用户信息(标准化后)。"""

    provider_code: str
    provider_user_id: str  # provider 端的唯一 ID(GitHub id / Google sub)
    username: str = ""
    email: str = ""
    display_name: str = ""
    avatar_url: str = ""
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# OAuth 客户端
# ---------------------------------------------------------------------------


class OAuthClient:
    """OAuth2.0 客户端(封装 Authorization Code Flow)。

    用法:
        client = OAuthClient(config)
        url = client.build_authorization_url(state="random-state")
        # ... 用户授权后回调 ...
        token = client.exchange_code(code, state)
        user_info = client.fetch_userinfo(token["access_token"])
        local_user = client.sync_user_to_local(user_info)
    """

    def __init__(self, config: OAuthConfig):
        self.config = config

    def _import_requests(self):
        """延迟导入 requests。"""
        try:
            import requests

            return requests
        except ImportError as e:
            raise OAuthNotInstalledError("requests 库未安装,请运行 pip install requests") from e

    @staticmethod
    def generate_state() -> str:
        """生成随机 state(用于 CSRF 防护)。"""
        return secrets.token_urlsafe(24)

    def build_authorization_url(self, state: str) -> str:
        """构建授权 URL(用户跳转到此 URL 完成授权)。"""
        from urllib.parse import urlencode, urlsplit, urlunsplit

        cfg = self.config
        authorize_url = cfg.get_authorize_url()
        if not authorize_url:
            raise OAuthConfigError(f"OAuth provider {cfg.provider_code} 缺少 authorize_url")

        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "state": state,
        }
        scopes = cfg.get_scopes()
        if scopes:
            params["scope"] = " ".join(scopes)

        # 拼接到 authorize_url(保留原 URL 的 query string)
        parts = urlsplit(authorize_url)
        existing_query = parts.query
        new_query = urlencode(params)
        if existing_query:
            new_query = f"{existing_query}&{new_query}"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    def exchange_code(self, code: str, state: str | None = None) -> dict:
        """用授权码换取 access_token(POST 到 token 端点)。

        Returns:
            token 响应 dict(access_token / token_type / scope / ...)
        """
        requests = self._import_requests()

        cfg = self.config
        token_url = cfg.get_token_url()
        if not token_url:
            raise OAuthConfigError(f"OAuth provider {cfg.provider_code} 缺少 token_url")

        data = {
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {"Accept": "application/json"}
        # GitHub 的 token 端点默认返回 application/json,但要带 Accept 头

        try:
            resp = requests.post(token_url, data=data, headers=headers, timeout=15)
        except Exception as e:
            raise OAuthConnectionError(f"连接 token 端点失败: {e}") from e

        if resp.status_code != 200:
            raise OAuthAuthenticationError(f"token 端点返回 {resp.status_code}: {resp.text[:200]}")

        try:
            token_data = resp.json()
        except ValueError as e:
            raise OAuthAuthenticationError(f"token 响应非 JSON: {resp.text[:200]}") from e

        if "access_token" not in token_data:
            err = token_data.get("error_description") or token_data.get("error")
            raise OAuthAuthenticationError(f"未获取到 access_token: {err}")

        return token_data

    def fetch_userinfo(self, access_token: str) -> dict:
        """用 access_token 拉取用户信息。"""
        requests = self._import_requests()

        cfg = self.config
        userinfo_url = cfg.get_userinfo_url()
        if not userinfo_url:
            raise OAuthConfigError(f"OAuth provider {cfg.provider_code} 缺少 userinfo_url")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            resp = requests.get(userinfo_url, headers=headers, timeout=15)
        except Exception as e:
            raise OAuthConnectionError(f"连接 userinfo 端点失败: {e}") from e

        if resp.status_code != 200:
            raise OAuthAuthenticationError(
                f"userinfo 端点返回 {resp.status_code}: {resp.text[:200]}"
            )

        try:
            return resp.json()
        except ValueError as e:
            raise OAuthAuthenticationError(f"userinfo 响应非 JSON: {resp.text[:200]}") from e

    def normalize_userinfo(self, raw: dict) -> OAuthUserInfo:
        """将 provider 原始用户信息标准化(按 field_mapping)。"""
        mapping = self.config.get_field_mapping()

        def _get_field(std_field: str) -> str:
            """通过反向映射取值。"""
            for raw_field, target in mapping.items():
                if target == std_field:
                    return str(raw.get(raw_field, "") or "")
            return ""

        provider_user_id = _get_field("id")
        if not provider_user_id:
            # 兜底:用 username 或 email 作为 provider_user_id
            provider_user_id = _get_field("username") or _get_field("email")

        username = _get_field("username")
        if not username:
            email = _get_field("email")
            if email and "@" in email:
                username = email.split("@")[0]
            else:
                username = provider_user_id

        return OAuthUserInfo(
            provider_code=self.config.provider_code,
            provider_user_id=provider_user_id,
            username=username,
            email=_get_field("email"),
            display_name=_get_field("display_name") or username,
            avatar_url=_get_field("avatar_url"),
            raw=raw,
        )

    def authenticate(self, code: str, state: str | None = None) -> OAuthUserInfo:
        """端到端认证:换 token + 拉用户信息 + 标准化。

        Returns:
            OAuthUserInfo(标准化后的用户信息)
        """
        token_data = self.exchange_code(code, state)
        access_token = token_data["access_token"]
        raw = self.fetch_userinfo(access_token)
        return self.normalize_userinfo(raw)

    def sync_user_to_local(self, oauth_user: OAuthUserInfo):
        """将 OAuth 用户同步到本地(按 provider_user_id 或 email 绑定)。

        绑定优先级:
            1. 按 (provider_code, provider_user_id) 查 SSO 绑定 → 已绑定则直接返回用户
            2. 按 email 查本地用户 → 存在则创建绑定 + 返回用户
            3. 创建新用户(随机密码)+ 创建绑定
        """
        from fnixagent.services.storage_sso import get_sso_binding_store

        binding_store = get_sso_binding_store()
        user_store = get_user_store()

        # 1. 查绑定
        binding = binding_store.get_by_provider(
            provider_code=oauth_user.provider_code,
            provider_user_id=oauth_user.provider_user_id,
        )
        if binding is not None:
            local_user = user_store.get_by_id(binding.user_id)
            if local_user is not None:
                # 更新 profile(若需要)
                profile = local_user.profile or {}
                needs_update = (
                    profile.get("display_name") != oauth_user.display_name
                    or profile.get("avatar_url") != oauth_user.avatar_url
                )
                if needs_update:
                    user_store.update_profile(
                        local_user.id,
                        {
                            **profile,
                            "display_name": oauth_user.display_name,
                            "avatar_url": oauth_user.avatar_url,
                            "source": "oauth",
                            "oauth_provider": oauth_user.provider_code,
                        },
                    )
                return local_user
            else:
                # 绑定存在但用户被删除 → 清理绑定,继续走创建流程
                binding_store.delete(binding.id)

        # 2. 按 email 查本地用户
        if oauth_user.email:
            local_user = user_store.get_by_email(oauth_user.email)
            if local_user is not None:
                # 创建绑定 + 更新 profile
                binding_store.create(
                    user_id=local_user.id,
                    provider_code=oauth_user.provider_code,
                    provider_user_id=oauth_user.provider_user_id,
                )
                profile = local_user.profile or {}
                user_store.update_profile(
                    local_user.id,
                    {
                        **profile,
                        "source": "oauth",
                        "oauth_provider": oauth_user.provider_code,
                        "display_name": oauth_user.display_name,
                        "avatar_url": oauth_user.avatar_url,
                    },
                )
                return local_user

        # 3. 创建新用户(随机密码,OAuth 用户不需要本地密码)
        import secrets as _sec
        import string as _str

        random_pw = "".join(_sec.choice(_str.ascii_letters + _str.digits) for _ in range(32))
        username = oauth_user.username or (
            oauth_user.email.split("@")[0] if oauth_user.email else f"oauth_{_sec.token_hex(4)}"
        )
        # 用户名冲突时附加随机后缀
        if user_store.get_by_username(username):
            username = f"{username}_{_sec.token_hex(3)}"

        local_user, err = user_store.create(
            username=username,
            email=oauth_user.email,
            password=random_pw,
            role="user",
        )
        if not local_user:
            raise OAuthError(f"创建本地用户失败: {err}")

        # 创建绑定 + 写 profile
        binding_store.create(
            user_id=local_user.id,
            provider_code=oauth_user.provider_code,
            provider_user_id=oauth_user.provider_user_id,
        )
        user_store.update_profile(
            local_user.id,
            {
                "source": "oauth",
                "oauth_provider": oauth_user.provider_code,
                "display_name": oauth_user.display_name,
                "avatar_url": oauth_user.avatar_url,
            },
        )
        return local_user
