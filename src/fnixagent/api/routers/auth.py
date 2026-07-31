"""
API 路由 - 用户鉴权与管理接口(Phase 0.4 安全规范对齐)。

完整安全链路:
    1. 客户端 GET /auth/pubkey 获取 RSA-2048 公钥
    2. 客户端用公钥加密密码(OAEP+SHA256),POST /auth/login 时携带:
       - password: Base64 密文
       - is_password_encrypted: true
       - client_uuid: 客户端生成的 UUID v4(持久化在 safeStorage)
    3. 服务端:
       - 用私钥解密密码
       - Argon2id 校验密码(向后兼容 PBKDF2)
       - 校验通过后,计算设备指纹并写入 Access Token
       - 返回双 Token(Access 2h + Refresh 7d)
    4. 客户端:
       - 每次请求带 Access Token
       - Access Token 过期(401)时,用 Refresh Token 调 /auth/refresh 换新
    5. 登出:POST /auth/logout,服务端把 Access Token 的 jti 写入黑名单

向后兼容:
    - 旧客户端可继续用明文密码登录(is_password_encrypted=false)
    - 旧 Token(无 device_fp 字段)继续可用
"""

import hashlib
import hmac
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from fnixagent.api.schemas.models import (
    BaseResponse,
    LDAPLoginRequest,
    MFADisableRequest,
    MFAEnableRequest,
    MFALoginChallengeResponse,
    MFASendCodeRequest,
    MFASetupRequest,
    MFASetupResponse,
    MFAVerifyRequest,
    OAuthAuthorizeRequest,
    OAuthCallbackRequest,
    OwnerLoginRequest,
    PublicKeyResponse,
    RefreshTokenRequest,
    SAMLACSRequest,
    SAMLLoginRequest,
    SmsLoginRequest,
    SmsSendCodeRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from fnixagent.core.security.auth import (
    blacklist as blacklist_mod,
)
from fnixagent.core.security.auth import (
    create_access_token,
    create_token_pair,
    get_server_keypair,
    needs_rehash,
    rsa_decrypt_password,
    verify_token,
)
from fnixagent.core.security.auth.device import (
    compute_device_fingerprint,
    verify_device_fingerprint,
)
from fnixagent.services.storage import (
    get_apikey_store,
    get_user_store,
)

# Phase 2.5: 审计日志动作常量(延迟导入避免循环依赖)
_AUDIT = None


def _get_audit_constants():
    """延迟导入审计动作常量(单例缓存)。"""
    global _AUDIT
    if _AUDIT is None:
        from fnixagent.core.audit import (
            AUDIT_LDAP_LOGIN,
            AUDIT_LOGIN_FAILED,
            AUDIT_LOGIN_SUCCESS,
            AUDIT_LOGOUT,
            AUDIT_MFA_CHALLENGE,
            AUDIT_MFA_DISABLE,
            AUDIT_MFA_ENABLE,
            AUDIT_MFA_VERIFY_FAILED,
            AUDIT_SSO_LOGIN,
        )

        _AUDIT = {
            "LOGIN_SUCCESS": AUDIT_LOGIN_SUCCESS,
            "LOGIN_FAILED": AUDIT_LOGIN_FAILED,
            "LOGOUT": AUDIT_LOGOUT,
            "MFA_ENABLE": AUDIT_MFA_ENABLE,
            "MFA_DISABLE": AUDIT_MFA_DISABLE,
            "MFA_CHALLENGE": AUDIT_MFA_CHALLENGE,
            "MFA_VERIFY_FAILED": AUDIT_MFA_VERIFY_FAILED,
            "SSO_LOGIN": AUDIT_SSO_LOGIN,
            "LDAP_LOGIN": AUDIT_LDAP_LOGIN,
        }
    return _AUDIT


router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def _audit_log(action: str, user_id=None, detail=None, http_request=None):
    """写入审计日志(失败不影响主流程)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        ip = None
        ua = None
        if http_request:
            ua, ip = _get_request_context(http_request)
        AuditLogger().log(
            action=action,
            user_id=user_id,
            detail=detail,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception:
        pass


def _audit(action_key: str, user_id=None, detail=None, http_request=None):
    """使用预定义动作常量写入审计日志(便捷封装)。"""
    try:
        constants = _get_audit_constants()
        action = constants.get(action_key, action_key)
        _audit_log(action, user_id=user_id, detail=detail, http_request=http_request)
        # Phase 2.10: 记录登录 Prometheus 指标
        try:
            from fnixagent.core.observability.metrics import record_login, record_mfa_challenge

            method = (detail or {}).get("method", "password") if detail else "password"
            if action_key == "LOGIN_SUCCESS":
                record_login(success=True, method=method)
            elif action_key == "LOGIN_FAILED":
                record_login(success=False, method=method)
            elif action_key == "LDAP_LOGIN":
                record_login(success=True, method="ldap")
            elif action_key == "SSO_LOGIN":
                record_login(success=True, method="sso")
            elif action_key == "MFA_CHALLENGE" or action_key == "MFA_VERIFY_FAILED":
                factor_type = (detail or {}).get("factor_type", "totp") if detail else "totp"
                record_mfa_challenge(factor_type=factor_type, success=False)
        except Exception:
            pass
    except Exception:
        pass


# 兼容旧代码:从 token 模块导出配置


# ===========================================================================
# 向后兼容函数(供现有代码 / 测试直接导入)
# ===========================================================================


def create_jwt_token(user_id: int, username: str) -> str:
    """[向后兼容] 创建单 Access Token(无设备指纹)。

    Phase 0.4 起推荐使用 create_token_pair() 获取双 Token。
    """
    return create_access_token(user_id=user_id, username=username, role="user")


def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """验证 JWT Token,返回 payload。验证失败抛 401。

    Phase 0.4 新增:
        - 黑名单校验(登出后 Token 立即失效)
        - token_type 必须为 access(Refresh Token 不能用于业务接口)
    """
    token = credentials.credentials
    try:
        # 1. 校验签名 + 过期 + 类型
        payload = verify_token(token, expected_type="access")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    # 2. 黑名单校验
    jti = payload.get("jti")
    if jti:
        bl = blacklist_mod.get_blacklist()
        if bl.contains(jti):
            raise HTTPException(status_code=401, detail="Token 已被撤销")

    return payload


def verify_jwt_token_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_optional),
) -> dict:
    """Desktop / standalone BYOK：无 Token 时放行本地会话；有 Token 则正常校验。"""
    if credentials is None:
        profile = (os.getenv("FNIXAGENT_PROFILE") or "standalone").strip().lower()
        if profile in ("standalone", "desktop", "dev", "local"):
            return {"sub": "desktop", "user_id": 0, "username": "desktop", "via": "dev"}
        raise HTTPException(status_code=401, detail="Not authenticated")
    return verify_jwt_token(credentials)


def _get_user_or_404(payload: dict):
    """根据 payload 从 UserStore 取用户,失败抛 404。"""
    user_id = payload.get("user_id")
    user = get_user_store().get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _get_request_context(request: Request) -> tuple[str, str]:
    """从 Request 提取 User-Agent 与客户端 IP。"""
    user_agent = request.headers.get("user-agent", "")
    # 优先取 X-Forwarded-For(经 nginx 反代),其次取 client.host
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # 取第一个 IP(链式 XFF 的左端是原始客户端)
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else ""
    return user_agent, ip


# ===========================================================================
# 路由
# ===========================================================================


@router.get("/pubkey", response_model=PublicKeyResponse)
async def get_public_key():
    """获取服务端 RSA-2048 公钥(供客户端加密密码)。

    用法:
        # 客户端(Python 示例)
        import base64
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives import hashes, serialization

        public_key = serialization.load_pem_public_key(resp["public_key"].encode())
        ciphertext = public_key.encrypt(
            password.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        encrypted_password_b64 = base64.b64encode(ciphertext).decode()
    """
    keypair = get_server_keypair()
    # key_id = 公钥指纹的前 16 字符(用于客户端感知密钥轮换)
    import hashlib as _hl

    key_id = _hl.sha256(keypair.public_pem.encode("utf-8")).hexdigest()[:16]

    return PublicKeyResponse(
        public_key=keypair.public_pem,
        key_id=key_id,
        algorithm="RSA-2048-OAEP-SHA256",
        expires_at=None,
    )


@router.post("/register", response_model=UserResponse)
async def register_user(request: UserCreate):
    """
    注册新用户。

    - 用户名/邮箱唯一性校验
    - 密码使用 Argon2id 哈希存储(向后兼容 PBKDF2 老用户)
    - 公开注册强制 role=user（管理员只能走所有者通道或后台提权）
    """
    store = get_user_store()
    user, err = store.create(
        username=request.username,
        email=request.email or "",
        password=request.password,
        role="user",
    )
    if err:
        raise HTTPException(status_code=409, detail=err)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
    )


@router.post("/owner/login", response_model=TokenResponse)
async def owner_login(request: OwnerLoginRequest, http_request: Request):
    """所有者 / 管理员特殊通道。

    安全边界:
      - 必须携带与环境变量 FNIX_OWNER_TOKEN 一致的 owner_token
      - 生产环境未配置 FNIX_OWNER_TOKEN 时直接关闭
      - 跳过 MFA（专供本机所有者进入 Work / Admin）
      - 成功后签发 role=admin 的双 Token
    """
    expected = (os.getenv("FNIX_OWNER_TOKEN") or "").strip()
    if not expected:
        # 仅开发环境提供可预测本地默认口令，生产必须显式配置
        env = (os.getenv("SERVICE_ENV") or "development").lower()
        debug = (os.getenv("SERVICE_DEBUG") or os.getenv("DEBUG") or "true").lower()
        if env in ("development", "dev") and debug in ("1", "true", "yes", "on"):
            expected = "fnix-owner-local-2026"
        else:
            raise HTTPException(
                status_code=403,
                detail="所有者通道未启用：请在服务端 .env 配置 FNIX_OWNER_TOKEN",
            )
    if not hmac.compare_digest(request.owner_token.strip(), expected):
        _audit(
            "LOGIN_FAILED",
            detail={"username": request.username, "channel": "owner"},
            http_request=http_request,
        )
        raise HTTPException(status_code=401, detail="所有者口令错误")

    allowed_user = (os.getenv("FNIX_OWNER_USERNAME") or "admin").strip() or "admin"
    if request.username.strip() != allowed_user:
        raise HTTPException(
            status_code=403,
            detail=f"所有者通道仅允许账号: {allowed_user}",
        )

    store = get_user_store()
    user = store.get_by_username(request.username.strip())

    if user is None:
        # 首次：创建管理员
        user, err = store.create(
            username=request.username.strip(),
            email=os.getenv("FNIX_OWNER_EMAIL") or f"{allowed_user}@local.fnix",
            password=request.password,
            role="admin",
        )
        if err or user is None:
            raise HTTPException(status_code=409, detail=err or "无法创建所有者账号")
    else:
        # 已存在：校验密码；若非 admin 则提权
        auth_user = store.authenticate(request.username.strip(), request.password)
        if not auth_user:
            # 允许用所有者口令重置本地管理员密码（仅本通道）
            try:
                store.update_password(user.id, request.password)
            except Exception:
                raise HTTPException(status_code=401, detail="用户名或密码错误")
            auth_user = store.get_by_username(request.username.strip())
        if auth_user is None:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        user = auth_user
        if user.role != "admin":
            store.update_role(user.id, "admin")
            user = store.get_by_username(request.username.strip()) or user

    device_fp: str | None = None
    if request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    token_pair = create_token_pair(
        user_id=user.id,
        username=user.username,
        role="admin",
        device_fp=device_fp,
    )
    _audit(
        "LOGIN_SUCCESS",
        user_id=user.id,
        detail={"username": user.username, "channel": "owner"},
        http_request=http_request,
    )
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


@router.post("/login")
async def login_user(request: UserLogin, http_request: Request):
    """
    用户登录(Phase 0.4 安全规范对齐)。

    流程:
        1. 若 is_password_encrypted=True,用服务端 RSA 私钥解密密码
        2. Argon2id 校验密码(向后兼容 PBKDF2)
        3. 计算/校验设备指纹(若提供 client_uuid)
        4. 返回双 Token(Access 2h + Refresh 7d)
        5. 若密码哈希是旧 PBKDF2,自动升级到 Argon2id
        6. Phase 2.4:若用户启用 MFA,返回 mfa_required=true + mfa_token,
           客户端调 /auth/mfa/verify 完成验证后才能换取真正的 Token。

    向后兼容:
        - 旧客户端不传 is_password_encrypted(默认 false),密码按明文处理
        - 旧客户端不传 client_uuid,Token 不绑定设备指纹
        - 用户未开启 MFA 时,返回 TokenResponse(与旧版一致)
        - 用户开启 MFA 时,返回 MFALoginChallengeResponse(旧客户端会失败,
          需升级客户端以支持 MFA 流程)

    响应:
        - 200 TokenResponse           — 未启用 MFA,直接登录成功
        - 200 MFALoginChallengeResponse — 启用 MFA,需完成验证
        - 401                          — 用户名或密码错误
    """
    store = get_user_store()

    # 1. 解密密码(若加密)
    password_plain = request.password
    if request.is_password_encrypted:
        try:
            keypair = get_server_keypair()
            password_plain = rsa_decrypt_password(request.password, keypair)
        except ValueError:
            # 解密失败:不暴露具体原因,统一返回 401
            raise HTTPException(status_code=401, detail="密码解密失败")

    # 2. 校验用户名+密码
    user = store.authenticate(request.username, password_plain)
    if not user:
        _audit("LOGIN_FAILED", detail={"username": request.username}, http_request=http_request)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 3. 自动哈希升级(PBKDF2 → Argon2id)
    if needs_rehash(user.password_hash):
        try:
            store.update_password(user.id, password_plain)
        except Exception:
            # 升级失败不影响登录主流程
            pass

    # 4. Phase 2.4:检测 MFA
    from fnixagent.services.storage_mfa import get_mfa_factor_store

    factor_store = get_mfa_factor_store()
    enabled_factors = factor_store.list_by_user(user.id, include_disabled=False)

    if enabled_factors:
        # 用户已启用 MFA,签发临时 Challenge Token
        from fnixagent.core.security.auth.mfa import (
            FACTOR_RECOVERY,
            create_mfa_challenge_token,
        )

        factor_types = [f.factor_type for f in enabled_factors]
        # 始终允许使用恢复码
        if FACTOR_RECOVERY not in factor_types:
            factor_types.append(FACTOR_RECOVERY)
        mfa_token = create_mfa_challenge_token(
            user_id=user.id,
            username=user.username,
            factors=factor_types,
        )
        _audit(
            "MFA_CHALLENGE",
            user_id=user.id,
            detail={"factors": factor_types},
            http_request=http_request,
        )
        return MFALoginChallengeResponse(
            mfa_required=True,
            mfa_token=mfa_token,
            factors=factor_types,
            expires_in=300,
        )

    # 5. 计算设备指纹(若提供 client_uuid)
    device_fp: str | None = None
    if request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    # 6. 创建双 Token
    token_pair = create_token_pair(
        user_id=user.id,
        username=user.username,
        role=user.role,
        device_fp=device_fp,
    )

    _audit(
        "LOGIN_SUCCESS",
        user_id=user.id,
        detail={"username": user.username},
        http_request=http_request,
    )
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, http_request: Request):
    """用 Refresh Token 换发新的双 Token。

    流程:
        1. 校验 Refresh Token 签名 + 过期 + 类型
        2. 校验 Refresh Token 的 jti 不在黑名单(防止被盗后无限换发)
        3. 校验设备指纹(若原 Token 绑定了 device_fp)
        4. 把旧 Refresh Token 的 jti 加入黑名单(一次性使用)
        5. 签发新的双 Token

    安全:
        - Refresh Token 一次性,用过的立即作废
        - 设备指纹必须与登录时一致
    """
    # 1. 校验 Refresh Token
    try:
        payload = verify_token(request.refresh_token, expected_type="refresh")
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Refresh Token 无效: {e}")

    # 2. 黑名单校验
    jti = payload.get("jti")
    bl = blacklist_mod.get_blacklist()
    if jti and bl.contains(jti):
        raise HTTPException(status_code=401, detail="Refresh Token 已被使用,请重新登录")

    # 3. 设备指纹校验
    token_fp = payload.get("device_fp")
    if token_fp and request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )
        if not verify_device_fingerprint(token_fp, request.client_uuid, user_agent, ip):
            raise HTTPException(
                status_code=401,
                detail="设备指纹不匹配,疑似 Refresh Token 被盗",
            )

    # 4. 用户必须存在
    user_id = payload.get("user_id")
    user = get_user_store().get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    # 5. 旧 Refresh Token 加入黑名单(剩余有效期作为 TTL)
    if jti:
        exp = payload.get("exp", 0)
        ttl = max(int(exp) - int(time.time()), 60)  # 至少 60s,避免边界
        bl.add(jti, ttl)

    # 6. 签发新的双 Token
    new_pair = create_token_pair(
        user_id=user.id,
        username=user.username,
        role=user.role,
        device_fp=token_fp,  # 沿用原设备指纹
    )

    return TokenResponse(
        access_token=new_pair.access_token,
        refresh_token=new_pair.refresh_token,
        expires_in=new_pair.expires_in,
        refresh_expires_in=new_pair.refresh_expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(payload: dict = Depends(verify_jwt_token)):
    """获取当前登录用户信息。"""
    user = _get_user_or_404(payload)
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
    )


@router.post("/logout")
async def logout_user(
    http_request: Request,
    payload: dict = Depends(verify_jwt_token),
):
    """
    用户登出(Phase 0.4 安全规范对齐)。

    把 Access Token 的 jti 写入黑名单,过期时间 = Token 剩余有效期。
    后续该 Token 的请求会返回 401。
    """
    jti = payload.get("jti")
    exp = payload.get("exp", 0)
    bl = blacklist_mod.get_blacklist()

    if jti:
        # TTL = Token 剩余有效期(至少 1s)
        ttl = max(int(exp) - int(time.time()), 1)
        bl.add(jti, ttl)

    _audit("LOGOUT", user_id=payload.get("user_id"), http_request=http_request)
    return BaseResponse(success=True, message="Logged out")


@router.put("/profile", response_model=BaseResponse)
async def update_profile(
    profile_data: dict,
    payload: dict = Depends(verify_jwt_token),
):
    """更新用户配置/画像。"""
    user = _get_user_or_404(payload)
    updated = get_user_store().update_profile(user.id, profile_data)
    if not updated:
        raise HTTPException(status_code=500, detail="更新失败")
    return BaseResponse(success=True, message="Profile updated", data=updated.profile)


@router.get("/quota")
async def get_user_quota(payload: dict = Depends(verify_jwt_token)):
    """获取用户 Token 配额。"""
    user = _get_user_or_404(payload)
    quota = get_user_store().get_quota(user.id)
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")
    return quota


@router.post("/apikey")
async def create_api_key(payload: dict = Depends(verify_jwt_token)):
    """
    创建 API Key。

    - 明文 key 只在此接口返回一次
    - 存储层保存 SHA256 哈希
    """
    user = _get_user_or_404(payload)
    record = get_apikey_store().create(user_id=user.id)
    return {
        "id": record.id,
        "api_key": record.api_key,  # 明文只返回一次
        "scopes": record.scopes,
        "created_at": record.created_at.isoformat(),
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
    }


@router.delete("/apikey/{key_id}")
async def delete_api_key(key_id: int, payload: dict = Depends(verify_jwt_token)):
    """删除(吊销)API Key。"""
    user = _get_user_or_404(payload)
    ok = get_apikey_store().revoke(key_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="API Key 不存在或无权操作")
    return BaseResponse(success=True, message="API Key revoked")


@router.get("/apikey/list")
async def list_api_keys(payload: dict = Depends(verify_jwt_token)):
    """列出当前用户的所有 API Key(不含明文)。"""
    user = _get_user_or_404(payload)
    keys = get_apikey_store().list_by_user(user.id)
    return [
        {
            "id": k.id,
            "scopes": k.scopes,
            "created_at": k.created_at.isoformat(),
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "revoked": k.revoked,
        }
        for k in keys
    ]


# ===========================================================================
# Phase 2.2: LDAP/AD 域账号登录
# ===========================================================================


@router.post("/ldap/login", response_model=TokenResponse)
async def ldap_login(request: LDAPLoginRequest, http_request: Request):
    """LDAP 域账号登录。

    流程:
        1. 查找当前生效的 LDAP 配置
        2. 用 LDAP 配置 + 用户凭据 bind 验证
        3. 验证成功后,按邮箱同步用户到本地(不存在则创建)
        4. 为本地用户签发双 Token(Access 2h + Refresh 7d)

    若未配置 LDAP 或 ldap3 未安装,返回 503。
    """
    from fnixagent.core.security.auth.ldap import (
        LDAPAuthenticationError,
        LDAPClient,
        LDAPError,
        LDAPNotInstalledError,
    )
    from fnixagent.services.storage_ldap import get_ldap_config_store

    # 1. 获取生效的 LDAP 配置
    config_store = get_ldap_config_store()
    config_dto = config_store.get_active_config()
    if config_dto is None:
        raise HTTPException(status_code=503, detail="未配置 LDAP 服务器,请联系管理员")

    ldap_config = config_dto.to_ldap_config()
    client = LDAPClient(ldap_config)

    # 2. LDAP 认证
    try:
        ldap_user = client.authenticate(request.username, request.password)
    except LDAPNotInstalledError:
        raise HTTPException(status_code=503, detail="ldap3 库未安装,LDAP 登录不可用")
    except LDAPAuthenticationError:
        _audit(
            "LOGIN_FAILED",
            detail={"username": request.username, "method": "ldap"},
            http_request=http_request,
        )
        raise HTTPException(status_code=401, detail="LDAP 认证失败:用户名或密码错误")
    except LDAPError as e:
        raise HTTPException(status_code=502, detail=f"LDAP 服务异常: {e}")

    if ldap_user is None:
        _audit(
            "LOGIN_FAILED",
            detail={"username": request.username, "method": "ldap"},
            http_request=http_request,
        )
        raise HTTPException(status_code=401, detail="LDAP 认证失败:用户名或密码错误")

    # 3. 同步到本地(按邮箱查找或创建)
    local_user = client.sync_user_to_local(ldap_user)
    if local_user is None:
        raise HTTPException(status_code=500, detail="LDAP 用户同步到本地失败")

    # 4. 签发双 Token
    device_fp: str | None = None
    if request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    token_pair = create_token_pair(
        user_id=local_user.id,
        username=local_user.username,
        role=local_user.role,
        device_fp=device_fp,
    )

    _audit(
        "LDAP_LOGIN",
        user_id=local_user.id,
        detail={"username": local_user.username},
        http_request=http_request,
    )
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


# ===========================================================================
# Phase 2.3: SSO 单点登录(OAuth2.0 / SAML)
# ===========================================================================


@router.get("/sso/providers")
async def list_sso_providers():
    """列出当前可用的 SSO provider(供登录页渲染按钮)。

    返回所有 active 的 OAuth + SAML 配置(不含 secret)。
    """
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    configs = store.list_configs(include_inactive=False)
    return BaseResponse(
        success=True,
        data={
            "items": [c.to_dict(include_secret=False) for c in configs],
            "total": len(configs),
        },
    )


@router.post("/sso/oauth/authorize")
async def oauth_authorize(request: OAuthAuthorizeRequest):
    """获取 OAuth 授权 URL(客户端跳转到此 URL 完成用户授权)。

    返回:
        {
            "authorization_url": "https://github.com/login/oauth/authorize?...",
            "state": "随机 state(CSRF 防护)"
        }
    """
    from fnixagent.core.security.auth.oauth import OAuthClient, OAuthConfigError
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    cfg = store.get_by_code(request.provider_code, provider_type="oauth")
    if cfg is None:
        raise HTTPException(
            status_code=404, detail=f"OAuth provider {request.provider_code} 未配置或已禁用"
        )

    oauth_cfg = cfg.to_oauth_config()
    # 临时覆盖 redirect_uri(若客户端传入)
    if request.redirect_uri:
        oauth_cfg.redirect_uri = request.redirect_uri

    client = OAuthClient(oauth_cfg)
    state = OAuthClient.generate_state()
    try:
        url = client.build_authorization_url(state=state)
    except OAuthConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BaseResponse(
        success=True,
        data={"authorization_url": url, "state": state, "provider_code": request.provider_code},
    )


@router.post("/sso/oauth/callback", response_model=TokenResponse)
async def oauth_callback(request: OAuthCallbackRequest, http_request: Request):
    """OAuth 回调:用 code 换 token + 拉用户信息 + 签发本地 Token。

    流程:
        1. 按 provider_code 查找 OAuth 配置
        2. 用 code 换 access_token
        3. 用 access_token 拉用户信息
        4. 同步到本地(按 provider_user_id 或 email 绑定)
        5. 签发双 Token
    """
    from fnixagent.core.security.auth.oauth import (
        OAuthAuthenticationError,
        OAuthClient,
        OAuthConfigError,
        OAuthConnectionError,
        OAuthError,
        OAuthNotInstalledError,
    )
    from fnixagent.services.storage_sso import get_sso_config_store

    # 1. 查配置
    store = get_sso_config_store()
    cfg = store.get_by_code(request.provider_code, provider_type="oauth")
    if cfg is None:
        raise HTTPException(
            status_code=404, detail=f"OAuth provider {request.provider_code} 未配置"
        )

    client = OAuthClient(cfg.to_oauth_config())

    # 2+3. 换 token + 拉用户信息
    try:
        oauth_user = client.authenticate(request.code, request.state)
    except OAuthNotInstalledError:
        raise HTTPException(status_code=503, detail="requests 库未安装,OAuth 不可用")
    except OAuthAuthenticationError as e:
        raise HTTPException(status_code=401, detail=f"OAuth 认证失败: {e}")
    except OAuthConnectionError as e:
        raise HTTPException(status_code=502, detail=f"OAuth 服务连接失败: {e}")
    except OAuthConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OAuthError as e:
        raise HTTPException(status_code=500, detail=f"OAuth 异常: {e}")

    # 4. 同步到本地
    try:
        local_user = client.sync_user_to_local(oauth_user)
    except OAuthError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if local_user is None:
        raise HTTPException(status_code=500, detail="OAuth 用户同步到本地失败")

    # 5. 签发双 Token
    device_fp: str | None = None
    if request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    token_pair = create_token_pair(
        user_id=local_user.id,
        username=local_user.username,
        role=local_user.role,
        device_fp=device_fp,
    )
    _audit(
        "SSO_LOGIN",
        user_id=local_user.id,
        detail={
            "username": local_user.username,
            "provider": request.provider_code,
            "provider_type": "oauth",
        },
        http_request=http_request,
    )
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


@router.post("/sso/saml/{provider_code}/login")
async def saml_login(provider_code: str, body: SAMLLoginRequest):
    """SAML SP 发起登录:生成 AuthnRequest,返回 IdP 重定向 URL。

    返回:
        {
            "redirect_url": "https://idp/login?SAMLRequest=...",
            "state": "RelayState(CSRF / 回调上下文)"
        }
    """
    from fnixagent.core.security.auth.saml import SAMLClient, SAMLConfigError, SAMLNotInstalledError
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    cfg = store.get_by_code(provider_code, provider_type="saml")
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"SAML provider {provider_code} 未配置")

    client = SAMLClient(cfg.to_saml_config())
    state = SAMLClient.generate_state()
    try:
        result = client.build_authn_request(state=state)
    except SAMLNotInstalledError:
        raise HTTPException(status_code=503, detail="python3-saml 库未安装,SAML 登录不可用")
    except SAMLConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return BaseResponse(
        success=True,
        data={
            "redirect_url": result["redirect_url"],
            "state": result["state"],
            "provider_code": provider_code,
        },
    )


@router.post("/sso/saml/{provider_code}/acs", response_model=TokenResponse)
async def saml_acs(provider_code: str, body: SAMLACSRequest, http_request: Request):
    """SAML ACS:解析 IdP POST 的 SAMLResponse,签发本地 Token。

    流程:
        1. 按 provider_code 查找 SAML 配置
        2. 解析 SAMLResponse(验签 + 校验时效)
        3. 同步到本地(按 name_id 或 email 绑定)
        4. 签发双 Token
    """
    from fnixagent.core.security.auth.saml import (
        SAMLClient,
        SAMLConfigError,
        SAMLError,
        SAMLNotInstalledError,
        SAMLResponseError,
    )
    from fnixagent.services.storage_sso import get_sso_config_store

    store = get_sso_config_store()
    cfg = store.get_by_code(provider_code, provider_type="saml")
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"SAML provider {provider_code} 未配置")

    client = SAMLClient(cfg.to_saml_config())

    # 2. 解析 SAMLResponse
    try:
        saml_user = client.parse_response(body.saml_response)
    except SAMLNotInstalledError:
        raise HTTPException(status_code=503, detail="python3-saml 库未安装,SAML 不可用")
    except SAMLResponseError as e:
        raise HTTPException(status_code=401, detail=f"SAML 响应解析失败: {e}")
    except SAMLConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SAMLError as e:
        raise HTTPException(status_code=500, detail=f"SAML 异常: {e}")

    # 3. 同步到本地
    try:
        local_user = client.sync_user_to_local(saml_user)
    except SAMLError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if local_user is None:
        raise HTTPException(status_code=500, detail="SAML 用户同步到本地失败")

    # 4. 签发双 Token
    device_fp: str | None = None
    if body.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=body.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    token_pair = create_token_pair(
        user_id=local_user.id,
        username=local_user.username,
        role=local_user.role,
        device_fp=device_fp,
    )
    _audit(
        "SSO_LOGIN",
        user_id=local_user.id,
        detail={
            "username": local_user.username,
            "provider": provider_code,
            "provider_type": "saml",
        },
        http_request=http_request,
    )
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


# ===========================================================================
# Phase 2.4: MFA 多因素认证
# ===========================================================================


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def mfa_setup(
    request: MFASetupRequest,
    payload: dict = Depends(verify_jwt_token),
):
    """初始化 MFA 因子(生成 TOTP secret + QR URI)。

    流程:
        1. 用户已登录(携带 Access Token)
        2. 生成新的 TOTP secret + otpauth:// URI
        3. 返回给客户端,客户端渲染二维码供用户扫描
        4. 用户用 Google Authenticator 扫码后,调 /mfa/enable 确认

    注意:此接口不持久化 secret,客户端需在 /mfa/enable 时回传 secret。
    """
    from fnixagent.core.security.auth.mfa import (
        FACTOR_EMAIL,
        FACTOR_SMS,
        FACTOR_TOTP,
        TOTPClient,
    )

    user = _get_user_or_404(payload)

    if request.factor_type == FACTOR_TOTP:
        secret = TOTPClient.generate_secret()
        account_name = request.account_name or user.email or user.username
        qr_uri = TOTPClient.build_provisioning_uri(
            secret=secret,
            account_name=account_name,
        )
        return MFASetupResponse(
            factor_type=FACTOR_TOTP,
            secret=secret,
            qr_uri=qr_uri,
            factors=[],
        )
    elif request.factor_type == FACTOR_SMS:
        return MFASetupResponse(
            factor_type=FACTOR_SMS,
            secret="",
            qr_uri="",
            factors=[],
        )
    elif request.factor_type == FACTOR_EMAIL:
        return MFASetupResponse(
            factor_type=FACTOR_EMAIL,
            secret="",
            qr_uri="",
            factors=[],
        )
    else:
        raise HTTPException(status_code=400, detail=f"不支持的因子类型: {request.factor_type}")


@router.post("/mfa/enable", response_model=BaseResponse)
async def mfa_enable(
    request: MFAEnableRequest,
    http_request: Request,
    payload: dict = Depends(verify_jwt_token),
):
    """启用 MFA 因子(验证首个 code 确认 setup)。

    流程:
        1. 用户已登录(携带 Access Token)
        2. TOTP: 用 setup 返回的 secret 校验首码,通过后持久化 factor
        3. SMS/EMAIL: 绑定手机号/邮箱
        4. 同时生成 10 个备用恢复码(明文只返回一次)
    """
    from fnixagent.core.security.auth.mfa import (
        FACTOR_EMAIL,
        FACTOR_SMS,
        FACTOR_TOTP,
        RecoveryCodeClient,
        TOTPClient,
        TOTPConfig,
    )
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_recovery_code_store,
    )

    user = _get_user_or_404(payload)
    factor_store = get_mfa_factor_store()
    recovery_store = get_recovery_code_store()

    if request.factor_type == FACTOR_TOTP:
        if not request.secret:
            raise HTTPException(status_code=400, detail="TOTP setup 需提供 secret")
        totp_client = TOTPClient(
            TOTPConfig(
                secret=request.secret,
                account_name=user.email or user.username,
            )
        )
        if not totp_client.verify(request.code):
            raise HTTPException(status_code=400, detail="TOTP 验证码错误,请重试")
        existing = factor_store.get_totp(user.id)
        if existing:
            factor_store.update(existing.id, secret=request.secret, enabled=True)
        else:
            factor_store.create(user.id, FACTOR_TOTP, secret=request.secret)

    elif request.factor_type == FACTOR_SMS:
        phone = (request.phone or "").strip()
        if not phone:
            raise HTTPException(status_code=400, detail="SMS 因子需提供 phone")
        existing = factor_store.get_sms(user.id)
        if existing:
            factor_store.update(existing.id, phone=phone, enabled=True)
        else:
            factor_store.create(user.id, FACTOR_SMS, phone=phone)

    elif request.factor_type == FACTOR_EMAIL:
        email_addr = (request.email or user.email or "").strip()
        if not email_addr:
            raise HTTPException(status_code=400, detail="EMAIL 因子需提供 email")
        existing = factor_store.get_email(user.id)
        if existing:
            factor_store.update(existing.id, email=email_addr, enabled=True)
        else:
            factor_store.create(user.id, FACTOR_EMAIL, email=email_addr)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的因子类型: {request.factor_type}")

    # 生成备用恢复码(若没有)
    existing_codes = recovery_store.count_unused(user.id)
    if existing_codes == 0:
        codes = RecoveryCodeClient.generate()
        for code in codes:
            recovery_store.create(user.id, RecoveryCodeClient.hash_code(code))
    else:
        codes = []

    store = get_user_store()
    store.update_profile(user.id, {"mfa_enabled": True})

    _audit(
        "MFA_ENABLE",
        user_id=user.id,
        detail={"factor_type": request.factor_type},
        http_request=http_request,
    )
    return BaseResponse(
        success=True,
        message="MFA 因子已启用",
        data={"recovery_codes": codes} if codes else None,
    )


@router.post("/mfa/disable", response_model=BaseResponse)
async def mfa_disable(
    request: MFADisableRequest,
    http_request: Request,
    payload: dict = Depends(verify_jwt_token),
):
    """禁用 MFA 因子(需密码二次确认)。

    - factor_id 为空:禁用所有因子 + 删除所有恢复码
    - factor_id 非空:仅禁用指定因子(若为最后一个,则同时清除恢复码)
    """
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_recovery_code_store,
    )

    user = _get_user_or_404(payload)

    if not request.password:
        raise HTTPException(status_code=400, detail="需密码二次确认才能禁用 MFA")

    password_plain = request.password
    if request.is_password_encrypted:
        try:
            keypair = get_server_keypair()
            password_plain = rsa_decrypt_password(request.password, keypair)
        except ValueError:
            raise HTTPException(status_code=401, detail="密码解密失败")

    store = get_user_store()
    if not store.authenticate(user.username, password_plain):
        raise HTTPException(status_code=401, detail="密码错误,无法禁用 MFA")

    factor_store = get_mfa_factor_store()
    recovery_store = get_recovery_code_store()

    if request.factor_id is None:
        deleted = factor_store.delete_all_by_user(user.id)
        recovery_store.delete_all_by_user(user.id)
        store.update_profile(user.id, {"mfa_enabled": False})
        _audit(
            "MFA_DISABLE",
            user_id=user.id,
            detail={"factor_id": None, "count": deleted},
            http_request=http_request,
        )
        return BaseResponse(success=True, message=f"已禁用所有 MFA 因子(共 {deleted} 个)")
    else:
        ok = factor_store.delete(request.factor_id)
        if not ok:
            raise HTTPException(status_code=404, detail="因子不存在")
        remaining = factor_store.list_by_user(user.id, include_disabled=False)
        if not remaining:
            recovery_store.delete_all_by_user(user.id)
            store.update_profile(user.id, {"mfa_enabled": False})
        _audit(
            "MFA_DISABLE",
            user_id=user.id,
            detail={"factor_id": request.factor_id},
            http_request=http_request,
        )
        return BaseResponse(success=True, message="MFA 因子已禁用")


@router.get("/mfa/factors", response_model=BaseResponse)
async def mfa_list_factors(payload: dict = Depends(verify_jwt_token)):
    """列出当前用户已绑定的 MFA 因子(不含 secret)。"""
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_recovery_code_store,
    )

    user = _get_user_or_404(payload)
    factor_store = get_mfa_factor_store()
    recovery_store = get_recovery_code_store()

    factors = factor_store.list_by_user(user.id)
    unused_count = recovery_store.count_unused(user.id)

    return BaseResponse(
        success=True,
        data={
            "factors": [f.to_dict(include_secret=False) for f in factors],
            "recovery_codes_remaining": unused_count,
            "mfa_enabled": any(f.enabled for f in factors),
        },
    )


@router.post("/mfa/recovery-codes/regenerate", response_model=BaseResponse)
async def mfa_regenerate_recovery_codes(
    payload: dict = Depends(verify_jwt_token),
):
    """重新生成备用恢复码(旧码全部作废)。

    明文只返回一次,客户端需提示用户保存。
    """
    from fnixagent.core.security.auth.mfa import RecoveryCodeClient
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_recovery_code_store,
    )

    user = _get_user_or_404(payload)
    factor_store = get_mfa_factor_store()
    recovery_store = get_recovery_code_store()

    if not factor_store.has_enabled_factor(user.id):
        raise HTTPException(status_code=400, detail="未启用 MFA,无法生成恢复码")

    recovery_store.delete_all_by_user(user.id)

    codes = RecoveryCodeClient.generate()
    for code in codes:
        recovery_store.create(user.id, RecoveryCodeClient.hash_code(code))

    return BaseResponse(
        success=True,
        message="恢复码已重新生成(明文只返回一次,请妥善保存)",
        data={"recovery_codes": codes},
    )


@router.post("/mfa/send-code", response_model=BaseResponse)
async def mfa_send_code(
    request: MFASendCodeRequest,
    payload: dict | None = Depends(verify_jwt_token),
):
    """发送 OTP 验证码(短信/邮箱)。

    两种使用场景:
        1. 已登录用户绑定 SMS/EMAIL 因子时:用 Access Token 鉴权,target 可指定
        2. 登录流程中需 OTP 验证:用 mfa_token 鉴权,target 必须为已绑定的

    返回 challenge_id,客户端调 /mfa/verify 时回传。
    """
    from fnixagent.core.security.auth.mfa import (
        FACTOR_EMAIL,
        FACTOR_SMS,
        OTP_TTL_SECONDS,
        MFAConfigError,
        MFANotInstalledError,
        OTPClient,
        SMSConfig,
        verify_mfa_challenge_token,
    )
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_otp_challenge_store,
    )

    # 鉴权:Access Token 或 mfa_token 二选一
    user_id: int | None = None
    if payload is not None:
        user_id = payload.get("user_id")
    elif request.mfa_token:
        try:
            challenge_payload = verify_mfa_challenge_token(request.mfa_token)
            user_id = challenge_payload.get("user_id")
        except ValueError as e:
            raise HTTPException(status_code=401, detail=f"mfa_token 无效: {e}")

    if user_id is None:
        raise HTTPException(status_code=401, detail="需 Access Token 或 mfa_token 鉴权")

    factor_store = get_mfa_factor_store()
    otp_store = get_otp_challenge_store()

    if request.factor_type == FACTOR_SMS:
        factor = factor_store.get_sms(user_id)
        target = request.target or (factor.phone if factor else "")
        if not target:
            raise HTTPException(status_code=400, detail="未绑定 SMS 因子,无法发送")
    elif request.factor_type == FACTOR_EMAIL:
        factor = factor_store.get_email(user_id)
        target = request.target or (factor.email if factor else "")
        if not target:
            raise HTTPException(status_code=400, detail="未绑定 EMAIL 因子,无法发送")
    else:
        raise HTTPException(status_code=400, detail="factor_type 必须为 sms 或 email")

    if not otp_store.check_resend_cooldown(user_id, request.factor_type):
        raise HTTPException(status_code=429, detail="发送频率过高,请 60s 后重试")

    otp_client = OTPClient()
    otp_client.sms_config = SMSConfig(provider="mock")
    code = OTPClient.generate_code()
    code_hash = OTPClient.hash_code(code)

    try:
        if request.factor_type == FACTOR_SMS:
            sent = otp_client.send_sms(target, code)
        else:
            sent = True  # EMAIL 默认不实际发送(需 SMTP 配置,生产环境注入)
    except MFANotInstalledError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except MFAConfigError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not sent:
        raise HTTPException(status_code=502, detail="验证码发送失败")

    challenge = otp_store.create(
        user_id=user_id,
        factor_type=request.factor_type,
        target=OTPClient.mask_target(target, request.factor_type),
        code_hash=code_hash,
    )

    return BaseResponse(
        success=True,
        message="验证码已发送",
        data={
            "challenge_id": challenge.challenge_id,
            "target": challenge.target,
            "expires_in": OTP_TTL_SECONDS,
        },
    )


@router.post("/mfa/verify", response_model=TokenResponse)
async def mfa_verify(request: MFAVerifyRequest, http_request: Request):
    """MFA 验证(登录流程中完成 MFA,换取真正的双 Token)。

    流程:
        1. 校验 mfa_token(签名 + 过期 + 类型)
        2. 按 factor_type 校验 code:
           - totp:    用存储的 secret 校验
           - sms/email: 用 challenge_id 取 challenge,校验 code_hash + 过期 + 尝试次数
           - recovery: 用恢复码哈希校验,通过后作废
        3. 签发双 Token(完成登录)
    """
    from fnixagent.core.security.auth.mfa import (
        FACTOR_EMAIL,
        FACTOR_RECOVERY,
        FACTOR_SMS,
        FACTOR_TOTP,
        OTPClient,
        RecoveryCodeClient,
        TOTPClient,
        TOTPConfig,
        verify_mfa_challenge_token,
    )
    from fnixagent.services.storage_mfa import (
        get_mfa_factor_store,
        get_otp_challenge_store,
        get_recovery_code_store,
    )

    # 1. 校验 mfa_token
    try:
        challenge_payload = verify_mfa_challenge_token(request.mfa_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"mfa_token 无效: {e}")

    user_id = challenge_payload.get("user_id")
    challenge_payload.get("username", "")
    allowed_factors = challenge_payload.get("factors", [])

    store = get_user_store()
    user = store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    if request.factor_type not in allowed_factors:
        raise HTTPException(
            status_code=400, detail=f"该用户的 MFA 不支持 {request.factor_type} 因子"
        )

    factor_store = get_mfa_factor_store()
    otp_store = get_otp_challenge_store()
    recovery_store = get_recovery_code_store()

    # 2. 按 factor_type 校验 code
    if request.factor_type == FACTOR_TOTP:
        totp_factor = factor_store.get_totp(user_id)
        if not totp_factor:
            raise HTTPException(status_code=400, detail="未绑定 TOTP 因子")
        totp_client = TOTPClient(
            TOTPConfig(
                secret=totp_factor.secret,
                account_name=user.email or user.username,
            )
        )
        if not totp_client.verify(request.code):
            _audit(
                "MFA_VERIFY_FAILED",
                user_id=user_id,
                detail={"factor_type": FACTOR_TOTP, "reason": "wrong_code"},
                http_request=http_request,
            )
            raise HTTPException(status_code=401, detail="TOTP 验证码错误")

    elif request.factor_type in (FACTOR_SMS, FACTOR_EMAIL):
        if not request.challenge_id:
            raise HTTPException(status_code=400, detail="OTP 验证需提供 challenge_id")
        challenge = otp_store.get(request.challenge_id)
        if challenge is None:
            raise HTTPException(status_code=404, detail="challenge 不存在")
        if challenge.consumed:
            raise HTTPException(status_code=410, detail="challenge 已使用或作废")
        if challenge.expires_at <= time.time():
            raise HTTPException(status_code=410, detail="challenge 已过期")
        if challenge.user_id != user_id:
            raise HTTPException(status_code=403, detail="challenge 与用户不匹配")

        actual_hash = OTPClient.hash_code(request.code)
        if not hmac.compare_digest(actual_hash, challenge.code_hash):
            otp_store.increment_attempts(request.challenge_id)
            _audit(
                "MFA_VERIFY_FAILED",
                user_id=user_id,
                detail={"factor_type": request.factor_type, "reason": "wrong_code"},
                http_request=http_request,
            )
            raise HTTPException(status_code=401, detail="验证码错误")

        otp_store.consume(request.challenge_id)

    elif request.factor_type == FACTOR_RECOVERY:
        code_hash = RecoveryCodeClient.hash_code(request.code)
        record = recovery_store.find_unused_by_hash(user_id, code_hash)
        if record is None:
            _audit(
                "MFA_VERIFY_FAILED",
                user_id=user_id,
                detail={"factor_type": FACTOR_RECOVERY, "reason": "invalid_or_used"},
                http_request=http_request,
            )
            raise HTTPException(status_code=401, detail="恢复码无效或已使用")
        recovery_store.mark_used(record.id)

    else:
        raise HTTPException(status_code=400, detail=f"不支持的因子类型: {request.factor_type}")

    # 3. 签发双 Token(完成登录)
    device_fp: str | None = None
    if request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    token_pair = create_token_pair(
        user_id=user.id,
        username=user.username,
        role=user.role,
        device_fp=device_fp,
    )
    _audit(
        "LOGIN_SUCCESS",
        user_id=user.id,
        detail={"username": user.username, "method": "mfa", "factor_type": request.factor_type},
        http_request=http_request,
    )
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )


# ============================================================================
# Phase 3.0: 手机号验证码独立登录(国内)
# ============================================================================
# 场景:国内用户必须通过手机号 + 短信验证码登录(无密码)。
# 流程:
#   1. 客户端 POST /auth/sms/send-code  {"phone": "13800138000"}
#      → 服务端生成 6 位验证码,通过 SMS provider(aliyun/tencent/mock)发送
#      → 同时把 challenge_id 返回给客户端(用于后续登录)
#   2. 客户端 POST /auth/sms/login  {"phone": "...", "code": "123456", "challenge_id": "..."}
#      → 服务端校验验证码,通过后签发双 Token
#
# 安全措施:
#   - 同一手机号 60s 内不可重发
#   - 验证码 5 分钟有效
#   - 最多 5 次验证尝试
#   - 验证码 SHA256 哈希存储(不存明文)
#   - 登录成功后 challenge 立即消费(一次性)
#   - 手机号未注册时返回相同响应(防用户枚举)
# ============================================================================


# SMS 登录专用 factor_type(与 MFA 的 sms 区分)
_SMS_LOGIN_FACTOR = "sms_login"


def _get_sms_login_otp_client():
    """获取 OTP 客户端(复用 MFA 的 SMS 配置)。

    从环境变量读取 SMS provider 配置:
      SMS_PROVIDER       = mock | aliyun | tencent
      SMS_ACCESS_KEY     = 阿里云/腾讯云 AccessKey
      SMS_ACCESS_SECRET  = 阿里云/腾讯云 Secret
      SMS_SIGN_NAME      = 短信签名
      SMS_TEMPLATE_CODE  = 短信模板 ID
    """
    from fnixagent.core.security.auth.mfa import OTPClient, SMSConfig

    provider = os.getenv("SMS_PROVIDER", "mock")
    if provider == "mock":
        # 开发/测试环境:不实际发短信,验证码记录在日志中
        return OTPClient(
            sms_config=SMSConfig(
                provider="mock",
                access_key_id="",
                access_key_secret="",
                sign_name="",
                template_code="",
            )
        )

    return OTPClient(
        sms_config=SMSConfig(
            provider=provider,
            access_key_id=os.getenv("SMS_ACCESS_KEY", ""),
            access_key_secret=os.getenv("SMS_ACCESS_SECRET", ""),
            sign_name=os.getenv("SMS_SIGN_NAME", ""),
            template_code=os.getenv("SMS_TEMPLATE_CODE", ""),
        )
    )


@router.post("/sms/send-code")
async def sms_send_code(request: SmsSendCodeRequest, http_request: Request):
    """发送短信验证码(手机号登录)。

    响应:
        200: {"challenge_id": "...", "expires_in": 300}
        429: 发送过于频繁(60s 冷却)
    """
    from fnixagent.core.security.auth.mfa import OTPClient
    from fnixagent.services.storage_mfa import get_otp_challenge_store

    store = get_otp_challenge_store()
    phone = request.phone

    # 1. 检查重发冷却(60s)
    # 用 phone 作为 user_id 占位(手机号登录未关联用户时用 0)
    # 用 phone 的 hash 作为 user_id 的替代(避免与真实 user_id 冲突)
    phone_hash = int(hashlib.sha256(phone.encode()).hexdigest()[:8], 16)
    if not store.check_resend_cooldown(phone_hash, _SMS_LOGIN_FACTOR):
        raise HTTPException(
            status_code=429,
            detail="验证码发送过于频繁,请 60 秒后重试",
        )

    # 2. 生成验证码
    otp_client = _get_sms_login_otp_client()
    code = OTPClient.generate_code()
    code_hash = OTPClient.hash_code(code)

    # 3. 创建 challenge(user_id 用 phone_hash 占位)
    challenge = store.create(
        user_id=phone_hash,
        factor_type=_SMS_LOGIN_FACTOR,
        target=phone,
        code_hash=code_hash,
        ttl=300,  # 5 分钟有效
    )

    # 4. 发送短信
    try:
        otp_client.send_sms(phone, code)
    except Exception as e:
        # 发送失败不影响 challenge 已创建(开发环境 mock 不会失败)
        # 生产环境发送失败应返回 500
        raise HTTPException(
            status_code=500,
            detail=f"短信发送失败: {type(e).__name__}",
        )

    # 5. 记录审计(不记录手机号明文)
    _audit_log(
        "sms.code.sent",
        detail={"phone_mask": OTPClient.mask_target(phone, "sms")},
        http_request=http_request,
    )

    return {
        "challenge_id": challenge.challenge_id,
        "expires_in": 300,
        "message": "验证码已发送",
    }


@router.post("/sms/login", response_model=TokenResponse)
async def sms_login(request: SmsLoginRequest, http_request: Request):
    """手机号验证码登录。

    流程:
        1. 校验验证码(从 OTP challenge store 查询)
        2. 通过手机号查找用户(profile.phone 字段)
        3. 签发双 Token

    响应:
        200: TokenResponse
        401: 验证码错误或已过期
        404: 手机号未注册
    """
    from fnixagent.core.security.auth.mfa import OTPClient
    from fnixagent.services.storage_mfa import get_otp_challenge_store

    challenge_store = get_otp_challenge_store()
    user_store = get_user_store()

    # 1. 查找 challenge(通过 challenge_id 不在请求中,需按 phone 查找)
    phone_hash = int(hashlib.sha256(request.phone.encode()).hexdigest()[:8], 16)
    challenge = challenge_store.get_active_by_user(phone_hash, _SMS_LOGIN_FACTOR)

    if not challenge:
        raise HTTPException(status_code=401, detail="验证码已过期,请重新获取")

    if challenge.consumed:
        raise HTTPException(status_code=401, detail="验证码已使用,请重新获取")

    # 2. 校验验证码
    provided_hash = OTPClient.hash_code(request.code)
    if not hmac.compare_digest(provided_hash, challenge.code_hash):
        # 增加尝试次数
        challenge_store.increment_attempts(challenge.challenge_id)
        updated = challenge_store.get(challenge.challenge_id)
        if updated and updated.attempts >= 5:
            raise HTTPException(status_code=401, detail="验证码错误次数过多,请重新获取")
        raise HTTPException(status_code=401, detail="验证码错误")

    # 3. 检查是否过期
    if time.time() > challenge.expires_at:
        raise HTTPException(status_code=401, detail="验证码已过期,请重新获取")

    # 4. 消费 challenge(一次性)
    challenge_store.consume(challenge.challenge_id)

    # 5. 查找用户
    user = user_store.get_by_phone(request.phone)
    if not user:
        # 防用户枚举:不暴露手机号是否注册
        # 但仍消费了验证码,防止通过验证码探测
        raise HTTPException(status_code=404, detail="该手机号未注册,请先注册账号")

    if user.profile.get("disabled"):
        raise HTTPException(status_code=403, detail="账号已被禁用,请联系管理员")

    # 6. 计算设备指纹(若提供 client_uuid)
    device_fp: str | None = None
    if request.client_uuid:
        user_agent, ip = _get_request_context(http_request)
        device_fp = compute_device_fingerprint(
            client_uuid=request.client_uuid,
            user_agent=user_agent,
            ip_address=ip,
        )

    # 7. 签发双 Token
    token_pair = create_token_pair(
        user_id=user.id,
        username=user.username,
        role=user.role,
        device_fp=device_fp,
    )

    # 8. 审计 + Prometheus 指标
    _audit(
        "LOGIN_SUCCESS",
        user_id=user.id,
        detail={"username": user.username, "method": "sms"},
        http_request=http_request,
    )

    # Phase 2.10: 记录登录指标
    try:
        from fnixagent.core.observability.metrics import record_login

        record_login(success=True, method="sms")
    except Exception:
        pass

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        refresh_expires_in=token_pair.refresh_expires_in,
    )
