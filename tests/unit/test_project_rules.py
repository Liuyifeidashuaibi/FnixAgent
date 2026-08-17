"""项目规则 AGENTS.md / .fnix/rules.md 加载与注入。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path

from fnixagent.harness.local_context import local_context_prompt
from fnixagent.harness.project_rules import format_project_rules_block, load_project_rules
from fnixagent.harness.workspace import ensure_project_layout


def test_load_fnix_rules_and_agents_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "home"))
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_project_layout(str(ws))

    marker = "FNIX_RULES_MARKER_7f3a"
    (ws / ".fnix" / "rules.md").write_text(f"# rules\n{marker}\n", encoding="utf-8")
    (ws / "AGENTS.md").write_text("# agents\nUse pytest for tests.\n", encoding="utf-8")

    loaded = load_project_rules(str(ws))
    assert loaded["ok"] is True
    assert marker in loaded["text"]
    assert "Use pytest for tests." in loaded["text"]
    assert any(str(p).endswith("rules.md") for p in loaded["sources"])
    assert any(str(p).endswith("AGENTS.md") for p in loaded["sources"])

    block = format_project_rules_block(str(ws))
    assert "Project Rules" in block
    assert marker in block


def test_nested_agents_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "home"))
    ws = tmp_path / "proj"
    pkg = ws / "pkg"
    pkg.mkdir(parents=True)
    ensure_project_layout(str(ws))
    (ws / "AGENTS.md").write_text("ROOT_RULE\n", encoding="utf-8")
    (pkg / "AGENTS.override.md").write_text("PKG_OVERRIDE\n", encoding="utf-8")
    (pkg / "AGENTS.md").write_text("PKG_RULE\n", encoding="utf-8")

    loaded = load_project_rules(str(ws), cwd=str(pkg))
    text = loaded["text"]
    assert "ROOT_RULE" in text
    assert "PKG_OVERRIDE" in text
    assert "PKG_RULE" in text
    # override 同层应出现在 AGENTS.md 之前
    assert text.index("PKG_OVERRIDE") < text.index("PKG_RULE")


def test_local_context_prompt_includes_rules(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "home"))
    # 指向不可达地址，避免误连本机 sidecar
    monkeypatch.setenv("FNIX_LOCAL_URL", "http://127.0.0.1:1")
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_project_layout(str(ws))
    token = "UNIQUE_INJECT_TOKEN_9c2e"
    (ws / "AGENTS.md").write_text(f"Must follow: {token}\n", encoding="utf-8")

    prompt = local_context_prompt(str(ws), query="hello")
    assert token in prompt
    assert "Project Rules" in prompt


def test_attach_mcp_empty_config_is_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "home"))
    from fnixagent.core.tools.registry import ToolRegistry
    from fnixagent.harness.config import attach_mcp_tools_to_registry, write_mcp_config
    from fnixagent.harness.workspace import ensure_home_layout

    ensure_home_layout()
    write_mcp_config({"version": 1, "servers": []})
    reg = ToolRegistry()
    names = attach_mcp_tools_to_registry(reg, connect=False)
    assert names == []
    assert len(getattr(reg, "_tools", {})) == 0
