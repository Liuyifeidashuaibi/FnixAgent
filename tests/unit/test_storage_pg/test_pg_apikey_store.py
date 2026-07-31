"""
PgApiKeyStore 单元测试。

验证:
  - create(明文只返回一次)
  - revoke
  - list_by_user
  - 数据持久化
"""

from __future__ import annotations

from fnixagent.services.storage_pg import PgApiKeyStore, PgUserStore


class TestPgApiKeyStoreCreate:
    """API Key 创建。"""

    def test_create_returns_key_with_plaintext(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("alice", "alice@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        key = store.create(user.id, scopes=["chat", "read"])
        assert key.id > 0
        assert key.user_id == user.id
        assert key.api_key.startswith("sk-fnixagent-")
        assert key.api_key_hash != key.api_key  # 哈希 != 明文
        assert key.scopes == ["chat", "read"]
        assert key.expires_at is not None
        assert not key.revoked

    def test_create_default_scopes(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("bob", "bob@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        key = store.create(user.id)
        assert key.scopes == ["chat"]

    def test_create_unique_hashes(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("carol", "carol@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        k1 = store.create(user.id)
        k2 = store.create(user.id)
        assert k1.api_key != k2.api_key
        assert k1.api_key_hash != k2.api_key_hash


class TestPgApiKeyStoreRevoke:
    """API Key 吊销。"""

    def test_revoke_own_key(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("dave", "dave@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        key = store.create(user.id)
        assert store.revoke(key.id, user.id) is True
        # 已吊销的 key 不在 list_by_user 中
        keys = store.list_by_user(user.id)
        assert len(keys) == 0

    def test_revoke_other_users_key_rejected(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        u1, _ = user_store.create("eve1", "eve1@example.com", "Passw0rd!")
        u2, _ = user_store.create("eve2", "eve2@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        key = store.create(u1.id)
        # u2 不能吊销 u1 的 key
        assert store.revoke(key.id, u2.id) is False

    def test_revoke_nonexistent_key(self, db_adapter):
        store = PgApiKeyStore(db_adapter)
        assert store.revoke(99999, 1) is False

    def test_revoke_already_revoked(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("frank", "frank@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        key = store.create(user.id)
        assert store.revoke(key.id, user.id) is True
        # 再次吊销应返回 False(已吊销)
        assert store.revoke(key.id, user.id) is False


class TestPgApiKeyStoreList:
    """API Key 列表。"""

    def test_list_by_user_returns_only_own_keys(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        u1, _ = user_store.create("grace1", "grace1@example.com", "Passw0rd!")
        u2, _ = user_store.create("grace2", "grace2@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        store.create(u1.id)
        store.create(u1.id)
        store.create(u2.id)

        assert len(store.list_by_user(u1.id)) == 2
        assert len(store.list_by_user(u2.id)) == 1

    def test_list_excludes_revoked(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("heidi", "heidi@example.com", "Passw0rd!")

        store = PgApiKeyStore(db_adapter)
        k1 = store.create(user.id)
        k2 = store.create(user.id)
        store.revoke(k1.id, user.id)

        keys = store.list_by_user(user.id)
        assert len(keys) == 1
        assert keys[0].id == k2.id

    def test_list_empty_user(self, db_adapter):
        store = PgApiKeyStore(db_adapter)
        assert len(store.list_by_user(99999)) == 0


class TestPgApiKeyStorePersistence:
    """数据持久化。"""

    def test_keys_survive_adapter_restart(self, db_adapter):
        user_store = PgUserStore(db_adapter)
        user, _ = user_store.create("ivan", "ivan@example.com", "Passw0rd!")

        store1 = PgApiKeyStore(db_adapter)
        store1.create(user.id)

        store2 = PgApiKeyStore(db_adapter)
        keys = store2.list_by_user(user.id)
        assert len(keys) == 1
