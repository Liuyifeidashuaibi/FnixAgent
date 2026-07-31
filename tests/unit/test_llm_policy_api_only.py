"""Tests for API-only BYOK policy."""

from __future__ import annotations

import pytest

from fnixagent.services import llm_policy


def test_api_only_requires_user_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_API_ONLY", "1")
    llm, err = llm_policy.resolve_llm_for_request({}, is_admin=True)
    assert llm is None
    assert err and "API Key" in err


def test_api_only_accepts_byok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_API_ONLY", "1")
    llm, err = llm_policy.resolve_llm_for_request(
        {"api_key": "sk-test-key", "provider": "openai", "model": "gpt-4o"},
        is_admin=True,
    )
    assert err is None
    assert llm is not None
    assert llm.get("api_key") == "sk-test-key"


def test_admin_server_key_when_not_api_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_API_ONLY", "0")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-admin")
    llm, err = llm_policy.resolve_llm_for_request({"use_server_key": True}, is_admin=True)
    assert err is None
    assert llm is not None
    assert "api_key" not in llm
