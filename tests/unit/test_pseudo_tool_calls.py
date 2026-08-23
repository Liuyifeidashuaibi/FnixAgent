"""Recover fake XML tool calls that some models emit instead of tools API."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.agent.loop import extract_pseudo_tool_calls, strip_pseudo_tool_markup


def test_extract_write_file_xml() -> None:
    text = """
我将创建网站。
<write_file>
<path>.fnix/artifacts/demo/index.html</path>
<content><!DOCTYPE html>
<html><body>hi</body></html></content>
</write_file>
<write_file>
<file_path>.fnix/artifacts/demo/style.css</file_path>
<content>body { margin: 0; }</content>
</write_file>
"""
    calls = extract_pseudo_tool_calls(text)
    assert len(calls) == 2
    assert calls[0]["function"]["name"] == "write_file"
    assert calls[0]["function"]["arguments"]["file_path"].endswith("index.html")
    assert "<!DOCTYPE html>" in calls[0]["function"]["arguments"]["content"]
    assert "{" in calls[1]["function"]["arguments"]["content"]


def test_strip_pseudo_markup() -> None:
    text = "done\n<write_file><path>a.html</path><content>x</content></write_file>\nok"
    cleaned = strip_pseudo_tool_markup(text)
    assert "<write_file>" not in cleaned
    assert "done" in cleaned
