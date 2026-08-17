"""Code Agent apply endpoint — preview 变更落盘。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fnixagent.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_agent_apply_create_file(client, monkeypatch):
    monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")
    monkeypatch.setenv("FNIX_JWT_SECRET", "test-secret-for-unit-tests-only!!")

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        target = ws / "hello.txt"

        client.post(
            "/api/v1/auth/register",
            json={
                "username": "apply_tester",
                "email": "apply@example.com",
                "password": "secret123",
                "role": "user",
            },
        )
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "apply_tester", "password": "secret123"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        res = client.post(
            "/api/v1/chat/agent/apply",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "workspace": str(ws),
                "changes": [
                    {"path": "hello.txt", "action": "create", "content": "fnix harness\n"},
                ],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("ok") is True
        assert target.read_text(encoding="utf-8") == "fnix harness\n"


def test_agent_apply_no_jwt_in_standalone(client, monkeypatch):
    monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        target = ws / "standalone.txt"

        res = client.post(
            "/api/v1/chat/agent/apply",
            json={
                "workspace": str(ws),
                "changes": [
                    {"path": "standalone.txt", "action": "create", "content": "no login\n"},
                ],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body.get("ok") is True
        assert target.read_text(encoding="utf-8") == "no login\n"
