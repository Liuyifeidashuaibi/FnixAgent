"""
blacklist 模块单元测试(验收标准 ⑤ 登出后 Access Token 在 1s 内失效 - 单元层)。

覆盖:
    - TokenBlacklist 内存模式初始化
    - add / contains 基本操作
    - add 后 contains 立即返回 True(1s 内生效)
    - 过期项自动清理(TTL 到期后 contains 返回 False)
    - remove 显式移除
    - clear 清空所有
    - size 返回当前数量
    - 空 jti 被拒绝
    - 全局单例 get_blacklist / reset_blacklist
    - is_using_memory 在无 Redis 时为 True
"""
import time

import pytest

from fnixagent.core.security.auth.blacklist import (
    TokenBlacklist,
    get_blacklist,
    reset_blacklist,
)


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

class TestBlacklistInit:
    """TokenBlacklist 初始化。"""

    def test_init_without_redis_uses_memory(self, fresh_blacklist):
        """无 Redis 时使用内存降级模式。"""
        assert fresh_blacklist.is_using_memory() is True

    def test_init_empty(self, fresh_blacklist):
        """初始化后黑名单为空。"""
        assert fresh_blacklist.size() == 0
        assert fresh_blacklist.contains("any_jti") is False


# ---------------------------------------------------------------------------
# add / contains(验收标准 ⑤)
# ---------------------------------------------------------------------------

class TestAddAndContains:
    """add / contains 操作。"""

    def test_add_then_contains_immediately(self, fresh_blacklist):
        """add 后 contains 立即返回 True(验收标准 ⑤:1s 内失效)。"""
        jti = "test_jti_123"
        fresh_blacklist.add(jti, ttl=3600)
        # 立即查询(0 延迟)
        assert fresh_blacklist.contains(jti) is True

    def test_contains_unknown_jti_returns_false(self, fresh_blacklist):
        """未加入的 jti 返回 False。"""
        fresh_blacklist.add("real_jti", ttl=3600)
        assert fresh_blacklist.contains("another_jti") is False

    def test_add_multiple_jtis(self, fresh_blacklist):
        """添加多个 jti 都能被查询到。"""
        for i in range(10):
            fresh_blacklist.add(f"jti_{i}", ttl=3600)
        assert fresh_blacklist.size() == 10
        for i in range(10):
            assert fresh_blacklist.contains(f"jti_{i}") is True

    def test_add_empty_jti_returns_false(self, fresh_blacklist):
        """空 jti 拒绝添加。"""
        assert fresh_blacklist.add("", ttl=3600) is False
        assert fresh_blacklist.add(None, ttl=3600) is False

    def test_contains_empty_jti_returns_false(self, fresh_blacklist):
        """空 jti 查询返回 False。"""
        assert fresh_blacklist.contains("") is False
        assert fresh_blacklist.contains(None) is False

    def test_add_duplicate_jti_idempotent(self, fresh_blacklist):
        """重复添加同一 jti 不增加 size(覆盖)。"""
        fresh_blacklist.add("dup_jti", ttl=3600)
        fresh_blacklist.add("dup_jti", ttl=3600)
        assert fresh_blacklist.size() == 1
        assert fresh_blacklist.contains("dup_jti") is True


# ---------------------------------------------------------------------------
# TTL 过期
# ---------------------------------------------------------------------------

class TestTtlExpiry:
    """TTL 到期后自动失效。"""

    def test_expired_jti_removed_on_contains(self, fresh_blacklist):
        """TTL 到期后 contains 返回 False(并清理)。"""
        fresh_blacklist.add("short_lived", ttl=1)
        assert fresh_blacklist.contains("short_lived") is True
        # 等待 1.1 秒让 TTL 过期
        time.sleep(1.1)
        assert fresh_blacklist.contains("short_lived") is False

    def test_expired_jti_cleaned_from_size(self, fresh_blacklist):
        """过期项从 size 中清理。"""
        fresh_blacklist.add("jti_a", ttl=1)
        fresh_blacklist.add("jti_b", ttl=3600)
        assert fresh_blacklist.size() == 2
        time.sleep(1.1)
        # 触发清理
        assert fresh_blacklist.size() == 1
        assert fresh_blacklist.contains("jti_b") is True

    def test_zero_ttl_immediately_expired(self, fresh_blacklist):
        """TTL=0 的项立即过期(下一次 contains 清理)。"""
        fresh_blacklist.add("zero_ttl", ttl=0)
        # TTL=0 表示立即过期,但内存模式按 time.time() + 0 写入
        # 由于 contains 会清理 <= now 的项,所以应返回 False
        # 加一个微小延迟确保 time.time() 推进
        time.sleep(0.01)
        assert fresh_blacklist.contains("zero_ttl") is False


# ---------------------------------------------------------------------------
# remove / clear
# ---------------------------------------------------------------------------

class TestRemoveAndClear:
    """remove / clear 操作。"""

    def test_remove_existing_jti(self, fresh_blacklist):
        """remove 已存在的 jti 返回 True。"""
        fresh_blacklist.add("to_remove", ttl=3600)
        assert fresh_blacklist.remove("to_remove") is True
        assert fresh_blacklist.contains("to_remove") is False

    def test_remove_nonexistent_jti(self, fresh_blacklist):
        """remove 不存在的 jti 返回 False。"""
        assert fresh_blacklist.remove("not_there") is False

    def test_remove_empty_jti(self, fresh_blacklist):
        """remove 空 jti 返回 False。"""
        assert fresh_blacklist.remove("") is False

    def test_clear_empties_all(self, fresh_blacklist):
        """clear 清空所有 jti。"""
        for i in range(5):
            fresh_blacklist.add(f"jti_{i}", ttl=3600)
        assert fresh_blacklist.size() == 5
        fresh_blacklist.clear()
        assert fresh_blacklist.size() == 0

    def test_clear_on_empty_blacklist_no_error(self, fresh_blacklist):
        """clear 空黑名单不报错。"""
        fresh_blacklist.clear()
        assert fresh_blacklist.size() == 0


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

class TestGlobalSingleton:
    """get_blacklist / reset_blacklist 全局单例。"""

    def test_get_blacklist_returns_singleton(self):
        """get_blacklist 多次调用返回同一实例。"""
        reset_blacklist()
        bl1 = get_blacklist()
        bl2 = get_blacklist()
        assert bl1 is bl2

    def test_reset_blacklist_creates_new_instance(self):
        """reset_blacklist 后 get_blacklist 返回新实例。"""
        reset_blacklist()
        bl1 = get_blacklist()
        reset_blacklist()
        bl2 = get_blacklist()
        assert bl1 is not bl2

    def test_reset_clears_existing_entries(self):
        """reset_blacklist 清空已有条目。"""
        reset_blacklist()
        bl = get_blacklist()
        bl.add("persistent_jti", ttl=3600)
        assert bl.contains("persistent_jti") is True
        reset_blacklist()
        bl_new = get_blacklist()
        assert bl_new.contains("persistent_jti") is False

    def test_singleton_default_memory_mode(self):
        """全局单例默认内存模式(无 Redis host 参数)。"""
        reset_blacklist()
        bl = get_blacklist()
        assert bl.is_using_memory() is True
