"""
Full benchmark runner - executes all dataset tasks through FnixAgent API,
records traces, detects problems, and generates reports.

Features:
- Resumable (tracks completed tasks in a state file)
- Full trace recording per task
- Automated problem detection and failure classification
- Regression test set generation
- Statistical summary report
"""

import json
import os
import time
import sys
import traceback
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.benchmark.dataset_loader import load_all_datasets, BenchmarkTask
from tests.agent_eval.trace_collector import TraceCollector, ExecutionTrace
from tests.agent_eval.problem_detector import ProblemDetector, Problem, TestCaseResult


# --- Configuration ---
API_BASE = "http://127.0.0.1:8003"

def _load_env_key() -> str:
    """Load DashScope BYOK key from repo .env（后端为纯 BYOK，必须随请求传递）"""
    env_file = Path("E:/FNIX/FnixAgent/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DASHSCOPE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("DASHSCOPE_API_KEY", "")

LLM_CONFIG = {
    "provider": "qwen",
    "model": os.environ.get("LLM_MODEL", "qwen3.6-max-preview"),
    "api_key": _load_env_key(),
    "timeout": 300,
}
WORK_MODE = "craft"  # craft mode for code generation tasks
TIMEOUT_PER_TASK = 180  # seconds

OUTPUT_DIR = Path("E:/FNIX/FnixAgent/test-results/benchmark")
TRACES_DIR = OUTPUT_DIR / "traces"
RESULTS_DIR = OUTPUT_DIR / "results"
REPORTS_DIR = OUTPUT_DIR / "reports"
STATE_FILE = OUTPUT_DIR / "eval_state.json"
REGRESSION_FILE = OUTPUT_DIR / "regression_testset.json"

# Ensure dirs exist
for d in [TRACES_DIR, RESULTS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


class BenchmarkRunner:
    """Runs benchmark tasks through FnixAgent and records results."""

    def __init__(self):
        self.collector = TraceCollector(API_BASE)
        self.detector = ProblemDetector()
        self.state = self._load_state()
        self.bugs_found = []

    def _load_state(self) -> dict:
        """Load resumable state."""
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {"completed": {}, "stats": {"total": 0, "pass": 0, "fail": 0, "error": 0}}

    def _save_state(self):
        """Save state for resumption."""
        STATE_FILE.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _trace_file(self, task: BenchmarkTask) -> Path:
        """Get trace file path for a task."""
        safe_id = task.task_id.replace("/", "__").replace("\\", "__")
        return TRACES_DIR / f"{task.dataset}__{safe_id}.json"

    def _is_completed(self, task: BenchmarkTask) -> bool:
        """Check if task was already completed."""
        return task.unique_id in self.state["completed"]

    def run_task(self, task: BenchmarkTask) -> dict:
        """Run a single task and return result dict."""
        result = {
            "dataset": task.dataset,
            "task_id": task.task_id,
            "unique_id": task.unique_id,
            "subset": task.subset,
            "prompt_preview": task.prompt[:300],
            "prompt_length": len(task.prompt),
            "timestamp": datetime.now().isoformat(),
            "status": "unknown",
            "duration_s": 0,
            "step_count": 0,
            "tool_call_count": 0,
            "tool_names_used": [],
            "final_text_length": 0,
            "final_text_preview": "",
            "artifacts": [],
            "errors": [],
            "problems": [],
            "failure_category": "",
            "failure_detail": "",
        }

        # Collect trace
        try:
            trace = self.collector.collect(
                test_id=task.unique_id,
                prompt=task.prompt,
                work_mode=WORK_MODE,
                llm_config=LLM_CONFIG,
                timeout=TIMEOUT_PER_TASK,
            )

            result["duration_s"] = round(trace.total_duration_s, 2)
            result["step_count"] = trace.step_count
            result["tool_call_count"] = trace.tool_call_count
            result["tool_names_used"] = trace.tool_names_used
            result["final_text_length"] = len(trace.final_text)
            result["final_text_preview"] = trace.final_text[:500]
            result["artifacts"] = trace.artifacts
            result["errors"] = trace.errors
            result["saw_done"] = trace.saw_done
            result["saw_text"] = trace.saw_text
            result["session_id"] = trace.session_id
            result["trace_id"] = trace.trace_id

            # Detect problems
            problems = self.detector.detect(trace, {"expect_text": True, "max_steps": 15})
            result["problems"] = [
                {
                    "category": p.category,
                    "severity": p.severity,
                    "description": p.description,
                    "evidence": p.evidence[:200],
                }
                for p in problems
            ]

            # Determine pass/fail
            result["status"], result["failure_category"], result["failure_detail"] = (
                self._classify_result(trace, problems)
            )

            # Save full trace
            trace_path = self._trace_file(task)
            trace_path.write_text(
                json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

        except Exception as e:
            result["status"] = "error"
            result["failure_category"] = "runtime_crash"
            result["failure_detail"] = f"{type(e).__name__}: {str(e)[:300]}"
            result["errors"].append(result["failure_detail"])
            traceback.print_exc()

        # Update state
        self.state["completed"][task.unique_id] = {
            "status": result["status"],
            "duration_s": result["duration_s"],
            "failure_category": result["failure_category"],
            "timestamp": result["timestamp"],
        }
        self.state["stats"]["total"] += 1
        if result["status"] == "pass":
            self.state["stats"]["pass"] += 1
        elif result["status"] == "fail":
            self.state["stats"]["fail"] += 1
        else:
            self.state["stats"]["error"] += 1
        self._save_state()

        return result

    def _classify_result(
        self, trace: ExecutionTrace, problems: list[Problem]
    ) -> tuple[str, str, str]:
        """Classify result as pass/fail/error with failure category."""
        # Error = agent crashed or couldn't produce any output
        if trace.errors and not trace.saw_text and not trace.saw_done:
            return "error", "runtime_crash", "; ".join(trace.errors[:2])

        # Check for blocking safety
        if trace.blocked_by_safety:
            return "fail", "safety_block", trace.safety_block_reason or "blocked by safety"

        # Check for no output at all
        if not trace.saw_text and not trace.saw_done:
            return "fail", "no_output", "Agent produced no output"

        # Check for critical problems
        critical = [p for p in problems if p.severity == "critical"]
        if critical:
            cat = critical[0].category
            return "fail", f"critical_{cat}", critical[0].description

        # Check for MCP failures
        mcp_fails = [p for p in problems if p.category == "mcp"]
        if mcp_fails:
            return "fail", "mcp_call_error", mcp_fails[0].description

        # Check for tool call failures (high severity)
        tool_fails = [p for p in problems if p.category == "tool_params" and p.severity == "high"]
        if tool_fails:
            return "fail", "tool_call_error", tool_fails[0].description

        # Check for planning errors (high severity)
        plan_errors = [p for p in problems if p.category == "planning" and p.severity == "high"]
        if plan_errors:
            return "fail", "planning_error", plan_errors[0].description

        # Check for interruption
        interruptions = [
            p for p in problems if p.category == "interruption" and p.severity == "high"
        ]
        if interruptions:
            return "fail", "context_loss", interruptions[0].description

        # Check for rollback issues
        rollback_issues = [p for p in problems if p.category == "rollback" and p.severity == "high"]
        if rollback_issues:
            return "fail", "rollback_missing", rollback_issues[0].description

        # Check output quality: needs some meaningful text
        if trace.final_text and len(trace.final_text) < 20:
            return "fail", "output_truncated", f"Final text too short: {trace.final_text[:50]}"

        # Passed all checks
        return "pass", "", ""

    def run_all(self, datasets: dict[str, list[BenchmarkTask]], max_per_dataset: int = 0):
        """Run all tasks across all datasets."""
        all_results = []
        total_tasks = sum(len(v) for v in datasets.values())
        completed = len(self.state["completed"])

        print(f"\n{'=' * 60}")
        print(f"  FnixAgent Full Benchmark Evaluation")
        print(f"  Total tasks: {total_tasks} | Already completed: {completed}")
        print(f"  Remaining: {total_tasks - completed}")
        print(f"  Model: {LLM_CONFIG['model']} | Mode: {WORK_MODE}")
        print(f"  Timeout: {TIMEOUT_PER_TASK}s per task")
        print(f"{'=' * 60}\n")

        for dataset_name, tasks in datasets.items():
            if max_per_dataset > 0:
                tasks = tasks[:max_per_dataset]

            print(f"\n--- Dataset: {dataset_name} ({len(tasks)} tasks) ---")

            for i, task in enumerate(tasks):
                if self._is_completed(task):
                    continue

                print(f"  [{i + 1}/{len(tasks)}] {task.task_id[:60]}... ", end="", flush=True)

                result = self.run_task(task)
                all_results.append(result)

                status_icon = {"pass": "PASS", "fail": "FAIL", "error": "ERR"}[result["status"]]
                duration = result["duration_s"]
                print(f"{status_icon} ({duration}s)")

                # Check for bugs to fix
                if result["status"] != "pass":
                    self._check_for_fixable_bug(result)

        # Generate reports
        self._generate_regression_set(all_results)
        self._generate_summary_report(all_results)

        return all_results

    def _check_for_fixable_bug(self, result: dict):
        """Check if a failure indicates a fixable bug in the agent."""
        bug_patterns = [
            ("web_search returns 0 results", "BUG-020"),
            ("Mermaid", "BUG-018"),
            ("Markdown table", "BUG-017"),
        ]
        for pattern, bug_id in bug_patterns:
            if pattern.lower() in result.get("failure_detail", "").lower():
                self.bugs_found.append(
                    {
                        "bug_id": bug_id,
                        "task": result["unique_id"],
                        "detail": result["failure_detail"],
                    }
                )

    def _generate_regression_set(self, results: list[dict]):
        """Generate regression test set from failed tasks."""
        failed = [r for r in results if r["status"] != "pass"]
        regression = {
            "generated_at": datetime.now().isoformat(),
            "total_failed": len(failed),
            "description": "Regression test set - rerun after agent modifications to prevent degradation",
            "test_cases": [
                {
                    "dataset": r["dataset"],
                    "task_id": r["task_id"],
                    "prompt_preview": r["prompt_preview"],
                    "failure_category": r["failure_category"],
                    "failure_detail": r["failure_detail"],
                    "original_status": r["status"],
                }
                for r in failed
            ],
        }
        REGRESSION_FILE.write_text(
            json.dumps(regression, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n  Regression set: {len(failed)} failed tasks -> {REGRESSION_FILE}")

    def _generate_summary_report(self, results: list[dict]):
        """Generate summary statistics report."""
        from collections import Counter, defaultdict

        # Per-dataset stats
        dataset_stats = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "error": 0})
        failure_types = Counter()
        durations = []

        for r in results:
            ds = r["dataset"]
            dataset_stats[ds]["total"] += 1
            dataset_stats[ds][r["status"]] += 1
            if r["status"] != "pass":
                failure_types[r["failure_category"]] += 1
            durations.append(r["duration_s"])

        total = len(results)
        passed = sum(1 for r in results if r["status"] == "pass")
        failed = sum(1 for r in results if r["status"] == "fail")
        errors = sum(1 for r in results if r["status"] == "error")

        report = {
            "generated_at": datetime.now().isoformat(),
            "model": LLM_CONFIG["model"],
            "work_mode": WORK_MODE,
            "summary": {
                "total_tasks": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "success_rate": round(passed / total * 100, 1) if total else 0,
                "avg_duration_s": round(sum(durations) / len(durations), 2) if durations else 0,
                "total_duration_min": round(sum(durations) / 60, 1),
            },
            "per_dataset": {
                ds: {
                    **stats,
                    "success_rate": round(stats["pass"] / stats["total"] * 100, 1)
                    if stats["total"]
                    else 0,
                }
                for ds, stats in sorted(dataset_stats.items())
            },
            "failure_type_distribution": dict(failure_types.most_common()),
        }

        report_file = REPORTS_DIR / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        # Also write latest
        (REPORTS_DIR / "summary_latest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  EVALUATION COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Total: {total} | Pass: {passed} | Fail: {failed} | Error: {errors}")
        print(f"  Success Rate: {report['summary']['success_rate']}%")
        print(f"  Avg Duration: {report['summary']['avg_duration_s']}s")
        print(f"  Total Time: {report['summary']['total_duration_min']}min")
        print(f"\n  Per Dataset:")
        for ds, stats in report["per_dataset"].items():
            print(
                f"    {ds:25s} {stats['pass']:4d}/{stats['total']:4d} ({stats['success_rate']:5.1f}%)"
            )
        print(f"\n  Failure Types:")
        for ftype, count in report["failure_type_distribution"].items():
            print(f"    {ftype:30s} {count:4d}")
        print(f"\n  Reports: {report_file}")
        print(f"  Regression: {REGRESSION_FILE}")
        print(f"{'=' * 60}\n")

        return report


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run full benchmark evaluation")
    parser.add_argument(
        "--max-per-dataset", type=int, default=0, help="Max tasks per dataset (0 = all)"
    )
    parser.add_argument("--dataset", type=str, default="", help="Run only specific dataset")
    parser.add_argument("--reset", action="store_true", help="Reset state and start fresh")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("State reset.")

    # Load datasets
    print("Loading datasets...")
    datasets = load_all_datasets()

    if args.dataset:
        datasets = {k: v for k, v in datasets.items() if k == args.dataset}

    # Run evaluation
    runner = BenchmarkRunner()
    runner.run_all(datasets, max_per_dataset=args.max_per_dataset)


if __name__ == "__main__":
    main()
