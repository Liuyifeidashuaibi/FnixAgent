"""
API 路由 - RBAC 管理接口(Phase 2.1)。

提供:
    1. 权限查询(列表 / 详情)
    2. 角色 CRUD + 角色-权限分配
    3. 用户-角色分配(给用户分配 / 撤销角色,全量替换)
    4. 部门 CRUD + 树形查询
    5. 职位 CRUD
    6. 当前用户权限查询(供前端菜单/按钮控制)

鉴权:
    - 读类操作(列表/详情/树)要求 role:read / department:read / position:read
    - 写类操作要求 :create / :update / :delete / :assign
    - 使用 core.security.rbac.require_permission 装饰器
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from officeagent.api.schemas.models import BaseResponse
from officeagent.core.security.rbac import (
    get_current_user_permissions,
    get_user_permissions,
    require_permission,
    require_any_permission,
)
from officeagent.services.storage_rbac import get_rbac_store
from officeagent.api.routers.auth import verify_jwt_token, _get_user_or_404

router = APIRouter(prefix="/rbac", tags=["rbac"])


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class RoleCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_]+$",
                      description="角色代码:2-64位,字母/数字/下划线")
    name: str = Field(..., min_length=1, max_length=128, description="显示名")
    description: str = Field("", max_length=512)
    permission_codes: list[str] = Field(default_factory=list, description="权限码列表")
    sort_order: int = Field(0, ge=0, le=1000)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0, le=1000)


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str] = Field(..., description="全量替换的权限码列表")


class UserRoleAssign(BaseModel):
    role_ids: list[int] = Field(..., description="全量替换的角色 ID 列表")


class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    parent_id: Optional[int] = Field(None, description="父部门 ID,顶层部门不传")
    manager_id: Optional[int] = None
    description: str = Field("", max_length=512)
    sort_order: int = Field(0, ge=0, le=1000)


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    manager_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0, le=1000)


class PositionCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    level: int = Field(0, ge=0, le=100, description="级别:0-100,越大越高")
    description: str = Field("", max_length=512)
    sort_order: int = Field(0, ge=0, le=1000)


class PositionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    level: Optional[int] = Field(None, ge=0, le=100)
    description: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0, le=1000)


# ===========================================================================
# 权限查询
# ===========================================================================


@router.get("/permissions")
async def list_permissions(
    resource: Optional[str] = Query(None, description="按资源过滤,如 user/document/chat"),
    _: dict = Depends(require_any_permission("role:read", "system:manage")),
):
    """列出全部权限(可按 resource 分组过滤)。"""
    store = get_rbac_store()
    perms = store.list_permissions(resource=resource)
    return BaseResponse(success=True, data={"items": [p.to_dict() for p in perms], "total": len(perms)})


@router.get("/permissions/grouped")
async def list_permissions_grouped(
    _: dict = Depends(require_any_permission("role:read", "system:manage")),
):
    """按 resource 分组返回权限(前端权限矩阵展示用)。"""
    store = get_rbac_store()
    perms = store.list_permissions()
    grouped: dict[str, list] = {}
    for p in perms:
        grouped.setdefault(p.resource, []).append(p.to_dict())
    return BaseResponse(success=True, data=grouped)


# ===========================================================================
# 角色 CRUD
# ===========================================================================


@router.get("/roles")
async def list_roles(
    _: dict = Depends(require_permission("role:read")),
):
    """列出全部角色(含权限码)。"""
    store = get_rbac_store()
    roles = store.list_roles(include_permissions=True)
    return BaseResponse(success=True, data={"items": [r.to_dict() for r in roles], "total": len(roles)})


@router.get("/roles/{role_id}")
async def get_role(
    role_id: int,
    _: dict = Depends(require_permission("role:read")),
):
    """获取角色详情(含权限码)。"""
    store = get_rbac_store()
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return BaseResponse(success=True, data=role.to_dict())


@router.post("/roles")
async def create_role(
    body: RoleCreate,
    _: dict = Depends(require_permission("role:create")),
):
    """创建自定义角色。"""
    store = get_rbac_store()
    try:
        role = store.create_role(
            code=body.code, name=body.name, description=body.description,
            permission_codes=body.permission_codes, sort_order=body.sort_order,
        )
    except Exception as e:
        # 唯一约束冲突等
        raise HTTPException(status_code=409, detail=f"创建角色失败:{e}")
    return BaseResponse(success=True, data=role.to_dict())


@router.put("/roles/{role_id}")
async def update_role(
    role_id: int,
    body: RoleUpdate,
    _: dict = Depends(require_permission("role:update")),
):
    """更新角色(名称/描述/状态/排序)。"""
    store = get_rbac_store()
    role = store.update_role(
        role_id, name=body.name, description=body.description,
        is_active=body.is_active, sort_order=body.sort_order,
    )
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return BaseResponse(success=True, data=role.to_dict())


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    _: dict = Depends(require_permission("role:delete")),
):
    """删除角色(内置角色不可删)。"""
    store = get_rbac_store()
    try:
        ok = store.delete_role(role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    return BaseResponse(success=True, data={"deleted": True})


@router.put("/roles/{role_id}/permissions")
async def set_role_permissions(
    role_id: int,
    body: RolePermissionsUpdate,
    _: dict = Depends(require_permission("role:assign")),
):
    """全量替换角色的权限集合。"""
    store = get_rbac_store()
    role = store.set_role_permissions(role_id, body.permission_codes)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    return BaseResponse(success=True, data=role.to_dict())


# ===========================================================================
# 用户-角色分配
# ===========================================================================


@router.get("/users/{user_id}/roles")
async def get_user_roles(
    user_id: int,
    _: dict = Depends(require_any_permission("role:read", "role:assign")),
):
    """获取用户的角色列表。"""
    store = get_rbac_store()
    roles = store.get_user_roles(user_id)
    return BaseResponse(success=True, data={"items": [r.to_dict() for r in roles], "total": len(roles)})


@router.put("/users/{user_id}/roles")
async def set_user_roles(
    user_id: int,
    body: UserRoleAssign,
    payload: dict = Depends(require_permission("role:assign")),
):
    """全量替换用户的角色集合。

    角色变更后立即失效该用户的权限缓存,确保实时刷新。
    """
    # 确保用户存在
    _get_user_or_404(payload) if payload.get("user_id") == user_id else None
    store = get_rbac_store()
    granted_by = payload.get("user_id")
    store.set_user_roles(user_id, body.role_ids, granted_by=granted_by)
    roles = store.get_user_roles(user_id)
    return BaseResponse(success=True, data={"items": [r.to_dict() for r in roles], "total": len(roles)})


@router.post("/users/{user_id}/roles/{role_id}")
async def assign_role(
    user_id: int,
    role_id: int,
    payload: dict = Depends(require_permission("role:assign")),
):
    """给用户分配单个角色(幂等)。"""
    store = get_rbac_store()
    granted_by = payload.get("user_id")
    ok = store.assign_role_to_user(user_id, role_id, granted_by=granted_by)
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    return BaseResponse(success=True, data={"assigned": True})


@router.delete("/users/{user_id}/roles/{role_id}")
async def revoke_role(
    user_id: int,
    role_id: int,
    _: dict = Depends(require_permission("role:assign")),
):
    """撤销用户的单个角色。"""
    store = get_rbac_store()
    ok = store.revoke_role_from_user(user_id, role_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户未分配该角色")
    return BaseResponse(success=True, data={"revoked": True})


# ===========================================================================
# 当前用户权限查询(供前端菜单/按钮控制)
# ===========================================================================


@router.get("/my-permissions")
async def my_permissions(
    perms: set = Depends(get_current_user_permissions),
):
    """返回当前用户全部权限码(供前端菜单/按钮级权限控制)。"""
    return BaseResponse(success=True, data={"permissions": sorted(perms)})


@router.get("/users/{user_id}/permissions")
async def get_user_permissions_endpoint(
    user_id: int,
    _: dict = Depends(require_any_permission("role:read", "role:assign")),
):
    """查询指定用户的全部权限码(管理员查看用)。"""
    perms = get_user_permissions(user_id)
    return BaseResponse(success=True, data={"permissions": sorted(perms)})


# ===========================================================================
# 部门 CRUD + 树形查询
# ===========================================================================


@router.get("/departments")
async def list_departments(
    _: dict = Depends(require_permission("department:read")),
):
    """列出全部部门(扁平)。"""
    store = get_rbac_store()
    depts = store.list_departments()
    return BaseResponse(success=True, data={"items": [d.to_dict() for d in depts], "total": len(depts)})


@router.get("/departments/tree")
async def get_department_tree(
    _: dict = Depends(require_permission("department:read")),
):
    """返回部门树形结构。"""
    store = get_rbac_store()
    tree = store.get_department_tree()
    return BaseResponse(success=True, data={"tree": [d.to_dict() for d in tree]})


@router.post("/departments")
async def create_department(
    body: DepartmentCreate,
    _: dict = Depends(require_permission("department:create")),
):
    """创建部门。"""
    store = get_rbac_store()
    try:
        dept = store.create_department(
            code=body.code, name=body.name, parent_id=body.parent_id,
            manager_id=body.manager_id, description=body.description,
            sort_order=body.sort_order,
        )
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"创建部门失败:{e}")
    return BaseResponse(success=True, data=dept.to_dict())


@router.put("/departments/{dept_id}")
async def update_department(
    dept_id: int,
    body: DepartmentUpdate,
    _: dict = Depends(require_permission("department:update")),
):
    """更新部门。"""
    store = get_rbac_store()
    try:
        dept = store.update_department(
            dept_id, name=body.name, parent_id=body.parent_id,
            manager_id=body.manager_id, description=body.description,
            is_active=body.is_active, sort_order=body.sort_order,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")
    return BaseResponse(success=True, data=dept.to_dict())


@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: int,
    _: dict = Depends(require_permission("department:delete")),
):
    """删除部门(子部门级联删除)。"""
    store = get_rbac_store()
    ok = store.delete_department(dept_id)
    if not ok:
        raise HTTPException(status_code=404, detail="部门不存在")
    return BaseResponse(success=True, data={"deleted": True})


# ===========================================================================
# 职位 CRUD
# ===========================================================================


@router.get("/positions")
async def list_positions(
    _: dict = Depends(require_permission("position:read")),
):
    """列出全部职位(按级别降序)。"""
    store = get_rbac_store()
    positions = store.list_positions()
    return BaseResponse(success=True, data={"items": [p.to_dict() for p in positions], "total": len(positions)})


@router.post("/positions")
async def create_position(
    body: PositionCreate,
    _: dict = Depends(require_permission("position:create")),
):
    """创建职位。"""
    store = get_rbac_store()
    try:
        pos = store.create_position(
            code=body.code, name=body.name, level=body.level,
            description=body.description, sort_order=body.sort_order,
        )
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"创建职位失败:{e}")
    return BaseResponse(success=True, data=pos.to_dict())


@router.put("/positions/{pos_id}")
async def update_position(
    pos_id: int,
    body: PositionUpdate,
    _: dict = Depends(require_permission("position:update")),
):
    """更新职位。"""
    store = get_rbac_store()
    pos = store.update_position(
        pos_id, name=body.name, level=body.level,
        description=body.description, is_active=body.is_active,
        sort_order=body.sort_order,
    )
    if not pos:
        raise HTTPException(status_code=404, detail="职位不存在")
    return BaseResponse(success=True, data=pos.to_dict())


@router.delete("/positions/{pos_id}")
async def delete_position(
    pos_id: int,
    _: dict = Depends(require_permission("position:delete")),
):
    """删除职位。"""
    store = get_rbac_store()
    ok = store.delete_position(pos_id)
    if not ok:
        raise HTTPException(status_code=404, detail="职位不存在")
    return BaseResponse(success=True, data={"deleted": True})
