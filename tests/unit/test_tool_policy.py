"""Tool policy — risk classification, approval, idempotency."""

from __future__ import annotations

from fnixagent.core.tools.policy import (
    ToolPolicy,
    ToolRisk,
    classify_risk,
    make_idempotency_key,
    reset_tool_policy_for_tests,
)


def test_classify_risk() -> None:
    assert classify_risk("read_file") == ToolRisk.READ
    assert classify_risk("write_file") == ToolRisk.WRITE
    assert classify_risk("run_terminal") == ToolRisk.SHELL
    assert classify_risk("delete_path") == ToolRisk.DESTRUCTIVE
    assert classify_risk("mcp_fetch") == ToolRisk.NETWORK


def test_destructive_blocked_without_approval() -> None:
    policy = ToolPolicy(auto_approve_high=False)
    d = policy.evaluate("delete_path", {"path": "x"})
    assert d.allowed is False
    assert d.requires_approval is True
    assert d.reason == "approval_required"


def test_approval_and_idempotency() -> None:
    policy = ToolPolicy(auto_approve_high=False)
    args = {"path": "a.txt"}
    key = make_idempotency_key("delete_path", args)
    policy.approve(key)
    d = policy.evaluate("delete_path", args)
    assert d.allowed is True
    policy.remember_success(key, {"ok": True})
    hit = policy.evaluate("delete_path", args)
    assert hit.reason == "idempotent_cache_hit"
    assert hit.cached_result == {"ok": True}


def test_registry_policy_gate() -> None:
    from fnixagent.core.tools.protocol import ToolMetadata
    from fnixagent.core.tools.registry import ToolRegistry

    reset_tool_policy_for_tests()
    reg = ToolRegistry()
    calls = {"n": 0}

    def _fn(args: dict):
        calls["n"] += 1
        return {"ok": True, "args": args}

    reg.register(ToolMetadata(name="write_file", description="w"), _fn)
    assert reg.execute("write_file", {"path": "t"})["ok"] is True
    assert reg.execute("write_file", {"path": "t"})["ok"] is True
    assert calls["n"] == 1  # second call served from idempotency cache


def test_shell_blocked_in_strict_mode() -> None:
    policy = ToolPolicy(auto_approve_high=False)
    d = policy.evaluate("run_command", {"cmd": "echo hi"})
    assert d.allowed is False
