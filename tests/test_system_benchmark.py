"""Tests for full-chain system benchmark."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from fnixagent.main import app

    return TestClient(app)


def test_benchmark_suites(client: TestClient):
    res = client.get("/api/v1/benchmark/suites")
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok")
    assert any(s["id"] == "full_chain" for s in data.get("suites", []))


def test_benchmark_run_stream(client: TestClient):
    res = client.post(
        "/api/v1/benchmark/run",
        json={"include_llm": False, "client_stages": []},
    )
    assert res.status_code == 200
    lines = [ln for ln in res.text.strip().split("\n") if ln.strip()]
    assert len(lines) >= 2
    last = json.loads(lines[-1])
    assert last.get("type") == "done"
    report = last.get("report") or {}
    assert "overall_score" in report
    assert report.get("stage_count", 0) >= 4
