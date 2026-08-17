"""Workspace / DiffEngine path containment — block sibling-prefix escape."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path

import pytest

from fnixagent.core.code.diff import DiffEngine
from fnixagent.core.tools.workspace import _safe_path


def test_safe_path_allows_inside(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    target = root / "src" / "a.py"
    target.parent.mkdir()
    target.write_text("x = 1\n", encoding="utf-8")
    assert _safe_path(str(root), "src/a.py") == target.resolve()


def test_safe_path_rejects_parent_escape(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    sibling = tmp_path / "proj_evil"
    sibling.mkdir()
    secret = sibling / "secret.txt"
    secret.write_text("leak", encoding="utf-8")
    with pytest.raises(ValueError, match="路径遍历"):
        _safe_path(str(root), "../proj_evil/secret.txt")


def test_safe_path_rejects_prefix_sibling(tmp_path: Path) -> None:
    """startswith bug: /data/proj vs /data/proj2 must not be treated as inside."""
    root = tmp_path / "proj"
    root.mkdir()
    sibling = tmp_path / "proj2"
    sibling.mkdir()
    (sibling / "x.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="路径遍历"):
        _safe_path(str(root), str(sibling / "x.txt"))


def test_diff_engine_resolve_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "code"
    root.mkdir()
    engine = DiffEngine(project_root=str(root))
    with pytest.raises(ValueError, match="escapes project root"):
        engine._resolve("../outside.txt")
