"""检查点管理器 - 工作流状态持久化与恢复(借鉴 kaoyan checkpoint + zhua reclaim_stale)。

特性:
  1. 每步状态持久化: 工作流每完成一个节点,保存当前状态
  2. 崩溃恢复: 重启后从最近 checkpoint 恢复
  3. 活跃任务超时回收: 超时未完成的任务自动回收
  4. TTL 自动清理: 过期 checkpoint 自动清理
  5. 双存储: 内存(快路径) + Redis(持久化,可选)

设计要点:
  - 内存为单一事实源(in-process);Redis 为跨进程可见的"最佳努力"镜像
  - 线程安全: threading.Lock 保护所有读写
  - Redis 操作全部 try/except 包裹,失败时降级到纯内存(不影响主流程)
  - 惰性清理: 每 N 次操作触发一次 cleanup_expired(计数器触发,非定时器)
  - 模块级惰性单例 get_checkpoint_manager() / reset_checkpoint_manager()

集成方式:
  engine = get_workflow_engine()
  checkpoint = get_checkpoint_manager()

  # 在 WorkflowEngine.run() 中,每个节点执行后:
  checkpoint.save(ctx.task_id, ctx.current_node.value, ctx.to_dict())

  # 崩溃恢复:
  entry = checkpoint.load(task_id)
  if entry and entry.status == "active":
      ctx = WorkflowContext.from_dict(entry.state)
      await engine.run(ctx)

依赖: 仅标准库(threading / json / logging / time / dataclasses),
Redis 客户端为可选注入(Any 类型,duck typing)。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# 检查点条目
# ============================================================================


@dataclass
class CheckpointEntry:
    """检查点条目。

    一个 task_id 对应一个 CheckpointEntry,保存该任务最近一次节点完成后的状态快照。

    Attributes:
        task_id:      任务ID
        session_id:   会话ID
        user_id:      用户ID
        node:         当前节点(analyze/plan/think/...)
        state:        序列化的 WorkflowContext(可 JSON 序列化的 dict)
        created_at:   创建时间戳(time.time, wall clock)
        updated_at:   最近更新时间戳
        status:       状态(active / completed / failed / stale)
        ttl_seconds:  存活时间(秒),过期自动清理
    """

    task_id: str
    session_id: str = ""
    user_id: str = ""
    node: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "active"  # active / completed / failed / stale
    ttl_seconds: float = 3600.0

    def is_expired(self) -> bool:
        """是否已过期(距 created_at 超过 ttl_seconds)。"""
        return time.time() - self.created_at > self.ttl_seconds

    def is_stale(self, stale_timeout: float = 300.0) -> bool:
        """是否超时未更新(stale)。

        距 updated_at 超过 stale_timeout 秒视为 stale,
        通常意味着执行该任务的进程已崩溃或卡死。

        Args:
            stale_timeout: 超时阈值(秒)。

        Returns:
            True=已 stale,False=仍在正常执行窗口内。
        """
        return time.time() - self.updated_at > stale_timeout

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典(用于 Redis 持久化与拷贝)。

        state 做浅拷贝返回,避免外部修改污染内部状态。
        """
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "node": self.node,
            "state": dict(self.state),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointEntry:
        """从字典反序列化。

        Args:
            data: to_dict() 产出的字典(或从 Redis JSON 解析得到)。

        Returns:
            CheckpointEntry 实例。
        """
        return cls(
            task_id=data.get("task_id", ""),
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", ""),
            node=data.get("node", ""),
            state=dict(data.get("state", {})),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            status=data.get("status", "active"),
            ttl_seconds=float(data.get("ttl_seconds", 3600.0)),
        )


# ============================================================================
# 检查点管理器
# ============================================================================


