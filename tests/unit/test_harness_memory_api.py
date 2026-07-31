"""Harness 记忆核心：读写 + 注入摘要。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("FNIX_HOME", str(tmp_path))
    monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")
    monkeypatch.setenv("FNIX_API_ONLY", "1")
    from fnixagent.main import app

    with TestClient(app) as c:
        yield c


def test_memory_get_put_and_injection(client: TestClient) -> None:
    r = client.get("/api/v1/harness/memory")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "soul" in data
    assert "memories" in data

    r2 = client.put(
        "/api/v1/harness/memory",
        json={
            "soul": "# Test Soul\nBe helpful.\n",
            "memories": {"MEMORY.md": "User prefers concise answers.\n"},
        },
    )
    assert r2.status_code == 200
    body = r2.json()
    assert "Be helpful" in (body.get("soul") or "")
    assert "concise" in (body.get("memories") or {}).get("MEMORY.md", "")

    inj = client.get("/api/v1/harness/memory/injection")
    assert inj.status_code == 200
    summary = inj.json()
    assert summary.get("soul", {}).get("present") is True
    assert "SOUL.md" in (summary.get("blocks") or [])


def test_memory_rejects_bad_filename(client: TestClient) -> None:
    r = client.put(
        "/api/v1/harness/memory",
        json={"memories": {"../../etc/passwd": "x"}},
    )
    assert r.status_code == 400
