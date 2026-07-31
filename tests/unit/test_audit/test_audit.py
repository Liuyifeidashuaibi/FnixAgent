"""Phase 2.5 全量审计日志测试。

覆盖:
    1. 哈希链计算与校验(完整性 / 篡改检测)
    2. AuditLogger 写入与查询
    3. InMemoryAuditStore CRUD + 多维筛选
    4. 导出 JSON / CSV
    5. API 端点(/audit/logs /audit/export /audit/verify /audit/actions)
    6. 敏感操作埋点(login success/failed、MFA、权限拒绝)
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_stores():
    """每个测试前后重置审计存储,确保隔离。"""
    from fnixagent.core.security import rbac
    from fnixagent.services.storage import reset_stores
    from fnixagent.services.storage_audit import reset_audit_store
    from fnixagent.services.storage_rbac import reset_rbac_store

    reset_audit_store()
    reset_stores()
    reset_rbac_store()
    rbac.invalidate_all_permission_cache()
    yield
    reset_audit_store()
    reset_stores()
    reset_rbac_store()
    rbac.invalidate_all_permission_cache()


# ===========================================================================
# 1. 哈希链计算与校验
# ===========================================================================


class TestHashChain:
    def test_compute_entry_hash_deterministic(self):
        """相同输入应产生相同哈希。"""
        from fnixagent.core.audit.logger import _compute_entry_hash

        h1 = _compute_entry_hash(
            "0" * 64, "login.success", 1, "{}", "2026-01-01T00:00:00", "127.0.0.1"
        )
        h2 = _compute_entry_hash(
            "0" * 64, "login.success", 1, "{}", "2026-01-01T00:00:00", "127.0.0.1"
        )
        assert h1 == h2
        assert len(h1) == 64

    def test_compute_entry_hash_changes_on_any_field(self):
        """任一字段变化应导致哈希变化。"""
        from fnixagent.core.audit.logger import _compute_entry_hash

        base = _compute_entry_hash(
            "0" * 64, "login.success", 1, "{}", "2026-01-01T00:00:00", "127.0.0.1"
        )
        assert base != _compute_entry_hash(
            "1" * 64, "login.success", 1, "{}", "2026-01-01T00:00:00", "127.0.0.1"
        )
        assert base != _compute_entry_hash(
            "0" * 64, "login.failed", 1, "{}", "2026-01-01T00:00:00", "127.0.0.1"
        )
        assert base != _compute_entry_hash(
            "0" * 64, "login.success", 2, "{}", "2026-01-01T00:00:00", "127.0.0.1"
        )
        assert base != _compute_entry_hash(
            "0" * 64, "login.success", 1, '{"a":1}', "2026-01-01T00:00:00", "127.0.0.1"
        )
        assert base != _compute_entry_hash(
            "0" * 64, "login.success", 1, "{}", "2026-01-02T00:00:00", "127.0.0.1"
        )
        assert base != _compute_entry_hash(
            "0" * 64, "login.success", 1, "{}", "2026-01-01T00:00:00", "192.168.1.1"
        )

    def test_verify_hash_chain_empty_list(self):
        """空列表应通过校验。"""
        from fnixagent.core.audit import verify_hash_chain

        is_valid, broken_id = verify_hash_chain([])
        assert is_valid is True
        assert broken_id is None

    def test_verify_hash_chain_single_entry(self):
        """单条记录(prev_hash=genesis)应通过。"""
        from datetime import datetime

        from fnixagent.core.audit import AuditLogDTO, verify_hash_chain
        from fnixagent.core.audit.logger import _GENESIS_HASH, _compute_entry_hash

        now = datetime.utcnow()
        detail = {"username": "alice"}
        detail_json = json.dumps(detail, sort_keys=True, ensure_ascii=False)
        entry_hash = _compute_entry_hash(
            _GENESIS_HASH, "login.success", 1, detail_json, now.isoformat(), "127.0.0.1"
        )

        log = AuditLogDTO(
            id=1,
            user_id=1,
            action="login.success",
            detail=detail,
            ip_address="127.0.0.1",
            prev_hash=_GENESIS_HASH,
            entry_hash=entry_hash,
            created_at=now,
        )
        is_valid, broken_id = verify_hash_chain([log])
        assert is_valid is True
        assert broken_id is None

    def test_verify_hash_chain_detects_tampering(self):
        """篡改任一记录应导致后续哈希链断裂。"""
        from fnixagent.core.audit import AuditLogger, verify_hash_chain

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={"u": "a"}, ip_address="1.1.1.1")
        logger.log(action="logout", user_id=1, detail={}, ip_address="1.1.1.1")
        logger.log(action="login.success", user_id=2, detail={"u": "b"}, ip_address="2.2.2.2")

        # 获取全部记录(正序)
        store = logger.store
        logs = store.get_all_ordered()

        # 篡改第二条记录的 detail
        logs[1].detail = {"tampered": True}
        is_valid, broken_id = verify_hash_chain(logs)
        assert is_valid is False
        assert broken_id == logs[1].id

    def test_verify_hash_chain_detects_missing_link(self):
        """prev_hash 不匹配应被检测。"""
        from fnixagent.core.audit import AuditLogger, verify_hash_chain

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={}, ip_address="1.1.1.1")
        logger.log(action="logout", user_id=1, detail={}, ip_address="1.1.1.1")

        logs = logger.store.get_all_ordered()
        # 篡改第二条的 prev_hash
        logs[1].prev_hash = "f" * 64
        is_valid, broken_id = verify_hash_chain(logs)
        assert is_valid is False
        assert broken_id == logs[1].id


# ===========================================================================
# 2. AuditLogger 写入与查询
# ===========================================================================


class TestAuditLogger:
    def test_log_returns_dto(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        entry = logger.log(action="login.success", user_id=1, detail={"u": "alice"})
        assert entry is not None
        assert entry.id > 0
        assert entry.action == "login.success"
        assert entry.user_id == 1
        assert entry.detail == {"u": "alice"}
        assert entry.prev_hash != ""
        assert entry.entry_hash != ""
        assert entry.created_at is not None

    def test_log_chain_links_correctly(self):
        """连续写入的记录应正确链接(prev_hash = 上一条的 entry_hash)。"""
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        e1 = logger.log(action="login.success", user_id=1, detail={"n": 1})
        e2 = logger.log(action="logout", user_id=1, detail={"n": 2})
        e3 = logger.log(action="login.failed", user_id=2, detail={"n": 3})

        assert e2.prev_hash == e1.entry_hash
        assert e3.prev_hash == e2.entry_hash

    def test_log_with_none_user_id(self):
        """未登录操作(user_id=None)应正常记录。"""
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        entry = logger.log(action="login.failed", user_id=None, detail={"username": "unknown"})
        assert entry is not None
        assert entry.user_id is None

    def test_list_with_pagination(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        for i in range(10):
            logger.log(action="login.success", user_id=i, detail={"i": i})

        logs, total = logger.list(limit=5, offset=0)
        assert total == 10
        assert len(logs) == 5
        # 默认按 id 降序(最新优先)
        assert logs[0].id > logs[-1].id

    def test_list_filter_by_user_id(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={})
        logger.log(action="login.failed", user_id=2, detail={})
        logger.log(action="logout", user_id=1, detail={})

        logs, total = logger.list(user_id=1)
        assert total == 2
        assert all(log.user_id == 1 for log in logs)

    def test_list_filter_by_action(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={})
        logger.log(action="login.failed", user_id=2, detail={})
        logger.log(action="login.success", user_id=3, detail={})

        logs, total = logger.list(action="login.success")
        assert total == 2
        assert all(log.action == "login.success" for log in logs)

    def test_list_filter_by_ip(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={}, ip_address="1.1.1.1")
        logger.log(action="login.failed", user_id=2, detail={}, ip_address="2.2.2.2")
        logger.log(action="logout", user_id=1, detail={}, ip_address="1.1.1.1")

        logs, total = logger.list(ip_address="1.1.1.1")
        assert total == 2
        assert all(log.ip_address == "1.1.1.1" for log in logs)

    def test_verify_chain_intact(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={})
        logger.log(action="logout", user_id=1, detail={})

        is_valid, broken_id = logger.verify_chain()
        assert is_valid is True
        assert broken_id is None


# ===========================================================================
# 3. InMemoryAuditStore
# ===========================================================================


class TestInMemoryAuditStore:
    def test_create_and_get_last_hash(self):
        from fnixagent.services.storage_audit import InMemoryAuditStore

        store = InMemoryAuditStore()
        # 空存储返回空字符串
        assert store.get_last_hash() == ""

        entry = store.create(
            action="login.success", user_id=1, prev_hash="0" * 64, entry_hash="abc123"
        )
        assert entry.id == 1
        assert store.get_last_hash() == "abc123"

        entry2 = store.create(action="logout", user_id=1, prev_hash="abc123", entry_hash="def456")
        assert entry2.id == 2
        assert store.get_last_hash() == "def456"

    def test_query_with_filters(self):
        from fnixagent.services.storage_audit import InMemoryAuditStore

        store = InMemoryAuditStore()
        store.create(user_id=1, action="login.success", ip_address="1.1.1.1")
        store.create(user_id=2, action="login.failed", ip_address="2.2.2.2")
        store.create(user_id=1, action="logout", ip_address="1.1.1.1")

        # 全部
        _, total = store.query()
        assert total == 3

        # 按 user_id
        _, total = store.query(user_id=1)
        assert total == 2

        # 按 action
        _, total = store.query(action="login.success")
        assert total == 1

        # 按 ip
        _, total = store.query(ip_address="1.1.1.1")
        assert total == 2

    def test_query_with_time_range(self):
        from datetime import datetime, timedelta

        from fnixagent.services.storage_audit import InMemoryAuditStore

        store = InMemoryAuditStore()
        now = datetime.utcnow()

        # 手动创建带时间戳的记录
        entry1 = store.create(user_id=1, action="login.success")
        entry1.created_at = now - timedelta(hours=2)
        entry2 = store.create(user_id=1, action="logout")
        entry2.created_at = now - timedelta(hours=1)
        entry3 = store.create(user_id=1, action="login.success")
        entry3.created_at = now

        # 按时间范围筛选:只包含 entry2(now - 1h)
        start = (now - timedelta(minutes=90)).isoformat()
        end = (now - timedelta(minutes=30)).isoformat()
        _, total = store.query(start=start, end=end)
        assert total == 1  # 只有 entry2

    def test_count_and_clear(self):
        from fnixagent.services.storage_audit import InMemoryAuditStore

        store = InMemoryAuditStore()
        store.create(user_id=1, action="login.success")
        store.create(user_id=2, action="login.failed")

        assert store.count() == 2
        cleared = store.clear()
        assert cleared == 2
        assert store.count() == 0

    def test_get_all_ordered(self):
        from fnixagent.services.storage_audit import InMemoryAuditStore

        store = InMemoryAuditStore()
        store.create(user_id=1, action="a")
        store.create(user_id=2, action="b")
        store.create(user_id=3, action="c")

        logs = store.get_all_ordered()
        assert len(logs) == 3
        # 正序(id 升序)
        assert logs[0].id < logs[1].id < logs[2].id


# ===========================================================================
# 4. 导出 JSON / CSV
# ===========================================================================


class TestAuditExport:
    def test_export_json(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={"u": "alice"}, ip_address="1.1.1.1")
        logger.log(action="logout", user_id=1, detail={}, ip_address="1.1.1.1")

        content = logger.export(format="json")
        data = json.loads(content)
        assert len(data) == 2
        # 导出按时间正序
        assert data[0]["action"] == "login.success"
        assert data[1]["action"] == "logout"
        # 导出格式不含内部哈希
        assert "prev_hash" not in data[0]
        assert "entry_hash" not in data[0]
        assert "timestamp" in data[0]
        assert "ip" in data[0]

    def test_export_csv(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={"u": "alice"}, ip_address="1.1.1.1")
        logger.log(action="logout", user_id=1, detail={}, ip_address="1.1.1.1")

        content = logger.export(format="csv")
        lines = content.strip().split("\n")
        # 表头 + 2 条数据
        assert len(lines) == 3
        assert "id,timestamp,user_id,action,detail,ip,user_agent,trace_id" in lines[0]
        assert "login.success" in lines[1]

    def test_export_empty(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        json_content = logger.export(format="json")
        assert json.loads(json_content) == []

        csv_content = logger.export(format="csv")
        assert "id,timestamp" in csv_content

    def test_export_with_filters(self):
        from fnixagent.core.audit import AuditLogger

        logger = AuditLogger()
        logger.log(action="login.success", user_id=1, detail={})
        logger.log(action="login.failed", user_id=2, detail={})
        logger.log(action="login.success", user_id=3, detail={})

        content = logger.export(format="json", action="login.success")
        data = json.loads(content)
        assert len(data) == 2
        assert all(d["action"] == "login.success" for d in data)


# ===========================================================================
# 5. API 端点
# ===========================================================================


class TestAuditAPIEndpoints:
    @pytest.fixture
    def client(self):
        """构建带 audit 路由的 TestClient。"""
        from fnixagent.api.routers import audit, auth

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(audit.router, prefix="/api/v1")
        return TestClient(app)

    @pytest.fixture
    def admin_token(self):
        """创建管理员 Token(super_admin 角色拥有 system:audit_log 权限)。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="audit_admin",
            email="auditadmin@e.com",
            password="Pass1234",
            role="super_admin",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    @pytest.fixture
    def user_token(self):
        """创建普通用户 Token(无 audit 权限)。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="audit_user",
            email="audituser@e.com",
            password="Pass1234",
            role="user",
        )
        return create_jwt_token(user_id=user.id, username=user.username), user.id

    def _headers(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _write_some_logs(self):
        from fnixagent.core.audit import AUDIT_LOGIN_SUCCESS, AUDIT_LOGOUT, AuditLogger

        logger = AuditLogger()
        logger.log(action=AUDIT_LOGIN_SUCCESS, user_id=1, detail={"u": "alice"})
        logger.log(action=AUDIT_LOGOUT, user_id=1, detail={})
        logger.log(action=AUDIT_LOGIN_SUCCESS, user_id=2, detail={"u": "bob"})

    def test_list_logs_no_auth(self, client):
        """未认证应返回 401。"""
        resp = client.get("/api/v1/audit/logs")
        assert resp.status_code == 401

    def test_list_logs_user_forbidden(self, client, user_token):
        """普通用户无 audit 权限应返回 403。"""
        token, _ = user_token
        resp = client.get("/api/v1/audit/logs", headers=self._headers(token))
        assert resp.status_code == 403

    def test_list_logs_success(self, client, admin_token):
        """管理员可查询审计日志。"""
        token, _ = admin_token
        self._write_some_logs()

        resp = client.get("/api/v1/audit/logs", headers=self._headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 3

    def test_list_logs_with_pagination(self, client, admin_token):
        token, _ = admin_token
        self._write_some_logs()

        resp = client.get(
            "/api/v1/audit/logs?limit=2&offset=0",
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 3
        assert len(data["data"]["items"]) == 2

    def test_list_logs_filter_by_action(self, client, admin_token):
        from fnixagent.core.audit import AUDIT_LOGIN_SUCCESS

        token, _ = admin_token
        self._write_some_logs()

        resp = client.get(
            f"/api/v1/audit/logs?action={AUDIT_LOGIN_SUCCESS}",
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 2

    def test_export_json(self, client, admin_token):
        token, _ = admin_token
        self._write_some_logs()

        resp = client.get(
            "/api/v1/audit/export?format=json",
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        # 导出会额外记录一条 data.export,所以原 3 条 + 1 条 = 4 条
        data = json.loads(resp.text)
        # 导出按时间正序,login.success 应在前
        actions = [d["action"] for d in data]
        assert "login.success" in actions
        assert "data.export" in actions

    def test_export_csv(self, client, admin_token):
        token, _ = admin_token
        self._write_some_logs()

        resp = client.get(
            "/api/v1/audit/export?format=csv",
            headers=self._headers(token),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        # 表头 + 数据行(原 3 条 + 导出操作 1 条 = 4 条)
        assert len(lines) >= 2
        assert "id,timestamp" in lines[0]

    def test_verify_chain_intact(self, client, admin_token):
        token, _ = admin_token
        self._write_some_logs()

        resp = client.get("/api/v1/audit/verify", headers=self._headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["is_valid"] is True
        assert data["data"]["broken_at_id"] is None

    def test_list_actions(self, client, admin_token):
        token, _ = admin_token
        resp = client.get("/api/v1/audit/actions", headers=self._headers(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        actions = data["data"]["items"]
        assert "login.success" in actions
        assert "login.failed" in actions
        assert "logout" in actions
        assert "mfa.enable" in actions
        assert "permission.denied" in actions


# ===========================================================================
# 6. 敏感操作埋点
# ===========================================================================


class TestAuditInstrumentation:
    @pytest.fixture
    def client(self):
        """构建带 auth + audit 路由的 TestClient。"""
        from fnixagent.api.routers import audit, auth

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1")
        app.include_router(audit.router, prefix="/api/v1")
        return TestClient(app)

    def test_login_success_writes_audit(self, client):
        """登录成功应写入 login.success 审计日志。"""
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        store.create(username="audit_login", email="al@e.com", password="Pass1234", role="user")

        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "audit_login",
                "password": "Pass1234",
            },
        )
        assert resp.status_code == 200

        # 检查审计日志
        from fnixagent.core.audit import AUDIT_LOGIN_SUCCESS, AuditLogger

        logger = AuditLogger()
        logs, total = logger.list(action=AUDIT_LOGIN_SUCCESS)
        assert total >= 1
        assert logs[0].action == AUDIT_LOGIN_SUCCESS

    def test_login_failed_writes_audit(self, client):
        """登录失败应写入 login.failed 审计日志。"""
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        store.create(username="audit_fail", email="af@e.com", password="Pass1234", role="user")

        resp = client.post(
            "/api/v1/auth/login",
            json={
                "username": "audit_fail",
                "password": "WrongPassword",
            },
        )
        assert resp.status_code == 401

        from fnixagent.core.audit import AUDIT_LOGIN_FAILED, AuditLogger

        logger = AuditLogger()
        logs, total = logger.list(action=AUDIT_LOGIN_FAILED)
        assert total >= 1
        assert logs[0].action == AUDIT_LOGIN_FAILED

    def test_logout_writes_audit(self, client):
        """登出应写入 logout 审计日志。"""
        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.services.storage import get_user_store

        store = get_user_store()
        user, _ = store.create(
            username="audit_logout", email="alo@e.com", password="Pass1234", role="user"
        )
        token = create_jwt_token(user_id=user.id, username=user.username)

        resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        from fnixagent.core.audit import AUDIT_LOGOUT, AuditLogger

        logger = AuditLogger()
        logs, total = logger.list(action=AUDIT_LOGOUT)
        assert total >= 1

    def test_permission_denied_writes_audit(self):
        """权限拒绝时应写入 permission.denied 审计日志。"""
        from fastapi import Depends

        from fnixagent.api.routers.auth import create_jwt_token
        from fnixagent.core.security import rbac
        from fnixagent.services.storage import get_user_store

        # 创建普通用户(无 system:manage 权限)
        store = get_user_store()
        user, _ = store.create(
            username="perm_user", email="pu@e.com", password="Pass1234", role="user"
        )
        token = create_jwt_token(user_id=user.id, username=user.username)

        app = FastAPI()

        @app.get("/api/v1/protected")
        async def protected(_p: dict = Depends(rbac.require_permission("system:manage"))):
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/api/v1/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

        from fnixagent.core.audit import AUDIT_PERMISSION_DENIED, AuditLogger

        logger = AuditLogger()
        logs, total = logger.list(action=AUDIT_PERMISSION_DENIED)
        assert total >= 1
        assert "system:manage" in logs[0].detail.get("required_permissions", [])

    def test_audit_actions_includes_all_types(self):
        """ALL_AUDIT_ACTIONS 应包含所有 26 个动作类型(20 原有 + 6 Phase 3.2 新增)。"""
        from fnixagent.core.audit import ALL_AUDIT_ACTIONS

        assert len(ALL_AUDIT_ACTIONS) == 26
        # 关键动作都在
        expected = {
            "login.success",
            "login.failed",
            "logout",
            "sso.login",
            "ldap.login",
            "mfa.enable",
            "mfa.disable",
            "mfa.challenge",
            "mfa.verify_failed",
            "mfa.factor_force_disabled",
            "permission.denied",
            "user.disable",
            "user.enable",
            "user.role_change",
            "user.password_reset",
            "config.update",
            "sensitive.hit",
            "injection.blocked",
            "data.export",
            "data.delete",
            # Phase 3.2 新增
            "privacy.export",
            "account.delete_request",
            "account.delete_cancel",
            "account.hard_deleted",
            "moderation.input_blocked",
            "moderation.output_blocked",
        }
        assert set(ALL_AUDIT_ACTIONS) == expected
