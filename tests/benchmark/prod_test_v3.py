#!/usr/bin/env python3
"""
FnixAgent Production Test v3 - Real benchmark task execution via API.

Tests the FnixAgent backend with real benchmark tasks to:
1. Measure task success rate
2. Detect bugs and performance issues
3. Record full traces for analysis
4. Find and fix problems to make FnixAgent production-ready

Usage:
    PYTHONPATH=src python tests/benchmark/prod_test_v3.py [--max-tasks N] [--dataset NAME]
"""

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import httpx

# --- Config ---
BACKEND_URL = os.getenv("FNIX_BACKEND_URL", "http://127.0.0.1:8013")
DATASETS_DIR = Path("test-results/benchmark/datasets")
RESULTS_DIR = Path("test-results/prod_test_v3")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# --- Dataset Loaders ---


def load_vibe_code_bench(max_tasks: int = 20) -> list[dict]:
    """Load vibe-code-bench tasks (cleanest: spec.md = complete prompt)."""
    tasks = []
    vcb_dir = DATASETS_DIR / "vibe-code-bench" / "eval_cases"
    if not vcb_dir.exists():
        # Try alternate path
        vcb_dir = DATASETS_DIR / "vibe-code-bench"
    for case_dir in sorted(vcb_dir.iterdir()):
        if not case_dir.is_dir() or not case_dir.name.startswith("case_"):
            continue
        spec_file = case_dir / "spec.md"
        if not spec_file.exists():
            continue
        prompt = spec_file.read_text(encoding="utf-8").strip()
        tasks.append(
            {
                "dataset": "vibe-code-bench",
                "task_id": case_dir.name,
                "prompt": prompt,
            }
        )
        if len(tasks) >= max_tasks:
            break
    return tasks