class CheckpointManager:
    """检查点管理器。

    存储层级:
      1. 内存: dict[task_id, CheckpointEntry] (快路径,进程内)
      2. Redis(可选): HASH field=task_id, value=JSON (持久化,跨进程)

    内存为单一事实源;Redis 用于跨进程可见与崩溃恢复。Redis 不可用或操作失败时
    降级到纯内存,不影响主流程。

    用法::

        mgr = get_checkpoint_manager()

        # 工作流每步后保存
        mgr.save(task_id, node="think", state=ctx.to_dict())

        # 崩溃后恢复
        entry = mgr.load(task_id)
        if entry and entry.status == "active":
            ctx = WorkflowContext.from_dict(entry.state)
            await engine.run(ctx)  # 从断点继续

        # 回收超时任务
        reclaimed = mgr.reclaim_stale()
    """

    def __init__(
        self,
        redis_client: Any = None,
        redis_prefix: str = "fnixagent:checkpoint:",
        default_ttl: float = 3600.0,
        stale_timeout: float = 300.0,
        cleanup_interval: int = 100,
    ) -> None:
        """初始化检查点管理器。

        Args:
            redis_client: Redis 客户端实例(redis-py 的 Redis 对象),
                None 时降级到纯内存模式。duck typing,需支持
                hset/hget/hdel/hgetall/delete。
            redis_prefix: Redis 键前缀。
            default_ttl: 默认存活时间(秒),过期检查点自动清理。
            stale_timeout: active 检查点超时未更新视为 stale 的阈值(秒)。
            cleanup_interval: 每 N 次操作触发一次惰性清理(计数器触发)。
        """
        self._redis: Any = redis_client
        self._redis_prefix: str = redis_prefix
        self._redis_hash_key: str = f"{redis_prefix}entries"
        self._default_ttl: float = default_ttl
        self._stale_timeout: float = stale_timeout
        self._cleanup_interval: int = cleanup_interval

        # 内存存储: task_id -> CheckpointEntry
        self._store: dict[str, CheckpointEntry] = {}

        # 统计计数(受 _lock 保护)
        self._total_saved: int = 0
        self._total_loaded: int = 0
        self._total_completed: int = 0
        self._total_reclaimed: int = 0
        self._total_expired: int = 0

        # 操作计数(用于惰性清理触发)
        self._op_count: int = 0

        # 线程锁
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 内部:Redis 操作(best effort,失败降级)
    # ------------------------------------------------------------------

    def _redis_save(self, entry: CheckpointEntry) -> None:
        """将 entry 写入 Redis HASH(best effort)。"""
        if self._redis is None:
            return
        try:
            data = json.dumps(entry.to_dict(), ensure_ascii=False)
            self._redis.hset(self._redis_hash_key, entry.task_id, data)
        except Exception as e:
            logger.warning(
                "Redis 保存检查点失败 task_id=%s: %s",
                entry.task_id,
                e,
            )

    def _redis_load(self, task_id: str) -> Optional[CheckpointEntry]:
        """从 Redis HASH 读取 entry(best effort)。"""
        if self._redis is None:
            return None
        try:
            data = self._redis.hget(self._redis_hash_key, task_id)
        except Exception as e:
            logger.warning(
                "Redis 读取检查点失败 task_id=%s: %s",
                task_id,
                e,
            )
            return None
        if data is None:
            return None
        # redis-py 返回 bytes 或 str(取决于 decode_responses 配置)
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        try:
            return CheckpointEntry.from_dict(json.loads(data))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(
                "Redis 检查点反序列化失败 task_id=%s: %s",
                task_id,
                e,
            )
            return None

    def _redis_delete(self, task_id: str) -> None:
        """从 Redis HASH 删除 entry(best effort)。"""
        if self._redis is None:
            return
        try:
            self._redis.hdel(self._redis_hash_key, task_id)
        except Exception as e:
            logger.warning(
                "Redis 删除检查点失败 task_id=%s: %s",
                task_id,
                e,
            )

    def _redis_list_all(self) -> list[CheckpointEntry]:
        """从 Redis HASH 读取所有 entry(best effort)。"""
        if self._redis is None:
            return []
        try:
            items = self._redis.hgetall(self._redis_hash_key)
        except Exception as e:
            logger.warning("Redis 读取所有检查点失败: %s", e)
            return []
        entries: list[CheckpointEntry] = []
        for task_id, data in items.items():
            # redis-py 返回 bytes 或 str(取决于 decode_responses 配置)
            tid = task_id.decode("utf-8") if isinstance(task_id, bytes) else task_id
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            try:
                entries.append(CheckpointEntry.from_dict(json.loads(data)))
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning(
                    "Redis 检查点反序列化失败 task_id=%s: %s",
                    tid,
                    e,
                )
                continue
        return entries

    def _redis_clear_all(self) -> None:
        """清空 Redis HASH(best effort)。"""
        if self._redis is None:
            return
        try:
            self._redis.delete(self._redis_hash_key)
        except Exception as e:
            logger.warning("Redis 清空检查点失败: %s", e)

    # ------------------------------------------------------------------
    # 内部:惰性清理
    # ------------------------------------------------------------------

    def _maybe_cleanup(self) -> None:
        """操作计数达到阈值时触发惰性清理(调用者需持锁)。

        基于计数器而非定时器:每 cleanup_interval 次 save/load/delete 等操作
        触发一次 cleanup_expired,避免引入后台线程,同时控制清理频率。
        """
        self._op_count += 1
        if self._op_count >= self._cleanup_interval:
            self._op_count = 0
            self._cleanup_expired_locked()

    def _cleanup_expired_locked(self) -> int:
        """清理过期检查点(调用者需持锁)。

        遍历内存 store,删除 is_expired() 为 True 的条目,并同步删除 Redis。
        Redis-only 的过期条目不在本次清理范围(它们会在 load 时被回填并随后
        清理,或在 clear_all 时统一清除)。

        Returns:
            清理的数量。
        """
        expired_ids: list[str] = [
            task_id
            for task_id, entry in self._store.items()
            if entry.is_expired()
        ]
        for task_id in expired_ids:
            del self._store[task_id]
            self._redis_delete(task_id)
        if expired_ids:
            self._total_expired += len(expired_ids)
            logger.info("清理了 %d 个过期检查点", len(expired_ids))
        return len(expired_ids)

    # ------------------------------------------------------------------
    # 公共:保存/加载
    # ------------------------------------------------------------------

    def save(
        self,
        task_id: str,
        node: str,
        state: dict[str, Any],
        session_id: str = "",
        user_id: str = "",
    ) -> None:
        """保存检查点(同步写入内存 + Redis)。

        若 task_id 已存在则更新(刷新 updated_at,node,state;保留 created_at),
        否则新建。stale 状态的检查点被更新时自动恢复为 active。

        Args:
            task_id:    任务ID。
            node:       当前节点名(analyze/plan/think/...)。
            state:      序列化的 WorkflowContext 状态(可 JSON 序列化的 dict)。
            session_id: 会话ID(空字符串表示不更新已有值)。
            user_id:    用户ID(空字符串表示不更新已有值)。
        """
        now = time.time()
        with self._lock:
            existing = self._store.get(task_id)
            if existing is not None:
                # 更新:保留 created_at 与 ttl_seconds
                existing.node = node
                existing.state = state
                if session_id:
                    existing.session_id = session_id
                if user_id:
                    existing.user_id = user_id
                existing.updated_at = now
                # stale 被续期后恢复为 active
                if existing.status == "stale":
                    existing.status = "active"
                entry = existing
            else:
                entry = CheckpointEntry(
                    task_id=task_id,
                    session_id=session_id,
                    user_id=user_id,
                    node=node,
                    state=state,
                    created_at=now,
                    updated_at=now,
                    status="active",
                    ttl_seconds=self._default_ttl,
                )
                self._store[task_id] = entry

            # 同步 Redis(best effort)
            self._redis_save(entry)
            self._total_saved += 1
            self._maybe_cleanup()

    def load(self, task_id: str) -> Optional[CheckpointEntry]:
        """加载检查点(先查内存,再查 Redis)。

        Redis 命中时回填内存缓存,加速后续访问。返回的是副本,修改不影响内部状态。

        Args:
            task_id: 任务ID。

        Returns:
            CheckpointEntry 或 None(不存在时)。
        """
        with self._lock:
            entry = self._store.get(task_id)
            if entry is None:
                # 内存未命中,查 Redis(跨进程恢复场景)
                entry = self._redis_load(task_id)
                if entry is None:
                    return None
                # 回填内存缓存
                self._store[task_id] = entry
            self._total_loaded += 1
            # 返回副本,避免外部修改污染内部状态
            return CheckpointEntry.from_dict(entry.to_dict())

    # ------------------------------------------------------------------
    # 公共:状态管理
    # ------------------------------------------------------------------

    def mark_completed(self, task_id: str, success: bool = True) -> None:
        """标记任务完成。

        Args:
            task_id: 任务ID。
            success: True=完成(status=completed),False=失败(status=failed)。
        """
        with self._lock:
            entry = self._store.get(task_id)
            if entry is None:
                # 尝试从 Redis 加载
                entry = self._redis_load(task_id)
                if entry is not None:
                    self._store[task_id] = entry
            if entry is None:
                logger.warning("标记完成时未找到检查点 task_id=%s", task_id)
                return
            entry.status = "completed" if success else "failed"
            entry.updated_at = time.time()
            self._redis_save(entry)
            self._total_completed += 1
            self._maybe_cleanup()

    def delete(self, task_id: str) -> bool:
        """删除检查点。

        Args:
            task_id: 任务ID。

        Returns:
            True=已删除(内存中存在),False=内存中不存在(仍会尝试清理 Redis)。
        """
        with self._lock:
            existed = task_id in self._store
            if existed:
                del self._store[task_id]
            self._redis_delete(task_id)
            self._maybe_cleanup()
            return existed

    # ------------------------------------------------------------------
    # 公共:崩溃恢复
    # ------------------------------------------------------------------

    def reclaim_stale(self) -> list[str]:
        """回收超时任务。

        将 active 状态且超过 stale_timeout 未更新的检查点标记为 stale。
        适用于进程崩溃后遗留的活跃任务:重启后调用本方法识别它们,
        上层(WorkflowEngine)可据此决定重新执行或丢弃。

        同时检查内存与 Redis(跨进程崩溃恢复):其他进程崩溃后遗留的
        active 检查点会出现在 Redis 中但不在本进程内存中,本方法会将其
        回填内存并标记为 stale。

        Returns:
            被回收(标记为 stale)的 task_id 列表。
        """
        reclaimed: list[str] = []
        now = time.time()
        with self._lock:
            # 1) 检查内存中的 active 检查点
            for task_id, entry in self._store.items():
                if entry.status == "active" and entry.is_stale(self._stale_timeout):
                    entry.status = "stale"
                    entry.updated_at = now
                    reclaimed.append(task_id)

            # 2) 检查 Redis 中的 active 检查点(跨进程崩溃恢复)
            if self._redis is not None:
                redis_entries = self._redis_list_all()
                for entry in redis_entries:
                    if entry.task_id in self._store:
                        continue  # 内存已处理
                    if entry.status == "active" and entry.is_stale(self._stale_timeout):
                        entry.status = "stale"
                        entry.updated_at = now
                        self._store[entry.task_id] = entry
                        self._redis_save(entry)
                        reclaimed.append(entry.task_id)

            if reclaimed:
                self._total_reclaimed += len(reclaimed)
                logger.info("reclaim_stale 回收了 %d 个超时检查点", len(reclaimed))
        return reclaimed

    def cleanup_expired(self) -> int:
        """清理过期检查点。

        主动触发清理(非惰性),遍历内存 store 删除 is_expired() 为 True 的条目,
        并同步删除 Redis。

        Returns:
            清理的数量。
        """
        with self._lock:
            return self._cleanup_expired_locked()

    # ------------------------------------------------------------------
    # 公共:查询/统计
    # ------------------------------------------------------------------

    def list_active(self) -> list[CheckpointEntry]:
        """列出所有活跃检查点(status == active)。

        Returns:
            CheckpointEntry 列表(副本,修改不影响内部状态)。
        """
        with self._lock:
            return [
                CheckpointEntry.from_dict(e.to_dict())
                for e in self._store.values()
                if e.status == "active"
            ]

    def get_stats(self) -> dict[str, Any]:
        """返回统计信息。

        Returns:
            包含存储大小、状态分布、各类计数与 Redis 状态的字典。
        """
        with self._lock:
            status_counts: dict[str, int] = {}
            for entry in self._store.values():
                status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            return {
                "total_entries": len(self._store),
                "status_counts": status_counts,
                "redis_enabled": self._redis is not None,
                "default_ttl": self._default_ttl,
                "stale_timeout": self._stale_timeout,
                "cleanup_interval": self._cleanup_interval,
                "total_saved": self._total_saved,
                "total_loaded": self._total_loaded,
                "total_completed": self._total_completed,
                "total_reclaimed": self._total_reclaimed,
                "total_expired": self._total_expired,
            }

    def clear_all(self) -> int:
        """清空所有检查点(测试用)。

        清空内存与 Redis 中的全部检查点。不重置统计计数
        (如需完全重置请使用 reset_checkpoint_manager())。

        Returns:
            清空的检查点数量。
        """
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._redis_clear_all()
            logger.info("清空了 %d 个检查点", count)
            return count


