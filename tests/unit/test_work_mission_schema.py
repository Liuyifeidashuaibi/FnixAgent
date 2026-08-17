# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.services.work_pipeline import build_mission_schema


def test_mission_schema_selects_spreadsheet_workspace() -> None:
    schema = build_mission_schema("分析 Excel 销售数据并生成趋势报告")

    assert schema["workspace_kind"] == "spreadsheet"
    assert schema["blocks"] == ["mission", "data_preview", "analysis", "artifacts"]
    assert "xlsx" in schema["expected_deliverables"]
    assert schema["execution_policy"]["artifact_first"] is True


def test_mission_schema_uses_only_controlled_workspace_kinds() -> None:
    prompts = {
        "presentation": "制作产品路演 PPT",
        "research": "调研行业趋势并列出来源",
        "document": "生成本周工作周报 Word",
        "code": "修复接口代码中的 bug",
        "general": "帮我完成这项工作",
    }

    for expected_kind, prompt in prompts.items():
        schema = build_mission_schema(prompt)
        assert schema["workspace_kind"] == expected_kind
        assert schema["schema_version"] == "1.0"
        assert schema["acceptance_criteria"]


def test_mission_schema_does_not_claim_rollback_before_checkpoint_support() -> None:
    schema = build_mission_schema("生成一份项目方案")

    assert schema["execution_policy"]["reversible"] is False
    assert schema["execution_policy"]["human_can_interrupt"] is True
