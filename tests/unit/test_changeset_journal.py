"""Accept 变更集落盘与回滚。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
from pathlib import Path

from fnixagent.harness.changeset_journal import (
    latest_changeset_id,
    rollback_persisted_async,
    save_changeset,
)
from fnixagent.harness.workspace import ensure_project_layout


def test_save_and_rollback_modify(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "home"))
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_project_layout(str(ws))
    target = ws / "hello.txt"
    target.write_text("NEW", encoding="utf-8")

    save_changeset(
        str(ws),
        "cs-test-1",
        [
            {
                "path": "hello.txt",
                "action": "modify",
                "content": "NEW",
                "old_content": "OLD",
            }
        ],
    )
    assert latest_changeset_id(str(ws)) == "cs-test-1"

    result = asyncio.run(rollback_persisted_async(str(ws), "cs-test-1"))
    assert result["ok"] is True, result
    assert target.read_text(encoding="utf-8") == "OLD"
    assert latest_changeset_id(str(ws)) is None
