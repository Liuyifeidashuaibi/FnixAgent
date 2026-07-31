"""Empty / unparseable code review must fail closed (no default pass)."""

from __future__ import annotations

from fnixagent.core.code.agent import CodingAgent


class _StubTools:
    pass


class _StubCtx:
    pass


class _StubLlm:
    async def complete(self, _payload):  # noqa: ANN001
        return ""


def _agent() -> CodingAgent:
    return CodingAgent(_StubTools(), _StubCtx(), _StubLlm())


def test_empty_review_fails() -> None:
    passed, notes = _agent()._parse_review("")
    assert passed is False
    assert "无响应" in notes


def test_missing_passed_field_fails() -> None:
    passed, notes = _agent()._parse_review('{"notes": "looks fine"}')
    assert passed is False
    assert "passed" in notes


def test_explicit_pass_ok() -> None:
    passed, notes = _agent()._parse_review('{"passed": true, "notes": "ok"}')
    assert passed is True
    assert notes == "ok"


def test_garbage_review_fails() -> None:
    passed, _notes = _agent()._parse_review("maybe okay somehow")
    assert passed is False
