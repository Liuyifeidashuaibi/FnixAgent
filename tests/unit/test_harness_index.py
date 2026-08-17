"""Harness index API tests."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fnixagent.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_harness_index_delegates_to_bridge(client, tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    mock_result = {"ok": True, "session_id": "idx-1", "stats": {"total_files": 1}}

    with patch("fnixagent.harness.local_bridge.get_local_bridge") as get_bridge:
        bridge = MagicMock()
        bridge.index_workspace.return_value = mock_result
        get_bridge.return_value = bridge

        res = client.post(
            "/api/v1/harness/index",
            json={"workspace": str(ws), "force": False},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["session_id"] == "idx-1"
    bridge.index_workspace.assert_called_once()
