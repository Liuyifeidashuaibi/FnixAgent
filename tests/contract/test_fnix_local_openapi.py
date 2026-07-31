"""OpenAPI 契约 — fnix-local sidecar 路由与 Python 实现对齐。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from fnixagent.local.sidecar_app import create_app

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "packages" / "protocol" / "openapi" / "fnix-local-v1.yaml"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def openapi_paths() -> dict:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    return spec.get("paths", {})


def test_openapi_file_exists():
    assert OPENAPI.is_file()


def test_health_matches_contract(client: TestClient, openapi_paths: dict):
    assert "/health" in openapi_paths
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    for key in ("ok", "service", "version", "runtime"):
        assert key in data


def test_index_and_context_roundtrip(client: TestClient, tmp_path: Path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "main.py").write_text("def hello():\n    return 1\n", encoding="utf-8")

    r = client.post("/v1/index", json={"workspace": str(ws), "force": True})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    sid = body.get("session_id")
    assert sid

    ctx = client.get("/v1/context", params={"workspace": str(ws), "query": "hello"})
    assert ctx.status_code == 200
    c = ctx.json()
    assert c.get("ok") is True
    assert "pdg_digest" in c


def test_run_and_read(client: TestClient, tmp_path: Path):
    ws = tmp_path / "run"
    ws.mkdir()
    sample = ws / "readme.txt"
    sample.write_text("hello fnix", encoding="utf-8")

    if __import__("sys").platform == "win32":
        cmd = "type readme.txt"
    else:
        cmd = "cat readme.txt"

    run = client.post(
        "/v1/run",
        json={"workspace": str(ws), "command": cmd, "timeout": 10},
    )
    assert run.status_code == 200
    out = run.json()
    assert "stdout" in out
    assert "stderr" in out
    assert "exit_code" in out

    read = client.get(
        "/v1/read", params={"workspace": str(ws), "path": "readme.txt", "offset": 0, "limit": 2}
    )
    assert read.status_code == 200
    assert read.json().get("ok") is True