def load_workbuddy_bench(max_tasks: int = 10) -> list[dict]:
    """Load workbuddy-bench code tasks (Chinese instructions)."""
    tasks = []
    wbb_dir = DATASETS_DIR / "workbuddy-bench" / "extracted" / "wb-bench-code-v1.0" / "tasks"
    if not wbb_dir.exists():
        # Try alternate structure
        wbb_dir = DATASETS_DIR / "workbuddy-bench"
        # Search for instruction.md files
        for root, dirs, files in os.walk(wbb_dir):
            if "instruction.md" in files:
                inst_path = Path(root) / "instruction.md"
                prompt = inst_path.read_text(encoding="utf-8").strip()
                task_name = Path(root).name
                tasks.append(
                    {
                        "dataset": "workbuddy-bench",
                        "task_id": f"workbuddy/{task_name}",
                        "prompt": prompt,
                    }
                )
                if len(tasks) >= max_tasks:
                    break
            # Don't recurse into .git
            dirs[:] = [d for d in dirs if d != ".git"]
        return tasks

    for task_dir in sorted(wbb_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        inst_file = task_dir / "instruction.md"
        if not inst_file.exists():
            continue
        prompt = inst_file.read_text(encoding="utf-8").strip()
        tasks.append(
            {
                "dataset": "workbuddy-bench",
                "task_id": f"workbuddy/{task_dir.name}",
                "prompt": prompt,
            }
        )
        if len(tasks) >= max_tasks:
            break
    return tasks


def load_web_bench_standalone(max_tasks: int = 10) -> list[dict]:
    """Load web-bench tasks (pick first task from each project = standalone)."""
    tasks = []
    wb_dir = DATASETS_DIR / "web-bench" / "projects"
    if not wb_dir.exists():
        wb_dir = DATASETS_DIR / "web-bench"
    for proj_dir in sorted(wb_dir.iterdir()):
        if not proj_dir.is_dir() or proj_dir.name.startswith("."):
            continue
        tasks_file = proj_dir / "tasks.jsonl"
        if not tasks_file.exists():
            continue
        with open(tasks_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    tasks.append(
                        {
                            "dataset": "web-bench",
                            "task_id": f"{proj_dir.name}/{d.get('id', '')}",
                            "prompt": d.get("description", ""),
                        }
                    )
                    break  # Only take first task from each project (standalone)
                except json.JSONDecodeError:
                    continue
        if len(tasks) >= max_tasks:
            break
    return tasks


def load_custom_tasks() -> list[dict]:
    """Custom tasks designed to test specific FnixAgent capabilities."""
    return [
        {
            "dataset": "custom",
            "task_id": "custom-react-dashboard",
            "prompt": "Create a single-file React dashboard HTML page with: a header showing 'Sales Dashboard', 3 KPI cards (Revenue $1.2M, Orders 8,432, Conversion 3.2%), a bar chart showing monthly sales (Jan-Dec), and a data table with 5 sample orders. Use Tailwind CSS via CDN and Chart.js via CDN. Make it visually appealing with a modern color scheme.",
        },
        {
            "dataset": "custom",
            "task_id": "custom-python-api",
            "prompt": 'Create a Python FastAPI application with: a /health endpoint returning {"status": "healthy"}, a /users endpoint returning a list of 3 sample users with id/name/email, and a /users/{user_id} endpoint returning a single user. Include proper error handling for 404s. Write it as a single main.py file.',
        },
        {
            "dataset": "custom",
            "task_id": "custom-landing-page",
            "prompt": "Create a beautiful single-file HTML landing page for a fictional AI product called 'NeuroFlow'. Include: hero section with headline and CTA button, features section with 4 feature cards (each with icon, title, description), pricing section with 3 tiers, and a footer. Use modern CSS with gradients, animations on hover, and responsive design. No external dependencies except Google Fonts.",
        },
        {
            "dataset": "custom",
            "task_id": "custom-todo-app",
            "prompt": "Build a todo list application as a single HTML file. Features: add new todo items, mark items as complete (strikethrough), delete items, filter by All/Active/Completed, local storage persistence, clean UI with smooth transitions. Use vanilla JavaScript only (no frameworks).",
        },
    ]


# --- Task Execution ---


async def execute_task(client: httpx.AsyncClient, task: dict, timeout: int = 180) -> dict:
    """Execute a single task via FnixAgent backend API."""
    task_start = time.time()
    result = {
        "task": task,
        "start_time": datetime.now().isoformat(),
        "events": [],
        "artifacts": [],
        "errors": [],
        "tool_calls": [],
        "duration_sec": 0,
        "status": "unknown",
        "issues_detected": [],
    }

    try:
        # POST /api/v1/work/stream — NDJSON streaming endpoint
        # Use stream=True to read NDJSON line by line
        async with client.stream(
            "POST",
            f"{BACKEND_URL}/api/v1/work/stream",
            json={
                "user_input": task["prompt"],
                "workspace": str(Path.cwd()),
                "work_mode": "craft",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                result["status"] = "api_error"
                result["errors"].append(
                    f"HTTP {resp.status_code}: {body.decode('utf-8', errors='replace')[:500]}"
                )
                result["duration_sec"] = round(time.time() - task_start, 2)
                return result

            # Parse NDJSON stream
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    result["events"].append(event)

                    evt_type = event.get("type", "")
                    evt_data = event.get("data", {})

                    if evt_type == "tool_call":
                        result["tool_calls"].append(
                            {
                                "name": evt_data.get("name", ""),
                                "status": evt_data.get("status", ""),
                                "path": evt_data.get("path", ""),
                            }
                        )
                    elif evt_type == "artifact":
                        result["artifacts"].append(evt_data)
                    elif evt_type == "error":
                        result["errors"].append(evt_data)
                        result["issues_detected"].append(
                            f"error_event: {evt_data.get('message', '')[:200]}"
                        )
                    elif evt_type == "done":
                        result["status"] = "success" if evt_data.get("success", False) else "failed"
                        result["answer"] = evt_data.get("result", "")
                        result["final_artifacts"] = evt_data.get("artifacts", [])
                    elif evt_type == "critic_skipped":
                        result["issues_detected"].append(
                            f"critic_skipped: {evt_data.get('reason', '')}"
                        )

                except json.JSONDecodeError:
                    continue

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["errors"].append(f"Task timed out after {timeout}s")
        result["issues_detected"].append("timeout: task exceeded time limit")
    except Exception as e:
        result["status"] = "exception"
        result["errors"].append(f"{type(e).__name__}: {e}")
        result["issues_detected"].append(f"exception: {type(e).__name__}: {str(e)[:200]}")

    result["duration_sec"] = round(time.time() - task_start, 2)

    # Post-execution issue detection
    if result["duration_sec"] > 120:
        result["issues_detected"].append(
            f"slow_response: {result['duration_sec']}s > 120s threshold"
        )
    if len(result["tool_calls"]) == 0 and result["status"] == "success":
        result["issues_detected"].append(
            "no_tool_calls: task marked success but no tools were called"
        )
    if len(result["artifacts"]) == 0 and result["status"] == "success":
        result["issues_detected"].append(
            "no_artifacts: task marked success but no artifacts produced"
        )
    if result["status"] == "unknown":
        result["issues_detected"].append("no_done_event: stream ended without done event")

    return result


# --- Main ---


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-tasks", type=int, default=15, help="Max tasks per dataset")
    parser.add_argument(
        "--dataset", type=str, default="all", help="Dataset: all|vibe|workbuddy|web|custom"
    )
    parser.add_argument("--timeout", type=int, default=180, help="Per-task timeout (seconds)")
    args = parser.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  FnixAgent Production Test v3")
    print(f"  Backend: {BACKEND_URL}")
    print(f"  Model: qwen3.6-max-preview")
    print(f"  Max tasks/dataset: {args.max_tasks}")
    print(f"  Timeout: {args.timeout}s/task")
    print(f"{'=' * 60}\n")

    # Load tasks
    all_tasks = []
    if args.dataset in ("all", "custom"):
        all_tasks.extend(load_custom_tasks())
    if args.dataset in ("all", "vibe"):
        all_tasks.extend(load_vibe_code_bench(args.max_tasks))
    if args.dataset in ("all", "workbuddy"):
        all_tasks.extend(load_workbuddy_bench(args.max_tasks))
    if args.dataset in ("all", "web"):
        all_tasks.extend(load_web_bench_standalone(args.max_tasks))

    print(f"Loaded {len(all_tasks)} tasks total\n")

    # Check backend health
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{BACKEND_URL}/health", timeout=10.0)
            print(f"Backend health: {health.json()}\n")
        except Exception as e:
            print(f"ERROR: Backend not reachable: {e}")
            sys.exit(1)

    # Execute tasks
    results = []
    issues_summary = []

    async with httpx.AsyncClient() as client:
        for i, task in enumerate(all_tasks, 1):
            print(f"\n[{i}/{len(all_tasks)}] {task['dataset']}/{task['task_id']}")
            print(f"  Prompt: {task['prompt'][:120]}...")
            print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")

            result = await execute_task(client, task, timeout=args.timeout)
            results.append(result)

            print(f"  Status: {result['status']}")
            print(f"  Duration: {result['duration_sec']}s")
            print(f"  Tools: {len(result['tool_calls'])} calls")
            print(f"  Artifacts: {len(result['artifacts'])}")

            if result["issues_detected"]:
                for issue in result["issues_detected"]:
                    print(f"  [ISSUE] {issue}")
                    issues_summary.append(
                        {
                            "task": task["task_id"],
                            "issue": issue,
                        }
                    )

            # Save individual result
            task_file = RESULTS_DIR / f"{i:03d}_{task['task_id'].replace('/', '_')}.json"
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            # Early stop if too many consecutive failures
            recent = [
                r for r in results[-3:] if r["status"] in ("api_error", "timeout", "exception")
            ]
            if len(recent) >= 3:
                print("\n  [WARN] 3 consecutive failures, stopping early")
                break

    # Generate summary report
    summary = {
        "test_time": datetime.now().isoformat(),
        "backend": BACKEND_URL,
        "model": "qwen3.6-max-preview",
        "total_tasks": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "timeout": sum(1 for r in results if r["status"] == "timeout"),
        "api_error": sum(1 for r in results if r["status"] == "api_error"),
        "exception": sum(1 for r in results if r["status"] == "exception"),
        "avg_duration": round(sum(r["duration_sec"] for r in results) / max(len(results), 1), 2),
        "issues_detected": issues_summary,
        "per_dataset": {},
    }

    for ds in set(r["task"]["dataset"] for r in results):
        ds_results = [r for r in results if r["task"]["dataset"] == ds]
        summary["per_dataset"][ds] = {
            "total": len(ds_results),
            "success": sum(1 for r in ds_results if r["status"] == "success"),
            "avg_duration": round(
                sum(r["duration_sec"] for r in ds_results) / max(len(ds_results), 1), 2
            ),
        }

    summary_file = RESULTS_DIR / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  TEST SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total: {summary['total_tasks']}")
    print(f"  Success: {summary['success']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Timeout: {summary['timeout']}")
    print(f"  API Error: {summary['api_error']}")
    print(f"  Exception: {summary['exception']}")
    print(f"  Avg Duration: {summary['avg_duration']}s")
    print(f"  Issues Detected: {len(issues_summary)}")
    for ds, stats in summary["per_dataset"].items():
        print(
            f"    {ds}: {stats['success']}/{stats['total']} success, avg {stats['avg_duration']}s"
        )
    print(f"\n  Results saved to: {RESULTS_DIR}")
    print(f"  Summary: {summary_file}")


if __name__ == "__main__":
    asyncio.run(main())
