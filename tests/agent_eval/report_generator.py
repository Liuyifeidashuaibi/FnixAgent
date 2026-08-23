"""
Report Generator - Generates structured evaluation reports.

Outputs:
1. JSON report (machine-readable, for CI integration)
2. Markdown report (human-readable, for review)
3. HTML report (visual, for portfolio showcase)
"""

import json
import time
from typing import Optional
from pathlib import Path
from .problem_detector import TestCaseResult


class ReportGenerator:
    """Generates evaluation reports from test results."""

    def __init__(self, output_dir: str = "test-results/agent_eval"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json(self, results: list[TestCaseResult], suite_name: str = "default") -> str:
        """Generate JSON report."""
        report = {
            "suite_name": suite_name,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_cases": len(results),
            "summary": self._compute_summary(results),
            "results": [r.to_dict() for r in results],
            "problem_distribution": self._compute_problem_distribution(results),
        }
        path = self.output_dir / f"{suite_name}_report.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def generate_markdown(self, results: list[TestCaseResult], suite_name: str = "default") -> str:
        """Generate Markdown report."""
        summary = self._compute_summary(results)
        dist = self._compute_problem_distribution(results)

        lines = [
            f"# FnixAgent Evaluation Report - {suite_name}",
            "",
            f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Cases**: {len(results)}",
            f"**Pass Rate**: {summary['pass_rate']:.1%}",
            f"**Average Score**: {summary['avg_score']:.2f}",
            f"**Total Duration**: {summary['total_duration_s']:.1f}s",
            "",
            "## Summary",
            "",
            "| Status | Count |",
            "|--------|-------|",
            f"| PASS | {summary['pass_count']} |",
            f"| FAIL | {summary['fail_count']} |",
            f"| PARTIAL | {summary['partial_count']} |",
            f"| BLOCKED | {summary['blocked_count']} |",
            "",
            "## Problem Distribution",
            "",
            "| Category | Critical | High | Medium | Low | Total |",
            "|----------|----------|------|--------|-----|-------|",
        ]

        for cat, counts in dist.items():
            lines.append(
                f"| {cat} | {counts['critical']} | {counts['high']} | {counts['medium']} | {counts['low']} | {counts['total']} |"
            )

        lines.extend(["", "## Detailed Results", ""])

        for r in results:
            status_emoji = {
                "pass": "PASS",
                "fail": "FAIL",
                "partial": "PART",
                "blocked": "BLOCK",
            }.get(r.pass_status, "?")
            lines.extend(
                [
                    f"### [{status_emoji}] {r.test_id}: {r.test_name}",
                    "",
                    f"- **Score**: {r.score:.2f}",
                    f"- **Duration**: {r.trace.total_duration_s:.1f}s",
                    f"- **Steps**: {r.trace.step_count}",
                    f"- **Tools Used**: {r.trace.tool_names_used}",
                    f"- **Expected**: {r.expected_behavior}",
                    f"- **Actual**: {r.actual_behavior[:200]}",
                    "",
                ]
            )

            if r.problems:
                lines.append("**Problems Found**:")
                lines.append("")
                for p in r.problems:
                    lines.append(
                        f"- [{p.severity.upper()}] [{p.category}] Step {p.step_index}: {p.description}"
                    )
                    lines.append(f"  - Evidence: {p.evidence[:150]}")
                    lines.append(f"  - Suggestion: {p.suggestion}")
                lines.append("")

            if r.llm_judge_feedback:
                lines.append(f"**LLM Judge**: {r.llm_judge_feedback[:300]}")
                lines.append("")

            lines.append("---")
            lines.append("")

        path = self.output_dir / f"{suite_name}_report.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    def generate_html(self, results: list[TestCaseResult], suite_name: str = "default") -> str:
        """Generate HTML report with visual charts."""
        summary = self._compute_summary(results)
        dist = self._compute_problem_distribution(results)

        # Build result cards
        cards_html = []
        for r in results:
            status_color = {
                "pass": "#22c55e",
                "fail": "#ef4444",
                "partial": "#f59e0b",
                "blocked": "#8b5cf6",
            }.get(r.pass_status, "#6b7280")

            problems_html = ""
            if r.problems:
                problems_html = "<ul class='problems'>"
                for p in r.problems:
                    sev_color = {
                        "critical": "#dc2626",
                        "high": "#ea580c",
                        "medium": "#d97706",
                        "low": "#6b7280",
                    }.get(p.severity, "#6b7280")
                    problems_html += (
                        f"<li><span class='sev' style='color:{sev_color}'>[{p.severity.upper()}]</span> "
                        f"<span class='cat'>[{p.category}]</span> "
                        f"Step {p.step_index}: {p.description}</li>"
                    )
                problems_html += "</ul>"

            cards_html.append(f"""
            <div class="card" style="border-left: 4px solid {status_color}">
                <div class="card-header">
                    <span class="status-badge" style="background:{status_color}">{r.pass_status.upper()}</span>
                    <span class="test-id">{r.test_id}</span>
                    <span class="test-name">{r.test_name}</span>
                    <span class="score">Score: {r.score:.2f}</span>
                    <span class="duration">{r.trace.total_duration_s:.1f}s</span>
                </div>
                <div class="card-body">
                    <div class="metrics">
                        Steps: {r.trace.step_count} | Tools: {r.trace.tool_call_count} | {r.trace.tool_names_used}
                    </div>
                    <div class="expected"><strong>Expected:</strong> {r.expected_behavior}</div>
                    <div class="actual"><strong>Actual:</strong> {r.actual_behavior[:200]}</div>
                    {problems_html}
                </div>
            </div>
            """)

        # Problem distribution chart data
        dist_labels = list(dist.keys())
        dist_data = [d["total"] for d in dist.values()]

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FnixAgent Evaluation Report - {suite_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0f; color: #e0e0e8; padding: 24px; }}
h1 {{ color: #a78bfa; margin-bottom: 8px; }}
.meta {{ color: #888; margin-bottom: 24px; font-size: 14px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.stat-card {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 20px; }}
.stat-value {{ font-size: 32px; font-weight: 700; color: #a78bfa; }}
.stat-label {{ color: #888; font-size: 13px; margin-top: 4px; }}
.dist-bar {{ display: flex; gap: 4px; margin: 8px 0; }}
.dist-segment {{ height: 8px; border-radius: 4px; }}
.card {{ background: rgba(255,255,255,0.03); border-radius: 12px; margin-bottom: 16px; overflow: hidden; }}
.card-header {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: rgba(255,255,255,0.03); }}
.status-badge {{ padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; color: white; }}
.test-id {{ color: #a78bfa; font-weight: 600; font-size: 13px; }}
.test-name {{ flex: 1; font-size: 14px; }}
.score {{ color: #fbbf24; font-size: 13px; }}
.duration {{ color: #888; font-size: 12px; }}
.card-body {{ padding: 12px 16px; }}
.metrics {{ font-size: 12px; color: #888; margin-bottom: 8px; }}
.expected, .actual {{ font-size: 13px; margin: 4px 0; }}
.problems {{ list-style: none; margin-top: 8px; padding-left: 0; }}
.problems li {{ padding: 4px 0; font-size: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
.sev {{ font-weight: 700; }}
.cat {{ color: #818cf8; }}
</style>
</head>
<body>
<h1>FnixAgent Evaluation Report</h1>
<p class="meta">Suite: {suite_name} | Generated: {time.strftime("%Y-%m-%d %H:%M:%S")} | Cases: {len(results)}</p>

<div class="summary-grid">
    <div class="stat-card"><div class="stat-value">{summary["pass_rate"]:.0%}</div><div class="stat-label">Pass Rate</div></div>
    <div class="stat-card"><div class="stat-value">{summary["avg_score"]:.2f}</div><div class="stat-label">Avg Score</div></div>
    <div class="stat-card"><div class="stat-value">{summary["pass_count"]}/{len(results)}</div><div class="stat-label">Passed</div></div>
    <div class="stat-card"><div class="stat-value">{summary["total_problems"]}</div><div class="stat-label">Problems Found</div></div>
    <div class="stat-card"><div class="stat-value">{summary["total_duration_s"]:.0f}s</div><div class="stat-label">Total Duration</div></div>
</div>

<h2 style="color:#a78bfa;margin:24px 0 12px">Test Results</h2>
{"".join(cards_html)}
</body>
</html>"""

        path = self.output_dir / f"{suite_name}_report.html"
        path.write_text(html, encoding="utf-8")
        return str(path)

    def _compute_summary(self, results: list[TestCaseResult]) -> dict:
        total = len(results)
        pass_count = sum(1 for r in results if r.pass_status == "pass")
        fail_count = sum(1 for r in results if r.pass_status == "fail")
        partial_count = sum(1 for r in results if r.pass_status == "partial")
        blocked_count = sum(1 for r in results if r.pass_status == "blocked")
        total_problems = sum(len(r.problems) for r in results)
        total_duration = sum(r.trace.total_duration_s for r in results)
        avg_score = sum(r.score for r in results) / total if total else 0

        return {
            "pass_count": pass_count,
            "fail_count": fail_count,
            "partial_count": partial_count,
            "blocked_count": blocked_count,
            "pass_rate": pass_count / total if total else 0,
            "avg_score": avg_score,
            "total_problems": total_problems,
            "total_duration_s": total_duration,
        }

    def _compute_problem_distribution(self, results: list[TestCaseResult]) -> dict:
        cats = ["planning", "tool_params", "rollback", "interruption", "mcp"]
        dist: dict[str, dict] = {}
        for cat in cats:
            dist[cat] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}

        for r in results:
            for p in r.problems:
                if p.category in dist:
                    dist[p.category][p.severity] = dist[p.category].get(p.severity, 0) + 1
                    dist[p.category]["total"] += 1

        return dist
