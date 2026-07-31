"""
缓存适配器 - Redis 连接与操作封装。

提供 Redis 的常用操作接口,线程安全(redis-py 的 ConnectionPool 已内置线程安全)。

安全特性:
    - host/port 参数校验
    - 密码不出现在日志/__repr__(脱敏)
    - 所有操作捕获 RedisError, 不向上抛(降级返回 None/False)
    - close() 显式关闭连接池, 避免连接泄漏
"""

import json
import logging
from typing import Any

import redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def _validate_host_port(host: str, port: int) -> None:
    """校验 Redis 连接参数。

    Args:
        host: 主机名/IP
        port: 端口号

    Raises:
        ValueError: host 为空或 port 越界
    """
    if not host or not isinstance(host, str):
        raise ValueError(f"host 必须为非空字符串, 收到 {host!r}")
    if not isinstance(port, int) or isinstance(port, bool):
        raise ValueError(f"port 必须为 int, 收到 {type(port).__name__}")
    if not (1 <= port <= 65535):
        raise ValueError(f"port 越界(1-65535), 收到 {port}")


class CacheAdapter:
    """Redis 缓存适配器。

    线程安全: redis-py 的 ConnectionPool 内置线程安全, 多线程共享 client 安全。
    连接管理: 显式调用 close() 关闭连接池, 避免连接泄漏。

    用法:
        cache = CacheAdapter("localhost", 6379, password="...")
        cache.set("key", "value", ttl=3600)
        value = cache.get("key")
        cache.close()  # 显式关闭连接池
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str | None = None,
        db: int = 0,
        max_connections: int = 50,
    ):
        """初始化 Redis 连接。

        Args:
            host:            Redis 主机
            port:            Redis 端口(1-65535)
            password:        Redis 密码(可选, 不会打印到日志)
            db:              Redis 数据库编号
            max_connections: 最大连接数

        Raises:
            ValueError: host 为空或 port 越界
        """
        # 参数校验
        _validate_host_port(host, port)
        if not isinstance(db, int) or db < 0:
            raise ValueError(f"db 必须为非负 int, 收到 {db!r}")
        if not isinstance(max_connections, int) or max_connections <= 0:
            raise ValueError(f"max_connections 必须为正 int, 收到 {max_connections!r}")

        # 连接参数(脱敏保存, 仅 host/port/db 用于 __repr__)
        self._host = host
        self._port = port
        self._db = db
        self._password = password  # 私有属性, 不暴露
        # ConnectionPool 内置线程安全(基于 socket 复用 + 队列)
        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            password=password,
            db=db,
            max_connections=max_connections,
        )
        self.client = redis.Redis(connection_pool=self.pool)

    def __repr__(self) -> str:
        """脱敏 repr: 不暴露密码。"""
        return f"CacheAdapter(host={self._host!r}, port={self._port}, db={self._db}, password=***)"

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """设置缓存。

        Args:
            key:   键
            value: 值(自动 JSON 序列化)
            ttl:   过期时间(秒), None 表示永久

        Returns:
            是否设置成功(失败返回 False, 不抛异常)
        """
        try:
            serialized = json.dumps(value)
            if ttl:
                return self.client.setex(key, ttl, serialized)
            return self.client.set(key, serialized)
        except (RedisError, TypeError, ValueError) as e:
            # RedisError: 连接/协议错误; TypeError/ValueError: JSON 序列化失败
            logger.warning("Redis set 失败 key=%s: %s", key, e)
            return False

    def get(self, key: str) -> Any | None:
        """获取缓存。

        Args:
            key: 键

        Returns:
            值(自动 JSON 反序列化)或 None(不存在/失败)
        """
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning("Redis get 失败 key=%s: %s", key, e)
            return None

    def delete(self, key: str) -> bool:
        """删除缓存。

        Args:
            key: 键

        Returns:
            是否删除成功
        """
        try:
            return self.client.delete(key) > 0
        except RedisError as e:
            logger.warning("Redis delete 失败 key=%s: %s", key, e)
            return False

    def exists(self, key: str) -> bool:
        """检查键是否存在。"""
        try:
            return self.client.exists(key) > 0
        except RedisError as e:
            logger.warning("Redis exists 失败 key=%s: %s", key, e)
            return False

    def expire(self, key: str, ttl: int) -> bool:
        """设置键过期时间。

        Args:
            key: 键
            ttl: 过期时间(秒)

        Returns:
            是否设置成功
        """
        try:
            return self.client.expire(key, ttl)
        except RedisError as e:
            logger.warning("Redis expire 失败 key=%s: %s", key, e)
            return False

    def ttl(self, key: str) -> int | None:
        """获取键剩余过期时间。

        Args:
            key: 键

        Returns:
            剩余秒数; 永久/不存在/失败均返回 None
        """
        try:
            ttl = self.client.ttl(key)
            # -1: 永久; -2: 不存在; 均归一化为 None
            if ttl in (-1, -2):
                return None
            return ttl
        except RedisError as e:
            logger.warning("Redis ttl 失败 key=%s: %s", key, e)
            return None

    # List 操作(用于短期记忆)

    def lpush(self, key: str, value: Any) -> int:
        """列表左侧插入。返回列表长度; 失败返回 0。"""
        try:
            serialized = json.dumps(value)
            return self.client.lpush(key, serialized)
        except (RedisError, TypeError, ValueError) as e:
            logger.warning("Redis lpush 失败 key=%s: %s", key, e)
            return 0

    def rpush(self, key: str, value: Any) -> int:
        """列表右侧插入。返回列表长度; 失败返回 0。"""
        try:
            serialized = json.dumps(value)
            return self.client.rpush(key, serialized)
        except (RedisError, TypeError, ValueError) as e:
            logger.warning("Redis rpush 失败 key=%s: %s", key, e)
            return 0

    def lrange(self, key: str, start: int, end: int) -> list[Any]:
        """获取列表范围。返回值列表; 失败返回空列表。"""
        try:
            values = self.client.lrange(key, start, end)
            return [json.loads(v) for v in values]
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning("Redis lrange 失败 key=%s: %s", key, e)
            return []

    def llen(self, key: str) -> int:
        """获取列表长度。失败返回 0。"""
        try:
            return self.client.llen(key)
        except RedisError as e:
            logger.warning("Redis llen 失败 key=%s: %s", key, e)
            return 0

    def ltrim(self, key: str, start: int, end: int) -> bool:
        """裁剪列表。"""
        try:
            self.client.ltrim(key, start, end)
            return True
        except RedisError as e:
            logger.warning("Redis ltrim 失败 key=%s: %s", key, e)
            return False

    # Hash 操作(用于实体记忆)

    def hset(self, key: str, field: str, value: Any) -> bool:
        """设置 Hash 字段。"""
        try:
            serialized = json.dumps(value)
            return self.client.hset(key, field, serialized)
        except (RedisError, TypeError, ValueError) as e:
            logger.warning("Redis hset 失败 key=%s field=%s: %s", key, field, e)
            return False

    def hget(self, key: str, field: str) -> Any | None:
        """获取 Hash 字段。"""
        try:
            value = self.client.hget(key, field)
            if value:
                return json.loads(value)
            return None
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning("Redis hget 失败 key=%s field=%s: %s", key, field, e)
            return None

    def hgetall(self, key: str) -> dict[str, Any]:
        """获取所有 Hash 字段。失败返回空 dict。"""
        try:
            values = self.client.hgetall(key)
            return {k: json.loads(v) for k, v in values.items()}
        except (RedisError, json.JSONDecodeError) as e:
            logger.warning("Redis hgetall 失败 key=%s: %s", key, e)
            return {}

    def hdel(self, key: str, field: str) -> bool:
        """删除 Hash 字段。"""
        try:
            return self.client.hdel(key, field) > 0
        except RedisError as e:
            logger.warning("Redis hdel 失败 key=%s field=%s: %s", key, field, e)
            return False

    def close(self) -> None:
        """关闭连接池(显式释放资源, 避免连接泄漏)。

        线程安全: 内部调用 disconnect(), 多线程调用安全。
        """
        try:
            self.pool.disconnect()
        except RedisError as e:
            logger.warning("Redis 连接池关闭失败: %s", e)

    # 上下文管理器支持(推荐使用 with 语法确保连接关闭)
    def __enter__(self) -> "CacheAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# 向后兼容别名: 部分代码/文档使用 RedisCache 名称
RedisCache = CacheAdapter
