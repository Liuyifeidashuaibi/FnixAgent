"""
审计日志存储层(Phase 2.5)。

双存储实现:
    1. InMemoryAuditStore — 开发/测试环境
    2. PgAuditStore — 生产环境(使用 SQLAlchemy + AuditLog 模型)

工厂函数 get_audit_store() 根据 DATABASE_URL 是否配置自动选择。
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Optional

from fnixagent.core.audit.logger import AuditLogDTO


# ---------------------------------------------------------------------------
# 内存实现
# ---------------------------------------------------------------------------


class InMemoryAuditStore:
    """内存审计日志存储(开发/测试用)。

    线程安全,支持哈希链(get_last_hash 返回最后一条的 entry_hash)。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._logs: dict[int, AuditLogDTO] = {}
        self._next_id = 1

    def create(
        self,
        tenant_id: int = 0,
        user_id: Optional[int] = None,
        action: str = "",
        detail: Optional[dict] = None,
        trace_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        prev_hash: str = "",
        entry_hash: str = "",
        created_at: Optional[datetime] = None,
    ) -> AuditLogDTO:
        with self._lock:
            lid = self._next_id
            self._next_id += 1
            log = AuditLogDTO(
                id=lid,
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                detail=detail or {},
                trace_id=trace_id,
                ip_address=ip_address,
                user_agent=user_agent,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                created_at=created_at or datetime.utcnow(),
            )
            self._logs[lid] = log
            return log

    def get_last_hash(self, tenant_id: int = 0) -> str:
        """获取最后一条记录的 entry_hash(用于哈希链续接)。"""
        with self._lock:
            if not self._logs:
                return ""
            # 按 id 降序找最后一条
            last_id = max(self._logs.keys())
            return self._logs[last_id].entry_hash

    def query(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        ip_address: Optional[str] = None,
        tenant_id: int = 0,
    ) -> tuple[list[AuditLogDTO], int]:
        with self._lock:
            results = list(self._logs.values())

        # 筛选
        if tenant_id:
            results = [r for r in results if r.tenant_id == tenant_id]
        if user_id is not None:
            results = [r for r in results if r.user_id == user_id]
        if action:
            results = [r for r in results if r.action == action]
        if ip_address:
            results = [r for r in results if r.ip_address == ip_address]
        if start:
            try:
                start_dt = datetime.fromisoformat(start)
                results = [r for r in results
                           if r.created_at and r.created_at >= start_dt]
            except ValueError:
                pass
        if end:
            try:
                end_dt = datetime.fromisoformat(end)
                results = [r for r in results
                           if r.created_at and r.created_at <= end_dt]
            except ValueError:
                pass

        # 按 id 降序(最新优先)
        results.sort(key=lambda x: x.id, reverse=True)
        total = len(results)
        page = results[offset:offset + limit]
        return page, total

    def get_all_ordered(self, tenant_id: int = 0) -> list[AuditLogDTO]:
        """获取全部日志(按 id 升序,用于哈希链校验)。"""
        with self._lock:
            results = list(self._logs.values())
        if tenant_id:
            results = [r for r in results if r.tenant_id == tenant_id]
        results.sort(key=lambda x: x.id)
        return results

    def count(self, tenant_id: int = 0) -> int:
        with self._lock:
            if not tenant_id:
                return len(self._logs)
            return sum(1 for r in self._logs.values() if r.tenant_id == tenant_id)

    def clear(self) -> int:
        """清空所有审计日志(仅测试用)。"""
        with self._lock:
            count = len(self._logs)
            self._logs.clear()
            self._next_id = 1
            return count


# ---------------------------------------------------------------------------
# PostgreSQL 实现
# ---------------------------------------------------------------------------


