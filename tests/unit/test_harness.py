"""Harness workspace / session 单元测试。"""

from __future__ import annotations

import pytest


@pytest.fixture
def harness_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "fnix"))
    monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")
    return tmp_path / "fnix"


@pytest.fixture
def project_workspace(tmp_path):
    ws = tmp_path / "project"
    ws.mkdir()
    return ws


def test_ensure_home_layout(harness_home):
    from fnixagent.harness.workspace import ensure_home_layout, read_home_config

    home = ensure_home_layout()
    assert home.is_dir()
    assert (home / "sessions").is_dir()
    assert (home / "config.toml").is_file()
    cfg = read_home_config()
    assert isinstance(cfg, dict)


def test_ensure_project_layout(harness_home, project_workspace):
    from fnixagent.harness.paths import project_artifacts_dir, project_skills_dir
    from fnixagent.harness.workspace import ensure_project_layout

    layout = ensure_project_layout(project_workspace)
    assert layout["workspace"] == str(project_workspace.resolve())
    assert project_skills_dir(project_workspace).is_dir()
    assert project_artifacts_dir(project_workspace).is_dir()
    assert (project_workspace / ".fnix" / "rules.md").is_file()


def test_session_store_crud(harness_home, project_workspace):
    from fnixagent.harness.session import get_session_store

    store = get_session_store()
    session = store.create(
        session_id="sess-test-1",
        user_id="u1",
        workspace=str(project_workspace),
        title="测试任务",
        description="写一份周报",
    )
    assert session.id == "sess-test-1"
    assert session.status == "running"

    loaded = store.get("sess-test-1")
    assert loaded is not None
    assert loaded.title == "测试任务"

    store.update("sess-test-1", status="completed", result="完成")
    updated = store.get("sess-test-1")
    assert updated is not None
    assert updated.status == "completed"
    assert updated.result == "完成"

    listed = store.list_sessions(workspace=str(project_workspace))
    assert any(s.id == "sess-test-1" for s in listed)


def test_skills_loader(harness_home, project_workspace):
    from fnixagent.harness.skills_loader import format_skills_block, load_workspace_skills
    from fnixagent.harness.workspace import ensure_project_layout

    ensure_project_layout(project_workspace)
    skill = project_workspace / ".fnix" / "skills" / "weekly-report.md"
    skill.write_text("# 周报\n\n生成周报 docx 到 artifacts。", encoding="utf-8")

    skills = load_workspace_skills(str(project_workspace), use_cache=False)
    assert len(skills) >= 1
    block = format_skills_block(skills)
    assert "weekly-report" in block or "周报" in block


def test_local_bridge_degraded():
    from fnixagent.harness.local_bridge import LocalBridge

    bridge = LocalBridge(base_url="http://127.0.0.1:1")
    status = bridge.health()
    assert status.available is False
    assert "离线" in status.message or "unreachable" in status.message.lower()
