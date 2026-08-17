"""MCP trust ledger + OAuth 2.1 PKCE helpers (Beta Day 31–60).

Servers must be approved before register/connect. Remote auth records
PKCE verifier/challenge; tokens stay in ledger (never plaintext mcp.json).
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from fnixagent.harness.paths import fnix_home

TrustStatus = Literal["pending", "approved", "denied", "revoked"]
AuthType = Literal["none", "token", "oauth"]


@dataclass
class McpTrustEntry:
    server_id: str
    status: TrustStatus = "pending"
    auth_type: AuthType = "none"
    scopes: list[str] = field(default_factory=list)
    command_hash: str = ""
    remote_url: str = ""
    approved_at: float | None = None
    notes: str = ""
    # OAuth PKCE / token handles (no long-lived secrets in mcp.json)
    oauth_client_id: str = ""
    pkce_verifier: str = ""
    pkce_challenge: str = ""
    access_token_ref: str = ""  # keychain / env handle name
    refresh_token_ref: str = ""
    token_expires_at: float | None = None


class McpTrustError(Exception):
    """Trust / OAuth gate failure."""


def trust_ledger_path() -> Path:
    override = os.environ.get("FNIX_MCP_TRUST_PATH", "").strip()
    if override:
        return Path(override)
    return fnix_home() / "mcp-trust.json"


def _load_raw(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": 1, "servers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise McpTrustError(f"corrupt trust ledger: {exc}") from exc
    if not isinstance(data, dict):
        raise McpTrustError("trust ledger must be an object")
    data.setdefault("version", 1)
    data.setdefault("servers", {})
    return data


def _save_raw(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def hash_command(command: str | None, args: list[str] | None = None) -> str:
    blob = json.dumps({"command": command or "", "args": args or []}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def generate_pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge) per RFC 7636 / OAuth 2.1."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _entry_from_raw(server_id: str, raw: dict[str, Any]) -> McpTrustEntry:
    return McpTrustEntry(
        server_id=server_id,
        status=raw.get("status") or "pending",  # type: ignore[arg-type]
        auth_type=raw.get("auth_type") or "none",  # type: ignore[arg-type]
        scopes=list(raw.get("scopes") or []),
        command_hash=str(raw.get("command_hash") or ""),
        remote_url=str(raw.get("remote_url") or ""),
        approved_at=raw.get("approved_at"),
        notes=str(raw.get("notes") or ""),
        oauth_client_id=str(raw.get("oauth_client_id") or ""),
        pkce_verifier=str(raw.get("pkce_verifier") or ""),
        pkce_challenge=str(raw.get("pkce_challenge") or ""),
        access_token_ref=str(raw.get("access_token_ref") or ""),
        refresh_token_ref=str(raw.get("refresh_token_ref") or ""),
        token_expires_at=raw.get("token_expires_at"),
    )


def get_entry(server_id: str) -> McpTrustEntry | None:
    data = _load_raw(trust_ledger_path())
    raw = (data.get("servers") or {}).get(server_id)
    if not isinstance(raw, dict):
        return None
    return _entry_from_raw(server_id, raw)


def list_entries() -> list[McpTrustEntry]:
    data = _load_raw(trust_ledger_path())
    servers = data.get("servers") or {}
    out: list[McpTrustEntry] = []
    if not isinstance(servers, dict):
        return out
    for sid, raw in servers.items():
        if isinstance(raw, dict) and sid:
            out.append(_entry_from_raw(str(sid), raw))
    return sorted(out, key=lambda e: e.server_id)


def upsert_entry(entry: McpTrustEntry) -> McpTrustEntry:
    path = trust_ledger_path()
    data = _load_raw(path)
    servers = data.setdefault("servers", {})
    payload = asdict(entry)
    servers[entry.server_id] = payload
    _save_raw(path, data)
    return entry


def approve_server(
    server_id: str,
    *,
    auth_type: AuthType = "none",
    scopes: list[str] | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    remote_url: str = "",
    notes: str = "",
) -> McpTrustEntry:
    entry = get_entry(server_id) or McpTrustEntry(server_id=server_id)
    entry.status = "approved"
    entry.auth_type = auth_type
    entry.scopes = list(scopes or entry.scopes)
    entry.command_hash = hash_command(command, args) if command else entry.command_hash
    entry.remote_url = remote_url or entry.remote_url
    entry.approved_at = time.time()
    entry.notes = notes or entry.notes
    if auth_type == "oauth" and not entry.pkce_challenge:
        verifier, challenge = generate_pkce_pair()
        entry.pkce_verifier = verifier
        entry.pkce_challenge = challenge
    return upsert_entry(entry)


def deny_server(server_id: str, notes: str = "") -> McpTrustEntry:
    entry = get_entry(server_id) or McpTrustEntry(server_id=server_id)
    entry.status = "denied"
    entry.notes = notes or entry.notes
    return upsert_entry(entry)


def assert_trusted_for_connect(
    server_id: str,
    *,
    command: str | None = None,
    args: list[str] | None = None,
    remote_url: str = "",
    require_approval: bool | None = None,
) -> McpTrustEntry:
    """Fail-closed unless approved (or FNIX_MCP_TRUST_OPEN=1 for local smoke)."""
    open_mode = os.environ.get("FNIX_MCP_TRUST_OPEN", "").strip() in ("1", "true", "yes")
    if require_approval is None:
        require_approval = not open_mode

    entry = get_entry(server_id)
    if not require_approval:
        return entry or McpTrustEntry(server_id=server_id, status="approved")

    if entry is None or entry.status != "approved":
        raise McpTrustError(
            f"MCP server {server_id!r} is not approved "
            f"(status={(entry.status if entry else 'missing')}). "
            "Approve via trust ledger before connect."
        )

    if command and entry.command_hash:
        h = hash_command(command, args)
        if h != entry.command_hash:
            raise McpTrustError(
                f"MCP server {server_id!r} command hash mismatch — re-approve after change."
            )

    if remote_url and entry.remote_url and remote_url.rstrip("/") != entry.remote_url.rstrip("/"):
        raise McpTrustError(f"MCP server {server_id!r} remote URL mismatch — re-approve.")

    if entry.auth_type == "oauth":
        if not entry.pkce_challenge:
            raise McpTrustError(f"MCP server {server_id!r} OAuth missing PKCE challenge.")
        # Token may live in keychain; ref required for live remote
        if (
            remote_url
            and not entry.access_token_ref
            and not os.environ.get("FNIX_MCP_OAUTH_SKIP_TOKEN")
        ):
            raise McpTrustError(
                f"MCP server {server_id!r} OAuth approved but access_token_ref empty."
            )

    return entry
