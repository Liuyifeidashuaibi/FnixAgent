"""
API 路由 - 管理后台接口(Phase 1.8)。

仅 admin 角色可访问,提供:
    1. 用户管理(列表/搜索/禁用/启用/重置密码/改角色)
    2. 审计日志查询(按时间/用户/操作类型筛选)
    3. 系统配置管理(读取 settings.yaml + 运行时热更新安全项)

安全:
    - 所有接口要求 Access Token 且角色为 admin
    - 普通用户访问返回 403
    - 重置密码生成随机临时密码(Argon2id 哈希存储)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import logging
import os
import secrets
import string
from datetime import datetime

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from fnixagent.api.routers.auth import _get_user_or_404, verify_jwt_token
from fnixagent.api.schemas.models import BaseResponse, MFAEnforcementRequest
from fnixagent.services.storage import get_user_store

_logger = logging.getLogger(__name__)



# Phase 2.5: 审计动作常量(延迟导入避免循环依赖)
def _audit_constants():
    """延迟导入审计动作常量。"""
    from fnixagent.core.audit import (
        AUDIT_CONFIG_UPDATE,
        AUDIT_DATA_DELETE,
        AUDIT_FACTOR_FORCE_DISABLED,
        AUDIT_PASSWORD_RESET,
        AUDIT_USER_DISABLE,
        AUDIT_USER_ENABLE,
        AUDIT_USER_ROLE_CHANGE,
    )

    return {
        "USER_DISABLE": AUDIT_USER_DISABLE,
        "USER_ENABLE": AUDIT_USER_ENABLE,
        "USER_ROLE_CHANGE": AUDIT_USER_ROLE_CHANGE,
        "PASSWORD_RESET": AUDIT_PASSWORD_RESET,
        "CONFIG_UPDATE": AUDIT_CONFIG_UPDATE,
        "FACTOR_FORCE_DISABLED": AUDIT_FACTOR_FORCE_DISABLED,
        "DATA_DELETE": AUDIT_DATA_DELETE,
    }


router = APIRouter(prefix="/admin", tags=["admin"])

# settings.yaml 路径(相对于项目根)
_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "config",
    "settings.yaml",
)

# 允许运行时热更新的配置键白名单(避免敏感项被改)
_HOT_RELOADABLE_KEYS = {
    "memory.short_term.max_messages",
    "memory.short_term.max_tokens",
    "tools.executor.max_concurrent",
    "tools.executor.timeout_ms",
    "tools.sandbox.timeout_ms",
    "security.sensitive_words.check_level",
    "security.injection_protection.max_attempts",
    "monitoring.log_level",
    "flywheel.stage1_perception.max_iterations",
    "flywheel.stage3_reflection.trigger_interval",
}


def require_admin(payload: dict = Depends(verify_jwt_token)) -> dict:
    """管理员鉴权中间件:校验当前用户角色为 admin,否则 403。"""
    user = _get_user_or_404(payload)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return payload


def _audit_admin(action: str, admin_payload: dict, detail: dict, http_request: Request = None):
    """写入管理员操作的审计日志(失败不影响主流程)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        ip = None
        ua = None
        if http_request:
            ua = http_request.headers.get("user-agent", "")
            forwarded = http_request.headers.get("x-forwarded-for", "")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
            else:
                ip = http_request.client.host if http_request.client else ""
        AuditLogger().log(
            action=action,
            user_id=admin_payload.get("user_id"),
            detail=detail,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)


# ===========================================================================
# 用户管理
# ===========================================================================


