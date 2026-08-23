"""
Problem Detector - Analyzes execution traces to detect 5 categories of problems.

Categories (inspired by DeepEval + AgentBench):
1. Planning errors: Agent forgets next step, loops, or produces incoherent plan
2. Tool call parameter errors: Wrong tool selected, incorrect arguments
3. Missing rollback: Tool failure without retry or fallback
4. Multi-turn interruption: Session breaks, context lost, memory forgotten
5. MCP call failures: MCP tool discovery/discovery/execution errors
"""

from dataclasses import dataclass, field
from typing import Optional
from .trace_collector import ExecutionTrace


@dataclass
class Problem:
    """A detected problem in agent execution."""

    category: str  # planning / tool_params / rollback / interruption / mcp
    severity: str  # critical / high / medium / low
    step_index: int
    description: str
    evidence: str
    suggestion: str


@dataclass
class TestCaseResult:
    """Result of evaluating a single test case."""

    test_id: str
    test_name: str
    trace: ExecutionTrace
    problems: list[Problem] = field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    pass_status: str = "pass"  # pass / fail / partial / blocked
    score: float = 1.0  # 0.0 to 1.0
    llm_judge_feedback: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "pass_status": self.pass_status,
            "score": round(self.score, 2),
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "duration_s": round(self.trace.total_duration_s, 2),
            "step_count": self.trace.step_count,
            "tool_calls": self.trace.tool_call_count,
            "tool_names": self.trace.tool_names_used,
            "problems": [
                {
                    "category": p.category,
                    "severity": p.severity,
                    "step_index": p.step_index,
                    "description": p.description,
                    "evidence": p.evidence[:200],
                    "suggestion": p.suggestion,
                }
                for p in self.problems
            ],
            "llm_judge_feedback": self.llm_judge_feedback,
        }


