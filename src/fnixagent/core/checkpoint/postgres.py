"""PostgresCheckpointer —— P1-2 生产版 Checkpointer。

基于 PostgreSQL 的 Checkpointer 实现,使用 JSONB 存储 channel_values。
需要 psycopg(3.x)驱动。

表结构:
    CREATE TABLE agent_checkpoints (
        thread_id      TEXT NOT NULL,
        checkpoint_id  TEXT NOT NULL,
        parent_id      TEXT,
        checkpoint     JSONB NOT NULL,    -- Checkpoint.to_serializable()
        metadata       JSONB NOT NULL,    -- CheckpointMetadata.to_dict()
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (thread_id, checkpoint_id)
    );
    CREATE INDEX idx_checkpoints_thread ON agent_checkpoints(thread_id, created_at DESC);

连接配置:
    传入 conn_string 或已有 connection;每次操作从连接池获取连接。
    生产环境推荐启用 SSL(sslmode=require 或 verify-full),防止凭证与
    channel_values 在网络层被窃听。conn_string 中可通过 sslmode 参数控制。

异常处理:
    所有数据库操作捕获 psycopg.OperationalError / InterfaceError,
    不向上抛出(返回 None / 空结果),避免 Postgres 不可用时导致主流程崩溃。
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from typing import Any

from fnixagent.core.checkpoint.base import BaseCheckpointer
from fnixagent.core.checkpoint.types import (
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)


class PostgresCheckpointer(BaseCheckpointer):
    """PostgreSQL 版 Checkpointer(生产用)。

    依赖:psycopg >= 3.1
    若未安装,import 本模块会失败(由 __init__.py 的 try/except 捕获)。

    用法:
        cp = PostgresCheckpointer(conn_string="postgresql://user:pass@host/db")
        cp.setup()  # 首次使用创建表
        config = cp.put({"thread_id": "t1"}, checkpoint, metadata, new_versions)

    安全:
        - 推荐 conn_string 带 sslmode=require/verify-full 启用 SSL
        - channel_values 序列化前已由 Checkpoint.to_serializable 脱敏
    """

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS agent_checkpoints (
        thread_id      TEXT NOT NULL,
        checkpoint_id  TEXT NOT NULL,
        parent_id      TEXT,
        checkpoint     JSONB NOT NULL,
        metadata       JSONB NOT NULL,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (thread_id, checkpoint_id)
    );
    CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
        ON agent_checkpoints(thread_id, created_at DESC);
    """

    def __init__(
        self,
        conn_string: str | None = None,
        connection: Any | None = None,
        sslmode: str | None = None,
    ) -> None:
        """初始化。

        Args:
            conn_string: PostgreSQL 连接字符串。生产环境推荐带
                         ``sslmode=require`` 或 ``sslmode=verify-full`` 启用 SSL,
                         防止 channel_values(可能含凭证)在传输中被窃听。
            connection:  已有连接(优先使用,用于连接池场景)。注意:psycopg
                         连接非线程安全,共享连接时所有操作由本类的 _conn_lock
                         串行化保护。
            sslmode:     SSL 模式覆盖(disable/prefer/require/verify-ca/verify-full)。
                         若 conn_string 已含 sslmode 则本参数被忽略;否则追加。
                         优先使用 require 保证传输加密。

        二者至少提供一个。

        Raises:
            ValueError: conn_string 与 connection 均未提供
        """
        if conn_string is None and connection is None:
            raise ValueError("必须提供 conn_string 或 connection")
        # SSL 处理:若 conn_string 未显式指定 sslmode 且 sslmode 参数提供,则追加
        if conn_string and sslmode and "sslmode=" not in conn_string:
            sep = "&" if "?" in conn_string else "?"
            conn_string = f"{conn_string}{sep}sslmode={sslmode}"
        self._conn_string = conn_string
        self._connection = connection
        # 连接操作锁:保证共享 connection 时的串行访问(psycopg 连接非线程安全)
        self._lock = threading.Lock()
        # setup 完成标志(双检锁)
        self._setup_done = False

    def _get_conn(self):
        """获取连接(若使用 conn_string 则每次新建)。

        异常处理:连接失败时抛出,由调用方捕获(不在此处吞掉,
        因 setup/put/get_tuple 各自的 try/except 已覆盖)。
        """
        if self._connection is not None:
            return self._connection
        # 延迟 import,避免未安装 psycopg 时模块加载失败
        import psycopg  # type: ignore

        return psycopg.connect(self._conn_string)

    def setup(self) -> None:
        """创建表结构(幂等,首次使用时调用)。

        异常:连接或建表失败时静默返回(不崩溃),_setup_done 保持 False,
        后续操作会再次尝试 setup。这保证 Postgres 短暂不可用时主流程不中断。
        """
        if self._setup_done:
            return
        with self._lock:
            if self._setup_done:
                return
            try:
                conn = self._get_conn()
                with conn.cursor() as cur:
                    cur.execute(self.SCHEMA_SQL)
                conn.commit()
                self._setup_done = True
            except Exception:
                # 建表失败不崩溃(可能是连接异常或权限不足)
                # 尝试回滚以释放事务,避免连接处于 aborted 状态
                try:
                    conn.rollback()  # type: ignore[name-defined]
                except Exception:
                    pass
                return

    def put(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        """保存检查点到 PostgreSQL。

        Args:
            config: 必须含 thread_id(非空)
            checkpoint: 检查点内容(序列化前已脱敏)
            metadata: 元信息(序列化前已脱敏)
            new_versions: 新增的 channel 版本

        Returns:
            新检查点的 config;连接异常时返回包含新生成 checkpoint_id 的 config
            (数据未落库但保持接口契约一致,不崩溃)。

        Raises:
            ValueError: thread_id 为空
        """
        thread_id = config.get("thread_id", "")
        # 参数校验:thread_id 非空
        if not thread_id:
            raise ValueError("thread_id must not be empty")

        self.setup()
        parent_id = config.get("checkpoint_id")
        checkpoint_id = uuid.uuid4().hex[:16]
        new_config = {"thread_id": thread_id, "checkpoint_id": checkpoint_id}

        try:
            conn = self._get_conn()
            with self._lock:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_checkpoints
                            (thread_id, checkpoint_id, parent_id, checkpoint, metadata)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            thread_id,
                            checkpoint_id,
                            parent_id,
                            json.dumps(checkpoint.to_serializable()),
                            json.dumps(metadata.to_dict()),
                        ),
                    )
                conn.commit()
        except Exception:
            # 连接异常不崩溃:返回 new_config 保持接口契约
            # 数据未落库,调用方应通过 get_tuple 验证或重试
            try:
                conn.rollback()  # type: ignore[name-defined]
            except Exception:
                pass
        return new_config

    def get_tuple(self, config: dict) -> CheckpointTuple | None:
        """从 PostgreSQL 获取检查点元组。

        异常:连接失败时返回 None(不崩溃),调用方据此判断"无检查点"。
        """
        self.setup()
        thread_id = config.get("thread_id", "")
        checkpoint_id = config.get("checkpoint_id")

        try:
            conn = self._get_conn()
            with self._lock, conn.cursor() as cur:
                if checkpoint_id is None:
                    # 最新
                    cur.execute(
                        """
                            SELECT checkpoint_id, parent_id, checkpoint, metadata
                            FROM agent_checkpoints
                            WHERE thread_id = %s
                            ORDER BY created_at DESC
                            LIMIT 1
                            """,
                        (thread_id,),
                    )
                else:
                    cur.execute(
                        """
                            SELECT checkpoint_id, parent_id, checkpoint, metadata
                            FROM agent_checkpoints
                            WHERE thread_id = %s AND checkpoint_id = %s
                            """,
                        (thread_id, checkpoint_id),
                    )
                row = cur.fetchone()
        except Exception:
            # 连接异常不崩溃,返回 None(视为无检查点)
            return None

        if row is None:
            return None

        cp_id, parent_id, cp_json, meta_json = row
        checkpoint = Checkpoint.from_serializable(
            cp_json if isinstance(cp_json, dict) else json.loads(cp_json)
        )
        metadata = CheckpointMetadata.from_dict(
            meta_json if isinstance(meta_json, dict) else json.loads(meta_json)
        )
        parent_config = {"thread_id": thread_id, "checkpoint_id": parent_id} if parent_id else None
        return CheckpointTuple(
            config={"thread_id": thread_id, "checkpoint_id": cp_id},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
        )

    def list(
        self,
        config: dict | None,
        *,
        filter: dict | None = None,
        before: dict | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """列出 PostgreSQL 中的检查点历史。

        异常:连接失败时不抛出,直接 return(生成器不 yield 任何项)。
        """
        self.setup()
        if config is None:
            return
        thread_id = config.get("thread_id", "")
        before_id = before.get("checkpoint_id") if before else None
        sql = """
            SELECT checkpoint_id, parent_id, checkpoint, metadata
            FROM agent_checkpoints
            WHERE thread_id = %s
        """
        params: list = [thread_id]
        if before_id is not None:
            sql += (
                " AND created_at < (SELECT created_at FROM agent_checkpoints "
                "WHERE thread_id = %s AND checkpoint_id = %s)"
            )
            params.extend([thread_id, before_id])
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)

        try:
            conn = self._get_conn()
            with self._lock, conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        except Exception:
            # 连接异常不崩溃:不 yield 任何项(视为空历史)
            return

        for row in rows:
            cp_id, parent_id, cp_json, meta_json = row
            checkpoint = Checkpoint.from_serializable(
                cp_json if isinstance(cp_json, dict) else json.loads(cp_json)
            )
            metadata = CheckpointMetadata.from_dict(
                meta_json if isinstance(meta_json, dict) else json.loads(meta_json)
            )
            # filter 过滤
            if filter:
                match = True
                for k, v in filter.items():
                    if getattr(metadata, k, None) != v:
                        match = False
                        break
                if not match:
                    continue
            parent_config = (
                {"thread_id": thread_id, "checkpoint_id": parent_id} if parent_id else None
            )
            yield CheckpointTuple(
                config={"thread_id": thread_id, "checkpoint_id": cp_id},
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )
