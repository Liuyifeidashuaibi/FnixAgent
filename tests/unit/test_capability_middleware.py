"""Desktop capability token gate."""

from __future__ import annotations

import pytest

from fnixagent.core.gateway import capability as cap


def test_no_token_allows_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FNIX_CAPABILITY_TOKEN", raising=False)
    assert cap.check_capability({"type": "http", "path": "/api/v1/harness/config", "headers": []})


def test_public_health_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_CAPABILITY_TOKEN", "secret-token")
    assert cap.check_capability({"type": "http", "path": "/health", "headers": []})


def test_protected_requires_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_CAPABILITY_TOKEN", "secret-token")
    assert not cap.check_capability(
        {"type": "http", "path": "/api/v1/harness/config", "headers": []}
    )
    assert cap.check_capability(
        {
            "type": "http",
            "path": "/api/v1/harness/config",
            "headers": [(b"x-fnix-capability", b"secret-token")],
        }
    )


def test_options_preflight_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_CAPABILITY_TOKEN", "secret-token")
    assert cap.check_capability(
        {
            "type": "http",
            "method": "OPTIONS",
            "path": "/api/v1/work/stream",
            "headers": [(b"origin", b"http://tauri.localhost")],
        }
    )