class ProblemDetector:
    """Detects problems in agent execution traces."""

    def detect(self, trace: ExecutionTrace, expected: dict) -> list[Problem]:
        """Analyze a trace and return detected problems."""
        problems: list[Problem] = []

        # 1. Planning errors
        problems.extend(self._detect_planning_errors(trace, expected))

        # 2. Tool call parameter errors
        problems.extend(self._detect_tool_param_errors(trace, expected))

        # 3. Missing rollback
        problems.extend(self._detect_rollback_issues(trace))

        # 4. Multi-turn interruption
        problems.extend(self._detect_interruptions(trace))

        # 5. MCP call failures
        problems.extend(self._detect_mcp_failures(trace))

        return problems

    def _detect_planning_errors(self, trace: ExecutionTrace, expected: dict) -> list[Problem]:
        problems: list[Problem] = []

        # Check if agent produced any output
        if not trace.saw_text and not trace.saw_done and not trace.blocked_by_safety:
            problems.append(
                Problem(
                    category="planning",
                    severity="critical",
                    step_index=0,
                    description="Agent produced no text output and did not signal completion",
                    evidence=f"saw_done={trace.saw_done}, saw_text={trace.saw_text}, errors={trace.errors}",
                    suggestion="Check if the LLM connection is working and the agent loop is executing correctly",
                )
            )

        # Check for excessive steps (potential loop)
        max_expected_steps = expected.get("max_steps", 10)
        if trace.step_count > max_expected_steps:
            problems.append(
                Problem(
                    category="planning",
                    severity="medium",
                    step_index=trace.step_count,
                    description=f"Agent took {trace.step_count} steps, exceeding expected max of {max_expected_steps}",
                    evidence=f"step_count={trace.step_count}, expected_max={max_expected_steps}",
                    suggestion="Investigate whether the agent is looping or stuck in a retry cycle",
                )
            )

        # Check for empty final text when text was expected
        if (
            expected.get("expect_text", True)
            and not trace.final_text
            and not trace.blocked_by_safety
        ):
            problems.append(
                Problem(
                    category="planning",
                    severity="high",
                    step_index=trace.step_count,
                    description="Agent completed but produced no text response",
                    evidence=f"final_text_length={len(trace.final_text)}",
                    suggestion="Check if the agent's response is being captured in the correct chunk type",
                )
            )

        # Check for duplicate tool calls (same tool, same args)
        tool_calls = [(s.tool_name, str(s.tool_args)) for s in trace.steps if s.tool_name]
        for i in range(1, len(tool_calls)):
            if tool_calls[i] == tool_calls[i - 1] and tool_calls[i][0] != "write_file":
                problems.append(
                    Problem(
                        category="planning",
                        severity="medium",
                        step_index=trace.steps[i].step_index if i < len(trace.steps) else 0,
                        description=f"Duplicate tool call: {tool_calls[i][0]} with same args",
                        evidence=f"tool={tool_calls[i][0]}, args={tool_calls[i][1][:100]}",
                        suggestion="Agent may be stuck repeating the same action; add loop detection",
                    )
                )
                break

        return problems

    def _detect_tool_param_errors(self, trace: ExecutionTrace, expected: dict) -> list[Problem]:
        problems: list[Problem] = []

        expected_tools = expected.get("expected_tools", [])
        if expected_tools:
            used_tools = set(trace.tool_names_used)
            missing_tools = set(expected_tools) - used_tools
            if missing_tools:
                problems.append(
                    Problem(
                        category="tool_params",
                        severity="medium",
                        step_index=0,
                        description=f"Expected tools not used: {missing_tools}",
                        evidence=f"used={used_tools}, expected={set(expected_tools)}",
                        suggestion="Check if the agent is selecting the correct tools for this task",
                    )
                )

        # Check for failed tool calls
        for step in trace.steps:
            if step.tool_success is False:
                problems.append(
                    Problem(
                        category="tool_params",
                        severity="high",
                        step_index=step.step_index,
                        description=f"Tool '{step.tool_name}' returned failure",
                        evidence=f"tool={step.tool_name}, result={step.tool_result[:150] if step.tool_result else 'N/A'}",
                        suggestion=f"Check tool parameters for '{step.tool_name}'; verify args match the expected schema",
                    )
                )

        return problems

    def _detect_rollback_issues(self, trace: ExecutionTrace) -> list[Problem]:
        problems: list[Problem] = []

        # Check if any tool failed and agent didn't retry
        failed_tools = [s for s in trace.steps if s.tool_success is False]
        for failed_step in failed_tools:
            # Look for retry of same tool within next 3 steps
            found_retry = False
            for i in range(
                failed_step.step_index + 1, min(failed_step.step_index + 4, len(trace.steps))
            ):
                if trace.steps[i].tool_name == failed_step.tool_name:
                    found_retry = True
                    break

            if not found_retry and not trace.saw_done:
                problems.append(
                    Problem(
                        category="rollback",
                        severity="high",
                        step_index=failed_step.step_index,
                        description=f"Tool '{failed_step.tool_name}' failed but agent did not retry or provide fallback",
                        evidence=f"tool={failed_step.tool_name}, success={failed_step.tool_success}",
                        suggestion="Add retry logic or fallback strategy when tools fail",
                    )
                )

        # Check if agent encountered errors but didn't continue
        if trace.errors and not trace.saw_done and not trace.blocked_by_safety:
            problems.append(
                Problem(
                    category="rollback",
                    severity="high",
                    step_index=trace.step_count,
                    description="Agent encountered errors but did not complete execution",
                    evidence=f"errors={trace.errors[:2]}",
                    suggestion="Add error recovery: catch exceptions, log context, and continue or gracefully exit",
                )
            )

        return problems

    def _detect_interruptions(self, trace: ExecutionTrace) -> list[Problem]:
        problems: list[Problem] = []

        # Check for missing done signal
        if not trace.saw_done and not trace.blocked_by_safety and trace.total_duration_s > 5:
            problems.append(
                Problem(
                    category="interruption",
                    severity="high",
                    step_index=trace.step_count,
                    description="Agent execution ended without a 'done' signal - possible interruption",
                    evidence=f"saw_done={trace.saw_done}, duration={trace.total_duration_s:.1f}s",
                    suggestion="Check for timeout, network interruption, or unhandled exception in the agent loop",
                )
            )

        # Check for missing trace_id (session management issue)
        if not trace.trace_id:
            problems.append(
                Problem(
                    category="interruption",
                    severity="low",
                    step_index=0,
                    description="No trace_id in mission chunk - session tracking may be broken",
                    evidence="trace_id is None",
                    suggestion="Ensure the backend assigns a trace_id for every execution",
                )
            )

        return problems

    def _detect_mcp_failures(self, trace: ExecutionTrace) -> list[Problem]:
        problems: list[Problem] = []

        # Check for MCP-related tool calls
        mcp_tools = [s for s in trace.steps if s.tool_name and "mcp" in s.tool_name.lower()]
        for mcp_step in mcp_tools:
            if mcp_step.tool_success is False:
                problems.append(
                    Problem(
                        category="mcp",
                        severity="critical",
                        step_index=mcp_step.step_index,
                        description=f"MCP tool '{mcp_step.tool_name}' failed",
                        evidence=f"tool={mcp_step.tool_name}, result={mcp_step.tool_result[:150] if mcp_step.tool_result else 'N/A'}",
                        suggestion="Check MCP server connectivity, tool schema, and parameter types",
                    )
                )

        # Check for MCP discovery errors in error messages
        for err in trace.errors:
            if "mcp" in err.lower() or "tool_discovery" in err.lower():
                problems.append(
                    Problem(
                        category="mcp",
                        severity="high",
                        step_index=0,
                        description="MCP-related error detected in error stream",
                        evidence=err[:200],
                        suggestion="Verify MCP server is running and tool list is accessible",
                    )
                )

        return problems
