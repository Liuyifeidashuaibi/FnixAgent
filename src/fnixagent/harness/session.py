"""Work 任务 session 持久化 — ~/.fnix/sessions/{id}.json。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import sessions_dir
from fnixagent.harness.workspace import ensure_home_layout


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class WorkSession:
    """单次 Work 任务会话。"""

    id: str
    user_id: str
    workspace: str
    title: str
    description: str
    status: str = "pending"  # pending | running | completed | failed | cancelled
    trace_id: str = ""
    result: str = ""
    artifacts: list[dict[str, str]] = field(default_factory=list)
    mission: dict[str, Any] = field(default_factory=dict)
    mode: str = "work"
    # ── 多任务并行可视化扩展（P0）──
    progress: int = 0  # 0-100
    steps: list[dict[str, Any]] = field(default_factory=list)  # [{key, label, status, ts}]
    priority: int = 10
    error: str = ""
    parent_run_id: str = ""
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkSession:
        return cls(
            id=str(data["id"]),
            user_id=str(data.get("user_id") or "desktop"),
            workspace=str(data.get("workspace") or ""),
            title=str(data.get("title") or "新任务"),
            description=str(data.get("description") or ""),
            status=str(data.get("status") or "pending"),
            trace_id=str(data.get("trace_id") or ""),
            result=str(data.get("result") or ""),
            artifacts=list(data.get("artifacts") or []),
            mission=dict(data.get("mission") or {}),
            mode=str(data.get("mode") or "work"),
            progress=int(data.get("progress") or 0),
            steps=list(data.get("steps") or []),
            priority=int(data.get("priority") or 10),
            error=str(data.get("error") or ""),
            parent_run_id=str(data.get("parent_run_id") or ""),
            created_at=str(data.get("created_at") or _utc_now()),
            updated_at=str(data.get("updated_at") or _utc_now()),
        )


class SessionStore:
    """JSON 文件 session 存储。"""

    def __init__(self, base_dir: str | None = None) -> None:
        ensure_home_layout()
        self._dir = Path(base_dir) if base_dir else sessions_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_")
        return self._dir / f"{safe}.json"

    def create(
        self,
        *,
        user_id: str,
        workspace: str,
        title: str,
        description: str,
        session_id: str | None = None,
        mode: str = "work",
    ) -> WorkSession:
        sid = session_id or uuid.uuid4().hex[:16]
        session = WorkSession(
            id=sid,
            user_id=user_id,
            workspace=workspace,
            title=title[:120] or "新任务",
            description=description[:2000],
            status="running",
            mode=mode,
        )
        self.save(session)
        return session

    def save(self, session: WorkSession) -> None:
        session.updated_at = _utc_now()
        path = self._path(session.id)
        tmp = str(path) + ".tmp"
        with self._lock:
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
                self._atomic_replace(tmp, str(path))
            except Exception as exc:
                # session 持久化失败不阻断任务主流程：
                # Windows Defender / 沙箱实时扫描新建 .tmp 时 os.replace 偶发
                # WinError 5/32，重试与兜底后仍失败时降级为日志，任务继续执行
                # （任务正确性由 workspace 产物承载，session 仅作记录/展示）。
                try:
                    print(f"[session] save degraded (ignored): {exc}", flush=True)
                except Exception:
                    pass


    @staticmethod
    def _atomic_replace(tmp: str, path: str, attempts: int = 10) -> None:
        """Windows 鲁棒原子写入。

        os.replace 在防病毒(Defender)实时扫描新建 .tmp 或并发读者持有目标文件时,
        会偶发 WinError 5 / 32(拒绝访问 / 文件正在使用)。这里做指数退避重试;
        仍失败则回退为「直接写目标文件 + 删除 tmp」,放弃原子性但保证会话不丢。
        """
        last_exc: Exception | None = None
        for i in range(attempts):
            try:
                os.replace(tmp, path)
                return
            except (OSError, PermissionError) as exc:  # WinError 5 / 32 等
                last_exc = exc
                if i < attempts - 1:
                    time.sleep(0.08 * (i + 1))
        # 兜底:直接把 tmp 内容写到目标,再删 tmp(无原子性,但绝不丢会话)
        try:
            with open(path, "w", encoding="utf-8") as dst:
                with open(tmp, "r", encoding="utf-8") as src:
                    dst.write(src.read())
            try:
                os.remove(tmp)
            except OSError:
                pass
        except Exception:
            if last_exc:
                raise last_exc

    def get(self, session_id: str) -> WorkSession | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return WorkSession.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
        return None

    def update(
        self,
        session_id: str,
        *,
        status: str | None = None,
        trace_id: str | None = None,
        result: str | None = None,
        artifacts: list[dict[str, str]] | None = None,
        mission: dict[str, Any] | None = None,
        progress: int | None = None,
        steps: list[dict[str, Any]] | None = None,
        priority: int | None = None,
        error: str | None = None,
        parent_run_id: str | None = None,
    ) -> WorkSession | None:
        session = self.get(session_id)
        if session is None:
            return None
        if status is not None:
            session.status = status
        if trace_id is not None:
            session.trace_id = trace_id
        if result is not None:
            session.result = result
        if artifacts is not None:
            session.artifacts = artifacts
        if mission is not None:
            session.mission = mission
        if progress is not None:
            session.progress = max(0, min(100, int(progress)))
        if steps is not None:
            session.steps = steps
        if priority is not None:
            session.priority = int(priority)
        if error is not None:
            session.error = error
        if parent_run_id is not None:
            session.parent_run_id = parent_run_id
        self.save(session)
        return session

    def list_sessions(
        self,
        *,
        user_id: str | None = None,
        workspace: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WorkSession]:
        rows: list[WorkSession] = []
        base = Path(self._dir)
        if not base.is_dir():
            return []

        files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                session = WorkSession.from_dict(data)
            except (OSError, json.JSONDecodeError):
                continue

            if user_id and session.user_id != user_id:
                continue
            if workspace:
                try:
                    norm_ws = os.path.normcase(os.path.normpath(session.workspace))
                    norm_req = os.path.normcase(os.path.normpath(workspace))
                    if norm_ws != norm_req:
                        continue
                except Exception:
                    if session.workspace != workspace:
                        continue
            if status and session.status != status:
                continue

            rows.append(session)
            if len(rows) >= limit:
                break

        return rows

    def compact_old_sessions(self, *, max_keep: int = 200) -> int:
        """Delete oldest session JSON files beyond max_keep. Returns deleted count."""
        base = Path(self._dir)
        if not base.is_dir():
            return 0
        files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for path in files[max_keep:]:
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
        return removed


_store: SessionStore | None = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SessionStore()
    return _store
