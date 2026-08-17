"""全流程闭环：新建项目 → AI 写码 → 编译 → 报错修复。

使用脚本化 LLM（无需付费 Key），驱动 CodingAgent heal 闭环。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fnixagent.core.code.agent import CodingAgent, TaskStatus
from fnixagent.core.code.context import ContextBuilder
from fnixagent.core.code.tools import CodeTools
from fnixagent.harness.workspace import ensure_project_layout

BROKEN_APP = "def add(a, b):\n    return a - b  # intentional bug\n"
FIXED_APP = "def add(a, b):\n    return a + b\n"
TEST_APP = "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"


class ScriptedCodeLLM:
    """按调用次序返回 plan → heal → review（无需模糊匹配）。"""

    def __init__(self) -> None:
        self.calls = 0
        self.phases: list[str] = []

    async def complete(self, payload: dict) -> str:
        self.calls += 1
        # 1: 初始规划  2: heal 规划  3+: LLM review
        if self.calls == 1:
            self.phases.append("plan")
            return json.dumps(
                {
                    "steps": [
                        {"description": BROKEN_APP, "action": "write", "target": "app.py"},
                        {"description": TEST_APP, "action": "write", "target": "test_app.py"},
                        {"description": "compile", "action": "compile", "target": "app.py"},
                        {"description": "test", "action": "test", "target": ""},
                    ]
                },
                ensure_ascii=False,
            )
        if self.calls == 2:
            self.phases.append("heal")
            return json.dumps(
                {
                    "steps": [
                        {
                            "description": json.dumps(
                                {
                                    "old_text": "return a - b  # intentional bug",
                                    "new_text": "return a + b",
                                },
                                ensure_ascii=False,
                            ),
                            "action": "edit",
                            "target": "app.py",
                        },
                        {"description": "compile", "action": "compile", "target": "app.py"},
                        {"description": "test", "action": "test", "target": ""},
                    ]
                },
                ensure_ascii=False,
            )
        self.phases.append("review")
        return json.dumps({"passed": True, "notes": "scripted review ok"}, ensure_ascii=False)


class StubIndexer:
    async def index_directory(self, *_a, **_k):
        return None

    async def search_code(self, *_a, **_k):
        return []


@pytest.mark.asyncio
async def test_new_project_ai_write_compile_heal_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FNIX_CODE_HEAL_ROUNDS", "2")
    project = tmp_path / "demo_proj"
    project.mkdir()
    ensure_project_layout(str(project))

    tools = CodeTools(str(project))
    # 避免索引拖慢 / 依赖
    ctx = ContextBuilder(indexer=StubIndexer(), project_root=str(project))  # type: ignore[arg-type]
    llm = ScriptedCodeLLM()
    agent = CodingAgent(tools, ctx, llm)

    events: list[str] = []

    def on_event(ev) -> None:
        if getattr(ev, "type", None) == "status":
            events.append(str(getattr(ev, "status", "")))

    result = await agent.execute_task(
        "实现 add(a,b) 并写 pytest，确保 1+2==3",
        on_event=on_event,
    )

    assert (project / "app.py").is_file()
    assert (project / "test_app.py").is_file()
    assert "return a + b" in (project / "app.py").read_text(encoding="utf-8")
    assert result.status == TaskStatus.COMPLETED, result.error or result.review_notes
    assert result.review_passed is True
    assert "heal" in llm.phases or any("healing" in e for e in events)
    assert "plan" in llm.phases


@pytest.mark.asyncio
async def test_tools_compile_and_fix_direct(tmp_path: Path) -> None:
    """无 Agent：写坏 → 编译失败 → 修好 → 编译+测试通过。"""
    project = tmp_path / "direct"
    project.mkdir()
    tools = CodeTools(str(project))

    bad = "def add(a, b)\n    return a + b\n"  # syntax error
    await tools.write("app.py", bad)
    compile_bad = await tools.compile_check("app.py")
    assert compile_bad.success is False

    await tools.write("app.py", FIXED_APP)
    await tools.write("test_app.py", TEST_APP)
    compile_ok = await tools.compile_check("app.py")
    assert compile_ok.success is True
    test_ok = await tools.test(["-x", "--tb=short", "test_app.py"])
    assert test_ok.success is True, test_ok.error
