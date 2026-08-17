"""Code Agent：edit 解析、降级修复、stub 拒绝（与 Work workspace 工具对齐）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fnixagent.core.code.agent import CodingAgent, TaskStep
from fnixagent.core.code.tools import CodeTools


def test_parse_edit_json_aliases():
    agent = CodingAgent(None, None, None)  # type: ignore[arg-type]
    old, new = agent._parse_edit_payload('{"old": "a + b", "new": "a - b"}')
    assert old == "a + b"
    assert new == "a - b"


def test_parse_edit_markdown_block():
    agent = CodingAgent(None, None, None)  # type: ignore[arg-type]
    payload = '说明\n```json\n{"old_text": "x", "new_text": "y"}\n```'
    old, new = agent._parse_edit_payload(payload)
    assert old == "x"
    assert new == "y"


def test_parse_edit_pipe_separator():
    agent = CodingAgent(None, None, None)  # type: ignore[arg-type]
    old, new = agent._parse_edit_payload("foo|||bar")
    assert old == "foo"
    assert new == "bar"


@pytest.mark.asyncio
async def test_edit_fallback_subtract_bug():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "math_utils.py").write_text(
            "def subtract(a, b):\n    return a + b  # bug\n",
            encoding="utf-8",
        )
        tools = CodeTools(str(root))
        agent = CodingAgent(tools, None, None)  # type: ignore[arg-type]
        step = TaskStep(
            id="s1",
            description="fix subtract bug 改为减法",
            action="edit",
            target="math_utils.py",
        )
        result = await agent._edit_fallback(step)
        assert result.success
        text = (root / "math_utils.py").read_text(encoding="utf-8")
        assert "a - b" in text
        assert "a + b" not in text


@pytest.mark.asyncio
async def test_write_rejects_stub_chinese():
    with tempfile.TemporaryDirectory() as tmp:
        tools = CodeTools(tmp)
        r = await tools.write("calc.py", "创建一个计算器模块，包含 add 和 multiply 函数。")
        assert not r.success
        assert "拒绝" in (r.error or "")


@pytest.mark.asyncio
async def test_write_accepts_real_python():
    with tempfile.TemporaryDirectory() as tmp:
        tools = CodeTools(tmp)
        src = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
        r = await tools.write("calc.py", src)
        assert r.success
        assert Path(tmp, "calc.py").read_text(encoding="utf-8") == src
