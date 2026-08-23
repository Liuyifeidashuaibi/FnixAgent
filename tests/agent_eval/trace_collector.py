"""
Trace Collector - Captures step-by-step execution traces from FnixAgent's NDJSON stream.

Inspired by DeepEval's trace capture and LangSmith's execution tracing.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Optional, cast


@dataclass
class TraceStep:
    """Single step in an agent execution trace."""

    step_index: int
    step_type: str  # mission, evolution, skill_retrieved, route_decision, thinking, action, observation, text, done, error
    timestamp: float
    content: Any = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    tool_result: Optional[str] = None
    tool_success: Optional[bool] = None
    description: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass
class ExecutionTrace:
    """Complete execution trace for a single test case."""

    test_id: str
    prompt: str
    work_mode: str
    steps: list[TraceStep] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_s: float = 0.0
    final_text: str = ""
    artifacts: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    skill_score: Optional[float] = None
    saw_done: bool = False
    saw_text: bool = False
    # Metrics
    step_count: int = 0
    tool_call_count: int = 0
    tool_names_used: list[str] = field(default_factory=list)
    blocked_by_safety: bool = False
    safety_block_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "prompt": self.prompt,
            "work_mode": self.work_mode,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_s": round(self.total_duration_s, 2),
            "step_count": self.step_count,
            "tool_call_count": self.tool_call_count,
            "tool_names_used": self.tool_names_used,
            "final_text_length": len(self.final_text),
            "final_text_preview": self.final_text[:500],
            "artifacts": self.artifacts,
            "errors": self.errors,
            "saw_done": self.saw_done,
            "saw_text": self.saw_text,
            "blocked_by_safety": self.blocked_by_safety,
            "safety_block_reason": self.safety_block_reason,
            "skill_score": self.skill_score,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "steps": [
                {
                    "step_index": s.step_index,
                    "step_type": s.step_type,
                    "timestamp": s.timestamp,
                    "tool_name": s.tool_name,
                    "tool_args": s.tool_args,
                    "tool_result": s.tool_result[:200] if s.tool_result else None,
                    "tool_success": s.tool_success,
                    "description": s.description,
                    "duration_ms": s.duration_ms,
                }
                for s in self.steps
            ],
        }


class TraceCollector:
    """Collects execution traces from FnixAgent's work/stream API."""

    def __init__(self, api_base: str = "http://127.0.0.1:8003"):
        self.api_base = api_base.rstrip("/")

    def collect(
        self,
        test_id: str,
        prompt: str,
        work_mode: str,
        llm_config: dict,
        timeout: int = 120,
    ) -> ExecutionTrace:
        """Send a request to FnixAgent and collect the full execution trace."""
        trace = ExecutionTrace(
            test_id=test_id,
            prompt=prompt,
            work_mode=work_mode,
            start_time=time.time(),
        )

        data = json.dumps(
            {"user_input": prompt, "work_mode": work_mode, "llm": llm_config}
        ).encode()

        req = urllib.request.Request(
            f"{self.api_base}/api/v1/work/stream",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            result = resp.read().decode()
            trace.end_time = time.time()
            trace.total_duration_s = trace.end_time - trace.start_time

            lines = result.strip().split("\n")
            step_idx = 0

            for line in lines:
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                chunk_type = obj.get("chunk_type", "")
                content = obj.get("content", "")
                ts = obj.get("timestamp", time.time())

                step = TraceStep(
                    step_index=step_idx,
                    step_type=chunk_type,
                    timestamp=ts,
                    content=content,
                )

                # Extract tool info
                if chunk_type in ("action", "tool_call") and isinstance(content, dict):
                    step.tool_name = str(content.get("name", "unknown"))
                    step.tool_args = content.get("args", {})
                    trace.tool_names_used.append(step.tool_name)
                    trace.tool_call_count += 1

                if chunk_type in ("observation", "tool_result") and isinstance(content, dict):
                    step.tool_success = content.get("success", True)
                    step.tool_result = str(content.get("summary", content.get("content", "")))[:500]

                if chunk_type == "mission" and isinstance(content, dict):
                    trace.trace_id = content.get("trace_id")
                    trace.session_id = content.get("session_id")
                    step.description = content.get("title", "")

                if chunk_type == "text" and isinstance(content, str):
                    trace.final_text = content
                    trace.saw_text = True

                if chunk_type == "done":
                    trace.saw_done = True
                    if isinstance(content, dict):
                        arts = content.get("artifacts", [])
                        if arts:
                            trace.artifacts = arts

                if chunk_type == "error":
                    err_msg: str = str(content)[:500] if content else "Unknown error"
                    trace.errors.append(err_msg)
                    if "安全" in err_msg or "拦截" in err_msg:
                        trace.blocked_by_safety = True
                        trace.safety_block_reason = err_msg

                if chunk_type == "skill_saved" and isinstance(content, dict):
                    trace.skill_score = content.get("score")

                if chunk_type == "step_start":
                    trace.step_count += 1

                trace.steps.append(step)
                step_idx += 1

        except urllib.error.HTTPError as e:
            trace.end_time = time.time()
            trace.total_duration_s = trace.end_time - trace.start_time
            trace.errors.append(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            trace.end_time = time.time()
            trace.total_duration_s = trace.end_time - trace.start_time
            trace.errors.append(f"{type(e).__name__}: {str(e)[:300]}")

        return trace
