"""fnix-local sidecar 与 local_bridge 单元测试。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def project_workspace(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "main.py").write_text(
        "def hello():\n    return 'world'\n",
        encoding="utf-8",
    )
    return ws


@pytest.fixture
def sidecar_client():
    from fnixagent.local.sidecar_app import create_app

    return TestClient(create_app())


def test_sidecar_health(sidecar_client):
    res = sidecar_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True
    assert data.get("service") == "fnix-local"


def test_sidecar_index_and_context(sidecar_client, project_workspace):
    res = sidecar_client.post(
        "/v1/index",
        json={"workspace": str(project_workspace), "force": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("ok") is True
    session_id = body.get("session_id")
    assert session_id

    ctx = sidecar_client.get(
        "/v1/context",
        params={"workspace": str(project_workspace), "query": "hello"},
    )
    assert ctx.status_code == 200
    ctx_body = ctx.json()
    assert ctx_body.get("ok") is True
    assert isinstance(ctx_body.get("pdg_digest"), str)
    assert (project_workspace / ".fnix" / "index" / "pdg_summary.json").is_file()


def test_local_bridge_index_store(project_workspace):
    import asyncio

    from fnixagent.local.index_store import get_index_store

    store = get_index_store()
    session = asyncio.run(store.index_workspace(str(project_workspace), force=True))
    assert session.session_id
    ctx = asyncio.run(store.build_context(workspace=str(project_workspace), query="hello"))
    assert ctx.get("ok") is True


def test_local_bridge_offline(monkeypatch):
    from fnixagent.harness.local_bridge import LocalBridge

    bridge = LocalBridge(base_url="http://127.0.0.1:1")
    status = bridge.health()
    assert status.available is False
