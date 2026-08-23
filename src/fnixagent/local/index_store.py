"""Workspace 索引会话 — 内存 CodeIndexer + 落盘 pdg_summary.json。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fnixagent.core.code.indexer import CodeIndexer
from fnixagent.harness.paths import project_index_dir


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class IndexSession:
    session_id: str
    workspace: str
    indexer: CodeIndexer
    stats: dict[str, Any] = field(default_factory=dict)
    indexed_at: str = field(default_factory=_utc_now)


class IndexStore:
    """按 workspace / session_id 管理索引。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_session: dict[str, IndexSession] = {}
        self._by_workspace: dict[str, str] = {}

    def _norm(self, workspace: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(workspace)))

    async def index_workspace(
        self,
        workspace: str,
        *,
        force: bool = False,
        session_id: str | None = None,
    ) -> IndexSession:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"workspace 不是目录: {workspace}")

        norm = self._norm(str(root))
        sid = session_id or uuid.uuid4().hex[:16]

        with self._lock:
            if not force and norm in self._by_workspace:
                existing_id = self._by_workspace[norm]
                existing = self._by_session.get(existing_id)
                if existing is not None:
                    return existing

        indexer = CodeIndexer()
        stats_obj = await indexer.index_directory(str(root), incremental=not force)
        stats = {
            "total_files": stats_obj.total_files,
            "indexed_files": stats_obj.indexed_files,
            "skipped_files": stats_obj.skipped_files,
            "total_symbols": stats_obj.total_symbols,
            "total_slices": stats_obj.total_slices,
            "duration_sec": round(stats_obj.duration_sec, 3),
            "errors": stats_obj.errors[:20],
        }

        session = IndexSession(
            session_id=sid,
            workspace=str(root),
            indexer=indexer,
            stats=stats,
        )

        self._persist_summary(session)

        with self._lock:
            self._by_session[sid] = session
            self._by_workspace[norm] = sid

        return session

    def _persist_summary(self, session: IndexSession) -> None:
        """写入 {workspace}/.fnix/index/pdg_summary.json（Rust sidecar 兼容）。"""
        idx_dir = project_index_dir(session.workspace)
        idx_dir.mkdir(parents=True, exist_ok=True)

        repo_map = session.indexer.get_repo_map(max_tokens=6000)
        symbols: list[dict[str, Any]] = []
        for name, infos in list(session.indexer._symbols.items())[:200]:
            for info in infos[:3]:
                symbols.append(
                    {
                        "name": name,
                        "kind": info.kind.value,
                        "file": info.location.file,
                        "line": info.location.start_line,
                        "signature": info.signature[:200],
                    }
                )

        payload = {
            "session_id": session.session_id,
            "workspace": session.workspace,
            "indexed_at": session.indexed_at,
            "stats": session.stats,
            "pdg_digest": repo_map[:12000],
            "symbols": symbols[:150],
        }
        path = idx_dir / "pdg_summary.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def get_session(
        self,
        *,
        session_id: str | None = None,
        workspace: str | None = None,
    ) -> IndexSession | None:
        with self._lock:
            if session_id:
                return self._by_session.get(session_id)
            if workspace:
                sid = self._by_workspace.get(self._norm(workspace))
                if sid:
                    return self._by_session.get(sid)
        return None

    async def build_context(
        self,
        *,
        session_id: str | None = None,
        workspace: str | None = None,
        query: str | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        session = self.get_session(session_id=session_id, workspace=workspace)
        if session is None and workspace:
            session = await self.index_workspace(workspace, force=False)

        if session is None:
            return {
                "ok": False,
                "session_id": "",
                "symbols": [],
                "pdg_digest": "",
                "vector_hits": [],
                "message": "no index session",
            }

        pdg_digest = session.indexer.get_repo_map(max_tokens=4096)
        symbols: list[dict[str, Any]] = []
        for name, infos in list(session.indexer._symbols.items())[:80]:
            for info in infos[:2]:
                symbols.append(
                    {
                        "name": name,
                        "kind": info.kind.value,
                        "file": info.location.file,
                        "line": info.location.start_line,
                    }
                )

        vector_hits: list[dict[str, Any]] = []
        if query:
            slices = await session.indexer.search_code(query, top_k=top_k)
            for sl in slices:
                vector_hits.append(
                    {
                        "file": sl.file,
                        "symbol": sl.symbol_name,
                        "kind": sl.kind.value,
                        "lines": f"{sl.start_line}-{sl.end_line}",
                        "preview": sl.content[:400],
                    }
                )

        return {
            "ok": True,
            "session_id": session.session_id,
            "workspace": session.workspace,
            "stats": session.stats,
            "symbols": symbols,
            "pdg_digest": pdg_digest,
            "vector_hits": vector_hits,
        }


_store: IndexStore | None = None
_store_lock = threading.Lock()


def get_index_store() -> IndexStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = IndexStore()
    return _store
