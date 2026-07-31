"""上下文预算 trim。"""

from fnixagent.harness.context_budget import merge_budget_reports, trim_text


def test_trim_text_reports_budget() -> None:
    text = "a" * 5000
    out, report = trim_text(text, 1000)
    assert report.trimmed is True
    assert len(out) <= 1000
    assert report.tokens_est > 0
    merged = merge_budget_reports([report])
    assert merged["trimmed"] is True


def test_trim_noop_when_small() -> None:
    out, report = trim_text("hello", 1000)
    assert out == "hello"
    assert report.trimmed is False
