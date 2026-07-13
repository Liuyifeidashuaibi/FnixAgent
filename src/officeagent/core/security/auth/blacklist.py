"""
Token 黑名单(Phase 0.4)。

实现「登出即失效」:
    - 登出时把 Access Token 的 jti 写入黑名单,过期时间 = Token 剩余有效期
    - 中间件校验 Token 时检查 jti 是否在黑名单
    - Redis 可用时持久化(多实例共享),不可用时降级到内存(单实例)

Refresh Token 的撤销也通过黑名单实现:
    - /auth/refresh 接口换发新 Token 时,旧 Refresh Token 的 jti 写入黑名单
    - 防止 Refresh Token 被盗后无限换发
"""
from __future__ import annotations

import threading
import time
from typing import Optional

# 尝试导入 Redis 适配器(可选,开发环境可能无 Redis)
try:
    import redis as _redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False


# ---------------------------------------------------------------------------
# 黑名单接口
# ---------------------------------------------------------------------------


class TokenBlacklist:
    """Token 黑名单(Redis 优先,内存降级)。

    用法:
        blacklist = get_blacklist()
        blacklist.add(jti="abc123", ttl=3600)
        if blacklist.contains("abc123"):
            raise HTTPException(401, "Token 已撤销")
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: int = 6379,
        redis_password: Optional[str] = None,
        redis_db: int = 0,
    ):
        """初始化黑名单。

        Args:
            redis_host: Redis 主机,None 则使用内存降级
            redis_port: Redis 端口
            redis_password: Redis 密码
            redis_db: Redis 数据库编号
        """
        self._redis = None
        self._memory: dict[str, float] = {}    # jti -> expire_at
        self._lock = threading.RLock()
        self._use_memory = True

        if redis_host and _HAS_REDIS:
            try:
                self._redis = _redis_lib.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self._redis.ping()
                self._use_memory = False
            except Exception as e:
                print(f"[blacklist] Redis 连接失败,降级到内存: {e}")
                self._redis = None
                self._use_memory = True

    # ------------------------------------------------------------------
    # 添加到黑名单
    # ------------------------------------------------------------------

    def add(self, jti: str, ttl: int) -> bool:
        """将 jti 加入黑名单。

        Args:
            jti: Token 唯一 ID
            ttl: 过期时间(秒,通常为 Token 的剩余有效期)

        Returns:
            是否成功
        """
        if not jti:
            return False

        if self._use_memory or self._redis is None:
            return self._add_memory(jti, ttl)
        try:
            self._redis.setex(self._key(jti), ttl, "1")
            return True
        except Exception as e:
            print(f"[blacklist] Redis setex 失败,降级到内存: {e}")
            return self._add_memory(jti, ttl)

    def _add_memory(self, jti: str, ttl: int) -> bool:
        """内存模式添加。"""
        with self._lock:
            self._memory[jti] = time.time() + ttl
            return True

    # ------------------------------------------------------------------
    # 检查是否在黑名单
    # ------------------------------------------------------------------

    def contains(self, jti: str) -> bool:
        """检查 jti 是否在黑名单中。"""
        if not jti:
            return False

        if self._use_memory or self._redis is None:
            return self._contains_memory(jti)
        try:
            return self._redis.exists(self._key(jti)) > 0
        except Exception as e:
            print(f"[blacklist] Redis exists 失败,降级到内存: {e}")
            return self._contains_memory(jti)

    def _contains_memory(self, jti: str) -> bool:
        """内存模式检查(同时清理过期项)。"""
        with self._lock:
            # 清理过期项
            now = time.time()
            expired = [k for k, v in self._memory.items() if v <= now]
            for k in expired:
                self._memory.pop(k, None)

            return jti in self._memory

    # ------------------------------------------------------------------
    # 移除(仅用于测试)
    # ------------------------------------------------------------------

    def remove(self, jti: str) -> bool:
        """从黑名单移除(仅用于测试)。"""
        if not jti:
            return False

        if self._use_memory or self._redis is None:
            with self._lock:
                return self._memory.pop(jti, None) is not None
        try:
            return self._redis.delete(self._key(jti)) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 清空(仅用于测试)
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """清空黑名单(仅用于测试)。"""
        if self._use_memory or self._redis is None:
            with self._lock:
                self._memory.clear()
        else:
            try:
                # 扫描并删除所有 blacklist:* 键
                for key in self._redis.scan_iter(match=f"{self._prefix()}*"):
                    self._redis.delete(key)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def is_using_memory(self) -> bool:
        """返回是否运行在内存降级模式。"""
        return self._use_memory

    def size(self) -> int:
        """返回黑名单大小。"""
        if self._use_memory or self._redis is None:
            with self._lock:
                # 先清理过期项
                now = time.time()
                expired = [k for k, v in self._memory.items() if v <= now]
                for k in expired:
                    self._memory.pop(k, None)
                return len(self._memory)
        try:
            count = 0
            for _ in self._redis.scan_iter(match=f"{self._prefix()}*"):
                count += 1
            return count
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # 键名空间隔离
    # ------------------------------------------------------------------

    def _prefix(self) -> str:
        """Redis 键前缀。"""
        return "officeagent:blacklist:"

    def _key(self, jti: str) -> str:
        """完整 Redis 键。"""
        return f"{self._prefix()}{jti}"


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------


_blacklist_instance: Optional[TokenBlacklist] = None
_blacklist_lock = threading.Lock()


def get_blacklist(
    redis_host: Optional[str] = None,
    redis_port: int = 6379,
    redis_password: Optional[str] = None,
    redis_db: int = 0,
) -> TokenBlacklist:
    """获取全局 Token 黑名单单例(懒加载)。

    首次调用时尝试连接 Redis(若提供 host),否则使用内存降级。
    后续调用忽略参数,返回已创建的实例。
    """
    global _blacklist_instance
    if _blacklist_instance is None:
        with _blacklist_lock:
            if _blacklist_instance is None:
                _blacklist_instance = TokenBlacklist(
                    redis_host=redis_host,
                    redis_port=redis_port,
                    redis_password=redis_password,
                    redis_db=redis_db,
                )
    return _blacklist_instance


def reset_blacklist() -> None:
    """重置黑名单单例(用于测试)。"""
    global _blacklist_instance
    with _blacklist_lock:
        if _blacklist_instance is not None:
            _blacklist_instance.clear()
        _blacklist_instance = None
