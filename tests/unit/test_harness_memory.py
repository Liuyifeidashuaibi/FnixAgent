"""L4: SOUL / memories / skills 注入。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path

import pytest


def test_build_local_context_includes_soul_and_memory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path))
    from fnixagent.harness.memory import build_local_context_prompt
    from fnixagent.harness.paths import memories_dir, skills_dir, soul_path
    from fnixagent.harness.workspace import ensure_home_layout

    ensure_home_layout()
    soul_path().write_text("# Soul\nBe concise.\n", encoding="utf-8")
    (memories_dir() / "MEMORY.md").write_text("User likes markdown.\n", encoding="utf-8")
    (skills_dir() / "demo.md").write_text("# Demo skill\nDo X.\n", encoding="utf-8")

    prompt = build_local_context_prompt(extra="## Extra\nok")
    assert "SOUL.md" in prompt or "Soul" in prompt or "Be concise" in prompt
    assert "Local Memory" in prompt or "User likes markdown" in prompt
    assert "Global Skills" in prompt or "demo" in prompt
    assert "Extra" in prompt


def test_empty_home_still_returns_extra(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "empty-home"))
    from fnixagent.harness.memory import build_local_context_prompt

    # ensure layout may create defaults with SOUL — still must include extra
    text = build_local_context_prompt(extra="PDG_BLOCK")
    assert "PDG_BLOCK" in text
