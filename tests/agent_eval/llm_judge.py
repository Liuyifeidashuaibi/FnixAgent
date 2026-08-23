"""
LLM-as-Judge Module - Uses an LLM to evaluate agent execution traces.

Inspired by DeepEval's LLM-as-judge mechanism and Confident AI's scoring approach.
Instead of pure rule-based detection, this module sends the execution trace to
an LLM (kimi-k2.5 via Bailian) and gets structured feedback on 5 dimensions:

1. Task Completion - Did the agent accomplish what was asked?
2. Tool Call Quality - Were the right tools used with correct parameters?
3. Planning Coherence - Was the agent's plan logical and efficient?
4. Error Recovery - Did the agent handle failures gracefully?
5. Output Quality - Was the final output useful and well-structured?

Each dimension gets a 0.0-1.0 score and qualitative feedback.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

from .trace_collector import ExecutionTrace


@dataclass
class JudgeDimension:
    """Single dimension of LLM judge evaluation."""

    name: str
    score: float  # 0.0 to 1.0
    feedback: str
    issues: list[str] = field(default_factory=list)


@dataclass
class JudgeResult:
    """Complete LLM judge result for a test case."""

    test_id: str
    overall_score: float  # 0.0 to 1.0
    dimensions: list[JudgeDimension]
    summary: str
    problem_categories: list[str]  # e.g. ["planning", "tool_params"]
    recommendation: str  # "pass" / "fix_needed" / "critical_failure"

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "overall_score": round(self.overall_score, 2),
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 2),
                    "feedback": d.feedback,
                    "issues": d.issues,
                }
                for d in self.dimensions
            ],
            "summary": self.summary,
            "problem_categories": self.problem_categories,
            "recommendation": self.recommendation,
        }


class LLMJudge:
    """Evaluates agent traces using an LLM as judge."""

    JUDGE_PROMPT_TEMPLATE = """You are an expert AI Agent evaluator. You are evaluating the execution trace of an AI Agent called FnixAgent.

## Task Description
The user asked: "{prompt}"
Work mode: {work_mode}
Expected behavior: {expected_behavior}

## Execution Trace
The agent produced the following execution trace:

{trace_summary}

## Agent's Final Output
{final_output}

## Artifacts Created
{artifacts_summary}

## Errors Encountered
{errors_summary}

## Evaluation Instructions
Evaluate the agent's performance on 5 dimensions. For each dimension, give a score (0.0 to 1.0) and brief feedback.

1. **task_completion**: Did the agent accomplish what the user asked? Was the task fully completed?
2. **tool_quality**: Were the correct tools used? Were tool parameters correct? Any unnecessary tool calls?
3. **planning**: Was the agent's approach logical? Did it plan before acting? Any loops or redundant steps?
4. **error_recovery**: Did the agent handle errors gracefully? Did it retry or provide fallbacks when tools failed?
5. **output_quality**: Was the final output useful, well-structured, and accurate?

## Output Format
Respond with ONLY a JSON object (no markdown, no explanation outside JSON):

{{
  "overall_score": 0.0-1.0,
  "dimensions": [
    {{
      "name": "task_completion",
      "score": 0.0-1.0,
      "feedback": "brief feedback",
      "issues": ["issue1", "issue2"]
    }},
    {{
      "name": "tool_quality",
      "score": 0.0-1.0,
      "feedback": "brief feedback",
      "issues": ["issue1"]
    }},
    {{
      "name": "planning",
      "score": 0.0-1.0,
      "feedback": "brief feedback",
      "issues": []
    }},
    {{
      "name": "error_recovery",
      "score": 0.0-1.0,
      "feedback": "brief feedback",
      "issues": []
    }},
    {{
      "name": "output_quality",
      "score": 0.0-1.0,
      "feedback": "brief feedback",
      "issues": []
    }}
  ],
  "summary": "1-2 sentence overall assessment",
  "problem_categories": ["planning", "tool_params", "rollback", "interruption", "mcp"],
  "recommendation": "pass" | "fix_needed" | "critical_failure"
}}