@router.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, description="按用户名/邮箱搜索"),
    _admin: dict = Depends(require_admin),
):
    """列出所有用户(分页 + 搜索)。"""
    store = get_user_store()
    users, total = store.list_users(limit=limit, offset=offset, search=search)
    return BaseResponse(
        success=True,
        data={
            "items": [u.to_dict() for u in users],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: int,
    http_request: Request,
    _admin: dict = Depends(require_admin),
):
    """禁用用户(立即生效,该用户无法登录)。"""
    store = get_user_store()
    if not store.set_user_disabled(user_id, True):
        raise HTTPException(status_code=404, detail="用户不存在")
    _audit_admin(
        _audit_constants()["USER_DISABLE"], _admin, {"target_user_id": user_id}, http_request
    )
    return BaseResponse(success=True, message="用户已禁用")


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: int,
    http_request: Request,
    _admin: dict = Depends(require_admin),
):
    """启用用户。"""
    store = get_user_store()
    if not store.set_user_disabled(user_id, False):
        raise HTTPException(status_code=404, detail="用户不存在")
    _audit_admin(
        _audit_constants()["USER_ENABLE"], _admin, {"target_user_id": user_id}, http_request
    )
    return BaseResponse(success=True, message="用户已启用")


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    http_request: Request,
    _admin: dict = Depends(require_admin),
):
    """重置用户密码,生成随机临时密码(返回明文,仅此一次)。"""
    store = get_user_store()
    user = store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 生成 12 位随机密码(字母+数字)
    alphabet = string.ascii_letters + string.digits
    new_password = "".join(secrets.choice(alphabet) for _ in range(12))
    if not store.update_password(user_id, new_password):
        raise HTTPException(status_code=500, detail="重置失败")
    _audit_admin(
        _audit_constants()["PASSWORD_RESET"],
        _admin,
        {"target_user_id": user_id, "username": user.username},
        http_request,
    )
    return BaseResponse(
        success=True,
        message="密码已重置,请将临时密码告知用户",
        data={"temp_password": new_password},
    )


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    http_request: Request,
    role: str = Query(..., pattern="^(user|admin)$"),
    _admin: dict = Depends(require_admin),
):
    """更新用户角色(user/admin)。"""
    store = get_user_store()
    target_user = store.get_by_id(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    old_role = target_user.role
    if not store.update_role(user_id, role):
        raise HTTPException(status_code=404, detail="用户不存在")
    _audit_admin(
        _audit_constants()["USER_ROLE_CHANGE"],
        _admin,
        {"target_user_id": user_id, "old_role": old_role, "new_role": role},
        http_request,
    )
    return BaseResponse(success=True, message=f"角色已更新为 {role}")


# ===========================================================================
# 审计日志
# ===========================================================================


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: int | None = Query(None, description="按用户 ID 筛选"),
    action: str | None = Query(None, description="按操作类型筛选"),
    start: str | None = Query(None, description="起始时间 ISO 8601"),
    end: str | None = Query(None, description="结束时间 ISO 8601"),
    _admin: dict = Depends(require_admin),
):
    """查询审计日志(按时间/用户/操作类型筛选)。"""
    from fnixagent.models.db.models import AuditLog
    from fnixagent.services.storage_postgres import get_db_adapter

    db = get_db_adapter()
    if db is None:
        # 内存模式(未配置 Postgres):无审计日志
        return BaseResponse(
            success=True,
            data={"items": [], "total": 0, "limit": limit, "offset": offset},
        )
    with db.session() as session:
        q = session.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        if action:
            q = q.filter(AuditLog.action == action)
        if start:
            try:
                start_dt = datetime.fromisoformat(start)
                q = q.filter(AuditLog.created_at >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="start 格式无效")
        if end:
            try:
                end_dt = datetime.fromisoformat(end)
                q = q.filter(AuditLog.created_at <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="end 格式无效")
        total = q.count()
        logs = q.order_by(AuditLog.id.desc()).limit(limit).offset(offset).all()
        return BaseResponse(
            success=True,
            data={
                "items": [
                    {
                        "id": log.id,
                        "user_id": log.user_id,
                        "action": log.action,
                        "detail": log.detail,
                        "trace_id": log.trace_id,
                        "created_at": log.created_at.isoformat() if log.created_at else None,
                    }
                    for log in logs
                ],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        )


# ===========================================================================
# 系统配置
# ===========================================================================


def _read_settings() -> dict:
    """读取 settings.yaml。"""
    if not os.path.exists(_SETTINGS_PATH):
        return {}
    with open(_SETTINGS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_settings(data: dict) -> None:
    """写回 settings.yaml。"""
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _get_nested(d: dict, dotted: str):
    """按点分路径取嵌套值。"""
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_nested(d: dict, dotted: str, value) -> None:
    """按点分路径设嵌套值(自动创建中间 dict)。"""
    cur = d
    parts = dotted.split(".")
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


@router.get("/config")
async def get_config(_admin: dict = Depends(require_admin)):
    """获取系统配置(读取 settings.yaml)。"""
    config = _read_settings()
    # 仅返回可热更新的项 + 元信息
    hot_keys = {}
    for key in _HOT_RELOADABLE_KEYS:
        hot_keys[key] = _get_nested(config, key)
    return BaseResponse(
        success=True,
        data={
            "hot_reloadable_keys": sorted(_HOT_RELOADABLE_KEYS),
            "current_values": hot_keys,
            "settings_path": _SETTINGS_PATH,
        },
    )


@router.patch("/config")
async def update_config(
    request: Request,
    _admin: dict = Depends(require_admin),
):
    """更新系统配置(仅白名单内的键,写回 settings.yaml 即时生效)。

    请求体:JSON,扁平点分键值对,例如:
        {"memory.short_term.max_messages": 30}
    """
    body = await request.json()
    if not isinstance(body, dict) or not body:
        raise HTTPException(status_code=400, detail="请求体需为非空 JSON 对象")
    invalid = [k for k in body if k not in _HOT_RELOADABLE_KEYS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"以下键不在可热更新白名单内: {invalid}",
        )
    config = _read_settings()
    updated = {}
    for key, value in body.items():
        _set_nested(config, key, value)
        updated[key] = value
    _write_settings(config)
    _audit_admin(
        _audit_constants()["CONFIG_UPDATE"], _admin, {"updated_keys": list(updated.keys())}, request
    )
    return BaseResponse(
        success=True,
        message="配置已更新并写回 settings.yaml(即时生效)",
        data={"updated": updated},
    )


# ===========================================================================
# Phase 2.2: LDAP/AD 域集成 - 配置管理
# ===========================================================================


@router.get("/ldap/configs")
async def list_ldap_configs(_admin: dict = Depends(require_admin)):
    """列出所有 LDAP 配置(不含密码)。"""
    from fnixagent.services.storage_ldap import get_ldap_config_store

    store = get_ldap_config_store()
    configs = store.list_configs()
    return BaseResponse(
        success=True,
        data={
            "items": [c.to_dict(include_password=False) for c in configs],
            "total": len(configs),
        },
    )


@router.post("/ldap/configs")
async def create_ldap_config(
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """新建 LDAP 配置。

    必填:name, server_url, bind_dn, bind_password, user_search_base
    可选:user_filter, group_search_base, username_attribute, email_attribute, ...
    """
    from fnixagent.services.storage_ldap import get_ldap_config_store

    # 参数校验
    required = ["name", "server_url", "bind_dn", "bind_password", "user_search_base"]
    for k in required:
        if not body.get(k):
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {k}")

    store = get_ldap_config_store()
    cfg = store.create_config(
        name=body["name"],
        server_url=body["server_url"],
        bind_dn=body["bind_dn"],
        bind_password=body["bind_password"],
        user_search_base=body["user_search_base"],
        user_filter=body.get("user_filter", "(objectClass=person)"),
        group_search_base=body.get("group_search_base", ""),
        group_filter=body.get("group_filter", "(objectClass=group)"),
        username_attribute=body.get("username_attribute", "sAMAccountName"),
        email_attribute=body.get("email_attribute", "mail"),
        display_name_attribute=body.get("display_name_attribute", "displayName"),
        use_ssl=body.get("use_ssl", False),
        use_tls=body.get("use_tls", True),
        is_active=body.get("is_active", True),
        sync_interval_hours=body.get("sync_interval_hours", 24),
    )
    return BaseResponse(success=True, data=cfg.to_dict(include_password=False))


@router.put("/ldap/configs/{config_id}")
async def update_ldap_config(
    config_id: int,
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """更新 LDAP 配置。"""
    from fnixagent.services.storage_ldap import get_ldap_config_store

    store = get_ldap_config_store()
    cfg = store.update_config(config_id, **body)
    if cfg is None:
        raise HTTPException(status_code=404, detail="LDAP 配置不存在")
    return BaseResponse(success=True, data=cfg.to_dict(include_password=False))


@router.delete("/ldap/configs/{config_id}")
async def delete_ldap_config(
    config_id: int,
    http_request: Request,
    _admin: dict = Depends(require_admin),
):
    """删除 LDAP 配置。"""
    from fnixagent.services.storage_ldap import get_ldap_config_store

    store = get_ldap_config_store()
    if not store.delete_config(config_id):
        raise HTTPException(status_code=404, detail="LDAP 配置不存在")
    _audit_admin(
        _audit_constants()["DATA_DELETE"],
        _admin,
        {"target": "ldap_config", "config_id": config_id},
        http_request,
    )
    return BaseResponse(success=True, message="LDAP 配置已删除")


@router.post("/ldap/configs/{config_id}/test")
async def test_ldap_config(
    config_id: int,
    _admin: dict = Depends(require_admin),
):
    """测试 LDAP 配置连通性(服务账号 bind)。"""
    from fnixagent.core.security.auth.ldap import LDAPClient, LDAPNotInstalledError
    from fnixagent.services.storage_ldap import get_ldap_config_store

    store = get_ldap_config_store()
    cfg = store.get_config(config_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="LDAP 配置不存在")

    try:
        client = LDAPClient(cfg.to_ldap_config())
        ok = client.test_connection()
        return BaseResponse(success=ok, message="连接成功" if ok else "连接失败")
    except LDAPNotInstalledError:
        return BaseResponse(success=False, error="ldap3 库未安装")
    except Exception as e:
        return BaseResponse(success=False, error=str(e))


@router.post("/ldap/sync")
async def sync_ldap_users(
    config_id: int | None = None,
    _admin: dict = Depends(require_admin),
):
    """手动触发 LDAP 用户同步。

    Args:
        config_id: 指定配置 ID,不传则同步所有 active 配置
    """
    from fnixagent.core.security.auth.ldap import LDAPClient, LDAPError, LDAPNotInstalledError
    from fnixagent.services.storage_ldap import get_ldap_config_store

    store = get_ldap_config_store()
    if config_id:
        cfg = store.get_config(config_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail="LDAP 配置不存在")
        targets = [cfg]
    else:
        targets = [c for c in store.list_configs() if c.is_active]

    if not targets:
        raise HTTPException(status_code=404, detail="无可同步的 LDAP 配置")

    results = []
    for cfg in targets:
        try:
            client = LDAPClient(cfg.to_ldap_config())
            stats = client.sync_users_to_local()
            store.mark_synced(cfg.id)
            results.append(
                {"config_id": cfg.id, "config_name": cfg.name, "stats": stats, "ok": True}
            )
        except LDAPNotInstalledError:
            results.append(
                {"config_id": cfg.id, "config_name": cfg.name, "ok": False, "error": "ldap3 未安装"}
            )
        except LDAPError as e:
            results.append(
                {"config_id": cfg.id, "config_name": cfg.name, "ok": False, "error": str(e)}
            )

    return BaseResponse(success=True, data={"results": results})


# ===========================================================================
# Phase 2.3: SSO 单点登录 - 配置管理
# ===========================================================================


@router.get("/sso/configs")
async def list_sso_configs(
    provider_type: str | None = Query(None, description="按类型筛选:oauth/saml"),
    _admin: dict = Depends(require_admin),
):
    """列出所有 SSO 配置(不含 secret)。"""
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    configs = store.list_configs(provider_type=provider_type)
    return BaseResponse(
        success=True,
        data={
            "items": [c.to_dict(include_secret=False) for c in configs],
            "total": len(configs),
        },
    )


@router.post("/sso/configs")
async def create_sso_config(
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """新建 SSO 配置(OAuth / SAML)。

    必填:provider_type, provider_code, name
    OAuth 必填:client_id, client_secret, redirect_uri
    SAML 必填:sp_entity_id, acs_url, idp_entity_id, idp_sso_url, idp_x509_cert
    """
    from fnixagent.services.storage_sso import get_sso_config_store

    # 参数校验
    provider_type = body.get("provider_type")
    if provider_type not in ("oauth", "saml"):
        raise HTTPException(status_code=400, detail="provider_type 必须为 oauth 或 saml")
    for k in ("provider_code", "name"):
        if not body.get(k):
            raise HTTPException(status_code=400, detail=f"缺少必填字段: {k}")

    if provider_type == "oauth":
        for k in ("client_id", "client_secret", "redirect_uri"):
            if not body.get(k):
                raise HTTPException(status_code=400, detail=f"OAuth 配置缺少必填字段: {k}")
    else:  # saml
        for k in ("sp_entity_id", "acs_url", "idp_entity_id", "idp_sso_url", "idp_x509_cert"):
            if not body.get(k):
                raise HTTPException(status_code=400, detail=f"SAML 配置缺少必填字段: {k}")

    store = get_sso_config_store()
    cfg = store.create_config(**body)
    return BaseResponse(success=True, data=cfg.to_dict(include_secret=False))


@router.put("/sso/configs/{config_id}")
async def update_sso_config(
    config_id: int,
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """更新 SSO 配置。"""
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    cfg = store.update_config(config_id, **body)
    if cfg is None:
        raise HTTPException(status_code=404, detail="SSO 配置不存在")
    return BaseResponse(success=True, data=cfg.to_dict(include_secret=False))


@router.delete("/sso/configs/{config_id}")
async def delete_sso_config(
    config_id: int,
    http_request: Request,
    _admin: dict = Depends(require_admin),
):
    """删除 SSO 配置。"""
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    if not store.delete_config(config_id):
        raise HTTPException(status_code=404, detail="SSO 配置不存在")
    _audit_admin(
        _audit_constants()["DATA_DELETE"],
        _admin,
        {"target": "sso_config", "config_id": config_id},
        http_request,
    )
    return BaseResponse(success=True, message="SSO 配置已删除")


@router.post("/sso/configs/{config_id}/test")
async def test_sso_config(
    config_id: int,
    _admin: dict = Depends(require_admin),
):
    """测试 SSO 配置(仅校验配置完整性 + 库是否安装)。"""
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    cfg = store.get_config(config_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="SSO 配置不存在")

    if cfg.provider_type == "oauth":
        # OAuth:校验必填字段 + 测试 authorize URL 可达性(可选)
        missing = [k for k in ("client_id", "client_secret", "redirect_uri") if not getattr(cfg, k)]
        if missing:
            return BaseResponse(success=False, error=f"OAuth 配置缺少字段: {missing}")
        # 尝试构建授权 URL(验证配置完整性)
        try:
            from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfigError

            client = OAuthClient(cfg.to_oauth_config())
            url = client.build_authorization_url(state="test")
            return BaseResponse(
                success=True,
                message="OAuth 配置有效",
                data={"authorize_url_prefix": url.split("?")[0]},
            )
        except OAuthConfigError as e:
            return BaseResponse(success=False, error=str(e))
        except Exception as e:
            return BaseResponse(success=False, error=f"测试异常: {e}")
    else:  # saml
        # SAML:校验必填字段 + 检查 python3-saml 是否安装
        missing = [
            k
            for k in ("sp_entity_id", "acs_url", "idp_entity_id", "idp_sso_url", "idp_x509_cert")
            if not getattr(cfg, k)
        ]
        if missing:
            return BaseResponse(success=False, error=f"SAML 配置缺少字段: {missing}")
        try:
            from fnixagent.core.security.auth.saml import SAMLClient, SAMLNotInstalledError

            client = SAMLClient(cfg.to_saml_config())
            # 触发延迟导入以检查库是否可用
            client._import_saml()
            return BaseResponse(success=True, message="SAML 配置有效,python3-saml 已安装")
        except SAMLNotInstalledError:
            return BaseResponse(success=False, error="python3-saml 库未安装")
        except Exception as e:
            return BaseResponse(success=False, error=f"测试异常: {e}")


@router.get("/sso/bindings")
async def list_sso_bindings(
    user_id: int | None = Query(None, description="按用户 ID 筛选"),
    _admin: dict = Depends(require_admin),
):
    """查询用户的 SSO 绑定关系。"""
    from fnixagent.services.storage_sso import get_sso_binding_store

    store = get_sso_binding_store()
    if user_id is None:
        # 不传 user_id 时返回提示(避免全表扫描,绑定表通常按用户查询)
        return BaseResponse(
            success=True, data={"items": [], "total": 0, "message": "请提供 user_id 查询参数"}
        )
    bindings = store.list_by_user(user_id)
    return BaseResponse(
        success=True,
        data={"items": [b.to_dict() for b in bindings], "total": len(bindings)},
    )


@router.delete("/sso/bindings/{binding_id}")
async def delete_sso_binding(
    binding_id: int,
    _admin: dict = Depends(require_admin),
):
    """删除 SSO 绑定关系(解绑)。"""
    from fnixagent.services.storage_sso import get_sso_binding_store

    store = get_sso_binding_store()
    if not store.delete(binding_id):
        raise HTTPException(status_code=404, detail="SSO 绑定不存在")
    return BaseResponse(success=True, message="SSO 绑定已解除")


# ===========================================================================
# Phase 2.4: MFA 管理(强制策略 + 用户因子管理)
# ===========================================================================


@router.get("/mfa/enforcements")
async def list_mfa_enforcements(_admin: dict = Depends(require_admin)):
    """列出所有 MFA 强制策略。"""
    from fnixagent.services.storage_mfa import get_mfa_enforcement_store

    store = get_mfa_enforcement_store()
    items = store.list_all()
    return BaseResponse(
        success=True,
        data={"items": [e.to_dict() for e in items], "total": len(items)},
    )


@router.post("/mfa/enforcements")
async def upsert_mfa_enforcement(
    body: MFAEnforcementRequest,
    _admin: dict = Depends(require_admin),
):
    """创建或更新 MFA 强制策略(按角色)。

    示例:管理员要求 admin 角色必须开启 TOTP MFA:
        POST /admin/mfa/enforcements
        {"role": "admin", "factor_type": "totp", "enabled": true}
    """
    from fnixagent.services.storage_mfa import get_mfa_enforcement_store

    store = get_mfa_enforcement_store()
    e = store.upsert(role=body.role, factor_type=body.factor_type, enabled=body.enabled)
    action = "已更新" if e.updated_at and e.created_at != e.updated_at else "已创建"
    return BaseResponse(success=True, message=f"MFA 强制策略{action}", data=e.to_dict())


@router.delete("/mfa/enforcements/{enforcement_id}")
async def delete_mfa_enforcement(
    enforcement_id: int,
    _admin: dict = Depends(require_admin),
):
    """删除 MFA 强制策略。"""
    from fnixagent.services.storage_mfa import get_mfa_enforcement_store

    store = get_mfa_enforcement_store()
    if not store.delete(enforcement_id):
        raise HTTPException(status_code=404, detail="强制策略不存在")
    return BaseResponse(success=True, message="强制策略已删除")


@router.get("/mfa/users/{user_id}/factors")
async def admin_list_user_factors(
    user_id: int,
    _admin: dict = Depends(require_admin),
):
    """管理员查看指定用户的 MFA 因子(不含 secret)。"""
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_recovery_code_store,
    )

    factor_store = get_mfa_factor_store()
    recovery_store = get_recovery_code_store()

    user = get_user_store().get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    factors = factor_store.list_by_user(user_id)
    unused = recovery_store.count_unused(user_id)

    return BaseResponse(
        success=True,
        data={
            "user_id": user_id,
            "username": user.username,
            "factors": [f.to_dict(include_secret=False) for f in factors],
            "recovery_codes_remaining": unused,
            "mfa_enabled": any(f.enabled for f in factors),
        },
    )


@router.delete("/mfa/factors/{factor_id}")
async def admin_disable_factor(
    factor_id: int,
    http_request: Request,
    _admin: dict = Depends(require_admin),
):
    """管理员强制禁用用户的指定 MFA 因子(应急用,如用户手机丢失)。

    若禁用后用户没有任何启用的因子,同时清除恢复码 + 更新 profile。
    """
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_recovery_code_store,
    )

    factor_store = get_mfa_factor_store()
    recovery_store = get_recovery_code_store()

    factor = factor_store.get(factor_id)
    if not factor:
        raise HTTPException(status_code=404, detail="因子不存在")

    user_id = factor.user_id
    factor_type = factor.factor_type
    factor_store.delete(factor_id)

    remaining = factor_store.list_by_user(user_id, include_disabled=False)
    if not remaining:
        recovery_store.delete_all_by_user(user_id)
        user_store = get_user_store()
        user_store.update_profile(user_id, {"mfa_enabled": False})

    _audit_admin(
        _audit_constants()["FACTOR_FORCE_DISABLED"],
        _admin,
        {"target_user_id": user_id, "factor_id": factor_id, "factor_type": factor_type},
        http_request,
    )
    return BaseResponse(
        success=True,
        message="MFA 因子已被管理员禁用" + (",用户已无任何 MFA 因子" if not remaining else ""),
    )


# ===========================================================================
# Phase 2.3 (P2-03): 配置热更新管理
# ===========================================================================


def _config_manager():
    """延迟导入配置热更新管理器单例(避免循环依赖)。"""
    from fnixagent.core.config_watcher import get_config_manager

    return get_config_manager()


def _operator_from(admin_payload: dict) -> str:
    """从 admin JWT payload 提取操作者标识。"""
    return str(admin_payload.get("user_id", "system"))


@router.post("/config/rate-limit-rule")
async def add_rate_limit_rule(
    request: Request,
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """添加限流规则(P2-03 热更新)。

    请求体:
        {
            "prefix": "/api/v1/chat",
            "qps": 5.0,                  # 可选
            "concurrency": 10,           # 可选
            "min_interval": 0.5          # 可选(秒)
        }
    """
    from fnixagent.core.governance import EndpointRule

    prefix = body.get("prefix")
    if not prefix or not isinstance(prefix, str):
        raise HTTPException(status_code=400, detail="prefix 必填且为字符串")
    rule = EndpointRule(
        prefix=prefix,
        qps=body.get("qps"),
        concurrency=body.get("concurrency"),
        min_interval=body.get("min_interval"),
    )
    operator = _operator_from(_admin)
    ok = _config_manager().add_rate_limit_rule(rule, operator=operator)
    if not ok:
        raise HTTPException(status_code=500, detail="添加限流规则失败")
    _audit_admin(
        _audit_constants()["CONFIG_UPDATE"],
        _admin,
        {"target": "rate_limit_rule", "action": "add", "prefix": prefix},
        request,
    )
    return BaseResponse(success=True, message="限流规则已添加", data={"prefix": prefix})


@router.delete("/config/rate-limit-rule/{prefix:path}")
async def remove_rate_limit_rule(
    prefix: str,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    """移除限流规则(P2-03 热更新)。

    路径参数 prefix 为端点规则前缀(支持含斜杠的 URL 前缀)。
    若传入的前缀无前导斜杠且未命中,会自动补斜杠重试一次。
    """
    mgr = _config_manager()
    operator = _operator_from(_admin)
    ok = mgr.remove_rate_limit_rule(prefix, operator=operator)
    # 兼容前导斜杠:URL 路径可能剥离了前导 /,尝试补回
    if not ok and not prefix.startswith("/"):
        ok = mgr.remove_rate_limit_rule("/" + prefix, operator=operator)
        prefix = "/" + prefix
    if not ok:
        raise HTTPException(status_code=404, detail=f"限流规则不存在: {prefix}")
    _audit_admin(
        _audit_constants()["CONFIG_UPDATE"],
        _admin,
        {"target": "rate_limit_rule", "action": "remove", "prefix": prefix},
        request,
    )
    return BaseResponse(success=True, message="限流规则已移除")


@router.post("/config/guardrail/{name}/enable")
async def enable_guardrail(
    name: str,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    """启用指定护栏(P2-03 热更新)。"""
    operator = _operator_from(_admin)
    ok = _config_manager().enable_guardrail(name, operator=operator)
    if not ok:
        raise HTTPException(status_code=404, detail=f"护栏不存在: {name}")
    _audit_admin(
        _audit_constants()["CONFIG_UPDATE"],
        _admin,
        {"target": "guardrail", "action": "enable", "name": name},
        request,
    )
    return BaseResponse(success=True, message=f"护栏 {name} 已启用")


@router.post("/config/guardrail/{name}/disable")
async def disable_guardrail(
    name: str,
    request: Request,
    _admin: dict = Depends(require_admin),
):
    """禁用指定护栏(P2-03 热更新)。"""
    operator = _operator_from(_admin)
    ok = _config_manager().disable_guardrail(name, operator=operator)
    if not ok:
        raise HTTPException(status_code=404, detail=f"护栏不存在: {name}")
    _audit_admin(
        _audit_constants()["CONFIG_UPDATE"],
        _admin,
        {"target": "guardrail", "action": "disable", "name": name},
        request,
    )
    return BaseResponse(success=True, message=f"护栏 {name} 已禁用")


@router.get("/config/history")
async def get_config_history(
    module: str | None = Query(
        None, description="按模块筛选: rate_limit/guardrail/expert_route/autoscale"
    ),
    limit: int = Query(20, ge=1, le=200),
    _admin: dict = Depends(require_admin),
):
    """获取配置变更历史(P2-03)。"""
    changes = _config_manager().get_history(module=module, limit=limit)
    return BaseResponse(
        success=True,
        data={
            "items": [
                {
                    "timestamp": c.timestamp,
                    "module": c.module,
                    "action": c.action,
                    "target": c.target,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "operator": c.operator,
                }
                for c in changes
            ],
            "total": len(changes),
        },
    )


@router.post("/config/rollback")
async def rollback_config(
    request: Request,
    _admin: dict = Depends(require_admin),
):
    """回滚配置变更(P2-03,best-effort)。

    请求体(可选):
        {"steps": 1}   # 回滚步数,默认 1
    """
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    steps = body.get("steps", 1) if isinstance(body, dict) else 1
    if not isinstance(steps, int) or steps < 1:
        raise HTTPException(status_code=400, detail="steps 必须为正整数")
    ok = _config_manager().rollback(steps=steps)
    _audit_admin(
        _audit_constants()["CONFIG_UPDATE"],
        _admin,
        {"target": "config_rollback", "steps": steps, "success": ok},
        request,
    )
    if not ok:
        return BaseResponse(
            success=False,
            message="回滚部分失败(详见日志)",
            data={"steps": steps},
        )
    return BaseResponse(success=True, message=f"已回滚 {steps} 步", data={"steps": steps})


@router.get("/config/hotreload/stats")
async def get_hotreload_stats(_admin: dict = Depends(require_admin)):
    """获取配置热更新统计信息(P2-03)。"""
    return BaseResponse(success=True, data=_config_manager().get_stats())