# ============================================================================
# 模块级单例(双重检查锁定)
# ============================================================================

_singleton_lock = threading.Lock()
_singleton_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager(
    redis_client: Any = None,
    redis_prefix: str = "fnixagent:checkpoint:",
    default_ttl: float = 3600.0,
    stale_timeout: float = 300.0,
    cleanup_interval: int = 100,
) -> CheckpointManager:
    """获取全局 CheckpointManager 单例(双重检查锁定)。

    首次调用时创建实例,后续调用返回同一实例。
    首次调用传入的参数才生效;后续调用传入的参数被忽略
    (避免单例被意外替换导致并发问题)。

    Args:
        redis_client:      Redis 客户端(仅首次调用生效)。
        redis_prefix:      Redis 键前缀(仅首次调用生效)。
        default_ttl:       默认存活时间秒(仅首次调用生效)。
        stale_timeout:     超时回收阈值秒(仅首次调用生效)。
        cleanup_interval:  惰性清理间隔(仅首次调用生效)。

    Returns:
        全局 CheckpointManager 实例。
    """
    global _singleton_manager
    if _singleton_manager is not None:
        return _singleton_manager
    with _singleton_lock:
        # 双重检查:拿到锁后再检查一次,防止并发时重复创建
        if _singleton_manager is not None:
            return _singleton_manager
        _singleton_manager = CheckpointManager(
            redis_client=redis_client,
            redis_prefix=redis_prefix,
            default_ttl=default_ttl,
            stale_timeout=stale_timeout,
            cleanup_interval=cleanup_interval,
        )
        return _singleton_manager


def reset_checkpoint_manager() -> None:
    """重置全局单例(主要供测试使用)。

    重置后,下次 get_checkpoint_manager() 会重新创建实例。
    """
    global _singleton_manager
    with _singleton_lock:
        _singleton_manager = None
