"""Unified RunEngine + SQLite checkpoint."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
from pathlib import Path

from fnixagent.core.run import RunCheckpointStore, RunEngine
from fnixagent.core.run.engine import RunEvent


async def _fake_work_source():
    yield {"type": "thinking", "data": "planning"}
    yield {"type": "tool_call", "data": {"name": "write_file"}}
    yield {"type": "text", "data": "done body"}
    yield {"type": "done", "data": {"result": "ok"}}


def test_run_engine_envelope_and_checkpoint(tmp_path: Path) -> None:
    store = RunCheckpointStore(db_path=tmp_path / "runs.sqlite3")
    engine = RunEngine(store=store)

    async def _collect():
        out = []
        async for ev in engine.run_stream(
            _fake_work_source(),
            channel="work",
            run_id="run-test",
        ):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    assert len(events) == 4
    assert events[0].schema_version == 1
    assert events[0].run_id == "run-test"
    assert events[0].sequence == 1
    assert events[-1].type == "done"
    assert all(e.timestamp > 0 for e in events)

    loaded = store.load_events("run-test")
    assert len(loaded) == 4
    assert loaded[0]["type"] == "thinking"
    cp = store.load_checkpoint("run-test")
    assert cp is not None
    assert cp["last_type"] == "done"


def test_code_ndjson_mapping() -> None:
    ev = RunEvent(type="thinking", data="hi", run_id="r1", sequence=1, timestamp=1)
    assert ev.to_code_ndjson()["content"] == "hi"
    done = RunEvent(
        type="done",
        data={"status": "completed"},
        run_id="r1",
        sequence=2,
        timestamp=2,
    )
    assert done.to_code_ndjson()["status"] == "completed"