class PgAuditStore:
    """PostgreSQL 审计日志存储(生产环境)。

    通过 SQLAlchemy 操作 audit_logs 表。
    """

    def __init__(self, db_adapter):
        self._db = db_adapter

    def create(
        self,
        tenant_id: int = 0,
        user_id: Optional[int] = None,
        action: str = "",
        detail: Optional[dict] = None,
        trace_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        prev_hash: str = "",
        entry_hash: str = "",
        created_at: Optional[datetime] = None,
    ) -> AuditLogDTO:
        from fnixagent.models.db.models import AuditLog

        with self._db.session() as session:
            log = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                detail=detail or {},
                trace_id=trace_id,
                ip_address=ip_address,
                user_agent=user_agent,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                created_at=created_at or datetime.utcnow(),
            )
            session.add(log)
            session.flush()  # 获取 id
            lid = log.id
            return AuditLogDTO(
                id=lid,
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                detail=detail or {},
                trace_id=trace_id,
                ip_address=ip_address,
                user_agent=user_agent,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                created_at=log.created_at,
            )

    def get_last_hash(self, tenant_id: int = 0) -> str:
        from fnixagent.models.db.models import AuditLog

        with self._db.session() as session:
            last = (
                session.query(AuditLog)
                .filter(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.id.desc())
                .first()
            )
            return last.entry_hash if last else ""

    def query(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        ip_address: Optional[str] = None,
        tenant_id: int = 0,
    ) -> tuple[list[AuditLogDTO], int]:
        from fnixagent.models.db.models import AuditLog

        with self._db.session() as session:
            q = session.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)
            if user_id is not None:
                q = q.filter(AuditLog.user_id == user_id)
            if action:
                q = q.filter(AuditLog.action == action)
            if ip_address:
                q = q.filter(AuditLog.ip_address == ip_address)
            if start:
                try:
                    start_dt = datetime.fromisoformat(start)
                    q = q.filter(AuditLog.created_at >= start_dt)
                except ValueError:
                    pass
            if end:
                try:
                    end_dt = datetime.fromisoformat(end)
                    q = q.filter(AuditLog.created_at <= end_dt)
                except ValueError:
                    pass
            total = q.count()
            logs = (
                q.order_by(AuditLog.id.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            results = [
                AuditLogDTO(
                    id=log.id,
                    tenant_id=log.tenant_id,
                    user_id=log.user_id,
                    action=log.action,
                    detail=log.detail or {},
                    trace_id=log.trace_id,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                    prev_hash=log.prev_hash or "",
                    entry_hash=log.entry_hash or "",
                    created_at=log.created_at,
                )
                for log in logs
            ]
            return results, total

    def get_all_ordered(self, tenant_id: int = 0) -> list[AuditLogDTO]:
        from fnixagent.models.db.models import AuditLog

        with self._db.session() as session:
            q = session.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)
            logs = q.order_by(AuditLog.id.asc()).all()
            return [
                AuditLogDTO(
                    id=log.id,
                    tenant_id=log.tenant_id,
                    user_id=log.user_id,
                    action=log.action,
                    detail=log.detail or {},
                    trace_id=log.trace_id,
                    ip_address=log.ip_address,
                    user_agent=log.user_agent,
                    prev_hash=log.prev_hash or "",
                    entry_hash=log.entry_hash or "",
                    created_at=log.created_at,
                )
                for log in logs
            ]

    def count(self, tenant_id: int = 0) -> int:
        from fnixagent.models.db.models import AuditLog

        with self._db.session() as session:
            q = session.query(AuditLog).filter(AuditLog.tenant_id == tenant_id)
            return q.count()

    def clear(self) -> int:
        """清空(仅测试用)。"""
        from fnixagent.models.db.models import AuditLog

        with self._db.session() as session:
            count = session.query(AuditLog).count()
            session.query(AuditLog).delete()
            return count


# ---------------------------------------------------------------------------
# 工厂单例
# ---------------------------------------------------------------------------


_audit_store: Optional[object] = None
_audit_store_lock = threading.Lock()


def get_audit_store():
    """获取审计日志存储(根据 DATABASE_URL 自动选择)。

    Returns:
        InMemoryAuditStore 或 PgAuditStore
    """
    global _audit_store
    if _audit_store is None:
        with _audit_store_lock:
            if _audit_store is None:
                db_url = os.environ.get("DATABASE_URL", "")
                if db_url:
                    try:
                        from fnixagent.services.storage_postgres import get_db_adapter
                        db = get_db_adapter()
                        if db is not None:
                            _audit_store = PgAuditStore(db)
                        else:
                            _audit_store = InMemoryAuditStore()
                    except Exception:
                        _audit_store = InMemoryAuditStore()
                else:
                    _audit_store = InMemoryAuditStore()
    return _audit_store


def reset_audit_store() -> None:
    """重置存储单例(测试用)。"""
    global _audit_store
    with _audit_store_lock:
        _audit_store = None


def clear_audit_store() -> int:
    """清空当前存储的数据(测试用)。"""
    store = get_audit_store()
    return store.clear()
