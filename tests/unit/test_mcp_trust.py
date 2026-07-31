"""Unit tests for MCP trust ledger + PKCE."""

from __future__ import annotations

from pathlib import Path

import pytest

from fnixagent.core.mcp.trust import (
    McpTrustError,
    approve_server,
    assert_trusted_for_connect,
    deny_server,
    generate_pkce_pair,
    get_entry,
    hash_command,
)


def test_pkce_pair_shape():
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert verifier != challenge


def test_trust_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FNIX_MCP_TRUST_PATH", str(tmp_path / "trust.json"))
    monkeypatch.delenv("FNIX_MCP_TRUST_OPEN", raising=False)
    with pytest.raises(McpTrustError):
        assert_trusted_for_connect("demo")


def test_trust_approve_and_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FNIX_MCP_TRUST_PATH", str(tmp_path / "trust.json"))
    monkeypatch.delenv("FNIX_MCP_TRUST_OPEN", raising=False)
    approve_server(
        "demo",
        auth_type="none",
        command="npx",
        args=["-y", "@x/mcp"],
    )
    entry = assert_trusted_for_connect("demo", command="npx", args=["-y", "@x/mcp"])
    assert entry.status == "approved"
    assert entry.command_hash == hash_command("npx", ["-y", "@x/mcp"])
    with pytest.raises(McpTrustError):
        assert_trusted_for_connect("demo", command="npx", args=["evil"])


def test_oauth_requires_pkce_and_token_ref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FNIX_MCP_TRUST_PATH", str(tmp_path / "trust.json"))
    monkeypatch.delenv("FNIX_MCP_TRUST_OPEN", raising=False)
    monkeypatch.delenv("FNIX_MCP_OAUTH_SKIP_TOKEN", raising=False)
    entry = approve_server("remote", auth_type="oauth", remote_url="https://mcp.example/sse")
    assert entry.pkce_challenge
    with pytest.raises(McpTrustError):
        assert_trusted_for_connect("remote", remote_url="https://mcp.example/sse")
    # allow skip for CI unit path
    monkeypatch.setenv("FNIX_MCP_OAUTH_SKIP_TOKEN", "1")
    assert_trusted_for_connect("remote", remote_url="https://mcp.example/sse")


def test_deny(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FNIX_MCP_TRUST_PATH", str(tmp_path / "trust.json"))
    deny_server("bad", notes="nope")
    assert get_entry("bad").status == "denied"


def test_list_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fnixagent.core.mcp.trust import list_entries

    monkeypatch.setenv("FNIX_MCP_TRUST_PATH", str(tmp_path / "trust.json"))
    approve_server("alpha")
    deny_server("beta")
    ids = [e.server_id for e in list_entries()]
    assert ids == ["alpha", "beta"]
