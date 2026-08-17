"""Harness secrets 单元测试。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import pytest


@pytest.fixture
def harness_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "fnix"))
    return tmp_path / "fnix"


def test_secrets_roundtrip(harness_home):
    from fnixagent.harness.secrets import (
        get_llm_api_key,
        secrets_status,
        set_llm_api_key,
    )

    assert get_llm_api_key() == ""
    set_llm_api_key("sk-test-key-12345678")
    assert get_llm_api_key() == "sk-test-key-12345678"
    status = secrets_status()
    assert status["has_api_key"] is True
    assert "..." in status["key_hint"] or "sk-t" in status["key_hint"]

    set_llm_api_key("")
    assert get_llm_api_key() == ""
    assert secrets_status()["has_api_key"] is False
