"""
FnixAgent Evaluation Suite - Self-built Agent evaluation tool.

Benchmarked against Claude Code / Trae / WorkBuddy.

Modules:
  - trace_collector: Captures NDJSON execution traces from FnixAgent API
  - problem_detector: Rule-based detection of 5 problem categories
  - llm_judge: LLM-as-judge evaluation (inspired by DeepEval)
  - runner: Main evaluation runner with checkpoint support
  - report_generator: JSON/Markdown/HTML report generation
  - extended_cases: Additional SWE-bench/GAIA/MCP-Bench inspired test cases
  - test_suite: pytest integration for CI/CD

Usage:
    # Run all tests
    python -m tests.agent_eval.runner --suite all --report all

    # Run with LLM judge (slower but more thorough)
    python -m tests.agent_eval.runner --suite all --use-judge

    # Run specific category
    python -m tests.agent_eval.runner --filter SEC

    # As pytest (for CI)
    pytest tests/agent_eval/test_suite.py -v

    # With LLM judge in pytest
    FNIX_USE_LLM_JUDGE=1 pytest tests/agent_eval/test_suite.py -v
"""

from .trace_collector import TraceCollector, ExecutionTrace, TraceStep
from .problem_detector import ProblemDetector, Problem, TestCaseResult
from .llm_judge import LLMJudge, JudgeResult, JudgeDimension
from .cases import TEST_CASES, DEFAULT_LLM
from .runner import EvalRunner
from .report_generator import ReportGenerator
from .extended_cases import EXTENDED_CASES, ALL_CASES

__all__ = [
    "TraceCollector",
    "ExecutionTrace",
    "TraceStep",
    "ProblemDetector",
    "Problem",
    "TestCaseResult",
    "LLMJudge",
    "JudgeResult",
    "JudgeDimension",
    "EvalRunner",
    "TEST_CASES",
    "EXTENDED_CASES",
    "ALL_CASES",
    "DEFAULT_LLM",
    "ReportGenerator",
]
