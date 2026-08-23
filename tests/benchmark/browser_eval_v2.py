"""
Browser-based benchmark evaluation v2.
Tests FnixAgent through the real Tauri frontend using dumate-browser-cli.

Key improvement: reload page before each task to get fresh DOM refs,
avoiding the React re-render stale ref issue.
"""

import json
import time
import subprocess
import re
import base64
from pathlib import Path
from datetime import datetime
from collections import Counter
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from tests.benchmark.dataset_loader import load_all_datasets, BenchmarkTask

FRONTEND_URL = "http://127.0.0.1:5175"
OUTPUT_DIR = Path("E:/FNIX/FnixAgent/test-results/benchmark")
TRACES_DIR = OUTPUT_DIR / "browser_traces_v2"
RESULTS_DIR = OUTPUT_DIR / "browser_results_v2"
REPORTS_DIR = OUTPUT_DIR / "reports_v2"
STATE_FILE = OUTPUT_DIR / "browser_eval_v2_state.json"
INCREMENTAL_FILE = OUTPUT_DIR / "browser_results_v2_incremental.jsonl"
REGRESSION_FILE = OUTPUT_DIR / "browser_regression_v2.json"

for d in [TRACES_DIR, RESULTS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CLI = "dumate-browser-cli"


def cli(args, timeout=15):
    try:
        r = subprocess.run(
            f"{CLI} {args}", shell=True, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def reload_page():
    """Reload the page and wait for it to be ready."""
    ok, _ = cli("reload", 15)
    if not ok:
        cli("recover", 10)
        time.sleep(2)
        cli("init", 10)
        cli(f'open "{FRONTEND_URL}"', 15)
    time.sleep(4)
    # Verify page is loaded
    ok, snap = cli("snap --no-run", 10)
    return ok and "textbox" in snap


def fill_textbox(text):
    """Fill the textarea with the given text."""
    if len(text) > 12000:
        text = text[:12000] + "\n\n[Task truncated for testing]"

    # Get fresh ref
    ok, snap = cli("snap --no-run", 10)
    if not ok:
        return False

    ref_match = re.search(r"textbox.*?\[ref=(e\d+)\]", snap)
    if not ref_match:
        return False
    ref = ref_match.group(1)

    # Use fill command
    # Escape the text for shell
    # Write text to a temp file and use Python to call CLI with proper args
    safe_text = text.replace("'", "'\\''").replace("\n", " ").replace("\r", "")
    ok, output = cli(f'fill {ref} "{safe_text}"', 15)
    if ok and "actual" in output:
        return True

    # Fallback: try with shorter text
    if len(text) > 2000:
        short = text[:2000].replace("'", "'\\''").replace("\n", " ")
        ok, output = cli(f'fill {ref} "{short}"', 15)
        return ok

    return False


def click_send():
    """Click the send button."""
    ok, snap = cli("snap --no-run", 10)
    if not ok:
        return False

    # Find send button that's not disabled
    ref_match = re.search(r'button "发送" \[ref=(e\d+)\] \[cursor=pointer\]', snap)
    if ref_match:
        ref = ref_match.group(1)
        ok, _ = cli(f"click {ref}", 10)
        return ok

    # Fallback: try press Enter
    ok, _ = cli("press Enter", 10)
    return ok


def wait_for_completion(timeout=300, original_prompt=""):
    """Wait for agent to complete. Returns completion info."""
    start = time.time()
    result = {
        "completed": False,
        "duration_s": 0,
        "has_text": False,
        "has_artifacts": False,
        "has_error": False,
        "rendering_issues": [],
        "final_snap": "",
    }

    last_snap = ""
    stagnant_count = 0
    min_wait = 8  # Minimum wait time before checking completion

    while time.time() - start < timeout:
        time.sleep(3)  # Check every 3s instead of 5s
        elapsed = int(time.time() - start)
        result["duration_s"] = round(time.time() - start, 1)

        ok, snap = cli("snap --no-run", 10)
        if not ok:
            # Try to recover
            cli("recover", 10)
            time.sleep(2)
            cli("init", 10)
            time.sleep(1)
            cli(f'open "{FRONTEND_URL}"', 15)
            time.sleep(3)
            continue

        result["final_snap"] = snap[:5000]

        # Check for error signals
        if "LLM 调用失败" in snap or "HTTP 403" in snap or "HTTP 500" in snap:
            result["has_error"] = True

        # Check for completion signals
        # Agent is done when we see artifacts/download buttons and no "正在分析" or "停止"
        is_processing = "正在分析" in snap or "停止" in snap or "Step " in snap
        has_artifacts_ui = "下载" in snap or "新窗口" in snap or "产物" in snap
        has_content = "paragraph" in snap or "heading" in snap or "code" in snap

        if has_artifacts_ui:
            result["has_artifacts"] = True
        if has_content:
            result["has_text"] = True

        # Check for rendering issues (smart detection)
        issues = detect_rendering_issues(snap, original_prompt)
        for issue in issues:
            if issue not in result["rendering_issues"]:
                result["rendering_issues"].append(issue)

        # Check if page is stagnant
        if snap == last_snap:
            stagnant_count += 1
        else:
            stagnant_count = 0
            last_snap = snap

        # Completion logic:
        # 1. If we see artifacts UI and not processing -> done
        # 2. If we have text and stagnant for 3 checks (15s) -> done
        # 3. If error and no text -> error
        if elapsed >= min_wait:
            if result["has_artifacts"] and not is_processing:
                result["completed"] = True
                break
            if result["has_error"] and not result["has_text"] and not is_processing:
                result["completed"] = True
                break
            if result["has_text"] and stagnant_count >= 3 and not is_processing:
                result["completed"] = True
                break
            if not is_processing and stagnant_count >= 4:
                result["completed"] = True
                break

    if not result["completed"]:
        result["completed"] = result["has_text"] or result["has_artifacts"]

    return result


def detect_rendering_issues(snap, original_prompt=""):
    """Detect frontend rendering issues from snapshot."""
    issues = []

    # Check for raw markdown not rendered
    if "|" in snap and "---" in snap and "table" not in snap.lower():
        if re.search(r"\|.*\|.*\n.*\|.*--", snap):
            issues.append("markdown_table_not_rendered")

    # Check for raw mermaid code
    if "graph TB" in snap or "graph LR" in snap or "sequenceDiagram" in snap:
        if "mermaid" not in snap.lower() and "svg" not in snap.lower():
            issues.append("mermaid_not_rendered")

    # Check for raw code blocks not rendered
    if "```" in snap and "code" not in snap.lower():
        issues.append("code_block_not_rendered")

    # Smart error detection
    error_patterns = [
        "Internal Server Error",
        "Cannot read property",
        "undefined is not",
        "Failed to fetch",
        "TypeError:",
        "ReferenceError:",
        "SyntaxError:",
    ]

    prompt_lower = original_prompt.lower() if original_prompt else ""
    for pattern in error_patterns:
        if pattern not in snap:
            continue
        pattern_base = pattern.rstrip(":").lower()
        if pattern_base in prompt_lower:
            continue

        lines = snap.split("\n")
        in_content_block = False
        found_in_error_context = False

        for line in lines:
            line_lower = line.lower().strip()
            if any(tag in line_lower for tag in ["paragraph", "heading", "code", "pre"]):
                in_content_block = True
                continue
            if line_lower.startswith("button") or line_lower.startswith("div"):
                in_content_block = False

            if pattern in line and not in_content_block:
                clean = re.sub(r"\[ref=e\d+\]|\[level=\d+\]|\[cursor=pointer\]", "", line).strip()
                if len(clean) < 200 and not clean.endswith("."):
                    found_in_error_context = True
                    break

        if found_in_error_context:
            issues.append(f"error_visible: {pattern}")

    return issues


def run_single_task(task, task_index):
    """Run a single task through the browser."""
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
        "rendering_issues": [],
        "has_text_response": False,
        "has_artifacts": False,
        "response_preview": "",
        "failure_category": "",
        "failure_detail": "",
    }

    # Reload page for fresh refs
    if not reload_page():
        result["status"] = "error"
        result["failure_category"] = "page_load_failed"
        result["failure_detail"] = "Could not reload page"
        return result

    # Fill input
    if not fill_textbox(task.prompt):
        result["status"] = "error"
        result["failure_category"] = "ui_fill_failed"
        result["failure_detail"] = "Could not fill input textbox"
        return result

    time.sleep(0.5)

    # Click send
    if not click_send():
        result["status"] = "error"
        result["failure_category"] = "ui_send_failed"
        result["failure_detail"] = "Could not click send button"
        return result

    # Wait for completion
    completion = wait_for_completion(timeout=180, original_prompt=task.prompt)

    result["duration_s"] = completion["duration_s"]
    result["rendering_issues"] = completion["rendering_issues"]
    result["has_text_response"] = completion["has_text"]
    result["has_artifacts"] = completion["has_artifacts"]
    result["response_preview"] = completion["final_snap"][:500]

    # Classify result
    if completion["has_error"] and not completion["has_text"]:
        result["status"] = "error"
        result["failure_category"] = "backend_error"
        result["failure_detail"] = "Agent returned error without text"
    elif not completion["has_text"] and not completion["has_artifacts"]:
        result["status"] = "fail"
        result["failure_category"] = "no_output"
        result["failure_detail"] = "No response received"
    elif completion["rendering_issues"]:
        result["status"] = "fail"
        result["failure_category"] = "rendering_issue"
        result["failure_detail"] = "; ".join(completion["rendering_issues"])
    else:
        result["status"] = "pass"

    # Save trace for failed tasks
    if result["status"] != "pass":
        trace = {
            "task": {
                "dataset": task.dataset,
                "task_id": task.task_id,
                "unique_id": task.unique_id,
                "prompt": task.prompt[:5000],
                "prompt_length": len(task.prompt),
            },
            "result": result,
            "completion_detail": completion,
            "saved_at": datetime.now().isoformat(),
        }
        trace_file = TRACES_DIR / f"{task.unique_id.replace('/', '_').replace('::', '__')}.json"
        trace_file.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


class BrowserEvalV2:
    def __init__(self):
        self.state = self._load_state()
        self.all_results = []
        self.bugs_found = []

    def _load_state(self):
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {"completed": {}, "stats": {"total": 0, "pass": 0, "fail": 0, "error": 0}}

    def _save_state(self):
        STATE_FILE.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _append_incremental(self, result):
        with open(INCREMENTAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()

    def _is_completed(self, task):
        return task.unique_id in self.state["completed"]

    def run_all(self, datasets, max_per_dataset=0, max_total=0):
        total_tasks = sum(len(v) for v in datasets.values())
        completed = len(self.state["completed"])

        print(f"\n{'=' * 60}")
        print(f"  FnixAgent Browser Benchmark v2 (Reload Strategy)")
        print(f"  Total: {total_tasks} | Done: {completed} | Remaining: {total_tasks - completed}")
        print(f"  Frontend: {FRONTEND_URL}")
        print(f"  Model: qwen3.7-max-2026-06-08")
        print(f"{'=' * 60}\n")

        task_num = 0
        pass_count = self.state["stats"]["pass"]
        fail_count = self.state["stats"]["fail"]
        error_count = self.state["stats"]["error"]
        start_time = time.time()

        for dataset_name, tasks in datasets.items():
            if max_per_dataset > 0:
                tasks = tasks[:max_per_dataset]

            print(f"\n--- {dataset_name} ({len(tasks)} tasks) ---")

            for i, task in enumerate(tasks):
                if max_total > 0 and task_num >= max_total:
                    break

                if self._is_completed(task):
                    task_num += 1
                    continue

                task_num += 1
                elapsed = int(time.time() - start_time)
                rate = task_num / max(elapsed, 1)
                remaining = total_tasks - task_num - completed
                eta = int(remaining / max(rate, 0.01))

                task_desc = task.task_id[:40]
                print(
                    f"  [{task_num}/{total_tasks}] {task.dataset}/{task_desc}... ",
                    end="",
                    flush=True,
                )

                result = run_single_task(task, task_num)
                self.all_results.append(result)
                self._append_incremental(result)

                self.state["completed"][task.unique_id] = {
                    "status": result["status"],
                    "duration_s": result["duration_s"],
                    "failure_category": result["failure_category"],
                }
                self.state["stats"]["total"] += 1
                self.state["stats"][result["status"]] += 1
                self._save_state()

                if result["status"] == "pass":
                    pass_count += 1
                elif result["status"] == "error":
                    error_count += 1
                else:
                    fail_count += 1

                icon = {"pass": "PASS", "fail": "FAIL", "error": "ERR"}[result["status"]]
                dur = result["duration_s"]
                issues = (
                    f" issues={result['rendering_issues']}" if result["rendering_issues"] else ""
                )
                print(f"{icon} ({dur}s){issues}")

                if result["status"] != "pass":
                    self._check_for_fixable_bug(result)

                # Progress every 10 tasks
                if task_num % 10 == 0:
                    total_done = pass_count + fail_count + error_count
                    sr = round(pass_count / max(total_done, 1) * 100, 1)
                    print(
                        f"  --- Progress: {total_done}/{total_tasks} "
                        f"| P:{pass_count} F:{fail_count} E:{error_count} "
                        f"| SR:{sr}% | ETA:{eta}s ---"
                    )

            if max_total > 0 and task_num >= max_total:
                break

        self._generate_reports()
        return self.all_results

    def _check_for_fixable_bug(self, result):
        detail = result.get("failure_detail", "")
        category = result.get("failure_category", "")
        if category == "rendering_issue":
            self.bugs_found.append(
                {"type": "rendering", "detail": detail, "task": result["unique_id"]}
            )
        if category.startswith("ui_"):
            self.bugs_found.append(
                {"type": "ui_interaction", "detail": detail, "task": result["unique_id"]}
            )
        if category == "backend_error":
            self.bugs_found.append(
                {"type": "backend", "detail": detail, "task": result["unique_id"]}
            )

    def _generate_reports(self):
        total = len(self.all_results)
        if total == 0:
            # Load from incremental file
            if INCREMENTAL_FILE.exists():
                for line in INCREMENTAL_FILE.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        self.all_results.append(json.loads(line))
                total = len(self.all_results)

        if total == 0:
            print("No results to report.")
            return

        passed = [r for r in self.all_results if r["status"] == "pass"]
        failed = [r for r in self.all_results if r["status"] == "fail"]
        errors = [r for r in self.all_results if r["status"] == "error"]

        dataset_stats = {}
        failure_types = Counter()

        for r in self.all_results:
            ds = r["dataset"]
            dataset_stats.setdefault(ds, {"total": 0, "pass": 0, "fail": 0, "error": 0})
            dataset_stats[ds]["total"] += 1
            dataset_stats[ds][r["status"]] += 1
            if r["status"] != "pass":
                failure_types[r["failure_category"]] += 1

        report = {
            "generated_at": datetime.now().isoformat(),
            "testing_method": "browser_automation_v2_reload_strategy",
            "frontend_url": FRONTEND_URL,
            "model": "qwen3.7-max-2026-06-08",
            "summary": {
                "total_tasks": total,
                "passed": len(passed),
                "failed": len(failed),
                "errors": len(errors),
                "success_rate": round(len(passed) / total * 100, 1) if total else 0,
            },
            "per_dataset": {
                ds: {
                    **stats,
                    "success_rate": round(stats["pass"] / max(stats["total"], 1) * 100, 1),
                }
                for ds, stats in sorted(dataset_stats.items())
            },
            "failure_type_distribution": dict(failure_types.most_common()),
            "rendering_issues_found": list(
                set(issue for r in self.all_results for issue in r.get("rendering_issues", []))
            ),
            "bugs_identified": self.bugs_found,
        }

        # Regression set
        regression = {
            "generated_at": datetime.now().isoformat(),
            "total_failed": len(failed) + len(errors),
            "test_cases": [
                {
                    "dataset": r["dataset"],
                    "task_id": r["task_id"],
                    "prompt_preview": r["prompt_preview"],
                    "failure_category": r["failure_category"],
                    "failure_detail": r["failure_detail"],
                }
                for r in failed + errors
            ],
        }
        REGRESSION_FILE.write_text(
            json.dumps(regression, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report_file = (
            REPORTS_DIR / f"browser_v2_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (REPORTS_DIR / "browser_v2_summary_latest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  BROWSER EVALUATION V2 SUMMARY")
        print(f"{'=' * 60}")
        print(
            f"  Total: {total} | Pass: {len(passed)} | Fail: {len(failed)} | Error: {len(errors)}"
        )
        print(f"  Success Rate: {report['summary']['success_rate']}%")
        print()
        for ds, stats in sorted(dataset_stats.items()):
            sr = round(stats["pass"] / max(stats["total"], 1) * 100, 1)
            print(f"  {ds:25s}  {stats['pass']:4d}/{stats['total']:4d} ({sr}%)")
        print()
        if failure_types:
            print("  Failure Types:")
            for ftype, count in failure_types.most_common():
                print(f"    {ftype:30s}  {count}")
        print(f"\n  Reports: {report_file}")
        print(f"  Regression: {REGRESSION_FILE}")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-total", type=int, default=0, help="Max total tasks (0=all)")
    parser.add_argument("--max-per-dataset", type=int, default=0, help="Max per dataset (0=all)")
    parser.add_argument("--reset", action="store_true", help="Reset state and start fresh")
    args = parser.parse_args()

    if args.reset:
        STATE_FILE.write_text(
            json.dumps(
                {"completed": {}, "stats": {"total": 0, "pass": 0, "fail": 0, "error": 0}},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        INCREMENTAL_FILE.write_text("", encoding="utf-8")
        print("State reset.")

    datasets = load_all_datasets()
    runner = BrowserEvalV2()
    runner.run_all(datasets, max_per_dataset=args.max_per_dataset, max_total=args.max_total)
