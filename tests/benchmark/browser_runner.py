"""
Browser-based benchmark runner.
Tests FnixAgent through the real Tauri frontend using dumate-browser-cli.
Records traces, detects frontend rendering issues, and logs all results.

This is the authentic user testing approach - every task goes through the
actual UI, just like a real user would interact with the application.
"""

import json
import time
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.benchmark.dataset_loader import load_all_datasets, BenchmarkTask

# --- Config ---
FRONTEND_URL = "http://127.0.0.1:5175"
OUTPUT_DIR = Path("E:/FNIX/FnixAgent/test-results/benchmark")
BROWSER_TRACES_DIR = OUTPUT_DIR / "browser_traces"
BROWSER_RESULTS_DIR = OUTPUT_DIR / "browser_results"
REPORTS_DIR = OUTPUT_DIR / "reports"
STATE_FILE = OUTPUT_DIR / "browser_eval_state.json"
REGRESSION_FILE = OUTPUT_DIR / "browser_regression.json"

for d in [BROWSER_TRACES_DIR, BROWSER_RESULTS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Incremental JSONL file for crash-safe progress
INCREMENTAL_FILE = OUTPUT_DIR / "browser_results_incremental.jsonl"

# --- Browser CLI helper ---
CLI = "dumate-browser-cli"


def cli_cmd(args: str, timeout: int = 30, stdin_data: str | None = None) -> tuple[bool, str]:
    """Run a dumate-browser-cli command, return (success, output)."""
    try:
        result = subprocess.run(
            f"{CLI} {args}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=stdin_data,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


def cli_cmd_json(args: str, timeout: int = 30) -> dict:
    """Run CLI command with --json and parse output."""
    ok, output = cli_cmd(f"{args} --json", timeout)
    try:
        # Find JSON in output
        for line in output.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
    except:
        pass
    return {"ok": False, "raw": output}


def fill_input(text: str) -> bool:
    """Fill the input textbox with the given text.
    Uses a single eval call with base64-encoded text to minimize browser round-trips."""
    # Truncate very long prompts
    if len(text) > 12000:
        text = text[:12000] + "\n\n[Task truncated for testing]"

    import base64

    # Single eval: encode entire text as base64, decode and set in one JS call
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

    # Keep JS short to avoid timeout - no TextDecoder, use atob directly
    js = f"(()=>{{const t=document.querySelector('textarea');if(!t)return'e1';try{{const d=decodeURIComponent(escape(atob('{b64}')));const ns=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;ns.call(t,d);t.dispatchEvent(new Event('input',{{bubbles:true}}));return 'ok'}}catch(e){{return'e:'+e.message}}}})()"

    ok, output = cli_cmd(f'eval "{js}"', 15)
    if ok and "ok" in output:
        time.sleep(0.5)
        return True

    # Fallback: chunked approach for very long prompts that cause single-eval timeout
    if len(text) > 3000:
        # Clear global var
        cli_cmd("eval \"window._fp=''\"", 10)
        time.sleep(0.3)

        chunk_size = 1500
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            b64c = base64.b64encode(chunk.encode("utf-8")).decode("ascii")
            js_c = f"window._fp+=decodeURIComponent(escape(atob('{b64c}')))"
            ok, _ = cli_cmd(f'eval "{js_c}"', 10)
            if not ok:
                return False
            time.sleep(0.3)

        js_apply = (
            "(()=>{const t=document.querySelector('textarea');"
            "if(!t)return'no_ta';"
            "const ns=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
            "ns.call(t,window._fp);"
            "t.dispatchEvent(new Event('input',{bubbles:true}));"
            "return 'ok'})()"
        )
        ok, output = cli_cmd(f'eval "{js_apply}"', 10)
        if ok and "ok" in output:
            time.sleep(0.5)
            return True

    return False

    ref_match = re.search(r"textbox.*?\[ref=(e\d+)\]", output)
    if not ref_match:
        return False
    ref = ref_match.group(1)

    # Use eval to set the textarea value via JavaScript
    # Encode text as base64 to avoid all escaping issues
    import base64

    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

    js = f"(()=>{{const t=document.querySelector('textarea');if(!t)throw new Error('no textarea');const s=atob('{b64}');const u=new TextDecoder('utf-8').decode(Uint8Array.from(s,c=>c.charCodeAt(0)));const ns=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;ns.call(t,u);t.dispatchEvent(new Event('input',{{bubbles:true}}));t.dispatchEvent(new Event('change',{{bubbles:true}}));return 'ok'}})()"

    ok, output = cli_cmd(f'eval "{js}"', 15)
    if ok and "ok" in output:
        time.sleep(0.5)
        return True

    # Fallback: try fill with base64-decoded text (short prompts only)
    if len(text) <= 2000:
        # Use a Python-side approach: write to temp file, have browser read via eval
        # Actually just use fill with careful escaping
        # Replace problematic chars for shell
        safe = (
            text.replace("\\", "\\\\").replace("'", "'\\''").replace("`", "\\`").replace("$", "\\$")
        )
        safe = safe.replace("\n", "\\n").replace("\r", "")
        ok, output = cli_cmd(f"fill {ref} '{safe}'", 15)
        return ok

    return False

    ref_match = re.search(r"textbox.*?\[ref=(e\d+)\]", output)
    if not ref_match:
        return False

    ref = ref_match.group(1)
    if len(text) <= 2000:
        escaped = text.replace("'", "'\\''").replace("\n", "\\n")
        ok, output = cli_cmd(f"fill {ref} '{escaped}'", 15)
        return ok

    return False


def ensure_browser_alive() -> bool:
    """Check if browser is alive, recover if needed."""
    ok, output = cli_cmd("snap", 10)
    if ok:
        return True
    # Browser is dead, try to recover
    print("  [WARN] Browser session lost, recovering...", end="", flush=True)
    cli_cmd("recover", 15)
    time.sleep(2)
    cli_cmd("init", 15)
    time.sleep(1)
    cli_cmd(f'open "{FRONTEND_URL}"', 15)
    time.sleep(3)
    ok, _ = cli_cmd("snap", 10)
    if ok:
        print(" OK")
        return True
    print(" FAILED")
    return False


def click_send() -> bool:
    """Click the send button via JavaScript to bypass ref staleness."""
    # Use eval to find and click the send button directly
    js = (
        "(()=>{"
        "const btns=document.querySelectorAll('button');"
        "for(const b of btns){"
        "if(b.textContent.includes('发送')&&!b.disabled){"
        "b.click();return 'ok'"
        "}}"
        "return 'not_found'"
        "})()"
    )
    ok, output = cli_cmd(f'eval "{js}"', 10)
    if ok and "ok" in output:
        return True

    # Fallback: press Enter
    ok, _ = cli_cmd("press Enter", 10)
    return ok


def new_task() -> bool:
    """Click '新任务' button via JavaScript to start a fresh task."""
    # Use eval to click the first "新任务" button
    js = (
        "(()=>{"
        "const btns=document.querySelectorAll('button');"
        "for(const b of btns){"
        "if(b.textContent.includes('新任务')){b.click();return 'ok'}"
        "}"
        "return 'not_found'"
        "})()"
    )
    ok, output = cli_cmd(f'eval "{js}"', 10)
    if ok and "ok" in output:
        # Wait for the input textbox to appear
        for _ in range(5):
            time.sleep(1)
            ok2, snap = cli_cmd("snap", 10)
            if ok2 and "textbox" in snap:
                return True
        return True  # Return true even if we can't verify (click succeeded)

    # Fallback: check if we're already on a new task page
    ok, output = cli_cmd("snap", 10)
    if ok and "textbox" in output and ("有什么可以帮你" in output or "描述要构建" in output):
        return True

    return False

    # Priority 1: sidebar "新任务" button (button with text "新任务" that is NOT inside main area)
    # The sidebar one appears as: button "新任务" [ref=eXX]
    # We want the first one (sidebar), not the one inside main
    matches = re.findall(r'button "新任务" \[ref=(e\d+)\]', output)
    if matches:
        ref = matches[0]  # First match is sidebar button
        ok, _ = cli_cmd(f"click {ref}", 10)
        if ok:
            for _ in range(5):
                time.sleep(1)
                ok2, snap = cli_cmd("snap", 10)
                if ok2 and "textbox" in snap:
                    return True
        # Try second match if first didn't work
        if len(matches) > 1:
            ref = matches[1]
            ok, _ = cli_cmd(f"click {ref}", 10)
            if ok:
                for _ in range(5):
                    time.sleep(1)
                    ok2, snap = cli_cmd("snap", 10)
                    if ok2 and "textbox" in snap:
                        return True

    # Priority 2: check if we're already on a new task page (textbox visible)
    if "textbox" in output and ("有什么可以帮你" in output or "描述要构建" in output):
        return True

    # Priority 3: try any button containing "新任务" text
    match = re.search(r"button.*?\[ref=(e\d+)\][^\n]*新任务", output)
    if match:
        ref = match.group(1)
        ok, _ = cli_cmd(f"click {ref}", 10)
        if ok:
            for _ in range(5):
                time.sleep(1)
                ok2, snap = cli_cmd("snap", 10)
                if ok2 and "textbox" in snap:
                    return True

    return False

    # Find and click "新任务" button - try multiple patterns
    # Pattern 1: button with text "新任务"
    match = re.search(r'button "新任务" \[ref=(e\d+)\]', output)
    if not match:
        # Pattern 2: button containing "新任务" text
        match = re.search(r"button.*?\[ref=(e\d+)\][^\n]*新任务", output)
    if not match:
        # Pattern 3: any button with "新任务" nearby
        match = re.search(r"新任务.*?\[ref=(e\d+)\]", output)

    if match:
        ref = match.group(1)
        ok, _ = cli_cmd(f"click {ref}", 10)
        if ok:
            # Wait for the input textbox to appear
            for _ in range(5):
                time.sleep(1)
                ok2, snap = cli_cmd("snap", 10)
                if ok2 and "textbox" in snap:
                    return True
        return ok

    # If no "新任务" button found, try clicking on the Fnix logo/heading
    match2 = re.search(r'heading "有什么可以帮你？" \[level=1\] \[ref=(e\d+)\]', output)
    if match2:
        # The page is already in new task state
        return True

    return False


def wait_for_completion(timeout: int = 180, original_prompt: str = "") -> dict:
    """Wait for agent to complete the task. Returns completion info."""
    start = time.time()
    result = {
        "completed": False,
        "duration_s": 0,
        "has_text": False,
        "has_artifacts": False,
        "has_error": False,
        "final_text": "",
        "steps_seen": [],
        "rendering_issues": [],
    }

    last_snap = ""
    stagnant_count = 0

    while time.time() - start < timeout:
        time.sleep(3)
        elapsed = int(time.time() - start)

        ok, snap = cli_cmd("snap", 10)
        if not ok:
            continue

        result["duration_s"] = round(time.time() - start, 1)

        # Check for completion signals
        if "done" in snap.lower() or "完成" in snap:
            result["completed"] = True
        if "交付" in snap or "已生成" in snap or "artifacts" in snap.lower():
            result["has_artifacts"] = True

        # Check for error signals
        if "error" in snap.lower() and "agentd: 已连接" not in snap:
            result["has_error"] = True

        # Check for text content (agent response)
        if "paragraph" in snap or "heading" in snap:
            result["has_text"] = True

        # Detect rendering issues
        issues = detect_rendering_issues(snap, original_prompt)
        for issue in issues:
            if issue not in result["rendering_issues"]:
                result["rendering_issues"].append(issue)

        # Check if page is stagnant (no changes for 15s after having some content)
        if snap == last_snap:
            stagnant_count += 1
        else:
            stagnant_count = 0
            last_snap = snap

        # If we have content and it's been stagnant for 5 checks (15s), consider it done
        if result["has_text"] and stagnant_count >= 5:
            result["completed"] = True
            break

        # If we see explicit done signal
        if result["completed"] and stagnant_count >= 2:
            break

    if not result["completed"]:
        result["completed"] = result["has_text"]  # If we got text, consider it done

    # Get final text from last snapshot
    result["final_text"] = extract_text_from_snap(last_snap)
    result["snap_length"] = len(last_snap)

    return result


def detect_rendering_issues(snap: str, original_prompt: str = "") -> list[str]:
    """Detect frontend rendering issues from snapshot.

    Smart detection: only flag error patterns when they appear in UI error
    contexts (error boundaries, toast notifications), NOT when they are part
    of the agent's response text discussing those concepts (e.g. a coding
    task about Python TypeError handling).
    """
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

    # Smart error detection: only flag errors that appear in error UI contexts
    # (error boundaries, toast notifications), not in the agent's response text.
    #
    # Heuristic: if the error keyword also appears in the original prompt, it's
    # very likely the agent is discussing that concept as part of its response.
    # Also check if the error appears inside a code/paragraph context (legitimate)
    # vs. in a standalone error element.
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
    prompt_has_typeerror = "typeerror".lower() in prompt_lower
    prompt_has_error = "error" in prompt_lower

    for pattern in error_patterns:
        if pattern not in snap:
            continue

        # Skip if the pattern concept is part of the task prompt (agent is
        # legitimately discussing it)
        pattern_base = pattern.rstrip(":").lower()
        if pattern_base in prompt_lower:
            continue
        if pattern_base == "typeerror" and prompt_has_typeerror:
            continue
        if pattern_base == "syntaxerror" and "syntaxerror" in prompt_lower:
            continue

        # Check if the error appears in a genuine error UI context.
        # In the snap format, error boundaries / toast notifications appear as
        # standalone elements, not inside paragraph/heading/code blocks.
        lines = snap.split("\n")
        in_content_block = False
        found_in_error_context = False

        for line in lines:
            line_lower = line.lower().strip()
            # Track if we're inside a content block (paragraph, heading, code)
            if any(tag in line_lower for tag in ["paragraph", "heading", "code", "pre"]):
                in_content_block = True
                continue
            # If we hit a new element boundary, reset
            if line_lower.startswith("button") or line_lower.startswith("div"):
                in_content_block = False

            # If pattern appears outside a content block, it might be an error element
            if pattern in line and not in_content_block:
                # But only flag if it looks like a standalone error (short line, no sentence structure)
                clean = re.sub(r"\[ref=e\d+\]|\[level=\d+\]|\[cursor=pointer\]", "", line).strip()
                if len(clean) < 200 and not clean.endswith("."):
                    found_in_error_context = True
                    break

        if found_in_error_context:
            issues.append(f"error_visible: {pattern}")

    return issues


def extract_text_from_snap(snap: str) -> str:
    """Extract readable text from snapshot."""
    lines = []
    for line in snap.split("\n"):
        # Remove ref annotations
        clean = re.sub(r"\[ref=e\d+\]", "", line)
        clean = re.sub(r"\[cursor=pointer\]", "", clean)
        clean = re.sub(r"\[selected\]", "", clean)
        clean = re.sub(r"\[active\]", "", clean)
        clean = re.sub(r"\[disabled\]", "", clean)
        clean = clean.strip()
        if clean and not clean.startswith("-") and not clean.startswith("###"):
            lines.append(clean)
    return "\n".join(lines)[:2000]


def run_single_task(task: BenchmarkTask, task_index: int) -> dict:
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
        "frontend_errors": [],
        "has_text_response": False,
        "has_artifacts": False,
        "response_preview": "",
        "failure_category": "",
        "failure_detail": "",
    }

    # Ensure browser is alive before starting
    if not ensure_browser_alive():
        result["status"] = "error"
        result["failure_category"] = "browser_dead"
        result["failure_detail"] = "Browser session could not be recovered"
        return result

    # Start new task - but if textbox is already visible, skip
    ok, snap = cli_cmd("snap", 10)
    if not ok:
        result["status"] = "error"
        result["failure_category"] = "ui_snap_failed"
        result["failure_detail"] = "Could not get page snapshot"
        return result

    # Check if we already have a clean textbox (new task page)
    textbox_visible = "textbox" in snap and ("有什么可以帮你" in snap or "描述要构建" in snap)

    if not textbox_visible:
        if not new_task():
            # Even if new_task failed, check if textbox appeared anyway
            ok2, snap2 = cli_cmd("snap", 10)
            if not ok2 or "textbox" not in snap2:
                result["status"] = "error"
                result["failure_category"] = "ui_new_task_failed"
                result["failure_detail"] = "Could not click '新任务' button and no textbox found"
                return result

    time.sleep(1)

    # Fill input
    if not fill_input(task.prompt):
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
    result["response_preview"] = completion["final_text"][:500]

    # Classify result
    if completion["has_error"] and not completion["has_text"]:
        result["status"] = "error"
        result["failure_category"] = "backend_error"
        result["failure_detail"] = "Agent returned error without text"
    elif not completion["has_text"]:
        result["status"] = "fail"
        result["failure_category"] = "no_output"
        result["failure_detail"] = "No text response received"
    elif completion["rendering_issues"]:
        result["status"] = "fail"
        result["failure_category"] = "rendering_issue"
        result["failure_detail"] = "; ".join(completion["rendering_issues"])
    else:
        result["status"] = "pass"

    # Save full trace for failed/error tasks
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
        trace_file = (
            BROWSER_TRACES_DIR / f"{task.unique_id.replace('/', '_').replace('::', '__')}.json"
        )
        trace_file.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


class BrowserBenchmarkRunner:
    """Runs benchmark tasks through the browser."""

    def __init__(self):
        self.state = self._load_state()
        self.all_results = []
        self.bugs_found = []

    def _append_incremental(self, result: dict):
        """Append a single result to the incremental JSONL file (crash-safe)."""
        with open(INCREMENTAL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {"completed": {}, "stats": {"total": 0, "pass": 0, "fail": 0, "error": 0}}

    def _save_state(self):
        STATE_FILE.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _is_completed(self, task: BenchmarkTask) -> bool:
        return task.unique_id in self.state["completed"]

    def run_all(self, datasets: dict, max_per_dataset: int = 0, max_total: int = 0):
        """Run all tasks through the browser."""
        total_tasks = sum(len(v) for v in datasets.values())
        completed = len(self.state["completed"])

        print(f"\n{'=' * 60}")
        print(f"  FnixAgent Browser-Based Benchmark Evaluation")
        print(f"  Total tasks: {total_tasks} | Completed: {completed}")
        print(f"  Testing through: {FRONTEND_URL}")
        print(f"{'=' * 60}\n")

        task_num = 0
        pass_count = self.state["stats"]["pass"]
        fail_count = self.state["stats"]["fail"]
        error_count = self.state["stats"]["error"]
        start_time = time.time()

        for dataset_name, tasks in datasets.items():
            if max_per_dataset > 0:
                tasks = tasks[:max_per_dataset]

            print(f"\n--- Dataset: {dataset_name} ({len(tasks)} tasks) ---")

            for i, task in enumerate(tasks):
                if max_total > 0 and task_num >= max_total:
                    break

                if self._is_completed(task):
                    task_num += 1
                    continue

                task_num += 1
                elapsed = int(time.time() - start_time)
                rate = task_num / max(elapsed, 1)
                eta = int((total_tasks - task_num - completed) / max(rate, 0.01))
                print(
                    f"  [{task_num}/{total_tasks}] {task.dataset}/{task.task_id[:45]}... ",
                    end="",
                    flush=True,
                )

                result = run_single_task(task, task_num)
                self.all_results.append(result)

                # Incremental write (crash-safe)
                self._append_incremental(result)

                # Update state
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

                # Check for fixable bugs
                if result["status"] != "pass":
                    self._check_for_fixable_bug(result)

                # Periodic progress + health check every 10 tasks
                if task_num % 10 == 0:
                    total_done = pass_count + fail_count + error_count
                    sr = round(pass_count / max(total_done, 1) * 100, 1)
                    print(
                        f"  --- Progress: {total_done}/{total_tasks} "
                        f"| Pass:{pass_count} Fail:{fail_count} Err:{error_count} "
                        f"| SR:{sr}% | ETA:{eta}s ---"
                    )
                    if not ensure_browser_alive():
                        print("  [WARN] Could not recover browser, waiting 10s...")
                        time.sleep(10)
                        ensure_browser_alive()

            if max_total > 0 and task_num >= max_total:
                break

        # Generate reports
        self._generate_reports()

        return self.all_results

    def _check_for_fixable_bug(self, result: dict):
        """Identify fixable bugs from failures."""
        detail = result.get("failure_detail", "")
        category = result.get("failure_category", "")

        # Track rendering bugs
        if category == "rendering_issue":
            self.bugs_found.append(
                {
                    "type": "rendering",
                    "detail": detail,
                    "task": result["unique_id"],
                }
            )

        # Track UI interaction bugs
        if category.startswith("ui_"):
            self.bugs_found.append(
                {
                    "type": "ui_interaction",
                    "detail": detail,
                    "task": result["unique_id"],
                }
            )

    def _generate_reports(self):
        """Generate regression set and summary report."""
        from collections import Counter, defaultdict

        if not self.all_results:
            # Include state for stats
            stats = self.state["stats"]
            report = {
                "generated_at": datetime.now().isoformat(),
                "note": "Resumed run - stats from state file",
                "summary": {
                    "total_tasks": stats["total"],
                    "passed": stats["pass"],
                    "failed": stats["fail"],
                    "errors": stats["error"],
                    "success_rate": round(stats["pass"] / max(stats["total"], 1) * 100, 1),
                },
            }
        else:
            failed = [r for r in self.all_results if r["status"] != "pass"]
            passed = [r for r in self.all_results if r["status"] == "pass"]

            # Per-dataset stats
            dataset_stats = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "error": 0})
            failure_types = Counter()

            for r in self.all_results:
                ds = r["dataset"]
                dataset_stats[ds]["total"] += 1
                dataset_stats[ds][r["status"]] += 1
                if r["status"] != "pass":
                    failure_types[r["failure_category"]] += 1

            total = len(self.all_results)
            report = {
                "generated_at": datetime.now().isoformat(),
                "testing_method": "browser_automation_via_tauri_frontend",
                "frontend_url": FRONTEND_URL,
                "summary": {
                    "total_tasks": total,
                    "passed": len(passed),
                    "failed": len(failed),
                    "errors": sum(1 for r in self.all_results if r["status"] == "error"),
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
                "total_failed": len(failed),
                "test_cases": [
                    {
                        "dataset": r["dataset"],
                        "task_id": r["task_id"],
                        "prompt_preview": r["prompt_preview"],
                        "failure_category": r["failure_category"],
                        "failure_detail": r["failure_detail"],
                    }
                    for r in failed
                ],
            }
            REGRESSION_FILE.write_text(
                json.dumps(regression, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        report_file = (
            REPORTS_DIR / f"browser_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (REPORTS_DIR / "browser_summary_latest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Save all results
        results_file = (
            BROWSER_RESULTS_DIR / f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        results_file.write_text(
            json.dumps(self.all_results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Print summary
        print(f"\n{'=' * 60}")
        print(f"  BROWSER EVALUATION SUMMARY")
        print(f"{'=' * 60}")
        s = report["summary"]
        print(
            f"  Total: {s['total_tasks']} | Pass: {s['passed']} | Fail: {s['failed']} | Error: {s['errors']}"
        )
        print(f"  Success Rate: {s['success_rate']}%")
        if "per_dataset" in report:
            print(f"\n  Per Dataset:")
            for ds, stats in report["per_dataset"].items():
                print(
                    f"    {ds:25s} {stats['pass']:4d}/{stats['total']:4d} ({stats['success_rate']:5.1f}%)"
                )
        if "failure_type_distribution" in report and report["failure_type_distribution"]:
            print(f"\n  Failure Types:")
            for ftype, count in report["failure_type_distribution"].items():
                print(f"    {ftype:30s} {count:4d}")
        if "rendering_issues_found" in report and report["rendering_issues_found"]:
            print(f"\n  Rendering Issues:")
            for issue in report["rendering_issues_found"]:
                print(f"    - {issue}")
        if self.bugs_found:
            print(f"\n  Bugs Identified: {len(self.bugs_found)}")
        print(f"\n  Reports: {report_file}")
        print(f"  Regression: {REGRESSION_FILE}")
        print(f"{'=' * 60}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-dataset", type=int, default=0)
    parser.add_argument("--max-total", type=int, default=0)
    parser.add_argument("--dataset", type=str, default="")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        print("State reset.")

    print("Loading datasets...")
    datasets = load_all_datasets()

    if args.dataset:
        datasets = {k: v for k, v in datasets.items() if k == args.dataset}

    runner = BrowserBenchmarkRunner()
    runner.run_all(
        datasets,
        max_per_dataset=args.max_per_dataset,
        max_total=args.max_total,
    )


if __name__ == "__main__":
    main()
