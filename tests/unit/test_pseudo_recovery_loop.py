"""Pseudo XML recovery must write files and stop (no 45-step spin)."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
from pathlib import Path

from fnixagent.core.agent.loop import AgenticLoop
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.tools.workspace import register_workspace_tools


def test_pseudo_xml_recovery_writes_and_stops(tmp_path: Path) -> None:
    xml = """
<write_file>
<path>.fnix/artifacts/demo/index.html</path>
<content><!DOCTYPE html><html><body><h1>Hi</h1></body></html></content>
</write_file>
<write_file>
<path>.fnix/artifacts/demo/style.css</path>
<content>body{margin:0;font-family:sans-serif}</content>
</write_file>
<write_file>
<path>.fnix/artifacts/demo/script.js</path>
<content>document.body.onclick=()=>alert(1)</content>
</write_file>
"""

    async def fake_llm(messages, tools=None):
        return {"choices": [{"message": {"role": "assistant", "content": xml}}]}

    reg = ToolRegistry()
    register_workspace_tools(reg, str(tmp_path), craft_artifacts=True)
    loop = AgenticLoop(
        llm_call=fake_llm,
        tool_executor=reg,
        workspace_root=str(tmp_path),
        max_steps=8,
        force_tool_delivery=True,
    )

    async def run() -> list[str]:
        types: list[str] = []
        async for event in loop.run_stream("make site"):
            types.append(str(event.get("type")))
        return types

    types = asyncio.run(run())
    files = [
        str(p.relative_to(tmp_path)).replace("\\", "/")
        for p in (tmp_path / ".fnix" / "artifacts").rglob("*")
        if p.is_file()
    ]
    assert any(f.endswith("index.html") for f in files)
    assert any(f.endswith(".css") for f in files)
    assert any(f.endswith(".js") for f in files)
    assert "done" in types
    assert "error" not in types
    # 单轮恢复：step_start/end + thinking + 3×(action+tool_call+observation+tool_result)
    # + text + done ≈ 19。断言意图是「一轮内收敛，不进入重试循环」——
    # 若发生第二轮恢复会 ≥27 个事件，故上限取 24。
    assert len(types) < 24
