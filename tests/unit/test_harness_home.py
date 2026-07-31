"""~/.fnix home layout + memory（Hermes 对标）。"""

from __future__ import annotations

import pytest


@pytest.fixture
def harness_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "fnix"))
    return tmp_path / "fnix"


def test_ensure_home_layout_creates_hermes_style_tree(harness_home):
    from fnixagent.harness.paths import memories_dir, skills_dir, soul_path
    from fnixagent.harness.workspace import ensure_home_layout

    home = ensure_home_layout()
    assert home == harness_home
    assert (home / "config.toml").is_file()
    assert soul_path().is_file()
    assert (memories_dir() / "MEMORY.md").is_file()
    assert (memories_dir() / "USER.md").is_file()
    assert (skills_dir() / "README.md").is_file()
    assert (home / "mcp.json").is_file()
    assert (home / "sessions").is_dir()


def test_memory_prompt_includes_soul(harness_home):
    from fnixagent.harness.memory import build_local_context_prompt
    from fnixagent.harness.workspace import ensure_home_layout

    ensure_home_layout()
    text = build_local_context_prompt()
    assert "SOUL" in text or "Fnix" in text
