# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.services.llm_policy import normalize_llm_model


def test_normalize_qwen37_alias() -> None:
    assert normalize_llm_model("qwen3.7-plus", "qwen") == "qwen-plus"
    assert normalize_llm_model("qwen-plus-2025-07-28", "qwen") == "qwen-plus-2025-07-28"
    assert normalize_llm_model("qwen-plus", "qwen") == "qwen-plus"
