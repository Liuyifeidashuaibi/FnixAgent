"""
RBAC 细粒度权限控制(Phase 2.1)。

提供:
    1. 权限查询:`get_user_permissions(user_id)` 返回用户全部权限码集合
    2. 权限校验:`has_permission(user_id, code)` 单权限检查
    3. FastAPI 依赖装饰器:
       - `require_permission("document:read")` — 要求单个权限
       - `require_any_permission("user:read", "user:manage")` — 任一即可
       - `require_all_permissions("role:read", "role:assign")` — 全部都要
    4. 缓存与失效:`invalidate_user_permission_cache(user_id)` 角色变更时调用
    5. `PermissionDenied` 异常:权限检查失败时抛出(供非 HTTP 上下文使用)

设计要点:
    - 内存缓存 TTL=60 秒,平衡性能与实时性
    - 角色变更(分配/撤销/删除)时主动失效,确保「角色变更后用户权限实时刷新」
    - 优先查询 RBAC 存储(Pg 或 InMemory),未分配角色时回退到 User.role 字段
    - super_admin 角色短路返回全部权限(性能优化)
    - 角色权限聚合使用 visited 集合防止继承循环
    - 线程安全(threading.Lock 保护缓存)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from fnixagent.api.routers.auth import verify_jwt_token
from fnixagent.core.exceptions import fnixagentError
from fnixagent.services.storage import get_user_store

# ---------------------------------------------------------------------------
# PermissionDenied 异常
# ---------------------------------------------------------------------------


class PermissionDenied(fnixagentError):
    """权限检查失败异常(供非 HTTP 上下文使用)。

    HTTP 上下文(FastAPI 依赖装饰器)仍抛 HTTPException(403),
    非 HTTP 上下文(直接调用 check_permission)抛此异常。

    Attributes:
        user_id: 被拒绝的用户 ID
        required_permissions: 缺少的权限码列表
    """

    def __init__(
        self,
        user_id: int | None,
        required_permissions: str | list[str],
    ) -> None:
        """初始化权限拒绝异常。

        Args:
            user_id: 被拒绝的用户 ID
            required_permissions: 缺少的权限码或列表
        """
        self.user_id = user_id
        if isinstance(required_permissions, str):
            self.required_permissions = [required_permissions]
        else:
            self.required_permissions = list(required_permissions)
        perms_str = ", ".join(self.required_permissions)
        super().__init__(f"权限不足: 用户 {user_id} 缺少权限 [{perms_str}]")


# ---------------------------------------------------------------------------
# Phase 2.5: 权限拒绝审计日志
# ---------------------------------------------------------------------------


def _audit_permission_denied(
    user_id: int | None,
    required_perms: list[str],
    http_request: Request | None = None,
) -> None:
    """权限拒绝时写入审计日志(失败不影响主流程)。

    Args:
        user_id: 被拒绝的用户 ID
        required_perms: 缺少的权限码列表
        http_request: FastAPI Request(可选,用于提取 IP/UA)
    """
    try:
        from fnixagent.core.audit import AUDIT_PERMISSION_DENIED, AuditLogger

        ip: str | None = None
        ua: str | None = None
        endpoint = ""
        if http_request:
            ua = http_request.headers.get("user-agent", "")
            forwarded = http_request.headers.get("x-forwarded-for", "")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
            else:
                ip = http_request.client.host if http_request.client else ""
            endpoint = http_request.url.path
        AuditLogger().log(
            action=AUDIT_PERMISSION_DENIED,
            user_id=user_id,
            detail={"required_permissions": required_perms},
            ip_address=ip,
            user_agent=ua,
        )
        # Phase 2.10: 记录权限拒绝 Prometheus 指标
        try:
            from fnixagent.core.observability.metrics import record_permission_denied

            for perm in required_perms:
                record_permission_denied(permission=perm, endpoint=endpoint)
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 缓存:user_id → (permissions_set, expires_at)
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS: int = 60  # 60 秒 TTL

_permission_cache: dict[int, tuple[set[str], float]] = {}
_cache_lock = threading.Lock()


def invalidate_user_permission_cache(user_id: int) -> None:
    """失效指定用户的权限缓存。

    在以下场景调用:
        - 管理员给用户分配/撤销角色
        - 角色的权限集合被修改(此时需失效所有用户)
        - 用户被禁用/启用
    """
    with _cache_lock:
        _permission_cache.pop(user_id, None)


def invalidate_all_permission_cache() -> None:
    """失效全部用户的权限缓存(角色权限变更时调用)。"""
    with _cache_lock:
        _permission_cache.clear()


# ---------------------------------------------------------------------------
# 内置权限码集合(用于 DB 不可用时的回退)
# ---------------------------------------------------------------------------

# super_admin / admin 拥有的回退权限(DB 不可用时)
_FALLBACK_ADMIN_PERMS: set[str] = {
    "user:read",
    "user:create",
    "user:update",
    "user:delete",
    "user:manage",
    "user:reset_password",
    "role:read",
    "role:create",
    "role:update",
    "role:delete",
    "role:assign",
    "role:manage",
    "department:read",
    "department:create",
    "department:update",
    "department:delete",
    "department:manage",
    "position:read",
    "position:create",
    "position:update",
    "position:delete",
    "position:manage",
    "document:read",
    "document:upload",
    "document:delete",
    "document:manage",
    "chat:read",
    "chat:write",
    "chat:evolve",
    "chat:manage",
    "task:read",
    "task:create",
    "task:cancel",
    "task:manage",
    "system:config",
    "system:audit_log",
    "system:manage",
}

# 普通用户回退权限
_FALLBACK_USER_PERMS: set[str] = {
    "document:read",
    "document:upload",
    "chat:read",
    "chat:write",
    "chat:evolve",
    "task:read",
    "task:create",
}

# 访客回退权限(仅 :read)
_FALLBACK_VISITOR_PERMS: set[str] = {
    "document:read",
    "chat:read",
    "task:read",
}


# ---------------------------------------------------------------------------
# 权限查询
# ---------------------------------------------------------------------------


def _query_permissions_from_store(user_id: int) -> set[str] | None:
    """从 RBAC 存储查询用户全部权限码(兼容 Pg / InMemory)。

    通过 get_rbac_store() 获取存储单例,查询用户角色并聚合权限码。
    - 无 DATABASE_URL 时返回 InMemoryRbacStore 结果
    - 有 DATABASE_URL 时返回 PgRbacStore 结果
    - 用户未分配任何角色时返回 None(由调用方回退到 User.role 字段)
    - 异常时返回 None(由调用方回退)
    - 使用 visited 集合防止角色继承循环(最多 32 层深度)

    Args:
        user_id: 用户 ID(正整数)

    Returns:
        权限码集合;未分配角色或异常时返回 None
    """
    try:
        from fnixagent.services.storage_rbac import get_rbac_store

        store = get_rbac_store()
        roles = store.get_user_roles(user_id)
        if not roles:
            # 未分配 RBAC 角色 → 返回 None 让调用方回退到 User.role 字段
            return None

        # super_admin 短路:返回全部权限
        if any(r.code == "super_admin" and r.is_active for r in roles):
            return {p.code for p in store.list_permissions()}

        # 聚合所有活跃角色的权限(get_role 会填充 permission_codes)
        # visited 集合防止角色继承循环(如 A→B→A 导致无限递归)
        perms: set[str] = set()
        visited: set[int] = set()
        for role in roles:
            if not role.is_active:
                continue
            # 防御继承循环:每个角色 ID 只处理一次
            if role.id in visited:
                continue
            visited.add(role.id)
            full_role = store.get_role(role.id)
            if full_role:
                perms.update(full_role.permission_codes)
        return perms
    except Exception:
        return None


def _fallback_permissions(role: str) -> set[str]:
    """DB 不可用时的回退:根据 User.role 字段返回权限集合。

    Args:
        role: 用户角色字段(super_admin/admin/user/visitor)

    Returns:
        权限码集合

    Raises:
        ValueError: role 为空字符串
    """
    if not isinstance(role, str) or not role.strip():
        raise ValueError("role 不能为空字符串")
    if role == "super_admin" or role == "admin":
        return set(_FALLBACK_ADMIN_PERMS)
    if role == "visitor":
        return set(_FALLBACK_VISITOR_PERMS)
    return set(_FALLBACK_USER_PERMS)


def get_user_permissions(user_id: int) -> set[str]:
    """获取用户全部权限码集合(带缓存)。

    优先级:
        1. 内存缓存(60 秒 TTL)
        2. 数据库查询(user_roles → role_permissions → permissions)
        3. 回退:User.role 字段(super_admin/admin/user/visitor)

    Args:
        user_id: 用户 ID(正整数)

    Returns:
        权限码集合,如 {"document:read", "chat:write"}

    Raises:
        ValueError: user_id 为 None 或非正整数
    """
    if user_id is None or not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError(f"user_id 必须为正整数, 实为 {user_id}")
    if user_id <= 0:
        raise ValueError(f"user_id 必须为正整数, 实为 {user_id}")

    now = time.time()

    # 1. 查缓存
    with _cache_lock:
        cached = _permission_cache.get(user_id)
        if cached is not None:
            perms, expires_at = cached
            if now < expires_at:
                return set(perms)  # 返回副本,防止外部修改

    # 2. 查 RBAC 存储(Pg / InMemory)
    perms = _query_permissions_from_store(user_id)

    # 3. 未分配 RBAC 角色时回退到 User.role 字段(向后兼容)
    if perms is None:
        user = get_user_store().get_by_id(user_id)
        if user is None:
            return set()  # 用户不存在,无权限
        perms = _fallback_permissions(user.role)

    # 4. 写缓存
    with _cache_lock:
        _permission_cache[user_id] = (set(perms), now + _CACHE_TTL_SECONDS)

    return perms


def has_permission(user_id: int, code: str) -> bool:
    """检查用户是否拥有指定权限。

    Args:
        user_id: 用户 ID(正整数)
        code: 权限码(非空,如 "document:read")

    Returns:
        True 表示拥有该权限

    Raises:
        ValueError: user_id 为 None 或 code 为空
    """
    if not code or not isinstance(code, str):
        raise ValueError("code 必须为非空字符串")
    return code in get_user_permissions(user_id)


def has_any_permission(user_id: int, *codes: str) -> bool:
    """检查用户是否拥有任一权限。

    Args:
        user_id: 用户 ID
        *codes: 权限码(至少一个)

    Returns:
        True 表示拥有任一权限
    """
    perms = get_user_permissions(user_id)
    return any(c in perms for c in codes)


def has_all_permissions(user_id: int, *codes: str) -> bool:
    """检查用户是否拥有全部权限。

    Args:
        user_id: 用户 ID
        *codes: 权限码(至少一个)

    Returns:
        True 表示拥有全部权限
    """
    perms = get_user_permissions(user_id)
    return all(c in perms for c in codes)


def check_permission(user_id: int, code: str) -> None:
    """检查权限,失败时抛 PermissionDenied(供非 HTTP 上下文使用)。

    与 has_permission 的区别:此函数在权限不足时抛异常而非返回 False。
    HTTP 上下文请使用 require_permission 装饰器(抛 HTTPException 403)。

    Args:
        user_id: 用户 ID(正整数)
        code: 权限码(非空)

    Raises:
        PermissionDenied: 用户不具备指定权限
        ValueError: user_id 为 None 或 code 为空
    """
    if not has_permission(user_id, code):
        raise PermissionDenied(user_id, code)


# ---------------------------------------------------------------------------
# FastAPI 依赖装饰器
# ---------------------------------------------------------------------------


def require_permission(code: str) -> Callable:
    """要求当前用户拥有指定权限,否则 403。

    用法:
        @router.post("/documents/upload")
        async def upload(_: dict = Depends(require_permission("document:upload"))):
            ...

    Args:
        code: 权限码(非空,如 "document:upload")

    Returns:
        FastAPI 依赖函数
    """

    def _dep(
        http_request: Request,
        payload: dict = Depends(verify_jwt_token),
    ) -> dict:
        user_id = payload.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise HTTPException(status_code=401, detail="Token 缺少有效的 user_id")
        if not has_permission(user_id, code):
            _audit_permission_denied(user_id, [code], http_request)
            raise HTTPException(
                status_code=403,
                detail=f"权限不足:需要 {code}",
            )
        return payload

    return _dep


def require_any_permission(*codes: str) -> Callable:
    """要求当前用户拥有任一权限,否则 403。

    用法:
        @router.get("/users")
        async def list_users(_: dict = Depends(require_any_permission("user:read", "user:manage"))):
            ...

    Args:
        *codes: 权限码(至少一个)

    Returns:
        FastAPI 依赖函数
    """

    def _dep(
        http_request: Request,
        payload: dict = Depends(verify_jwt_token),
    ) -> dict:
        user_id = payload.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise HTTPException(status_code=401, detail="Token 缺少有效的 user_id")
        if not has_any_permission(user_id, *codes):
            _audit_permission_denied(user_id, list(codes), http_request)
            raise HTTPException(
                status_code=403,
                detail=f"权限不足:需要以下任一权限 {list(codes)}",
            )
        return payload

    return _dep


def require_all_permissions(*codes: str) -> Callable:
    """要求当前用户拥有全部权限,否则 403。

    Args:
        *codes: 权限码(至少一个)

    Returns:
        FastAPI 依赖函数
    """

    def _dep(
        http_request: Request,
        payload: dict = Depends(verify_jwt_token),
    ) -> dict:
        user_id = payload.get("user_id")
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise HTTPException(status_code=401, detail="Token 缺少有效的 user_id")
        if not has_all_permissions(user_id, *codes):
            _audit_permission_denied(user_id, list(codes), http_request)
            raise HTTPException(
                status_code=403,
                detail=f"权限不足:需要以下全部权限 {list(codes)}",
            )
        return payload

    return _dep


def get_current_user_permissions(payload: dict = Depends(verify_jwt_token)) -> set[str]:
    """FastAPI 依赖:返回当前用户全部权限码集合(供前端菜单/按钮展示)。

    用法:
        @router.get("/auth/my-permissions")
        async def my_permissions(perms: Set[str] = Depends(get_current_user_permissions)):
            return {"permissions": list(perms)}

    Args:
        payload: JWT payload(含 user_id)

    Returns:
        权限码集合;user_id 无效时返回空集合
    """
    user_id = payload.get("user_id")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        return set()
    return get_user_permissions(user_id)
