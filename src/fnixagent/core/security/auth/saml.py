"""
SAML 2.0 Service Provider(SP)客户端(Phase 2.3)。

支持:
    1. SP 发起的 SSO(AuthnRequest 重定向到 IdP)
    2. IdP 发起的 SSO(IdP 直接 POST SAMLResponse 到 ACS)
    3. 对接 Azure AD / Okta / 任意 SAML 2.0 兼容 IdP
    4. 用户信息按 name_id 或 email 绑定到本地

设计要点:
    - python3-saml 为延迟导入,未安装时抛 SAMLNotInstalledError(不阻断启动)
    - SAML 配置由 storage_sso 管理,此处只负责协议交互
    - SAMLResponse 解析时验签 + 校验时效 + 校验受众
    - 用户信息字段映射可配置(各 IdP claim 名称不同)

依赖:python3-saml>=1.16(可选)
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any, Optional

from fnixagent.services.storage import get_user_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SAMLError(Exception):
    """SAML 操作异常基类。"""


class SAMLNotInstalledError(SAMLError):
    """python3-saml 库未安装。"""


class SAMLConfigError(SAMLError):
    """SAML 配置错误(缺字段 / IdP 元数据无效)。"""


class SAMLResponseError(SAMLError):
    """SAML Response 解析 / 验签失败。"""


# ---------------------------------------------------------------------------
# 配置 DTO
# ---------------------------------------------------------------------------


@dataclass
class SAMLConfig:
    """SAML SP 配置(与 storage_sso.SSOConfigDTO 对应)。"""
    id: int
    provider_type: str               # "saml"
    provider_code: str               # 自定义标识(如 azure_ad / okta)
    name: str                        # 显示名
    # SP 端配置
    sp_entity_id: str                # SP Entity ID(通常为 ACS URL)
    acs_url: str                     # Assertion Consumer Service URL
    # IdP 端配置
    idp_entity_id: str = ""
    idp_sso_url: str = ""            # IdP Single Sign-On Service URL(用于重定向)
    idp_x509_cert: str = ""          # IdP 公钥证书(用于验签,PEM 内容)
    # 用户信息字段映射(IdP claim → 标准字段)
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    field_mapping: dict[str, str] = field(default_factory=dict)
    is_active: bool = True
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None


@dataclass
class SAMLUserInfo:
    """SAML 用户信息(标准化后)。"""
    provider_code: str
    name_id: str                     # SAML NameID(通常为邮箱或用户名)
    username: str = ""
    email: str = ""
    display_name: str = ""
    raw_attributes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SAML 客户端
# ---------------------------------------------------------------------------


class SAMLClient:
    """SAML 2.0 SP 客户端(封装 python3-saml)。

    用法:
        client = SAMLClient(config)
        authn_request = client.build_authn_request(state="random")
        # ... 用户在 IdP 完成认证,IdP POST SAMLResponse 到 ACS ...
        user_info = client.parse_response(saml_response_xml)
        local_user = client.sync_user_to_local(user_info)
    """

    def __init__(self, config: SAMLConfig):
        self.config = config

    def _import_saml(self):
        """延迟导入 python3-saml。

        python3-saml 包导出 onelogin.saml2.auth.OneLogin_Saml2_Auth。
        """
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth
            from onelogin.saml2.utils import OneLogin_Saml2_Utils
            return OneLogin_Saml2_Auth, OneLogin_Saml2_Utils
        except ImportError as e:
            raise SAMLNotInstalledError(
                "python3-saml 库未安装,请运行 pip install python3-saml"
            ) from e

    def _build_settings(self) -> dict:
        """构建 python3-saml 的 settings dict。"""
        cfg = self.config
        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": cfg.sp_entity_id,
                "assertionConsumerService": {
                    "url": cfg.acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
            },
            "idp": {
                "entityId": cfg.idp_entity_id,
                "singleSignOnService": {
                    "url": cfg.idp_sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": cfg.idp_x509_cert,
            },
        }

    @staticmethod
    def generate_state() -> str:
        """生成随机 state(用于 CSRF 防护 / RelayState)。"""
        return secrets.token_urlsafe(24)

    def _make_auth(self, request_dict: dict):
        """构造 OneLogin_Saml2_Auth 实例。

        Args:
            request_dict: python3-saml 需要的 request 信息 dict,含:
                - https: bool(是否 https)
                - http_host: str
                - server_port: int
                - script_name: str
                - get_data: dict
                - post_data: dict
        """
        OneLogin_Saml2_Auth, _ = self._import_saml()
        return OneLogin_Saml2_Auth(request_dict, old_settings=self._build_settings())

    def build_authn_request(self, request_dict: Optional[dict] = None,
                             state: Optional[str] = None) -> dict:
        """构建 SP 发起的 AuthnRequest,返回重定向信息。

        Returns:
            {
                "redirect_url": str,  # IdP 登录 URL(带 SAMLRequest)
                "state": str,         # RelayState(用于 CSRF / 回调上下文)
            }
        """
        if request_dict is None:
            request_dict = {"https": False, "http_host": "", "server_port": 80,
                             "script_name": "", "get_data": {}, "post_data": {}}
        if state is None:
            state = self.generate_state()

        auth = self._make_auth(request_dict)
        redirect_url = auth.login(return_to=state)
        return {"redirect_url": redirect_url, "state": state}

    def parse_response(self, saml_response: str,
                       request_dict: Optional[dict] = None) -> SAMLUserInfo:
        """解析 IdP POST 的 SAMLResponse,返回标准化用户信息。

        Args:
            saml_response: Base64 编码的 SAMLResponse(从 IdP POST 表单取)
            request_dict: 可选,python3-saml 需要的 request 信息

        Raises:
            SAMLResponseError: 验签失败 / 时效过期 / 受众不匹配
        """
        if request_dict is None:
            request_dict = {
                "https": False, "http_host": "", "server_port": 80,
                "script_name": "", "get_data": {},
                "post_data": {"SAMLResponse": saml_response},
            }
        else:
            request_dict = {**request_dict,
                            "post_data": {"SAMLResponse": saml_response}}

        auth = self._make_auth(request_dict)
        try:
            auth.process_response()
        except Exception as e:
            raise SAMLResponseError(f"SAML Response 处理失败: {e}") from e

        if not auth.is_authenticated():
            errors = auth.get_errors()
            err_msg = auth.get_last_error_reason() or "; ".join(errors)
            raise SAMLResponseError(f"SAML 认证失败: {err_msg}")

        # 提取属性
        name_id = auth.get_nameid() or ""
        attrs = auth.get_attributes() or {}
        # python3-saml 返回的属性值通常是 list
        flat_attrs = {k: (v[0] if isinstance(v, list) and v else v) for k, v in attrs.items()}

        # 标准化(按 field_mapping)
        mapping = self.config.field_mapping or {
            "email": "email",
            "name": "display_name",
            "username": "username",
        }

        def _get_field(std_field: str) -> str:
            for raw_field, target in mapping.items():
                if target == std_field:
                    return str(flat_attrs.get(raw_field, "") or "")
            return ""

        email = _get_field("email") or (name_id if "@" in name_id else "")
        username = _get_field("username") or (
            email.split("@")[0] if email else name_id
        )
        display_name = _get_field("display_name") or username

        return SAMLUserInfo(
            provider_code=self.config.provider_code,
            name_id=name_id,
            username=username,
            email=email,
            display_name=display_name,
            raw_attributes=flat_attrs,
        )

    def sync_user_to_local(self, saml_user: SAMLUserInfo):
        """将 SAML 用户同步到本地(按 name_id 或 email 绑定)。

        绑定优先级:
            1. 按 (provider_code, provider_user_id=name_id) 查 SSO 绑定
            2. 按 email 查本地用户 → 存在则创建绑定
            3. 创建新用户(随机密码)+ 创建绑定
        """
        from fnixagent.services.storage_sso import get_sso_binding_store

        binding_store = get_sso_binding_store()
        user_store = get_user_store()

        # 1. 查绑定(provider_user_id 即 name_id)
        binding = binding_store.get_by_provider(
            provider_code=saml_user.provider_code,
            provider_user_id=saml_user.name_id,
        )
        if binding is not None:
            local_user = user_store.get_by_id(binding.user_id)
            if local_user is not None:
                # 更新 profile(若需要)
                profile = local_user.profile or {}
                needs_update = (
                    profile.get("display_name") != saml_user.display_name
                )
                if needs_update:
                    user_store.update_profile(local_user.id, {
                        **profile,
                        "display_name": saml_user.display_name,
                        "source": "saml",
                        "saml_provider": saml_user.provider_code,
                    })
                return local_user
            else:
                binding_store.delete(binding.id)

        # 2. 按 email 查本地用户
        if saml_user.email:
            local_user = user_store.get_by_email(saml_user.email)
            if local_user is not None:
                binding_store.create(
                    user_id=local_user.id,
                    provider_code=saml_user.provider_code,
                    provider_user_id=saml_user.name_id,
                )
                profile = local_user.profile or {}
                user_store.update_profile(local_user.id, {
                    **profile,
                    "source": "saml",
                    "saml_provider": saml_user.provider_code,
                    "display_name": saml_user.display_name,
                })
                return local_user

        # 3. 创建新用户(随机密码)
        import secrets as _sec
        import string as _str
        random_pw = "".join(
            _sec.choice(_str.ascii_letters + _str.digits) for _ in range(32)
        )
        username = saml_user.username or (
            saml_user.email.split("@")[0] if saml_user.email
            else f"saml_{_sec.token_hex(4)}"
        )
        if user_store.get_by_username(username):
            username = f"{username}_{_sec.token_hex(3)}"

        local_user, err = user_store.create(
            username=username,
            email=saml_user.email,
            password=random_pw,
            role="user",
        )
        if not local_user:
            raise SAMLError(f"创建本地用户失败: {err}")

        binding_store.create(
            user_id=local_user.id,
            provider_code=saml_user.provider_code,
            provider_user_id=saml_user.name_id,
        )
        user_store.update_profile(local_user.id, {
            "source": "saml",
            "saml_provider": saml_user.provider_code,
            "display_name": saml_user.display_name,
        })
        return local_user
