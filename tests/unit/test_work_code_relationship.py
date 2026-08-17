"""Work 与 Code 模式关系：共享 Harness、分离执行路径。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.services.work_agent import format_code_task_prompt
from fnixagent.services.work_pipeline import build_mission_schema


def test_work_craft_code_targets_artifacts_not_repo():
    """Work Craft 编码任务：Chat 交付，artifacts 或仓库 preview。"""
    prompt = format_code_task_prompt()
    assert ".fnix/artifacts/" in prompt
    assert "Chat" in prompt or "Accept" in prompt


def test_work_code_mission_vs_office():
    code_m = build_mission_schema("创建一个静态网站 index.html", work_mode="craft")
    doc_m = build_mission_schema("写一份周报 Word", work_mode="craft")
    assert code_m["workspace_kind"] == "code"
    assert doc_m["workspace_kind"] == "document"


def test_ask_downgrades_explain_from_code():
    """Ask 解释类不应误判为 code 建站任务。"""
    m = build_mission_schema("解释一下 Python 的 def 和 class 区别", work_mode="ask")
    assert m["workspace_kind"] != "code"
