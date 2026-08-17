"""
PgUserStore 单元测试。

验证:
  - create / get_by_id / get_by_username / authenticate
  - 登录失败锁定
  - 密码哈希自动升级
  - profile 更新
  - quota 累加
  - 数据持久化(新 adapter 读取已有数据)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.services.storage import MAX_LOGIN_ATTEMPTS
from fnixagent.services.storage_pg import PgUserStore


class TestPgUserStoreCreate:
    """用户创建。"""

    def test_create_returns_user_with_id(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, err = store.create("alice", "alice@example.com", "Passw0rd!")
        assert err == ""
        assert user is not None
        assert user.id > 0
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.role == "user"
        # 密码哈希不应是明文
        assert user.password_hash != "Passw0rd!"
        assert len(user.password_hash) > 20

    def test_create_duplicate_username_rejected(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("bob", "bob@example.com", "Passw0rd!")
        user2, err = store.create("bob", "bob2@example.com", "Passw0rd!")
        assert user2 is None
        assert "已存在" in err

    def test_create_duplicate_email_rejected(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("carol", "carol@example.com", "Passw0rd!")
        user2, err = store.create("carol2", "carol@example.com", "Passw0rd!")
        assert user2 is None
        assert "邮箱" in err

    def test_create_admin_role(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("admin", "admin@example.com", "Passw0rd!", role="admin")
        assert user.role == "admin"


class TestPgUserStoreGet:
    """用户查询。"""

    def test_get_by_id_existing(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("dave", "dave@example.com", "Passw0rd!")
        fetched = store.get_by_id(user.id)
        assert fetched is not None
        assert fetched.username == "dave"

    def test_get_by_id_nonexistent(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.get_by_id(99999) is None

    def test_get_by_username_existing(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("eve", "eve@example.com", "Passw0rd!")
        fetched = store.get_by_username("eve")
        assert fetched is not None
        assert fetched.email == "eve@example.com"

    def test_get_by_username_nonexistent(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.get_by_username("nonexistent") is None

    def test_count_starts_at_zero(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.count == 0

    def test_count_increments(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("u1", "u1@example.com", "Passw0rd!")
        store.create("u2", "u2@example.com", "Passw0rd!")
        assert store.count == 2


class TestPgUserStoreAuthenticate:
    """用户认证 + 登录失败锁定。"""

    def test_authenticate_correct_password(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("frank", "frank@example.com", "MyPass123")
        user = store.authenticate("frank", "MyPass123")
        assert user is not None
        assert user.username == "frank"

    def test_authenticate_wrong_password(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("grace", "grace@example.com", "CorrectPass")
        assert store.authenticate("grace", "WrongPass") is None

    def test_authenticate_nonexistent_user(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.authenticate("ghost", "anything") is None

    def test_authenticate_locks_after_max_attempts(self, db_adapter):
        store = PgUserStore(db_adapter)
        store.create("heidi", "heidi@example.com", "RealPass")
        # 连续失败 MAX_LOGIN_ATTEMPTS 次
        for _ in range(MAX_LOGIN_ATTEMPTS):
            store.authenticate("heidi", "WrongPass")
        # 第 6 次即使密码正确也应被锁定
        locked_user = store.authenticate("heidi", "RealPass")
        assert locked_user is None


class TestPgUserStoreUpdateProfile:
    """用户画像更新。"""

    def test_update_profile_adds_fields(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("ivan", "ivan@example.com", "Passw0rd!")
        updated = store.update_profile(user.id, {"field": "AI", "level": 5})
        assert updated is not None
        assert updated.profile.get("field") == "AI"
        assert updated.profile.get("level") == 5

    def test_update_profile_nonexistent_user(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.update_profile(99999, {"x": 1}) is None

    def test_update_profile_preserves_quota(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("judy", "judy@example.com", "Passw0rd!")
        store.update_profile(user.id, {"topic": "math"})
        fetched = store.get_by_id(user.id)
        assert fetched is not None
        assert fetched.quota_total == 100000
        assert fetched.quota_used == 0


class TestPgUserStorePasswordUpdate:
    """密码更新。"""

    def test_update_password_changes_hash(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("karl", "karl@example.com", "OldPass123")
        old_hash = user.password_hash
        ok = store.update_password(user.id, "NewPass456")
        assert ok is True
        fetched = store.get_by_id(user.id)
        assert fetched.password_hash != old_hash

    def test_update_password_nonexistent_user(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.update_password(99999, "NewPass") is False

    def test_password_update_allows_new_login(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("leo", "leo@example.com", "OldPass")
        store.update_password(user.id, "NewPass")
        # 旧密码失败
        assert store.authenticate("leo", "OldPass") is None
        # 新密码成功
        assert store.authenticate("leo", "NewPass") is not None


class TestPgUserStoreQuota:
    """配额管理。"""

    def test_get_quota_default(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("mona", "mona@example.com", "Passw0rd!")
        quota = store.get_quota(user.id)
        assert quota is not None
        assert quota["total_quota"] == 100000
        assert quota["used_quota"] == 0
        assert quota["remaining_quota"] == 100000

    def test_add_usage_increments(self, db_adapter):
        store = PgUserStore(db_adapter)
        user, _ = store.create("nora", "nora@example.com", "Passw0rd!")
        store.add_usage(user.id, 500)
        store.add_usage(user.id, 300)
        quota = store.get_quota(user.id)
        assert quota["used_quota"] == 800
        assert quota["remaining_quota"] == 100000 - 800

    def test_get_quota_nonexistent_user(self, db_adapter):
        store = PgUserStore(db_adapter)
        assert store.get_quota(99999) is None


class TestPgUserStorePersistence:
    """数据持久化验证(新 adapter 实例读取已有数据)。"""

    def test_data_survives_adapter_restart(self, db_adapter):
        """同一数据库文件,新 PgUserStore 实例能读回旧数据。"""
        store1 = PgUserStore(db_adapter)
        store1.create("oscar", "oscar@example.com", "PersistPass")
        # 用同一 adapter 创建新 store 实例(模拟服务重启)
        store2 = PgUserStore(db_adapter)
        user = store2.get_by_username("oscar")
        assert user is not None
        assert user.email == "oscar@example.com"
        # 密码也能验证
        auth_user = store2.authenticate("oscar", "PersistPass")
        assert auth_user is not None
