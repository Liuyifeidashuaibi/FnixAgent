"""Work 模式编码任务：mission 识别 + Craft 落盘提示 + Ask/Plan/Craft。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.tools.workspace import register_workspace_tools
from fnixagent.services.work_agent import (
    format_ask_prompt,
    format_code_task_prompt,
    format_plan_prompt,
    normalize_work_mode,
    strip_mutating_tools,
    wrap_code_user_input,
)
from fnixagent.services.work_pipeline import build_mission_schema, scan_recent_artifacts


def test_mbti_explain_ask_not_code():
    m = build_mission_schema("解释一下 MBTI 四个维度", work_mode="ask")
    assert m["workspace_kind"] != "code"


def test_mbti_site_classified_as_code():
    m = build_mission_schema("在 .fnix/artifacts/mbti_test 创建一个 MBTI 测验网站")
    assert m["workspace_kind"] == "code"
    assert "产物路径" in m["expected_deliverables"] or "可运行" in str(m["expected_deliverables"])


def test_office_not_code():
    m = build_mission_schema("帮我写一份本周工作周报")
    assert m["workspace_kind"] == "document"


def test_wrap_code_user_input_forces_write_file():
    wrapped = wrap_code_user_input("做一个测验站")
    assert "write_file" in wrapped
    assert "做一个测验站" in wrapped
    assert "Craft" in format_code_task_prompt()


def test_normalize_work_mode():
    assert normalize_work_mode("ask") == "ask"
    assert normalize_work_mode("PLAN") == "plan"
    assert normalize_work_mode("craft") == "craft"
    assert normalize_work_mode(None) == "craft"
    assert normalize_work_mode("weird") == "craft"


def test_ask_plan_prompts_forbid_write():
    assert "禁止" in format_ask_prompt() or "不可" in format_ask_prompt()
    assert "不写盘" in format_plan_prompt() or "禁止" in format_plan_prompt()
    assert "Craft" in format_ask_prompt()
    assert "Craft" in format_plan_prompt()


def test_strip_mutating_tools_removes_write_file(tmp_path):
    reg = ToolRegistry()
    register_workspace_tools(reg, str(tmp_path))
    assert "write_file" in reg._tools
    strip_mutating_tools(reg)
    assert "write_file" not in reg._tools
    assert "edit_file" not in reg._tools
    # 读工具仍在
    assert "read_file" in reg._tools or "ls" in reg._tools


def test_scan_recent_artifacts_empty_missing_dir(tmp_path):
    assert scan_recent_artifacts(str(tmp_path), since_ts=0) == []


def test_normalize_artifact_path_dedupes():
    from fnixagent.services.work_pipeline import merge_artifact, normalize_artifact_path

    ws = r"E:\proj"
    assert (
        normalize_artifact_path(r"E:\proj\.fnix\artifacts\a.html", ws) == ".fnix/artifacts/a.html"
    )
    arts: list[dict[str, str]] = []
    merge_artifact(arts, ".fnix/artifacts/index.html", ws)
    merge_artifact(arts, r"E:\proj\.fnix\artifacts\index.html", ws)
    assert len(arts) == 1
    merge_artifact(arts, "index.html", ws)
    assert len(arts) == 1
    arts2: list[dict[str, str]] = []
    merge_artifact(arts2, "index.html", ws)
    merge_artifact(arts2, ".fnix/artifacts/mbti_test/index.html", ws)
    assert len(arts2) == 1
    assert arts2[0]["path"].startswith(".fnix/")
