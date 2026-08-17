"""L2 engine status + fnix-local degradation."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fnixagent.harness.local_bridge import LocalBridge, LocalBridgeStatus
from fnixagent.services.engine_status import collect_engine_status, merge_work_status


def test_collect_engine_status_api_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_API_ONLY", "1")

    class FakeBridge:
        enabled = True

        def health(self) -> LocalBridgeStatus:
            return LocalBridgeStatus(
                available=False,
                url="http://127.0.0.1:8710",
                version="",
                message="fnix-local 离线: test",
            )

    monkeypatch.setattr(
        "fnixagent.harness.local_bridge.get_local_bridge",
        lambda: FakeBridge(),
    )
    snap = collect_engine_status(None)
    assert snap["ok"] is True
    assert snap["api_only"] is True
    assert snap["degraded"] is True
    assert snap["degradation"]["fnix_local_offline"] is True
    assert snap["degradation"]["fallback"] == "python-workspace-tools"


def test_merge_work_status_with_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_API_ONLY", "1")

    class FakeTopo:
        def stats(self) -> dict:
            return {"nodes": 3, "edges": 2}

    class FakeBridge:
        def health(self) -> LocalBridgeStatus:
            return LocalBridgeStatus(
                available=True,
                url="http://127.0.0.1:8710",
                version="0.2.0-python",
                message="ok",
            )

    monkeypatch.setattr(
        "fnixagent.harness.local_bridge.get_local_bridge",
        lambda: FakeBridge(),
    )
    state = SimpleNamespace(
        graph_components=SimpleNamespace(topology_graph=FakeTopo()),
        memory_manager=object(),
        security_engine=object(),
        reasoning_selector=object(),
        mode="evolution",
    )
    status = merge_work_status(state, is_admin=False)
    assert status["ktg"] is True
    assert status["stp"] is True
    assert status["mfp"] is True
    assert status["memory"] is True
    assert status["degraded"] is False
    assert status["topology"]["nodes"] == 3
    assert "engine" in status


def test_local_bridge_offline_index_degrades() -> None:
    bridge = LocalBridge(base_url="http://127.0.0.1:1")
    # force offline without waiting long: stub health
    bridge._available = False
    result = bridge.index_workspace("/tmp/ws")
    assert result["ok"] is False
    assert "offline" in (result.get("message") or "").lower() or result.get("session_id") == ""


def test_format_local_context_empty_when_not_ok() -> None:
    from fnixagent.harness.local_bridge import format_local_context_block

    assert format_local_context_block({"ok": False}) == ""
