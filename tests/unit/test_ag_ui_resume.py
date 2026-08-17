"""AG-UI checkpoint resume helpers."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path

from fnixagent.core.ag_ui.mapper import map_work_chunk
from fnixagent.core.run import RunCheckpointStore


def test_load_events_after_sequence(tmp_path: Path) -> None:
    store = RunCheckpointStore(db_path=tmp_path / "runs.sqlite3")
    store.start_run("r1", channel="work", session_id="s1")
    store.append_event("r1", 1, "thinking", {"type": "thinking", "data": "a"})
    store.append_event("r1", 2, "text", {"type": "text", "data": "b"})
    store.append_event("r1", 3, "done", {"type": "done", "data": {"ok": True}})
    store.finish_run("r1", "completed")

    all_ev = store.load_events("r1", after_sequence=0)
    assert len(all_ev) == 3
    tail = store.load_events("r1", after_sequence=1)
    assert len(tail) == 2
    assert tail[0]["type"] == "text"

    meta = store.get_run("r1")
    assert meta is not None
    assert meta["status"] == "completed"


def test_map_resume_chunk_keeps_custom() -> None:
    ev = map_work_chunk("file_change", {"path": "a.py"}, "runx")
    assert ev["type"] == "CUSTOM"
    assert ev["name"] == "file_change"
