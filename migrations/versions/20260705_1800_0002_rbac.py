"""rbac: add roles/permissions/departments/positions tables + user columns

Revision ID: 0002_rbac
Revises: 0001_initial
Create Date: 2026-07-05 18:00:00

Phase 2.1 RBAC 细粒度权限 + 组织架构:
    - 新增 4 张主表:roles / permissions / departments / positions
    - 新增 2 张关联表:role_permissions / user_roles(多对多)
    - users 表新增 department_id / position_id 两列(可空,向后兼容)
    - 插入内置角色 + 内置权限种子数据

注意:
    - 所有新列允许 NULL,旧数据不受影响
    - 内置角色/权限通过 is_builtin=True 标记,后续不可删除
    - 部门自引用(parent_id → departments.id)在表创建后单独添加
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_rbac"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 RBAC 相关表 + 种子数据。"""

    # ------------------------------------------------------------------
    # 1. permissions 表(无 FK,先建)
    # ------------------------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("resource", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=512), server_default=""),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_permission_code"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])

    # ------------------------------------------------------------------
    # 2. roles 表
    # ------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), server_default=""),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_role_code"),
    )

    # ------------------------------------------------------------------
    # 3. departments 表(自引用,先建表再加 FK)
    # ------------------------------------------------------------------
    op.create_table(
        "departments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("manager_id", sa.BigInteger(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("description", sa.String(length=512), server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_dept_code"),
        sa.ForeignKeyConstraint(["parent_id"], ["departments.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_departments_parent_id", "departments", ["parent_id"])

    # ------------------------------------------------------------------
    # 4. positions 表
    # ------------------------------------------------------------------
    op.create_table(
        "positions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("description", sa.String(length=512), server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_tenant_position_code"),
    )

    # ------------------------------------------------------------------
    # 5. users 表新增 department_id / position_id 列(可空)
    # ------------------------------------------------------------------
    op.add_column("users", sa.Column("department_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("position_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_users_department_id", "users", "departments", ["department_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_users_position_id", "users", "positions", ["position_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.create_index("ix_users_position_id", "users", ["position_id"])

    # ------------------------------------------------------------------
    # 6. role_permissions 关联表(多对多)
    # ------------------------------------------------------------------
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.BigInteger(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    # ------------------------------------------------------------------
    # 7. user_roles 关联表(多对多,含审计字段)
    # ------------------------------------------------------------------
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.BigInteger(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column("granted_by", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    # ------------------------------------------------------------------
    # 8. 种子数据:内置权限(按 resource 分组)
    # ------------------------------------------------------------------
    _BUILTIN_PERMISSIONS = [
        # 用户管理
        ("user:read", "查看用户", "user", "read"),
        ("user:create", "创建用户", "user", "create"),
        ("user:update", "更新用户", "user", "update"),
        ("user:delete", "删除用户", "user", "delete"),
        ("user:manage", "用户全权限", "user", "manage"),
        ("user:reset_password", "重置密码", "user", "reset_password"),
        # 角色管理
        ("role:read", "查看角色", "role", "read"),
        ("role:create", "创建角色", "role", "create"),
        ("role:update", "更新角色", "role", "update"),
        ("role:delete", "删除角色", "role", "delete"),
        ("role:assign", "分配角色", "role", "assign"),
        ("role:manage", "角色全权限", "role", "manage"),
        # 部门管理
        ("department:read", "查看部门", "department", "read"),
        ("department:create", "创建部门", "department", "create"),
        ("department:update", "更新部门", "department", "update"),
        ("department:delete", "删除部门", "department", "delete"),
        ("department:manage", "部门全权限", "department", "manage"),
        # 职位管理
        ("position:read", "查看职位", "position", "read"),
        ("position:create", "创建职位", "position", "create"),
        ("position:update", "更新职位", "position", "update"),
        ("position:delete", "删除职位", "position", "delete"),
        ("position:manage", "职位全权限", "position", "manage"),
        # 文档
        ("document:read", "查看文档", "document", "read"),
        ("document:upload", "上传文档", "document", "upload"),
        ("document:delete", "删除文档", "document", "delete"),
        ("document:manage", "文档全权限", "document", "manage"),
        # 对话
        ("chat:read", "查看对话", "chat", "read"),
        ("chat:write", "发送消息", "chat", "write"),
        ("chat:evolve", "自进化", "chat", "evolve"),
        ("chat:manage", "对话全权限", "chat", "manage"),
        # 任务
        ("task:read", "查看任务", "task", "read"),
        ("task:create", "创建任务", "task", "create"),
        ("task:cancel", "取消任务", "task", "cancel"),
        ("task:manage", "任务全权限", "task", "manage"),
        # 系统管理
        ("system:config", "系统配置", "system", "config"),
        ("system:audit_log", "审计日志", "system", "audit_log"),
        ("system:manage", "系统全权限", "system", "manage"),
    ]
    perm_table = sa.table(
        "permissions",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("resource", sa.String),
        sa.column("action", sa.String),
        sa.column("description", sa.String),
        sa.column("is_builtin", sa.Boolean),
        sa.column("created_at", sa.TIMESTAMP),
    )
    op.bulk_insert(
        perm_table,
        [
            {
                "code": code,
                "name": name,
                "resource": resource,
                "action": action,
                "description": "",
                "is_builtin": True,
                "created_at": sa.func.now(),
            }
            for code, name, resource, action in _BUILTIN_PERMISSIONS
        ],
    )

    # ------------------------------------------------------------------
    # 9. 种子数据:内置角色
    # ------------------------------------------------------------------
    role_table = sa.table(
        "roles",
        sa.column("tenant_id", sa.BigInteger),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_builtin", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.SmallInteger),
        sa.column("created_at", sa.TIMESTAMP),
        sa.column("updated_at", sa.TIMESTAMP),
    )
    op.bulk_insert(
        role_table,
        [
            {
                "tenant_id": 1,
                "code": "super_admin",
                "name": "超级管理员",
                "description": "拥有全部权限,不可删除",
                "is_builtin": True,
                "is_active": True,
                "sort_order": 0,
                "created_at": sa.func.now(),
                "updated_at": sa.func.now(),
            },
            {
                "tenant_id": 1,
                "code": "admin",
                "name": "管理员",
                "description": "拥有大部分管理权限(除系统全权限)",
                "is_builtin": True,
                "is_active": True,
                "sort_order": 1,
                "created_at": sa.func.now(),
                "updated_at": sa.func.now(),
            },
            {
                "tenant_id": 1,
                "code": "user",
                "name": "普通用户",
                "description": "基础权限:文档/对话/任务",
                "is_builtin": True,
                "is_active": True,
                "sort_order": 2,
                "created_at": sa.func.now(),
                "updated_at": sa.func.now(),
            },
            {
                "tenant_id": 1,
                "code": "visitor",
                "name": "访客",
                "description": "只读权限",
                "is_builtin": True,
                "is_active": True,
                "sort_order": 3,
                "created_at": sa.func.now(),
                "updated_at": sa.func.now(),
            },
        ],
    )

    # ------------------------------------------------------------------
    # 10. 种子数据:super_admin 拥有全部权限;admin 拥有除 system:manage 外的全部;user 拥有基础权限
    # ------------------------------------------------------------------
    conn = op.get_bind()

    # super_admin → all permissions
    conn.execute(
        sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p
            WHERE r.code = 'super_admin'
        """)
    )

    # admin → all except system:manage
    conn.execute(
        sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p
            WHERE r.code = 'admin' AND p.code != 'system:manage'
        """)
    )

    # user → document:read, document:upload, chat:read, chat:write, chat:evolve, task:read, task:create
    conn.execute(
        sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p
            WHERE r.code = 'user' AND p.code IN (
                'document:read', 'document:upload',
                'chat:read', 'chat:write', 'chat:evolve',
                'task:read', 'task:create'
            )
        """)
    )

    # visitor → only :read permissions
    conn.execute(
        sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id FROM roles r, permissions p
            WHERE r.code = 'visitor' AND p.code LIKE '%:read'
        """)
    )


def downgrade() -> None:
    """回滚 RBAC 表(保留 users 表原有列)。"""

    # 先删关联表
    op.drop_table("user_roles")
    op.drop_table("role_permissions")

    # users 表移除新列
    op.drop_index("ix_users_position_id", table_name="users")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_constraint("fk_users_position_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_column("users", "position_id")
    op.drop_column("users", "department_id")

    # 再删主表
    op.drop_table("positions")
    op.drop_table("departments")
    op.drop_table("roles")
    op.drop_index("ix_permissions_code", table_name="permissions")
    op.drop_table("permissions")
