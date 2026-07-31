"""Harness memory CRUD without full app boot."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_write_read_soul_and_memory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path))
    from fnixagent.harness.memory import (
        get_memory_bundle,
        memory_injection_summary,
        read_memory_file,
        read_soul,
        write_memory_file,
        write_soul,
    )

    write_soul("# Soul\nFocus.\n")
    write_memory_file("MEMORY.md", "Prefers tables.\n")
    assert "Focus" in read_soul()
    assert "tables" in read_memory_file("MEMORY.md")

    bundle = get_memory_bundle()
    assert bundle["ok"] is True
    assert "Focus" in bundle["soul"]

    summary = memory_injection_summary()
    assert summary["soul"]["present"] is True
    assert "SOUL.md" in summary["blocks"]
    assert "memories" in summary["blocks"]


def test_reject_path_traversal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path))
    from fnixagent.harness.memory import write_memory_file

    with pytest.raises(ValueError):
        write_memory_file("../evil.md", "x")
