"""SQLite WAL checkpoint / event log for unified runs."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import fnix_home


class RunCheckpointStore:
    """Persist run envelopes for Stop / Resume / diagnostics.

    Schema is intentionally small: one runs row + append-only events.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        home = fnix_home()
        home.mkdir(parents=True, exist_ok=True)
        self._path = Path(db_path) if db_path else home / "runs.sqlite3"
        self._lock = threading.Lock()
        # P1: 复用单连接, 避免每次操作新开 sqlite3 连接的开销
        # check_same_thread=False + 外部 threading.Lock 保证线程安全
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        # 兼容旧调用, 返回复用的连接 (调用方不再负责 close)
        return self._conn

    def _ensure(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                  run_id TEXT PRIMARY KEY,
                  channel TEXT NOT NULL,
                  session_id TEXT,
                  status TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  meta_json TEXT
                );
                CREATE TABLE IF NOT EXISTS run_events (
                  run_id TEXT NOT NULL,
                  sequence INTEGER NOT NULL,
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS run_checkpoints (
                  run_id TEXT PRIMARY KEY,
                  sequence INTEGER NOT NULL,
                  state_json TEXT NOT NULL,
                  updated_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()

    def start_run(
        self,
        run_id: str,
        *,
        channel: str,
        session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO runs
                  (run_id, channel, session_id, status, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, 'running', ?, ?, ?)
                """,
                (
                    run_id,
                    channel,
                    session_id or "",
                    now,
                    now,
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def append_event(
        self,
        run_id: str,
        sequence: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO run_events
                  (run_id, sequence, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    event_type,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                ),
            )
            self._conn.execute(
                "UPDATE runs SET updated_at=?, status=? WHERE run_id=?",
                (
                    now,
                    "failed" if event_type == "error" else "running",
                    run_id,
                ),
            )
            self._conn.commit()

    def save_checkpoint(self, run_id: str, sequence: int, state: dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO run_checkpoints
                  (run_id, sequence, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, sequence, json.dumps(state, ensure_ascii=False), now),
            )
            self._conn.commit()

    def finish_run(self, run_id: str, status: str = "completed") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET updated_at=?, status=? WHERE run_id=?",
                (time.time(), status, run_id),
            )
            self._conn.commit()

    def load_events(
        self,
        run_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT sequence, event_type, payload_json FROM run_events
                WHERE run_id=? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (run_id, int(after_sequence)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for seq, et, payload in rows:
            data = json.loads(payload)
            data.setdefault("sequence", seq)
            data.setdefault("type", et)
            out.append(data)
        return out

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT run_id, channel, session_id, status, created_at, updated_at, meta_json
                FROM runs WHERE run_id=?
                """,
                (run_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "channel": row[1],
            "session_id": row[2],
            "status": row[3],
            "created_at": row[4],
            "updated_at": row[5],
            "meta": json.loads(row[6] or "{}"),
        }

    def load_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT sequence, state_json FROM run_checkpoints WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if not row:
            return None
        state = json.loads(row[1])
        state["sequence"] = row[0]
        return state