## Scoring Guide
- 0.9-1.0: Excellent, no issues
- 0.7-0.89: Good, minor issues
- 0.5-0.69: Acceptable, some issues need fixing
- 0.3-0.49: Poor, significant problems
- 0.0-0.29: Critical failure

## Problem Categories
- "planning": Agent forgot next step, looped, or produced incoherent plan
- "tool_params": Wrong tool selected, incorrect arguments
- "rollback": Tool failure without retry or fallback
- "interruption": Session broke, context lost, memory forgotten
- "mcp": MCP tool discovery/execution errors
"""

    def __init__(self, llm_config: dict):
        self.llm_config = llm_config
        self.api_key = llm_config.get("api_key", "")
        self.base_url = llm_config.get("base_url", "")
        self.model = llm_config.get("model", "kimi-k2.5")

    def judge(self, trace: ExecutionTrace, expected: dict) -> Optional[JudgeResult]:
        """Evaluate a trace using the LLM judge. Returns None if judge fails."""
        prompt = self._build_judge_prompt(trace, expected)
        response = self._call_llm(prompt)
        if not response:
            return None

        try:
            # Extract JSON from response (handle markdown code blocks)
            text = response.strip()
            if text.startswith("```"):
                # Remove markdown code fence
                lines = text.split("\n")
                json_lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(json_lines)

            data = json.loads(text)

            dimensions = []
            for d in data.get("dimensions", []):
                dimensions.append(
                    JudgeDimension(
                        name=d.get("name", ""),
                        score=float(d.get("score", 0.0)),
                        feedback=d.get("feedback", ""),
                        issues=d.get("issues", []),
                    )
                )

            return JudgeResult(
                test_id=trace.test_id,
                overall_score=float(data.get("overall_score", 0.0)),
                dimensions=dimensions,
                summary=data.get("summary", ""),
                problem_categories=data.get("problem_categories", []),
                recommendation=data.get("recommendation", "fix_needed"),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"    [LLM Judge] Failed to parse response: {e}", flush=True)
            return None

    def _build_judge_prompt(self, trace: ExecutionTrace, expected: dict) -> str:
        """Build the judge prompt from trace data."""
        # Summarize trace steps
        step_lines = []
        for s in trace.steps:
            line = f"  Step {s.step_index} [{s.step_type}]"
            if s.tool_name:
                args_preview = str(s.tool_args)[:100] if s.tool_args else ""
                success = (
                    "success"
                    if s.tool_success
                    else "FAILED"
                    if s.tool_success is False
                    else "unknown"
                )
                line += f" tool={s.tool_name} args={args_preview} result={success}"
            if s.description:
                line += f" desc={s.description[:80]}"
            step_lines.append(line)

        trace_summary = "\n".join(step_lines) if step_lines else "  (no steps recorded)"
        final_output = trace.final_text[:2000] if trace.final_text else "(no text output)"
        artifacts = (
            json.dumps(trace.artifacts, ensure_ascii=False, indent=2)
            if trace.artifacts
            else "(none)"
        )
        errors = "\n".join(f"  - {e[:200]}" for e in trace.errors) if trace.errors else "(none)"

        return self.JUDGE_PROMPT_TEMPLATE.format(
            prompt=trace.prompt[:500],
            work_mode=trace.work_mode,
            expected_behavior=expected.get("note", "N/A"),
            trace_summary=trace_summary,
            final_output=final_output,
            artifacts_summary=artifacts,
            errors_summary=errors,
        )

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call the LLM API with the judge prompt."""
        data = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert AI Agent evaluator. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 2000,
            }
        ).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read().decode())
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except urllib.error.HTTPError as e:
            print(f"    [LLM Judge] HTTP {e.code}: {e.reason}", flush=True)
            return None
        except Exception as e:
            print(f"    [LLM Judge] Error: {type(e).__name__}: {str(e)[:200]}", flush=True)
            return None
