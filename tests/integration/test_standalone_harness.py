"""Standalone Harness 集成测试 — session 持久化 + API 路由。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fnixagent.harness.session import SessionStore
from fnixagent.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_sessions(tmp_path, monkeypatch):
    """隔离 session 目录，避免污染 ~/.fnix。"""
    store = SessionStore(base_dir=str(tmp_path / "sessions"))
    monkeypatch.setattr(
        "fnixagent.harness.session.get_session_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "fnixagent.api.routers.work.get_session_store",
        lambda: store,
        raising=False,
    )
    return store


def test_work_sessions_list_and_get(client, isolated_sessions, tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()

    created = isolated_sessions.create(
        user_id="e2e-user",
        workspace=str(ws),
        title="E2E Work 任务",
        description="集成测试 session",
        mode="work",
    )
    isolated_sessions.update(created.id, status="completed", result="done", artifacts=[])

    code = isolated_sessions.create(
        user_id="e2e-user",
        workspace=str(ws),
        title="E2E Code 会话",
        description="code mode",
        mode="code",
    )
    isolated_sessions.save(code)

    list_res = client.get("/api/v1/work/sessions", params={"limit": 10})
    assert list_res.status_code == 200
    body = list_res.json()
    assert body["ok"] is True
    ids = {s["id"] for s in body["sessions"]}
    assert created.id in ids
    assert code.id in ids

    work_only = client.get("/api/v1/work/sessions", params={"mode": "work"})
    work_ids = {s["id"] for s in work_only.json()["sessions"]}
    assert created.id in work_ids
    assert code.id not in work_ids

    one = client.get(f"/api/v1/work/sessions/{created.id}")
    assert one.status_code == 200
    assert one.json()["session"]["title"] == "E2E Work 任务"

    missing = client.get("/api/v1/work/sessions/not-exists")
    assert missing.status_code == 404


def test_harness_status_includes_sidecar_field(client):
    res = client.get("/api/v1/harness/status")
    assert res.status_code == 200
    data = res.json()
    assert "sidecar" in data
    assert "profile" in data


def test_session_survives_store_reload(isolated_sessions, tmp_path):
    """模拟重启：新 SessionStore 实例仍能读到磁盘 session。"""
    ws = tmp_path / "proj"
    ws.mkdir()
    created = isolated_sessions.create(
        user_id="reload-user",
        workspace=str(ws),
        title="重启后应仍在",
        description="persistence",
        mode="work",
    )
    isolated_sessions.update(created.id, status="completed", result="ok")

    reloaded = SessionStore(base_dir=str(tmp_path / "sessions"))
    got = reloaded.get(created.id)
    assert got is not None
    assert got.status == "completed"
    assert got.title == "重启后应仍在"


def test_work_and_code_mission_kinds():
    """Work / Code 任务各映射到受控 workspace_kind。"""
    from fnixagent.services.work_pipeline import build_mission_schema

    work = build_mission_schema("生成本周办公周报 Word")
    code = build_mission_schema("修复接口代码中的 bug")
    assert work["workspace_kind"] == "document"
    assert code["workspace_kind"] == "code"


def test_work_status_kernel_flags(client):
    res = client.get("/api/v1/work/status")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "ktg" in data
    assert "mfp" in data
