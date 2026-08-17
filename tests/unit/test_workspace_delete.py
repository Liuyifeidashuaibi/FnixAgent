"""workspace delete_file + 危险命令拦截。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path

from fnixagent.core.tools.workspace import WorkspaceTools, _is_dangerous_command


def test_delete_file_inside_workspace(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    tools = WorkspaceTools(str(tmp_path))
    result = tools.delete_file("a.txt")
    assert result.success is True
    assert not f.exists()


def test_delete_file_rejects_outside(tmp_path: Path) -> None:
    tools = WorkspaceTools(str(tmp_path))
    result = tools.delete_file("../outside.txt")
    assert result.success is False


def test_delete_file_rejects_directory(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    tools = WorkspaceTools(str(tmp_path))
    result = tools.delete_file("sub")
    assert result.success is False
    assert "目录" in (result.error or "")


def test_dangerous_commands_blocked() -> None:
    assert _is_dangerous_command("rm -rf /")
    assert _is_dangerous_command("sudo rm -rf /tmp/x")
    assert not _is_dangerous_command("pytest -q")
