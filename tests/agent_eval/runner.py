"""
Eval Runner - Main entry point for running FnixAgent evaluation suites.

Usage:
    python -m tests.agent_eval.run --suite basic
    python -m tests.agent_eval.run --suite all --report html
"""

import json
import time
import argparse
from pathlib import Path
from typing import Optional

from .trace_collector import TraceCollector, ExecutionTrace, TraceStep
from .problem_detector import ProblemDetector, Problem, TestCaseResult
from .report_generator import ReportGenerator
from .llm_judge import LLMJudge
from .cases import TEST_CASES, DEFAULT_LLM
from .extended_cases import EXTENDED_CASES, ALL_CASES


class EvalRunner:
    """Main evaluation runner."""

    def __init__(
        self,
        api_base: str = "http://127.0.0.1:8003",
        llm_config: Optional[dict] = None,
        output_dir: str = "test-results/agent_eval",
        use_judge: bool = False,
        use_extended: bool = False,
    ):
        self.collector = TraceCollector(api_base)
        self.detector = ProblemDetector()
        self.reporter = ReportGenerator(output_dir)
        self.llm_config = llm_config or DEFAULT_LLM
        self.judge = LLMJudge(self.llm_config) if use_judge else None
        self.test_cases = ALL_CASES if use_extended else TEST_CASES

    def run_case(self, case: dict) -> TestCaseResult:
        """Run a single test case and return results."""
        case_id = case["id"]
        prompt = case["prompt"]
        mode = case["mode"]
        expected = case.get("expected", {})

        print(f"  Running {case_id}: {case['name']}...", flush=True)

        # Collect trace
        trace = self.collector.collect(case_id, prompt, mode, self.llm_config)

        # Detect problems
        problems = self.detector.detect(trace, expected)

        # Determine pass/fail
        pass_status = self._determine_status(trace, problems, expected)
        score = self._compute_score(trace, problems, expected)

        # Build actual behavior description
        actual = self._describe_actual(trace)

        result = TestCaseResult(
            test_id=case_id,
            test_name=case["name"],
            trace=trace,
            problems=problems,
            expected_behavior=expected.get("note", ""),
            actual_behavior=actual,
            pass_status=pass_status,
            score=score,
        )

        # LLM-as-judge evaluation (optional)
        if self.judge and trace.final_text:
            judge_result = self.judge.judge(trace, expected)
            if judge_result:
                result.llm_judge_feedback = judge_result.summary
                # Blend rule-based score with LLM judge score
                result.score = round((score + judge_result.overall_score) / 2, 2)
                # Add judge-identified problems
                for dim in judge_result.dimensions:
                    if dim.score < 0.5 and dim.issues:
                        cat_map = {
                            "task_completion": "planning",
                            "tool_quality": "tool_params",
                            "planning": "planning",
                            "error_recovery": "rollback",
                            "output_quality": "planning",
                        }
                        for issue in dim.issues:
                            problems.append(
                                Problem(
                                    category=cat_map.get(dim.name, "planning"),
                                    severity="high" if dim.score < 0.3 else "medium",
                                    step_index=trace.step_count,
                                    description=f"[LLM Judge] {dim.name}: {issue}",
                                    evidence=f"judge_score={dim.score:.2f}",
                                    suggestion=dim.feedback,
                                )
                            )

        status_emoji = {"pass": "PASS", "fail": "FAIL", "partial": "PART", "blocked": "BLOCK"}.get(
            pass_status, "?"
        )
        print(
            f"    -> {status_emoji} | {trace.total_duration_s:.1f}s | score={score:.2f} | problems={len(problems)}",
            flush=True,
        )

        return result

    def run_suite(
        self,
        suite_name: str = "all",
        filter_prefix: Optional[str] = None,
        skip_ids: Optional[list[str]] = None,
    ) -> list[TestCaseResult]:
        """Run a suite of test cases. Saves results incrementally to avoid data loss."""
        cases = self.test_cases
        if filter_prefix:
            cases = [c for c in cases if c["id"].startswith(filter_prefix)]
        if skip_ids:
            cases = [c for c in cases if c["id"] not in skip_ids]

        print(f"\n{'=' * 60}")
        print(f"  Eval Suite: {suite_name} | {len(cases)} cases")
        print(f"{'=' * 60}\n")

        # Load existing results if available
        results: list[TestCaseResult] = []
        checkpoint_path = self.reporter.output_dir / f"{suite_name}_checkpoint.json"
        completed_ids: set[str] = set()
        if checkpoint_path.exists():
            try:
                saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                for item in saved:
                    trace = ExecutionTrace(
                        test_id=item["trace"]["test_id"],
                        prompt=item["trace"]["prompt"],
                        work_mode=item["trace"]["work_mode"],
                        total_duration_s=item["trace"]["total_duration_s"],
                        step_count=item["trace"]["step_count"],
                        tool_call_count=item["trace"]["tool_call_count"],
                        tool_names_used=item["trace"]["tool_names_used"],
                        final_text=item["trace"]["final_text_preview"],
                        saw_done=item["trace"]["saw_done"],
                        saw_text=item["trace"]["saw_text"],
                        blocked_by_safety=item["trace"]["blocked_by_safety"],
                        safety_block_reason=item["trace"]["safety_block_reason"],
                        errors=item["trace"]["errors"],
                        artifacts=item["trace"]["artifacts"],
                    )
                    probs = [
                        Problem(
                            category=p["category"],
                            severity=p["severity"],
                            step_index=p["step_index"],
                            description=p["description"],
                            evidence=p["evidence"],
                            suggestion=p["suggestion"],
                        )
                        for p in item["problems"]
                    ]
                    r = TestCaseResult(
                        test_id=item["test_id"],
                        test_name=item["test_name"],
                        trace=trace,
                        problems=probs,
                        expected_behavior=item.get("expected_behavior", ""),
                        actual_behavior=item.get("actual_behavior", ""),
                        pass_status=item["pass_status"],
                        score=item["score"],
                    )
                    results.append(r)
                    completed_ids.add(r.test_id)
                print(f"  Loaded {len(completed_ids)} saved results from checkpoint")
            except Exception as e:
                print(f"  Warning: could not load checkpoint: {e}")

        # Run remaining cases
        remaining = [c for c in cases if c["id"] not in completed_ids]
        if remaining:
            print(f"  Running {len(remaining)} new cases...\n")
        else:
            print(f"  All cases already completed.\n")

        for case in remaining:
            result = self.run_case(case)
            results.append(result)
            # Save checkpoint after each case
            self._save_checkpoint(results, suite_name)

        print(f"\n{'=' * 60}")
        passed = sum(1 for r in results if r.pass_status == "pass")
        print(f"  Complete: {passed}/{len(results)} passed")
        print(f"{'=' * 60}\n")

        return results

    def _save_checkpoint(self, results: list[TestCaseResult], suite_name: str):
        """Save results to checkpoint file."""
        checkpoint_path = self.reporter.output_dir / f"{suite_name}_checkpoint.json"
        data = [
            r.to_dict()
            | {
                "trace": r.trace.to_dict(),
                "expected_behavior": r.expected_behavior,
                "actual_behavior": r.actual_behavior,
            }
            for r in results
        ]
        checkpoint_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def generate_reports(self, results: list[TestCaseResult], suite_name: str = "default") -> dict:
        """Generate all report formats."""
        json_path = self.reporter.generate_json(results, suite_name)
        md_path = self.reporter.generate_markdown(results, suite_name)
        html_path = self.reporter.generate_html(results, suite_name)

        print(f"\nReports generated:")
        print(f"  JSON: {json_path}")
        print(f"  Markdown: {md_path}")
        print(f"  HTML: {html_path}")

        return {"json": json_path, "markdown": md_path, "html": html_path}

    def _determine_status(self, trace: ExecutionTrace, problems: list, expected: dict) -> str:
        """Determine pass/fail status."""
        # If expected to be blocked
        if expected.get("expect_blocked", False):
            return "pass" if trace.blocked_by_safety else "fail"

        # If blocked unexpectedly
        if trace.blocked_by_safety and not expected.get("expect_blocked", False):
            return "blocked"

        # If critical problems
        critical = [p for p in problems if p.severity == "critical"]
        if critical:
            return "fail"

        # If high problems
        high = [p for p in problems if p.severity == "high"]
        if len(high) >= 2:
            return "fail"
        if len(high) == 1:
            return "partial"

        # Check expectations
        if expected.get("expect_text", False) and not trace.final_text:
            return "fail"

        if expected.get("expect_artifacts", False) and not trace.artifacts:
            return "partial"

        if expected.get("expect_done", False) and not trace.saw_done:
            return "partial"

        min_text = expected.get("min_text_length", 0)
        if min_text and len(trace.final_text) < min_text:
            return "partial"

        return "pass"

    def _compute_score(self, trace: ExecutionTrace, problems: list, expected: dict) -> float:
        """Compute a 0.0-1.0 score for the test case."""
        score = 1.0

        # Deduct for problems
        for p in problems:
            deduction = {"critical": 0.4, "high": 0.2, "medium": 0.1, "low": 0.05}.get(
                p.severity, 0.05
            )
            score -= deduction

        # Bonus for fast completion
        if trace.total_duration_s < 30:
            score += 0.05
        elif trace.total_duration_s > 90:
            score -= 0.05

        # Bonus for producing artifacts when expected
        if expected.get("expect_artifacts") and trace.artifacts:
            score += 0.05

        # Check text quality
        min_text = expected.get("min_text_length", 0)
        if min_text and len(trace.final_text) >= min_text * 2:
            score += 0.05

        return max(0.0, min(1.0, score))

    def _describe_actual(self, trace: ExecutionTrace) -> str:
        """Describe what actually happened."""
        parts: list[str] = []
        if trace.blocked_by_safety:
            parts.append(f"Blocked by safety: {trace.safety_block_reason}")
        if trace.saw_text:
            parts.append(f"Produced {len(trace.final_text)} chars of text")
        if trace.artifacts:
            parts.append(
                f"Created {len(trace.artifacts)} artifact(s): {[a.get('name', '') for a in trace.artifacts]}"
            )
        if trace.tool_names_used:
            parts.append(f"Used tools: {trace.tool_names_used}")
        if trace.errors:
            parts.append(f"Errors: {trace.errors[:2]}")
        if not parts:
            parts.append("No significant output produced")

        return " | ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="FnixAgent Evaluation Harness")
    parser.add_argument("--suite", default="all", help="Test suite name")
    parser.add_argument(
        "--filter", default=None, help="Filter test cases by ID prefix (e.g., FILE, SEC, CODE)"
    )
    parser.add_argument(
        "--report", default="all", choices=["json", "markdown", "html", "all"], help="Report format"
    )
    parser.add_argument(
        "--api-base", default="http://127.0.0.1:8003", help="FnixAgent API base URL"
    )
    parser.add_argument("--use-judge", action="store_true", help="Enable LLM-as-judge evaluation")
    parser.add_argument(
        "--use-extended",
        action="store_true",
        help="Use extended test cases (SWE-bench/GAIA/MCP inspired)",
    )
    args = parser.parse_args()

    runner = EvalRunner(
        api_base=args.api_base,
        use_judge=args.use_judge,
        use_extended=args.use_extended,
    )
    results = runner.run_suite(args.suite, args.filter)

    if args.report in ("all", "json", "markdown", "html"):
        runner.generate_reports(results, args.suite)


if __name__ == "__main__":
    main()
