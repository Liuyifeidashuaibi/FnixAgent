"""上下文预算 — 可观测 trim（不对 LLM 文本做 Huffman 压缩）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fnixagent.core.text import estimate_tokens

# 默认块上限（字符）；可用环境变量覆盖
DEFAULT_MAX_CHARS = 24_000
RULES_MAX = 8_000
INDEX_MAX = 8_000
MEMORY_MAX = 4_000


@dataclass
class BudgetReport:
    original_chars: int
    final_chars: int
    tokens_est: int
    trimmed: bool
    max_chars: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def trim_text(text: str, max_chars: int, *, label: str = "") -> tuple[str, BudgetReport]:
    raw = text or ""
    max_chars = max(256, int(max_chars))
    trimmed = len(raw) > max_chars
    out = raw if not trimmed else raw[: max_chars - 24] + "\n\n…(context trimmed)"
    report = BudgetReport(
        original_chars=len(raw),
        final_chars=len(out),
        tokens_est=estimate_tokens(out),
        trimmed=trimmed,
        max_chars=max_chars,
    )
    return out, report


def merge_budget_reports(reports: list[BudgetReport]) -> dict[str, Any]:
    if not reports:
        return {
            "original_chars": 0,
            "final_chars": 0,
            "tokens_est": 0,
            "trimmed": False,
            "parts": 0,
        }
    return {
        "original_chars": sum(r.original_chars for r in reports),
        "final_chars": sum(r.final_chars for r in reports),
        "tokens_est": sum(r.tokens_est for r in reports),
        "trimmed": any(r.trimmed for r in reports),
        "parts": len(reports),
    }
