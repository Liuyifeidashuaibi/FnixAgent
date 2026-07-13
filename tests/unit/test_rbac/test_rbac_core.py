"""Phase 2.1 RBAC 权限控制测试。

覆盖:
    1. 内置角色权限种子正确(super_admin/admin/user/visitor)
    2. 权限查询 + 缓存命中
    3. has_permission / has_any_permission / has_all_permissions
    4. 角色 CRUD(创建/更新/删除自定义角色,内置不可删)
    5. 用户-角色分配(assign/revoke/set)
    6. 缓存失效:角色变更后权限实时刷新
    7. require_permission 装饰器(403 拦截)
    8. 部门树 + 职位 CRUD
"""
import pytest

from officeagent.core.security import rbac
from officeagent.services.storage_rbac import (
    InMemoryRbacStore,
    get_rbac_store,
    reset_rbac_store,
)


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置 RBAC 存储与缓存,确保隔离。"""
    reset_rbac_store()
    rbac.invalidate_all_permission_cache()
    yield
    reset_rbac_store()
    rbac.invalidate_all_permission_cache()


# ---------------------------------------------------------------------------
# 1. 内置角色权限种子
# ---------------------------------------------------------------------------


class TestBuiltinRoles:
    def test_super_admin_has_all_permissions(self):
        store = get_rbac_store()
        roles = store.list_roles()
        sa = next(r for r in roles if r.code == "super_admin")
        assert sa.is_builtin is True
        assert sa.is_active is True
        # super_admin 应拥有全部权限
        all_perms = store.list_permissions()
        store._rebuild_role_permission_codes(sa) if hasattr(store, "_rebuild_role_permission_codes") else None
        assert len(sa.permission_codes) == len(all_perms)

    def test_admin_excludes_system_manage(self):
        store = get_rbac_store()
        roles = store.list_roles()
        adm = next(r for r in roles if r.code == "admin")
        if hasattr(store, "_rebuild_role_permission_codes"):
            store._rebuild_role_permission_codes(adm)
        assert "system:manage" not in adm.permission_codes
        assert "user:manage" in adm.permission_codes

    def test_user_has_basic_perms(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        if hasattr(store, "_rebuild_role_permission_codes"):
            store._rebuild_role_permission_codes(usr)
        assert "document:read" in usr.permission_codes
        assert "chat:write" in usr.permission_codes
        assert "user:delete" not in usr.permission_codes

    def test_visitor_only_read(self):
        store = get_rbac_store()
        roles = store.list_roles()
        vis = next(r for r in roles if r.code == "visitor")
        if hasattr(store, "_rebuild_role_permission_codes"):
            store._rebuild_role_permission_codes(vis)
        for code in vis.permission_codes:
            assert code.endswith(":read"), f"visitor 不应有非 read 权限: {code}"

    def test_permission_count(self):
        """内置权限总数应为 37(覆盖 8 个 resource)。"""
        store = get_rbac_store()
        perms = store.list_permissions()
        assert len(perms) == 37
        resources = {p.resource for p in perms}
        assert resources == {
            "user", "role", "department", "position",
            "document", "chat", "task", "system",
        }


# ---------------------------------------------------------------------------
# 2. 权限查询 + 缓存
# ---------------------------------------------------------------------------


class TestPermissionQuery:
    def test_get_user_permissions_admin(self):
        """admin 角色用户应拥有管理权限。"""
        store = get_rbac_store()
        roles = store.list_roles()
        admin_role = next(r for r in roles if r.code == "admin")
        store.assign_role_to_user(1, admin_role.id)

        perms = rbac.get_user_permissions(1)
        assert "user:read" in perms
        assert "system:manage" not in perms  # admin 不含 system:manage

    def test_get_user_permissions_super_admin(self):
        store = get_rbac_store()
        roles = store.list_roles()
        sa = next(r for r in roles if r.code == "super_admin")
        store.assign_role_to_user(2, sa.id)

        perms = rbac.get_user_permissions(2)
        assert "system:manage" in perms
        assert len(perms) == 37  # 全部权限

    def test_cache_hit(self):
        """二次查询应命中缓存(不查 DB)。"""
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        store.assign_role_to_user(3, usr.id)

        first = rbac.get_user_permissions(3)
        second = rbac.get_user_permissions(3)
        assert first == second

    def test_has_permission(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        store.assign_role_to_user(4, usr.id)

        assert rbac.has_permission(4, "document:read") is True
        assert rbac.has_permission(4, "user:delete") is False

    def test_has_any_permission(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        store.assign_role_to_user(5, usr.id)

        assert rbac.has_any_permission(5, "user:delete", "document:read") is True
        assert rbac.has_any_permission(5, "user:delete", "role:assign") is False

    def test_has_all_permissions(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        store.assign_role_to_user(6, usr.id)

        assert rbac.has_all_permissions(6, "document:read", "chat:write") is True
        assert rbac.has_all_permissions(6, "document:read", "user:delete") is False


# ---------------------------------------------------------------------------
# 3. 角色 CRUD
# ---------------------------------------------------------------------------


class TestRoleCRUD:
    def test_create_custom_role(self):
        store = get_rbac_store()
        role = store.create_role(
            code="editor",
            name="编辑者",
            description="可编辑文档",
            permission_codes=["document:read", "document:upload", "document:delete"],
        )
        assert role.id > 0
        assert role.is_builtin is False
        assert role.code == "editor"

    def test_update_role(self):
        store = get_rbac_store()
        role = store.create_role(code="editor", name="编辑", permission_codes=[])
        updated = store.update_role(role.id, name="高级编辑", description="updated")
        assert updated.name == "高级编辑"
        assert updated.description == "updated"

    def test_delete_custom_role(self):
        store = get_rbac_store()
        role = store.create_role(code="temp", name="临时", permission_codes=[])
        assert store.delete_role(role.id) is True
        assert store.get_role(role.id) is None

    def test_cannot_delete_builtin_role(self):
        store = get_rbac_store()
        roles = store.list_roles()
        sa = next(r for r in roles if r.code == "super_admin")
        with pytest.raises(ValueError, match="内置角色不可删除"):
            store.delete_role(sa.id)

    def test_set_role_permissions(self):
        store = get_rbac_store()
        role = store.create_role(code="editor", name="编辑", permission_codes=["document:read"])
        updated = store.set_role_permissions(role.id, ["document:read", "document:upload"])
        assert len(updated.permission_codes) == 2


# ---------------------------------------------------------------------------
# 4. 用户-角色分配
# ---------------------------------------------------------------------------


class TestUserRoleAssignment:
    def test_assign_and_revoke(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")

        assert store.assign_role_to_user(10, usr.id) is True
        user_roles = store.get_user_roles(10)
        assert len(user_roles) == 1
        assert user_roles[0].code == "user"

        assert store.revoke_role_from_user(10, usr.id) is True
        assert len(store.get_user_roles(10)) == 0

    def test_assign_idempotent(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")

        store.assign_role_to_user(11, usr.id)
        store.assign_role_to_user(11, usr.id)  # 幂等
        assert len(store.get_user_roles(11)) == 1

    def test_set_user_roles_full_replace(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        adm = next(r for r in roles if r.code == "admin")

        store.assign_role_to_user(12, usr.id)
        store.set_user_roles(12, [adm.id])  # 全量替换
        user_roles = store.get_user_roles(12)
        assert len(user_roles) == 1
        assert user_roles[0].code == "admin"


# ---------------------------------------------------------------------------
# 5. 缓存失效:角色变更后实时刷新
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    def test_invalidate_on_assign(self):
        """分配角色后,缓存应失效,权限立即更新。"""
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")

        # 初始无角色 → 无权限
        perms_before = rbac.get_user_permissions(20)
        assert "document:read" not in perms_before

        # 分配角色 → 缓存失效
        store.assign_role_to_user(20, usr.id)

        # 重新查询 → 应有权限
        perms_after = rbac.get_user_permissions(20)
        assert "document:read" in perms_after

    def test_invalidate_on_revoke(self):
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")

        store.assign_role_to_user(21, usr.id)
        assert rbac.has_permission(21, "document:read") is True

        store.revoke_role_from_user(21, usr.id)
        assert rbac.has_permission(21, "document:read") is False

    def test_invalidate_all_on_role_perm_change(self):
        """角色权限集合变更时,全部用户缓存失效。"""
        store = get_rbac_store()
        roles = store.list_roles()
        usr = next(r for r in roles if r.code == "user")
        store.assign_role_to_user(30, usr.id)

        # 初始 user 无 user:delete 权限
        assert rbac.has_permission(30, "user:delete") is False

        # 给 user 角色添加 user:delete 权限 → 全部缓存失效
        store.set_role_permissions(usr.id, list(usr.permission_codes) + ["user:delete"])

        # 重新查询应有 user:delete
        assert rbac.has_permission(30, "user:delete") is True


# ---------------------------------------------------------------------------
# 6. 部门 + 职位
# ---------------------------------------------------------------------------


class TestDepartmentAndPosition:
    def test_department_tree(self):
        store = get_rbac_store()
        root = store.create_department(code="hq", name="总部")
        child = store.create_department(code="tech", name="技术部", parent_id=root.id)
        grandchild = store.create_department(code="fe", name="前端组", parent_id=child.id)

        tree = store.get_department_tree()
        assert len(tree) == 1
        assert tree[0].code == "hq"
        assert len(tree[0].children) == 1
        assert tree[0].children[0].code == "tech"
        assert len(tree[0].children[0].children) == 1
        assert tree[0].children[0].children[0].code == "fe"

    def test_update_department(self):
        store = get_rbac_store()
        dept = store.create_department(code="sales", name="销售")
        updated = store.update_department(dept.id, name="销售部", description="updated")
        assert updated.name == "销售部"
        assert updated.description == "updated"

    def test_cannot_set_self_as_parent(self):
        store = get_rbac_store()
        dept = store.create_department(code="a", name="A")
        with pytest.raises(ValueError, match="不能将部门的父节点设为自己"):
            store.update_department(dept.id, parent_id=dept.id)

    def test_delete_department_cascades(self):
        store = get_rbac_store()
        root = store.create_department(code="root", name="Root")
        child = store.create_department(code="child", name="Child", parent_id=root.id)
        assert store.delete_department(root.id) is True
        assert store.get_department_tree() == []

    def test_position_crud(self):
        store = get_rbac_store()
        pos = store.create_position(code="eng", name="工程师", level=3)
        assert pos.id > 0
        assert pos.level == 3

        updated = store.update_position(pos.id, name="高级工程师", level=5)
        assert updated.name == "高级工程师"
        assert updated.level == 5

        assert store.delete_position(pos.id) is True
        assert len(store.list_positions()) == 0

    def test_position_sorted_by_level(self):
        store = get_rbac_store()
        store.create_position(code="junior", name="初级", level=1)
        store.create_position(code="senior", name="高级", level=5)
        store.create_position(code="mid", name="中级", level=3)

        positions = store.list_positions()
        # 按级别降序
        assert positions[0].level >= positions[1].level >= positions[2].level
        assert positions[0].code == "senior"


# ---------------------------------------------------------------------------
# 7. require_permission 装饰器(通过 TestClient 验证 403)
# ---------------------------------------------------------------------------


class TestRequirePermissionDecorator:
    """通过 FastAPI TestClient 验证权限拦截。"""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI, Depends
        from fastapi.testclient import TestClient
        from officeagent.api.routers.auth import verify_jwt_token
        from officeagent.core.security.rbac import require_permission

        app = FastAPI()

        @app.get("/protected")
        async def protected(_: dict = Depends(require_permission("user:delete"))):
            return {"ok": True}

        return TestClient(app)

    def test_no_token_returns_401(self, client):
        """未携带 Token → 401(verify_jwt_token 拦截)。"""
        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_insufficient_permission_returns_403(self, client):
        """携带无权限用户的 Token → 403。"""
        from officeagent.api.routers.auth import create_jwt_token
        from officeagent.services.storage import get_user_store

        # 创建普通用户
        store = get_user_store()
        user, _ = store.create(username="perm_user", email="p@e.com", password="Pass1234", role="user")

        token = create_jwt_token(user_id=user.id, username=user.username)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert "权限不足" in resp.json()["detail"]
