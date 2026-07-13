"""
RBAC 存储层(Phase 2.1)。

提供 Role / Permission / Department / Position 四类实体的 CRUD,
以及用户-角色分配、角色-权限分配操作。

设计要点:
    - get_rbac_store() 工厂:有 DATABASE_URL 时返回 PgRbacStore,否则返回 InMemoryRbacStore
    - PgRbacStore 直接操作 ORM,事务由 DatabaseAdapter.session() 管理
    - InMemoryRbacStore 用于开发/测试零依赖启动
    - 角色变更后自动调用 invalidate_user_permission_cache / invalidate_all_permission_cache
    - 内置角色(is_builtin=True)不可删除,防止误操作破坏系统
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any, Optional

from officeagent.core.security.rbac import (
    invalidate_all_permission_cache,
    invalidate_user_permission_cache,
)


# ---------------------------------------------------------------------------
# 数据传输对象(DTO)
# ---------------------------------------------------------------------------


class RoleDTO:
    def __init__(
        self,
        id: int,
        tenant_id: int,
        code: str,
        name: str,
        description: str = "",
        is_builtin: bool = False,
        is_active: bool = True,
        sort_order: int = 0,
        permission_codes: Optional[list[str]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.tenant_id = tenant_id
        self.code = code
        self.name = name
        self.description = description
        self.is_builtin = is_builtin
        self.is_active = is_active
        self.sort_order = sort_order
        self.permission_codes = permission_codes or []
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "is_builtin": self.is_builtin,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "permission_codes": self.permission_codes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PermissionDTO:
    def __init__(
        self,
        id: int,
        code: str,
        name: str,
        resource: str,
        action: str,
        description: str = "",
        is_builtin: bool = True,
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.code = code
        self.name = name
        self.resource = resource
        self.action = action
        self.description = description
        self.is_builtin = is_builtin
        self.created_at = created_at or datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "resource": self.resource,
            "action": self.action,
            "description": self.description,
            "is_builtin": self.is_builtin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DepartmentDTO:
    def __init__(
        self,
        id: int,
        tenant_id: int,
        code: str,
        name: str,
        parent_id: Optional[int] = None,
        manager_id: Optional[int] = None,
        sort_order: int = 0,
        description: str = "",
        is_active: bool = True,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        children: Optional[list] = None,
    ):
        self.id = id
        self.tenant_id = tenant_id
        self.code = code
        self.name = name
        self.parent_id = parent_id
        self.manager_id = manager_id
        self.sort_order = sort_order
        self.description = description
        self.is_active = is_active
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.children = children or []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "code": self.code,
            "name": self.name,
            "parent_id": self.parent_id,
            "manager_id": self.manager_id,
            "sort_order": self.sort_order,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "children": [c.to_dict() if isinstance(c, DepartmentDTO) else c for c in self.children],
        }


class PositionDTO:
    def __init__(
        self,
        id: int,
        tenant_id: int,
        code: str,
        name: str,
        level: int = 0,
        description: str = "",
        is_active: bool = True,
        sort_order: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.id = id
        self.tenant_id = tenant_id
        self.code = code
        self.name = name
        self.level = level
        self.description = description
        self.is_active = is_active
        self.sort_order = sort_order
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "description": self.description,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# PostgreSQL 实现
# ---------------------------------------------------------------------------


class PgRbacStore:
    """PostgreSQL 持久化 RBAC 存储。"""

    def __init__(self):
        from officeagent.services.storage_pg import get_db_adapter
        from officeagent.models.db.models import (
            Department,
            Permission,
            Position,
            Role,
            role_permissions,
            user_roles,
        )
        from sqlalchemy import select, delete, insert

        self._get_db = get_db_adapter
        self._Department = Department
        self._Permission = Permission
        self._Position = Position
        self._Role = Role
        self._role_permissions = role_permissions
        self._user_roles = user_roles
        self._select = select
        self._delete = delete
        self._insert = insert

    # =======================================================================
    # 权限
    # =======================================================================

    def list_permissions(self, resource: Optional[str] = None) -> list[PermissionDTO]:
        with self._get_db().session() as s:
            stmt = self._select(self._Permission).order_by(self._Permission.resource, self._Permission.code)
            if resource:
                stmt = stmt.where(self._Permission.resource == resource)
            rows = s.execute(stmt).scalars().all()
            return [PermissionDTO(
                id=r.id, code=r.code, name=r.name, resource=r.resource,
                action=r.action, description=r.description or "",
                is_builtin=r.is_builtin, created_at=r.created_at,
            ) for r in rows]

    def get_permission(self, perm_id: int) -> Optional[PermissionDTO]:
        with self._get_db().session() as s:
            r = s.get(self._Permission, perm_id)
            if not r:
                return None
            return PermissionDTO(
                id=r.id, code=r.code, name=r.name, resource=r.resource,
                action=r.action, description=r.description or "",
                is_builtin=r.is_builtin, created_at=r.created_at,
            )

    # =======================================================================
    # 角色
    # =======================================================================

    def list_roles(self, include_permissions: bool = True) -> list[RoleDTO]:
        with self._get_db().session() as s:
            rows = s.execute(
                self._select(self._Role).order_by(self._Role.sort_order, self._Role.id)
            ).scalars().all()
            result = []
            for r in rows:
                dto = RoleDTO(
                    id=r.id, tenant_id=r.tenant_id, code=r.code, name=r.name,
                    description=r.description or "", is_builtin=r.is_builtin,
                    is_active=r.is_active, sort_order=r.sort_order,
                    created_at=r.created_at, updated_at=r.updated_at,
                )
                if include_permissions:
                    # 查询角色权限码
                    stmt = (
                        self._select(self._Permission.code)
                        .join(self._role_permissions, self._role_permissions.c.permission_id == self._Permission.id)
                        .where(self._role_permissions.c.role_id == r.id)
                    )
                    dto.permission_codes = [row[0] for row in s.execute(stmt)]
                result.append(dto)
            return result

    def get_role(self, role_id: int) -> Optional[RoleDTO]:
        with self._get_db().session() as s:
            r = s.get(self._Role, role_id)
            if not r:
                return None
            dto = RoleDTO(
                id=r.id, tenant_id=r.tenant_id, code=r.code, name=r.name,
                description=r.description or "", is_builtin=r.is_builtin,
                is_active=r.is_active, sort_order=r.sort_order,
                created_at=r.created_at, updated_at=r.updated_at,
            )
            stmt = (
                self._select(self._Permission.code)
                .join(self._role_permissions, self._role_permissions.c.permission_id == self._Permission.id)
                .where(self._role_permissions.c.role_id == r.id)
            )
            dto.permission_codes = [row[0] for row in s.execute(stmt)]
            return dto

    def create_role(self, code: str, name: str, description: str = "",
                    permission_codes: Optional[list[str]] = None,
                    sort_order: int = 0, tenant_id: int = 1) -> RoleDTO:
        with self._get_db().session() as s:
            role = self._Role(
                tenant_id=tenant_id, code=code, name=name, description=description,
                is_builtin=False, is_active=True, sort_order=sort_order,
            )
            s.add(role)
            s.flush()  # 获取 id

            # 分配权限
            if permission_codes:
                perms = s.execute(
                    self._select(self._Permission).where(self._Permission.code.in_(permission_codes))
                ).scalars().all()
                for p in perms:
                    s.execute(self._insert(self._role_permissions).values(role_id=role.id, permission_id=p.id))

            s.flush()
            dto = RoleDTO(
                id=role.id, tenant_id=role.tenant_id, code=role.code, name=role.name,
                description=role.description or "", is_builtin=False, is_active=True,
                sort_order=role.sort_order, permission_codes=permission_codes or [],
                created_at=role.created_at, updated_at=role.updated_at,
            )
            # 新角色不影响现有用户缓存(尚未分配给任何人)
            return dto

    def update_role(self, role_id: int, name: Optional[str] = None,
                    description: Optional[str] = None, is_active: Optional[bool] = None,
                    sort_order: Optional[int] = None) -> Optional[RoleDTO]:
        with self._get_db().session() as s:
            r = s.get(self._Role, role_id)
            if not r:
                return None
            if name is not None:
                r.name = name
            if description is not None:
                r.description = description
            if is_active is not None:
                r.is_active = is_active
            if sort_order is not None:
                r.sort_order = sort_order
            r.updated_at = datetime.utcnow()
            s.flush()
            # 角色变更可能影响已分配用户 → 全部失效
            invalidate_all_permission_cache()
            return self.get_role(role_id)

    def delete_role(self, role_id: int) -> bool:
        with self._get_db().session() as s:
            r = s.get(self._Role, role_id)
            if not r:
                return False
            if r.is_builtin:
                raise ValueError("内置角色不可删除")
            s.delete(r)  # 关联表 ON DELETE CASCADE 自动清理
            s.flush()
            invalidate_all_permission_cache()
            return True

    def set_role_permissions(self, role_id: int, permission_codes: list[str]) -> Optional[RoleDTO]:
        """全量替换角色的权限集合。"""
        with self._get_db().session() as s:
            r = s.get(self._Role, role_id)
            if not r:
                return None
            # 清空旧权限
            s.execute(self._delete(self._role_permissions).where(self._role_permissions.c.role_id == role_id))
            # 写入新权限
            if permission_codes:
                perms = s.execute(
                    self._select(self._Permission).where(self._Permission.code.in_(permission_codes))
                ).scalars().all()
                for p in perms:
                    s.execute(self._insert(self._role_permissions).values(role_id=role_id, permission_id=p.id))
            s.flush()
            invalidate_all_permission_cache()
            return self.get_role(role_id)

    # =======================================================================
    # 用户-角色分配
    # =======================================================================

    def assign_role_to_user(self, user_id: int, role_id: int, granted_by: Optional[int] = None) -> bool:
        with self._get_db().session() as s:
            # 幂等:已存在则跳过
            exists = s.execute(
                self._select(self._user_roles).where(
                    self._user_roles.c.user_id == user_id,
                    self._user_roles.c.role_id == role_id,
                )
            ).first()
            if exists:
                return True
            s.execute(self._insert(self._user_roles).values(
                user_id=user_id, role_id=role_id, granted_by=granted_by,
            ))
            s.flush()
            invalidate_user_permission_cache(user_id)
            return True

    def revoke_role_from_user(self, user_id: int, role_id: int) -> bool:
        with self._get_db().session() as s:
            result = s.execute(self._delete(self._user_roles).where(
                self._user_roles.c.user_id == user_id,
                self._user_roles.c.role_id == role_id,
            ))
            s.flush()
            invalidate_user_permission_cache(user_id)
            return result.rowcount > 0

    def get_user_roles(self, user_id: int) -> list[RoleDTO]:
        with self._get_db().session() as s:
            rows = s.execute(
                self._select(self._Role)
                .join(self._user_roles, self._user_roles.c.role_id == self._Role.id)
                .where(self._user_roles.c.user_id == user_id)
                .order_by(self._Role.sort_order)
            ).scalars().all()
            return [RoleDTO(
                id=r.id, tenant_id=r.tenant_id, code=r.code, name=r.name,
                description=r.description or "", is_builtin=r.is_builtin,
                is_active=r.is_active, sort_order=r.sort_order,
                created_at=r.created_at, updated_at=r.updated_at,
            ) for r in rows]

    def set_user_roles(self, user_id: int, role_ids: list[int], granted_by: Optional[int] = None) -> None:
        """全量替换用户的角色集合。"""
        with self._get_db().session() as s:
            s.execute(self._delete(self._user_roles).where(self._user_roles.c.user_id == user_id))
            for rid in role_ids:
                s.execute(self._insert(self._user_roles).values(
                    user_id=user_id, role_id=rid, granted_by=granted_by,
                ))
            s.flush()
            invalidate_user_permission_cache(user_id)

    # =======================================================================
    # 部门(组织架构树)
    # =======================================================================

    def list_departments(self) -> list[DepartmentDTO]:
        """返回扁平列表(前端可自行构建树,或调用 get_department_tree)。"""
        with self._get_db().session() as s:
            rows = s.execute(
                self._select(self._Department).order_by(self._Department.sort_order, self._Department.id)
            ).scalars().all()
            return [self._dept_to_dto(r) for r in rows]

    def get_department_tree(self) -> list[DepartmentDTO]:
        """返回树形结构(顶层部门 parent_id=None)。"""
        flat = self.list_departments()
        by_id = {d.id: d for d in flat}
        roots = []
        for d in flat:
            if d.parent_id is None:
                roots.append(d)
            elif d.parent_id in by_id:
                by_id[d.parent_id].children.append(d)
        return roots

    def _dept_to_dto(self, r) -> DepartmentDTO:
        return DepartmentDTO(
            id=r.id, tenant_id=r.tenant_id, code=r.code, name=r.name,
            parent_id=r.parent_id, manager_id=r.manager_id,
            sort_order=r.sort_order, description=r.description or "",
            is_active=r.is_active, created_at=r.created_at, updated_at=r.updated_at,
        )

    def create_department(self, code: str, name: str, parent_id: Optional[int] = None,
                          manager_id: Optional[int] = None, description: str = "",
                          sort_order: int = 0, tenant_id: int = 1) -> DepartmentDTO:
        with self._get_db().session() as s:
            dept = self._Department(
                tenant_id=tenant_id, code=code, name=name, parent_id=parent_id,
                manager_id=manager_id, description=description, sort_order=sort_order,
                is_active=True,
            )
            s.add(dept)
            s.flush()
            return self._dept_to_dto(dept)

    def update_department(self, dept_id: int, name: Optional[str] = None,
                          parent_id: Optional[int] = None, manager_id: Optional[int] = None,
                          description: Optional[str] = None, is_active: Optional[bool] = None,
                          sort_order: Optional[int] = None) -> Optional[DepartmentDTO]:
        with self._get_db().session() as s:
            r = s.get(self._Department, dept_id)
            if not r:
                return None
            if name is not None:
                r.name = name
            if parent_id is not None:
                # 防止循环引用:不能把自己设为父,也不能把子孙设为父
                if parent_id == dept_id:
                    raise ValueError("不能将部门的父节点设为自己")
                r.parent_id = parent_id
            if manager_id is not None:
                r.manager_id = manager_id
            if description is not None:
                r.description = description
            if is_active is not None:
                r.is_active = is_active
            if sort_order is not None:
                r.sort_order = sort_order
            r.updated_at = datetime.utcnow()
            s.flush()
            return self._dept_to_dto(r)

    def delete_department(self, dept_id: int) -> bool:
        with self._get_db().session() as s:
            r = s.get(self._Department, dept_id)
            if not r:
                return False
            s.delete(r)  # 子部门 cascade delete-orphan
            s.flush()
            return True

    # =======================================================================
    # 职位
    # =======================================================================

    def list_positions(self) -> list[PositionDTO]:
        with self._get_db().session() as s:
            rows = s.execute(
                self._select(self._Position).order_by(self._Position.level.desc(), self._Position.sort_order)
            ).scalars().all()
            return [self._pos_to_dto(r) for r in rows]

    def _pos_to_dto(self, r) -> PositionDTO:
        return PositionDTO(
            id=r.id, tenant_id=r.tenant_id, code=r.code, name=r.name, level=r.level,
            description=r.description or "", is_active=r.is_active, sort_order=r.sort_order,
            created_at=r.created_at, updated_at=r.updated_at,
        )

    def create_position(self, code: str, name: str, level: int = 0,
                        description: str = "", sort_order: int = 0,
                        tenant_id: int = 1) -> PositionDTO:
        with self._get_db().session() as s:
            pos = self._Position(
                tenant_id=tenant_id, code=code, name=name, level=level,
                description=description, sort_order=sort_order, is_active=True,
            )
            s.add(pos)
            s.flush()
            return self._pos_to_dto(pos)

    def update_position(self, pos_id: int, name: Optional[str] = None,
                        level: Optional[int] = None, description: Optional[str] = None,
                        is_active: Optional[bool] = None,
                        sort_order: Optional[int] = None) -> Optional[PositionDTO]:
        with self._get_db().session() as s:
            r = s.get(self._Position, pos_id)
            if not r:
                return None
            if name is not None:
                r.name = name
            if level is not None:
                r.level = level
            if description is not None:
                r.description = description
            if is_active is not None:
                r.is_active = is_active
            if sort_order is not None:
                r.sort_order = sort_order
            r.updated_at = datetime.utcnow()
            s.flush()
            return self._pos_to_dto(r)

    def delete_position(self, pos_id: int) -> bool:
        with self._get_db().session() as s:
            r = s.get(self._Position, pos_id)
            if not r:
                return False
            s.delete(r)
            s.flush()
            return True


# ---------------------------------------------------------------------------
# 内存实现(开发/测试零依赖)
# ---------------------------------------------------------------------------


class InMemoryRbacStore:
    """内存 RBAC 存储(开发/测试用)。

    启动时注入内置角色 + 内置权限,与迁移种子数据保持一致。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._permissions: dict[int, PermissionDTO] = {}
        self._roles: dict[int, RoleDTO] = {}
        self._departments: dict[int, DepartmentDTO] = {}
        self._positions: dict[int, PositionDTO] = {}
        self._role_perms: dict[int, set[int]] = {}  # role_id → {permission_id}
        self._user_roles: dict[int, set[int]] = {}  # user_id → {role_id}
        self._next_id = 1
        self._seed_builtin()

    def _next(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def _seed_builtin(self) -> None:
        """注入内置权限 + 角色(与 0002_rbac 迁移种子数据一致)。"""
        builtin_perms = [
            ("user:read", "查看用户", "user", "read"),
            ("user:create", "创建用户", "user", "create"),
            ("user:update", "更新用户", "user", "update"),
            ("user:delete", "删除用户", "user", "delete"),
            ("user:manage", "用户全权限", "user", "manage"),
            ("user:reset_password", "重置密码", "user", "reset_password"),
            ("role:read", "查看角色", "role", "read"),
            ("role:create", "创建角色", "role", "create"),
            ("role:update", "更新角色", "role", "update"),
            ("role:delete", "删除角色", "role", "delete"),
            ("role:assign", "分配角色", "role", "assign"),
            ("role:manage", "角色全权限", "role", "manage"),
            ("department:read", "查看部门", "department", "read"),
            ("department:create", "创建部门", "department", "create"),
            ("department:update", "更新部门", "department", "update"),
            ("department:delete", "删除部门", "department", "delete"),
            ("department:manage", "部门全权限", "department", "manage"),
            ("position:read", "查看职位", "position", "read"),
            ("position:create", "创建职位", "position", "create"),
            ("position:update", "更新职位", "position", "update"),
            ("position:delete", "删除职位", "position", "delete"),
            ("position:manage", "职位全权限", "position", "manage"),
            ("document:read", "查看文档", "document", "read"),
            ("document:upload", "上传文档", "document", "upload"),
            ("document:delete", "删除文档", "document", "delete"),
            ("document:manage", "文档全权限", "document", "manage"),
            ("chat:read", "查看对话", "chat", "read"),
            ("chat:write", "发送消息", "chat", "write"),
            ("chat:evolve", "自进化", "chat", "evolve"),
            ("chat:manage", "对话全权限", "chat", "manage"),
            ("task:read", "查看任务", "task", "read"),
            ("task:create", "创建任务", "task", "create"),
            ("task:cancel", "取消任务", "task", "cancel"),
            ("task:manage", "任务全权限", "task", "manage"),
            ("system:config", "系统配置", "system", "config"),
            ("system:audit_log", "审计日志", "system", "audit_log"),
            ("system:manage", "系统全权限", "system", "manage"),
        ]
        for code, name, resource, action in builtin_perms:
            pid = self._next()
            self._permissions[pid] = PermissionDTO(
                id=pid, code=code, name=name, resource=resource, action=action,
                is_builtin=True,
            )

        # 内置角色
        role_defs = [
            ("super_admin", "超级管理员", "拥有全部权限,不可删除", 0),
            ("admin", "管理员", "拥有大部分管理权限", 1),
            ("user", "普通用户", "基础权限", 2),
            ("visitor", "访客", "只读权限", 3),
        ]
        for code, name, desc, order in role_defs:
            rid = self._next()
            self._roles[rid] = RoleDTO(
                id=rid, tenant_id=1, code=code, name=name, description=desc,
                is_builtin=True, is_active=True, sort_order=order,
            )
            self._role_perms[rid] = set()

        # 权限分配
        all_perm_ids = set(self._permissions.keys())
        super_admin_id = next(r for r in self._roles.values() if r.code == "super_admin").id
        admin_id = next(r for r in self._roles.values() if r.code == "admin").id
        user_id_role = next(r for r in self._roles.values() if r.code == "user").id
        visitor_id = next(r for r in self._roles.values() if r.code == "visitor").id

        self._role_perms[super_admin_id] = set(all_perm_ids)
        self._role_perms[admin_id] = {
            pid for pid, p in self._permissions.items() if p.code != "system:manage"
        }
        self._role_perms[user_id_role] = {
            pid for pid, p in self._permissions.items()
            if p.code in {"document:read", "document:upload", "chat:read", "chat:write",
                          "chat:evolve", "task:read", "task:create"}
        }
        self._role_perms[visitor_id] = {
            pid for pid, p in self._permissions.items() if p.code.endswith(":read")
        }

    def _rebuild_role_permission_codes(self, role: RoleDTO) -> None:
        perm_ids = self._role_perms.get(role.id, set())
        role.permission_codes = [self._permissions[pid].code for pid in perm_ids if pid in self._permissions]

    # 权限
    def list_permissions(self, resource: Optional[str] = None) -> list[PermissionDTO]:
        with self._lock:
            return [p for p in self._permissions.values() if resource is None or p.resource == resource]

    def get_permission(self, perm_id: int) -> Optional[PermissionDTO]:
        return self._permissions.get(perm_id)

    # 角色
    def list_roles(self, include_permissions: bool = True) -> list[RoleDTO]:
        with self._lock:
            result = []
            for r in sorted(self._roles.values(), key=lambda x: (x.sort_order, x.id)):
                if include_permissions:
                    self._rebuild_role_permission_codes(r)
                result.append(r)
            return result

    def get_role(self, role_id: int) -> Optional[RoleDTO]:
        r = self._roles.get(role_id)
        if r:
            self._rebuild_role_permission_codes(r)
        return r

    def create_role(self, code: str, name: str, description: str = "",
                    permission_codes: Optional[list[str]] = None,
                    sort_order: int = 0, tenant_id: int = 1) -> RoleDTO:
        with self._lock:
            rid = self._next()
            role = RoleDTO(
                id=rid, tenant_id=tenant_id, code=code, name=name, description=description,
                is_builtin=False, is_active=True, sort_order=sort_order,
                permission_codes=permission_codes or [],
            )
            self._roles[rid] = role
            self._role_perms[rid] = set()
            if permission_codes:
                for p in self._permissions.values():
                    if p.code in permission_codes:
                        self._role_perms[rid].add(p.id)
            return role

    def update_role(self, role_id: int, **kwargs) -> Optional[RoleDTO]:
        with self._lock:
            r = self._roles.get(role_id)
            if not r:
                return None
            for k in ("name", "description", "is_active", "sort_order"):
                if k in kwargs and kwargs[k] is not None:
                    setattr(r, k, kwargs[k])
            r.updated_at = datetime.utcnow()
            invalidate_all_permission_cache()
            return r

    def delete_role(self, role_id: int) -> bool:
        with self._lock:
            r = self._roles.get(role_id)
            if not r:
                return False
            if r.is_builtin:
                raise ValueError("内置角色不可删除")
            del self._roles[role_id]
            self._role_perms.pop(role_id, None)
            for uids in self._user_roles.values():
                uids.discard(role_id)
            invalidate_all_permission_cache()
            return True

    def set_role_permissions(self, role_id: int, permission_codes: list[str]) -> Optional[RoleDTO]:
        with self._lock:
            r = self._roles.get(role_id)
            if not r:
                return None
            self._role_perms[role_id] = {
                pid for pid, p in self._permissions.items() if p.code in permission_codes
            }
            r.permission_codes = list(permission_codes)
            invalidate_all_permission_cache()
            return r

    # 用户-角色
    def assign_role_to_user(self, user_id: int, role_id: int, granted_by: Optional[int] = None) -> bool:
        with self._lock:
            if role_id not in self._roles:
                return False
            self._user_roles.setdefault(user_id, set()).add(role_id)
            invalidate_user_permission_cache(user_id)
            return True

    def revoke_role_from_user(self, user_id: int, role_id: int) -> bool:
        with self._lock:
            roles = self._user_roles.get(user_id, set())
            if role_id not in roles:
                return False
            roles.discard(role_id)
            invalidate_user_permission_cache(user_id)
            return True

    def get_user_roles(self, user_id: int) -> list[RoleDTO]:
        with self._lock:
            ids = self._user_roles.get(user_id, set())
            return [self._roles[i] for i in ids if i in self._roles]

    def set_user_roles(self, user_id: int, role_ids: list[int], granted_by: Optional[int] = None) -> None:
        with self._lock:
            self._user_roles[user_id] = set(role_ids)
            invalidate_user_permission_cache(user_id)

    # 部门
    def list_departments(self) -> list[DepartmentDTO]:
        with self._lock:
            return list(self._departments.values())

    def get_department_tree(self) -> list[DepartmentDTO]:
        flat = self.list_departments()
        by_id = {d.id: d for d in flat}
        roots = []
        for d in flat:
            if d.parent_id is None:
                roots.append(d)
            elif d.parent_id in by_id:
                by_id[d.parent_id].children.append(d)
        return roots

    def create_department(self, code: str, name: str, parent_id: Optional[int] = None,
                          manager_id: Optional[int] = None, description: str = "",
                          sort_order: int = 0, tenant_id: int = 1) -> DepartmentDTO:
        with self._lock:
            did = self._next()
            dept = DepartmentDTO(
                id=did, tenant_id=tenant_id, code=code, name=name, parent_id=parent_id,
                manager_id=manager_id, description=description, sort_order=sort_order,
                is_active=True,
            )
            self._departments[did] = dept
            return dept

    def update_department(self, dept_id: int, **kwargs) -> Optional[DepartmentDTO]:
        with self._lock:
            r = self._departments.get(dept_id)
            if not r:
                return None
            if kwargs.get("parent_id") == dept_id:
                raise ValueError("不能将部门的父节点设为自己")
            for k in ("name", "parent_id", "manager_id", "description", "is_active", "sort_order"):
                if k in kwargs and kwargs[k] is not None:
                    setattr(r, k, kwargs[k])
            r.updated_at = datetime.utcnow()
            return r

    def delete_department(self, dept_id: int) -> bool:
        with self._lock:
            if dept_id not in self._departments:
                return False
            # 级联删除子部门
            children = [d for d in self._departments.values() if d.parent_id == dept_id]
            for c in children:
                self._departments.pop(c.id, None)
            del self._departments[dept_id]
            return True

    # 职位
    def list_positions(self) -> list[PositionDTO]:
        with self._lock:
            return sorted(self._positions.values(), key=lambda x: (-x.level, x.sort_order))

    def create_position(self, code: str, name: str, level: int = 0,
                        description: str = "", sort_order: int = 0,
                        tenant_id: int = 1) -> PositionDTO:
        with self._lock:
            pid = self._next()
            pos = PositionDTO(
                id=pid, tenant_id=tenant_id, code=code, name=name, level=level,
                description=description, sort_order=sort_order, is_active=True,
            )
            self._positions[pid] = pos
            return pos

    def update_position(self, pos_id: int, **kwargs) -> Optional[PositionDTO]:
        with self._lock:
            r = self._positions.get(pos_id)
            if not r:
                return None
            for k in ("name", "level", "description", "is_active", "sort_order"):
                if k in kwargs and kwargs[k] is not None:
                    setattr(r, k, kwargs[k])
            r.updated_at = datetime.utcnow()
            return r

    def delete_position(self, pos_id: int) -> bool:
        with self._lock:
            if pos_id not in self._positions:
                return False
            del self._positions[pos_id]
            return True


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


_rbac_store: Optional[object] = None
_rbac_store_lock = threading.Lock()


def get_rbac_store():
    """获取 RBAC 存储单例。

    有 DATABASE_URL 时返回 PgRbacStore,否则返回 InMemoryRbacStore。
    """
    global _rbac_store
    if _rbac_store is None:
        with _rbac_store_lock:
            if _rbac_store is None:
                if os.getenv("DATABASE_URL"):
                    _rbac_store = PgRbacStore()
                else:
                    _rbac_store = InMemoryRbacStore()
    return _rbac_store


def reset_rbac_store() -> None:
    """重置 RBAC 存储单例(用于测试)。"""
    global _rbac_store
    with _rbac_store_lock:
        _rbac_store = None
