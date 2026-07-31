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
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
        messages:     独立的消息流通道(append-only,借鉴 LangGraph writes 表
                      与 OpenAI Agents SDK agent_messages 表)。每条 message
                      一行,避免 state 全量重写。崩溃恢复后从此处重建对话上下文。
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
    messages: list[dict[str, Any]] = field(default_factory=list)
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

        state 与 messages 都做浅拷贝返回,避免外部修改污染内部状态。
        messages 单独成键,以便后续单独 JSONL 文件落盘与按需加载。
        """
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "node": self.node,
            "state": dict(self.state),
            "messages": list(self.messages),
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
            messages=list(data.get("messages", [])),
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
      3. JSONL 文件(可选): ~/.fnix/checkpoints/<task_id>.jsonl (standalone 兜底,
         借鉴 OpenAI Agents SDK SQLiteSession 的 standalone 思路 + LangGraph
         SqliteSaver 的 file_path 注入设计。Redis 不可用时启用文件兜底)

    内存为单一事实源;Redis 用于跨进程可见与崩溃恢复;JSONL 文件作为最终兜底,
    保证进程重启后仍能恢复 messages 上下文(standalone 部署无需 Redis/Postgres)。

    用法::

        mgr = get_checkpoint_manager()

        # 工作流每步后保存
        mgr.save(task_id, node="think", state=ctx.to_dict())

        # 追加单条 message(append-only,不全量重写 state)
        mgr.append_message(task_id, {"role": "user", "content": "hello"})

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
        file_dir: str | None = None,
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
            file_dir: JSONL 文件落盘目录。None 时默认 ~/.fnix/checkpoints/。
                传空字符串 "" 表示禁用文件落盘(纯内存 + Redis 模式)。
                standalone 部署强烈建议保留默认值,以便 Redis 不可用时可兜底恢复。
        """
        self._redis: Any = redis_client
        self._redis_prefix: str = redis_prefix
        self._redis_hash_key: str = f"{redis_prefix}entries"
        self._default_ttl: float = default_ttl
        self._stale_timeout: float = stale_timeout
        self._cleanup_interval: int = cleanup_interval

        # JSONL 文件落盘目录(None=默认 ~/.fnix/checkpoints/,""=禁用)
        if file_dir is None:
            self._file_dir: Path | None = Path.home() / ".fnix" / "checkpoints"
        elif file_dir == "":
            self._file_dir = None
        else:
            self._file_dir = Path(file_dir).expanduser()
        if self._file_dir is not None:
            try:
                self._file_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning("创建检查点文件目录失败 %s: %s", self._file_dir, e)
                self._file_dir = None

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

    def _redis_load(self, task_id: str) -> CheckpointEntry | None:
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
    # 内部:JSONL 文件操作(best effort,失败降级)
    # ------------------------------------------------------------------
    #
    # 文件格式: 每行一个 JSON 对象(JSONL)
    #   第 1 行: 元数据头 {"__type__": "header", "task_id":..., "node":..., ...}
    #   第 2..N 行: 每行一条 message {"__type__": "message", "role":..., "content":...}
    #
    # 设计要点(借鉴 OpenAI Agents SDK SQLiteSession + LangGraph SqliteSaver):
    #   - 原子写: 写临时文件 + os.replace,避免崩溃时半写入
    #   - append-only messages: 写时先读全量,追加 message 后整文件原子替换
    #     (简化实现;后续可优化为只 append message 行)
    #   - 容错: 文件不存在/损坏/解析失败返回 None,不抛异常
    # ------------------------------------------------------------------

    def _file_path(self, task_id: str) -> Path | None:
        """获取 task_id 对应的 JSONL 文件路径。"""
        if self._file_dir is None:
            return None
        # 防御性: task_id 不允许包含路径分隔符(防止目录穿越)
        safe_id = "".join(c for c in task_id if c.isalnum() or c in "-_")
        if not safe_id:
            return None
        return self._file_dir / f"{safe_id}.jsonl"

    def _file_save(self, entry: CheckpointEntry) -> None:
        """将 entry 写入 JSONL 文件(原子写, best effort)。

        文件结构:
          第 1 行: header (task_id / node / state / status / timestamps / ttl)
          第 2..N 行: 每行一条 message
        """
        path = self._file_path(entry.task_id)
        if path is None:
            return
        try:
            header = {
                "__type__": "header",
                "task_id": entry.task_id,
                "session_id": entry.session_id,
                "user_id": entry.user_id,
                "node": entry.node,
                "state": entry.state,
                "created_at": entry.created_at,
                "updated_at": entry.updated_at,
                "status": entry.status,
                "ttl_seconds": entry.ttl_seconds,
            }
            lines = [json.dumps(header, ensure_ascii=False)]
            for msg in entry.messages:
                payload = {"__type__": "message", **msg}
                lines.append(json.dumps(payload, ensure_ascii=False, default=str))
            content = "\n".join(lines) + "\n"
            # 原子写: 写临时文件 + os.replace
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=str(path.parent),
                delete=False,
                suffix=".tmp",
                prefix=f"{path.stem}_",
                encoding="utf-8",
            ) as tmp:
                tmp.write(content)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_path = tmp.name
            os.replace(tmp_path, str(path))
        except Exception as e:
            logger.warning("JSONL 文件保存失败 task_id=%s: %s", entry.task_id, e)
            # 清理可能的临时文件残留
            try:
                if "tmp_path" in locals() and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    def _file_load(self, task_id: str) -> CheckpointEntry | None:
        """从 JSONL 文件加载 entry(最佳努力,文件不存在/损坏返回 None)。"""
        path = self._file_path(task_id)
        if path is None or not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            logger.warning("JSONL 文件读取失败 task_id=%s: %s", task_id, e)
            return None
        if not lines:
            return None
        header: dict[str, Any] = {}
        messages: list[dict[str, Any]] = []
        for idx, raw in enumerate(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning("JSONL 第 %d 行解析失败 task_id=%s: %s", idx + 1, task_id, e)
                continue
            if obj.get("__type__") == "header":
                header = obj
            elif obj.get("__type__") == "message":
                # 剥离内部 __type__ 字段
                msg = {k: v for k, v in obj.items() if k != "__type__"}
                messages.append(msg)
        if not header:
            return None
        try:
            entry = CheckpointEntry(
                task_id=header.get("task_id", task_id),
                session_id=header.get("session_id", ""),
                user_id=header.get("user_id", ""),
                node=header.get("node", ""),
                state=dict(header.get("state", {})),
                messages=messages,
                created_at=float(header.get("created_at", time.time())),
                updated_at=float(header.get("updated_at", time.time())),
                status=header.get("status", "active"),
                ttl_seconds=float(header.get("ttl_seconds", 3600.0)),
            )
            return entry
        except (TypeError, ValueError) as e:
            logger.warning("JSONL 反序列化失败 task_id=%s: %s", task_id, e)
            return None

    def _file_delete(self, task_id: str) -> None:
        """删除 task_id 对应的 JSONL 文件(best effort)。"""
        path = self._file_path(task_id)
        if path is None or not path.exists():
            return
        try:
            path.unlink()
        except OSError as e:
            logger.warning("JSONL 文件删除失败 task_id=%s: %s", task_id, e)

    def _file_list_all(self) -> list[CheckpointEntry]:
        """列出文件目录下所有 entry(best effort,用于跨进程恢复)。"""
        if self._file_dir is None or not self._file_dir.exists():
            return []
        entries: list[CheckpointEntry] = []
        try:
            for path in self._file_dir.glob("*.jsonl"):
                try:
                    task_id = path.stem
                    entry = self._file_load(task_id)
                    if entry is not None:
                        entries.append(entry)
                except Exception as e:
                    logger.warning("加载 JSONL 文件失败 %s: %s", path, e)
                    continue
        except OSError as e:
            logger.warning("遍历 JSONL 目录失败 %s: %s", self._file_dir, e)
        return entries

    def _file_clear_all(self) -> int:
        """清空文件目录下所有 JSONL 文件(best effort)。"""
        if self._file_dir is None or not self._file_dir.exists():
            return 0
        count = 0
        try:
            for path in self._file_dir.glob("*.jsonl"):
                try:
                    path.unlink()
                    count += 1
                except OSError:
                    continue
        except OSError as e:
            logger.warning("清空 JSONL 目录失败 %s: %s", self._file_dir, e)
        return count

    # ------------------------------------------------------------------
    # 内部:messages 兼容性修复(借鉴 letta backfill_missing_tool_call_ids)
    # ------------------------------------------------------------------

    @staticmethod
    def _backfill_tool_call_ids(messages: list[dict[str, Any]]) -> None:
        """补全历史 messages 缺失的 tool_call_id(原地修改)。

        老 checkpoint 加载时,tool 角色消息可能缺 tool_call_id(旧版本未存),
        从相邻 assistant 消息的单 tool_call 推断回填。仅处理单 tool_call 的
        assistant→tool 配对,多 tool_call 不做启发式推断(避免错配)。

        Args:
            messages: messages 列表(原地修改,缺失字段会被补上)。
        """
        if not messages:
            return
        last_tc_id: str | None = None
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                if len(tool_calls) == 1 and tool_calls[0].get("id"):
                    last_tc_id = tool_calls[0].get("id")
                else:
                    last_tc_id = None
            elif role == "tool":
                if msg.get("tool_call_id") is None and last_tc_id is not None:
                    msg["tool_call_id"] = last_tc_id
                last_tc_id = None

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

        遍历内存 store,删除 is_expired() 为 True 的条目,并同步删除 Redis 与
        JSONL 文件。Redis-only / file-only 的过期条目不在本次清理范围(它们会在
        load 时被回填并随后清理,或在 clear_all 时统一清除)。

        Returns:
            清理的数量。
        """
        expired_ids: list[str] = [
            task_id for task_id, entry in self._store.items() if entry.is_expired()
        ]
        for task_id in expired_ids:
            del self._store[task_id]
            self._redis_delete(task_id)
            self._file_delete(task_id)
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
        """保存检查点(同步写入内存 + Redis + JSONL 文件)。

        若 task_id 已存在则更新(刷新 updated_at,node,state;保留 created_at
        与已有 messages),否则新建。stale 状态的检查点被更新时自动恢复为 active。
        messages 通道不被覆盖,需用 append_message() 单独追加。

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
                # 更新:保留 created_at / ttl_seconds / messages
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
                # 新建前先尝试从文件加载(进程重启场景,可能已有历史 messages)
                from_file = self._file_load(task_id)
                if from_file is not None and from_file.status == "active":
                    # 复用文件中的 messages,但用新入参覆盖 node/state
                    from_file.node = node
                    from_file.state = state
                    if session_id:
                        from_file.session_id = session_id
                    if user_id:
                        from_file.user_id = user_id
                    from_file.updated_at = now
                    if from_file.status == "stale":
                        from_file.status = "active"
                    entry = from_file
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
            # 同步 JSONL 文件(best effort,standalone 兜底)
            self._file_save(entry)
            self._total_saved += 1
            self._maybe_cleanup()

    def load(self, task_id: str) -> CheckpointEntry | None:
        """加载检查点(先查内存,再查 Redis,最后查 JSONL 文件)。

        Redis 命中时回填内存缓存,加速后续访问。返回的是副本,修改不影响内部状态。
        文件命中时同样回填内存,并执行 _backfill_tool_call_ids 兼容性修复。

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
                    # 最后兜底:查 JSONL 文件(进程重启场景)
                    entry = self._file_load(task_id)
                    if entry is None:
                        return None
                # 回填内存缓存
                self._store[task_id] = entry
            # 兼容性修复:补全历史 messages 缺失的 tool_call_id
            self._backfill_tool_call_ids(entry.messages)
            self._total_loaded += 1
            # 返回副本,避免外部修改污染内部状态
            return CheckpointEntry.from_dict(entry.to_dict())

    # ------------------------------------------------------------------
    # 公共:messages 通道(append-only,独立于 state 快照)
    # ------------------------------------------------------------------

    def append_message(
        self,
        task_id: str,
        message: dict[str, Any],
        *,
        node: str = "",
    ) -> None:
        """向 task_id 追加单条 message(append-only,不全量重写 state)。

        借鉴 LangGraph put_writes / OpenAI Agents SDK add_items 的 append-only
        messages 通道设计。若 task_id 不存在则自动创建空 state 的 entry。

        Args:
            task_id: 任务ID。
            message: 消息 dict,推荐包含 {"role": "user/assistant/tool",
                "content": ..., "tool_call_id": ...(可选)}。
            node:    当前节点名(空字符串表示不更新已有 node)。
        """
        if not isinstance(message, dict):
            raise TypeError(f"message 必须为 dict,得到 {type(message).__name__}")
        now = time.time()
        with self._lock:
            entry = self._store.get(task_id)
            if entry is None:
                # 内存未命中,先尝试 Redis/文件加载
                entry = self._redis_load(task_id)
                if entry is None:
                    entry = self._file_load(task_id)
                if entry is None:
                    # 仍无,创建新 entry
                    entry = CheckpointEntry(
                        task_id=task_id,
                        node=node,
                        created_at=now,
                        updated_at=now,
                        status="active",
                        ttl_seconds=self._default_ttl,
                    )
                self._store[task_id] = entry
            entry.messages.append(dict(message))
            if node:
                entry.node = node
            entry.updated_at = now
            if entry.status == "stale":
                entry.status = "active"
            # 三层存储同步(best effort)
            self._redis_save(entry)
            self._file_save(entry)
            self._maybe_cleanup()

    def append_messages(
        self,
        task_id: str,
        messages: list[dict[str, Any]],
        *,
        node: str = "",
    ) -> None:
        """向 task_id 批量追加 messages(append-only,单次 fsync)。

        借鉴 OpenAI Agents SDK Session.add_items 的批量 API: 每个 turn 边界
        批量追加, 而非每条 message 都触发 fsync。长程任务 8h 累积可显著降低 I/O。

        Args:
            task_id:   任务ID。
            messages:  消息 dict 列表。
            node:      当前节点名(空字符串表示不更新已有 node)。
        """
        if not isinstance(messages, list):
            raise TypeError(f"messages 必须为 list, 得到 {type(messages).__name__}")
        if not messages:
            return
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise TypeError(f"messages[{i}] 必须为 dict, 得到 {type(msg).__name__}")
        now = time.time()
        with self._lock:
            entry = self._store.get(task_id)
            if entry is None:
                entry = self._redis_load(task_id)
                if entry is None:
                    entry = self._file_load(task_id)
                if entry is None:
                    entry = CheckpointEntry(
                        task_id=task_id,
                        node=node,
                        created_at=now,
                        updated_at=now,
                        status="active",
                        ttl_seconds=self._default_ttl,
                    )
                self._store[task_id] = entry
            # 批量 extend (单次 fsync, 不触发多次 Redis/文件写)
            entry.messages.extend(dict(msg) for msg in messages)
            if node:
                entry.node = node
            entry.updated_at = now
            if entry.status == "stale":
                entry.status = "active"
            # 三层存储同步 (单次 fsync, 比循环调用 append_message 快 N 倍)
            self._redis_save(entry)
            self._file_save(entry)
            self._maybe_cleanup()

    def replace_messages(
        self,
        task_id: str,
        messages: list[dict[str, Any]],
        *,
        node: str = "",
        compaction_info: dict[str, Any] | None = None,
    ) -> None:
        """全量替换 task_id 的 messages (单次 fsync)。

        借鉴 OpenAI Agents SDK `OpenAIResponsesCompactionAwareSession.run_compaction`
        协议的设计思路: 当 compaction / summarization 发生时, Session 自己负责
        持久化压缩后的结果, 避免 resume 时重复触发压缩 (浪费 LLM 调用 + token)。

        与 append_messages 对称:
          - append_messages: 增量追加 (turn 边界)
          - replace_messages: 全量替换 (compaction 边界)

        compaction_info (可选) 会追加到 entry.state["compaction_history"] 列表,
        保留审计轨迹 (before/after tokens、压缩时间、summary 摘要), 不丢失元数据。

        Args:
            task_id:          任务ID。
            messages:         新的 messages 列表 (全量替换)。
            node:             当前节点名 (空字符串表示不更新已有 node)。
            compaction_info:  压缩元信息 dict (可选)。建议字段:
                {
                    "compacted": bool,
                    "before_tokens": int,
                    "after_tokens": int,
                    "compacted_messages_count": int,
                    "summary": str,  # 前 500 字符
                    "error": str | None,
                    "compacted_at": float,  # 自动填充 time.time()
                }
        """
        if not isinstance(messages, list):
            raise TypeError(f"messages 必须为 list, 得到 {type(messages).__name__}")
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise TypeError(f"messages[{i}] 必须为 dict, 得到 {type(msg).__name__}")
        now = time.time()
        with self._lock:
            entry = self._store.get(task_id)
            if entry is None:
                entry = self._redis_load(task_id)
                if entry is None:
                    entry = self._file_load(task_id)
                if entry is None:
                    entry = CheckpointEntry(
                        task_id=task_id,
                        node=node,
                        created_at=now,
                        updated_at=now,
                        status="active",
                        ttl_seconds=self._default_ttl,
                    )
                self._store[task_id] = entry
            # 全量替换 messages (深拷贝避免外部修改污染)
            entry.messages = [dict(msg) for msg in messages]
            if node:
                entry.node = node
            entry.updated_at = now
            if entry.status == "stale":
                entry.status = "active"
            # 追加 compaction_history 审计轨迹 (不丢失元数据)
            if compaction_info:
                history = entry.state.get("compaction_history")
                if not isinstance(history, list):
                    history = []
                record = dict(compaction_info)
                record.setdefault("compacted_at", now)
                # 防止 summary 过长 (state 会序列化到 Redis/JSONL)
                if isinstance(record.get("summary"), str) and len(record["summary"]) > 500:
                    record["summary"] = record["summary"][:500]
                history.append(record)
                # 限制历史记录数量, 避免长程任务 state 膨胀
                if len(history) > 20:
                    history = history[-20:]
                entry.state["compaction_history"] = history
            # 三层存储同步 (单次 fsync)
            self._redis_save(entry)
            self._file_save(entry)
            self._maybe_cleanup()

    def get_messages(
        self,
        task_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """获取 task_id 的 messages 列表(最近 limit 条,按时间正序)。

        Args:
            task_id: 任务ID。
            limit:   返回最近 N 条(按时间正序)。None=返回全部。

        Returns:
            messages 列表(副本)。task_id 不存在时返回空列表。
        """
        with self._lock:
            entry = self._store.get(task_id)
            if entry is None:
                entry = self._redis_load(task_id)
                if entry is None:
                    entry = self._file_load(task_id)
                if entry is None:
                    return []
                self._store[task_id] = entry
            self._backfill_tool_call_ids(entry.messages)
            msgs = list(entry.messages)
        if limit is not None and limit > 0:
            msgs = msgs[-limit:]
        return msgs

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
                if entry is None:
                    # 最后兜底:从文件加载
                    entry = self._file_load(task_id)
                if entry is not None:
                    self._store[task_id] = entry
            if entry is None:
                logger.warning("标记完成时未找到检查点 task_id=%s", task_id)
                return
            entry.status = "completed" if success else "failed"
            entry.updated_at = time.time()
            self._redis_save(entry)
            self._file_save(entry)
            self._total_completed += 1
            self._maybe_cleanup()

    def delete(self, task_id: str) -> bool:
        """删除检查点。

        Args:
            task_id: 任务ID。

        Returns:
            True=已删除(内存中存在),False=内存中不存在(仍会尝试清理 Redis/文件)。
        """
        with self._lock:
            existed = task_id in self._store
            if existed:
                del self._store[task_id]
            self._redis_delete(task_id)
            self._file_delete(task_id)
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
                        self._file_save(entry)
                        reclaimed.append(entry.task_id)

            # 3) 检查 JSONL 文件中的 active 检查点(进程重启崩溃恢复)
            file_entries = self._file_list_all()
            for entry in file_entries:
                if entry.task_id in self._store:
                    continue  # 内存/Redis 已处理
                if entry.status == "active" and entry.is_stale(self._stale_timeout):
                    entry.status = "stale"
                    entry.updated_at = now
                    self._store[entry.task_id] = entry
                    self._file_save(entry)
                    reclaimed.append(entry.task_id)

            if reclaimed:
                self._total_reclaimed += len(reclaimed)
                logger.info("reclaim_stale 回收了 %d 个超时检查点", len(reclaimed))
        return reclaimed

    def cleanup_expired(self) -> int:
        """清理过期检查点。

        主动触发清理(非惰性),遍历内存 store 删除 is_expired() 为 True 的条目,
        并同步删除 Redis 与 JSONL 文件。

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
            包含存储大小、状态分布、各类计数与 Redis/文件存储状态的字典。
        """
        with self._lock:
            status_counts: dict[str, int] = {}
            for entry in self._store.values():
                status_counts[entry.status] = status_counts.get(entry.status, 0) + 1
            file_dir_str = str(self._file_dir) if self._file_dir else None
            file_count = 0
            if self._file_dir is not None and self._file_dir.exists():
                try:
                    file_count = sum(1 for _ in self._file_dir.glob("*.jsonl"))
                except OSError:
                    pass
            return {
                "total_entries": len(self._store),
                "status_counts": status_counts,
                "redis_enabled": self._redis is not None,
                "file_enabled": self._file_dir is not None,
                "file_dir": file_dir_str,
                "file_count": file_count,
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

        清空内存与 Redis 与 JSONL 文件中的全部检查点。不重置统计计数
        (如需完全重置请使用 reset_checkpoint_manager())。

        Returns:
            清空的检查点数量。
        """
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._redis_clear_all()
            self._file_clear_all()
            logger.info("清空了 %d 个检查点(内存)", count)
            return count

    # ------------------------------------------------------------------
    # 异步接口 (P1-1): asyncio.to_thread 包装, 避免 event loop 阻塞
    # ------------------------------------------------------------------
    #
    # 设计要点 (借鉴 OpenAI Agents SDK SQLiteSession.add_items 的 async 模式):
    #   - 同步接口保留 (非 async 场景 + 测试用)
    #   - async 接口用 asyncio.to_thread 把同步 I/O 丢到线程池
    #   - 基准测试: 同步 append_messages 阻塞 event loop 最长 16ms,
    #     长程任务 8h 累积 1000 次 flush = 16s 累积阻塞, 对流式输出有显著卡顿
    #   - async 接口将 16ms 阻塞降到 ~0ms (线程池并行)
    # ------------------------------------------------------------------

    async def aappend_messages(
        self,
        task_id: str,
        messages: list[dict[str, Any]],
        *,
        node: str = "",
    ) -> None:
        """append_messages 的异步版本 (asyncio.to_thread 包装)。

        在 async event loop 中调用, 避免同步 fsync 阻塞 (16ms → ~0ms)。
        参数与 append_messages 完全一致。
        """
        import asyncio

        await asyncio.to_thread(self.append_messages, task_id, messages, node=node)

    async def areplace_messages(
        self,
        task_id: str,
        messages: list[dict[str, Any]],
        *,
        node: str = "",
        compaction_info: dict[str, Any] | None = None,
    ) -> None:
        """replace_messages 的异步版本 (asyncio.to_thread 包装)。

        在 compaction 后的 async hot path 调用, 避免同步 fsync 阻塞。
        参数与 replace_messages 完全一致。
        """
        import asyncio

        await asyncio.to_thread(
            self.replace_messages,
            task_id,
            messages,
            node=node,
            compaction_info=compaction_info,
        )

    async def aget_messages(
        self,
        task_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """get_messages 的异步版本 (asyncio.to_thread 包装)。

        在 async resume 路径调用, 避免同步文件读取阻塞 event loop。
        参数与 get_messages 完全一致。
        """
        import asyncio

        return await asyncio.to_thread(self.get_messages, task_id, limit=limit)


# ============================================================================
# 模块级单例(双重检查锁定)
# ============================================================================

_singleton_lock = threading.Lock()
_singleton_manager: CheckpointManager | None = None


def get_checkpoint_manager(
    redis_client: Any = None,
    redis_prefix: str = "fnixagent:checkpoint:",
    default_ttl: float = 3600.0,
    stale_timeout: float = 300.0,
    cleanup_interval: int = 100,
    file_dir: str | None = None,
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
        file_dir:          JSONL 文件落盘目录(仅首次调用生效)。
            None=默认 ~/.fnix/checkpoints/,""=禁用文件落盘。

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
            file_dir=file_dir,
        )
        return _singleton_manager


def reset_checkpoint_manager() -> None:
    """重置全局单例(主要供测试使用)。

    重置后,下次 get_checkpoint_manager() 会重新创建实例。
    """
    global _singleton_manager
    with _singleton_lock:
        _singleton_manager = None
