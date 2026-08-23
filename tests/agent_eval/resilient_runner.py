"""
Resilient evaluation runner v2 - fixed serialization, uses to_dict().
"""

import json
import os
import sys
import time
import subprocess
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))

from tests.agent_eval.extended_cases import ALL_CASES
from tests.agent_eval.cases import DEFAULT_LLM
from tests.agent_eval.runner import EvalRunner

CHECKPOINT_PATH = "test-results/agent_eval/full_eval_checkpoint.json"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8003
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_checkpoint(results):
    os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
    # Use default=str to handle any non-serializable objects (tool_args, etc.)
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)


def check_backend():
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False


def restart_backend():
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetTCPConnection -LocalPort {BACKEND_PORT} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique | ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}",
            ],
            capture_output=True,
            timeout=10,
        )
    except:
        pass
    time.sleep(2)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(PROJECT_ROOT, "src")
    env["PYTHONUTF8"] = "1"

    proc = subprocess.Popen(
        [
            "python",
            "-m",
            "uvicorn",
            "fnixagent.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
            "--timeout-keep-alive",
            "300",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=open("/tmp/fnix_backend.log", "w"),
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    print(f"  Backend restarted (PID={proc.pid})", flush=True)

    for i in range(30):
        time.sleep(2)
        if check_backend():
            print(f"  Backend ready after {i * 2}s", flush=True)
            return True
    print("  Backend failed to start!", flush=True)
    return False


def result_to_dict(result):
    """Convert TestCaseResult to dict for JSON serialization."""
    d = result.to_dict()
    d["trace"] = result.trace.to_dict()
    return d


def run_remaining():
    completed = load_checkpoint()
    completed_ids = {r["test_id"] for r in completed}
    print(f"Checkpoint: {len(completed_ids)} cases already done", flush=True)

    remaining = [c for c in ALL_CASES if c["id"] not in completed_ids]
    print(f"Remaining: {len(remaining)} cases", flush=True)
    print(f"To run: {[c['id'] for c in remaining]}", flush=True)

    if not remaining:
        print("All cases already completed!", flush=True)
        return completed

    if not check_backend():
        print("Backend not running, restarting...", flush=True)
        if not restart_backend():
            print("FATAL: Cannot start backend", flush=True)
            return completed

    runner = EvalRunner(api_base=BACKEND_URL, use_extended=True)

    for i, case in enumerate(remaining):
        case_id = case["id"]
        print(f"\n{'=' * 60}", flush=True)
        print(f"[{i + 1}/{len(remaining)}] Running {case_id}: {case['name']}", flush=True)
        print(f"{'=' * 60}", flush=True)

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                if not check_backend():
                    print(f"  Backend down, restarting...", flush=True)
                    if not restart_backend():
                        print(f"  Cannot restart, skipping {case_id}", flush=True)
                        completed.append(
                            {
                                "test_id": case_id,
                                "test_name": case["name"],
                                "pass_status": "skip",
                                "score": 0.0,
                                "expected_behavior": case.get("expected", {}).get("note", ""),
                                "actual_behavior": "Backend unavailable",
                                "duration_s": 0,
                                "step_count": 0,
                                "tool_calls": 0,
                                "tool_names": [],
                                "problems": [],
                                "llm_judge_feedback": None,
                                "trace": {
                                    "test_id": case_id,
                                    "prompt": case["prompt"],
                                    "work_mode": case["mode"],
                                    "total_duration_s": 0,
                                    "step_count": 0,
                                    "tool_call_count": 0,
                                    "tool_names_used": [],
                                    "final_text_preview": "",
                                    "saw_done": False,
                                    "saw_text": False,
                                    "blocked_by_safety": False,
                                    "safety_block_reason": "",
                                    "errors": [],
                                    "artifacts": [],
                                },
                            }
                        )
                        save_checkpoint(completed)
                        break
                    runner = EvalRunner(api_base=BACKEND_URL, use_extended=True)

                result = runner.run_case(case)
                result_dict = result_to_dict(result)
                completed.append(result_dict)
                save_checkpoint(completed)
                print(
                    f"  -> {result_dict['pass_status']} (score={result_dict.get('score', '?')})",
                    flush=True,
                )
                break

            except Exception as e:
                print(f"  Attempt {attempt + 1} failed: {e}", flush=True)
                if attempt < max_retries:
                    print(f"  Retrying...", flush=True)
                    time.sleep(5)
                    if not check_backend():
                        restart_backend()
                        runner = EvalRunner(api_base=BACKEND_URL, use_extended=True)
                else:
                    print(f"  All retries exhausted for {case_id}", flush=True)
                    completed.append(
                        {
                            "test_id": case_id,
                            "test_name": case["name"],
                            "pass_status": "fail",
                            "score": 0.0,
                            "expected_behavior": case.get("expected", {}).get("note", ""),
                            "actual_behavior": f"Exception: {str(e)[:200]}",
                            "duration_s": 0,
                            "step_count": 0,
                            "tool_calls": 0,
                            "tool_names": [],
                            "problems": [],
                            "llm_judge_feedback": None,
                            "trace": {
                                "test_id": case_id,
                                "prompt": case["prompt"],
                                "work_mode": case["mode"],
                                "total_duration_s": 0,
                                "step_count": 0,
                                "tool_call_count": 0,
                                "tool_names_used": [],
                                "final_text_preview": "",
                                "saw_done": False,
                                "saw_text": False,
                                "blocked_by_safety": False,
                                "safety_block_reason": "",
                                "errors": [],
                                "artifacts": [],
                            },
                        }
                    )
                    save_checkpoint(completed)

        time.sleep(2)

    return completed


def generate_final_report(results):
    from tests.agent_eval.report_generator import ReportGenerator
    from tests.agent_eval.problem_detector import TestCaseResult, Problem
    from tests.agent_eval.trace_collector import ExecutionTrace

    # Reconstruct TestCaseResult objects for the report generator
    tc_results = []
    for item in results:
        trace_data = item.get("trace", {})
        trace = ExecutionTrace(
            test_id=trace_data.get("test_id", item["test_id"]),
            prompt=trace_data.get("prompt", ""),
            work_mode=trace_data.get("work_mode", "craft"),
            total_duration_s=trace_data.get("total_duration_s", 0),
            step_count=trace_data.get("step_count", 0),
            tool_call_count=trace_data.get("tool_call_count", 0),
            tool_names_used=trace_data.get("tool_names_used", []),
            final_text=trace_data.get("final_text_preview", ""),
            saw_done=trace_data.get("saw_done", False),
            saw_text=trace_data.get("saw_text", False),
            blocked_by_safety=trace_data.get("blocked_by_safety", False),
            safety_block_reason=trace_data.get("safety_block_reason", ""),
            errors=trace_data.get("errors", []),
            artifacts=trace_data.get("artifacts", []),
        )
        probs = []
        for p in item.get("problems", []):
            probs.append(
                Problem(
                    category=p.get("category", "unknown"),
                    severity=p.get("severity", "medium"),
                    step_index=p.get("step_index", 0),
                    description=p.get("description", ""),
                    evidence=p.get("evidence", ""),
                    suggestion=p.get("suggestion", ""),
                )
            )
        tc_results.append(
            TestCaseResult(
                test_id=item["test_id"],
                test_name=item["test_name"],
                trace=trace,
                problems=probs,
                expected_behavior=item.get("expected_behavior", ""),
                actual_behavior=item.get("actual_behavior", ""),
                pass_status=item["pass_status"],
                score=item["score"],
                llm_judge_feedback=item.get("llm_judge_feedback"),
            )
        )

    gen = ReportGenerator()
    gen.generate(tc_results, "full_eval")
    print(f"\nReports generated in test-results/agent_eval/", flush=True)


if __name__ == "__main__":
    print("=" * 70, flush=True)
    print("FnixAgent Resilient Evaluation Runner v2", flush=True)
    print("=" * 70, flush=True)

    results = run_remaining()

    total = len(results)
    passed = sum(1 for r in results if r["pass_status"] == "pass")
    partial = sum(1 for r in results if r["pass_status"] == "partial")
    failed = sum(1 for r in results if r["pass_status"] == "fail")
    skipped = sum(1 for r in results if r["pass_status"] == "skip")

    print(f"\n{'=' * 70}", flush=True)
    print(f"EVALUATION COMPLETE", flush=True)
    print(f"{'=' * 70}", flush=True)
    print(f"Total: {total}", flush=True)
    print(f"  Pass:    {passed}", flush=True)
    print(f"  Partial: {partial}", flush=True)
    print(f"  Fail:    {failed}", flush=True)
    print(f"  Skip:    {skipped}", flush=True)
    if total > 0:
        print(f"  Pass Rate: {(passed / total) * 100:.1f}%", flush=True)

    print(f"\nGenerating reports...", flush=True)
    generate_final_report(results)
