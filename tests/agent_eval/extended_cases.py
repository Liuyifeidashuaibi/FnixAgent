"""
Extended Test Cases for FnixAgent Evaluation.

Inspired by:
- SWE-bench Verified: Real-world code tasks (bug fix, feature add, refactor)
- GAIA: Multi-step reasoning with tool combinations
- MCP-Bench: MCP tool discovery, parameter matching, multi-service coordination
- AgentBench: Long-chain multi-turn tasks, error recovery
- OWASP WSTG: Security testing

Categories:
  FILE-xxx   - File operations (SWE-bench inspired)
  TOOL-xxx   - Tool call correctness (MCP-Bench inspired)
  PLAN-xxx   - Multi-step planning (GAIA inspired)
  ERR-xxx    - Error recovery (AgentBench inspired)
  SEC-xxx    - Security tests (OWASP inspired)
  REL-xxx    - Reliability tests
  CODE-xxx   - Code generation quality (SWE-bench Verified)
  GAIA-xxx   - Complex system design (GAIA Level 2-3)
  MCP-xxx    - MCP-specific tests (MCP-Bench)
  REGR-xxx   - Regression tests (previously failed cases)
"""

# These cases extend the base TEST_CASES in runner.py
# Import base cases and add new ones
from .cases import TEST_CASES as BASE_CASES

EXTENDED_CASES = [
    # === MCP-Specific Tests (inspired by MCP-Bench) ===
    {
        "id": "MCP-001",
        "name": "MCP tool discovery and listing",
        "prompt": "List all available MCP tools and describe what each one does.",
        "mode": "ask",
        "expected": {
            "expect_text": True,
            "expect_artifacts": False,
            "max_steps": 5,
            "min_text_length": 200,
            "expect_done": True,
            "note": "Agent should enumerate available MCP tools",
        },
    },
    {
        "id": "MCP-002",
        "name": "MCP tool parameter matching",
        "prompt": "Use the write_file tool to create a file called test_mcp.txt with content 'MCP test successful'. Then read it back to verify.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 6,
            "expect_done": True,
        },
    },
    {
        "id": "MCP-003",
        "name": "MCP error recovery - invalid tool name",
        "prompt": "Use the tool called nonexistent_tool_xyz to do something.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": False,
            "max_steps": 8,
            "expect_done": True,
            "note": "Agent should recognize tool doesn't exist and explain",
        },
    },
    # === SWE-bench Inspired Code Tasks ===
    {
        "id": "SWE-001",
        "name": "Fix a bug in existing code",
        "prompt": "I have a Python function that should return the factorial of n, but it has a bug - it returns 1 for all inputs. Here's the code:\n\ndef factorial(n):\n    result = 1\n    for i in range(1, n):\n        result *= i\n    return result\n\nCreate a file called fixed_factorial.py with the corrected implementation, including type hints and a docstring.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 5,
            "expect_done": True,
            "note": "Bug is range(1, n) should be range(1, n+1). Agent should identify and fix this.",
        },
    },
    {
        "id": "SWE-002",
        "name": "Add feature to existing code",
        "prompt": "I have a simple Stack class in Python. Add a 'peek' method that returns the top element without removing it, and a 'is_empty' method. Create the complete file as enhanced_stack.py.\n\nclass Stack:\n    def __init__(self):\n        self.items = []\n    def push(self, item):\n        self.items.append(item)\n    def pop(self):\n        return self.items.pop() if self.items else None\n    def size(self):\n        return len(self.items)",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 5,
            "expect_done": True,
        },
    },
    {
        "id": "SWE-003",
        "name": "Refactor code for better structure",
        "prompt": "I have a monolithic function that does too much. Refactor it into smaller functions. Create a file called refactored_processor.py:\n\ndef process_data(data):\n    # filters\n    filtered = [d for d in data if d > 0]\n    # transforms\n    transformed = [d * 2 for d in filtered]\n    # sorts\n    sorted_data = sorted(transformed, reverse=True)\n    # formats\n    formatted = [f'Value: {d}' for d in sorted_data]\n    return formatted\n\nSplit into: filter_positive, scale_values, sort_descending, format_output. Include the original process_data that calls them.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 6,
            "expect_done": True,
        },
    },
    # === GAIA Level 2-3 Inspired Multi-Step Tasks ===
    {
        "id": "GAIA-003",
        "name": "Multi-step data processing pipeline",
        "prompt": "Create a complete data processing pipeline in Python that: 1) Reads a CSV file with columns: name, age, salary, department 2) Filters employees over 30 3) Groups by department and calculates average salary 4) Outputs a summary report as markdown. Create two files: pipeline.py and sample_data.csv with 10 sample rows.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 8,
            "expect_done": True,
        },
    },
    {
        "id": "GAIA-004",
        "name": "API design with documentation",
        "prompt": "Design a RESTful API for a blog platform with endpoints for: posts (CRUD), comments (CRUD), users (register, login, profile), and tags (list, assign). Create two files: api_spec.md with full endpoint documentation including request/response examples, and models.py with Pydantic models for all entities.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 10,
            "expect_done": True,
        },
    },
    # === Error Recovery (AgentBench inspired) ===
    {
        "id": "ERR-003",
        "name": "Handle tool failure gracefully",
        "prompt": "Read the file /nonexistent/path/file.txt and if it fails, create a new file at default_location.txt with content 'File was not found, created default.'",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 10,
            "expect_done": True,
            "note": "Agent should handle read failure and proceed with fallback",
        },
    },
    {
        "id": "ERR-004",
        "name": "Recover from invalid input",
        "prompt": "Calculate the average of these numbers: [10, 20, 'thirty', 40, null, 50]. Handle any invalid values gracefully.",
        "mode": "ask",
        "expected": {
            "expect_text": True,
            "expect_artifacts": False,
            "max_steps": 8,
            "min_text_length": 200,
            "expect_done": True,
            "note": "Agent should identify invalid values and compute average of valid ones",
        },
    },
    # === Regression Tests (previously failed/partial cases) ===
    {
        "id": "REGR-001",
        "name": "Regression: Plan mode widget rendering (was TOOL-002)",
        "prompt": "Design a real-time chat application architecture. Requirements: WebSocket support, message persistence, user presence, typing indicators, message search. Suggest tech stack and data flow.",
        "mode": "plan",
        "expected": {
            "expect_text": True,
            "expect_artifacts": False,
            "max_steps": 10,
            "min_text_length": 800,
            "expect_done": True,
            "note": "Previously PARTIAL due to duplicate show_widget calls. Verify no duplicate tool calls.",
        },
    },
    {
        "id": "REGR-002",
        "name": "Regression: API rate limit handling (was CODE-002)",
        "prompt": "Create a CSS file called design_system.css with: CSS variables for colors (primary, secondary, success, warning, danger, neutral), spacing scale, font sizes, border radius, shadows, and utility classes for buttons, cards, inputs, and badges. Use a modern aesthetic.",
        "mode": "craft",
        "expected": {
            "expect_text": True,
            "expect_artifacts": True,
            "expected_tools": ["write_file"],
            "max_steps": 6,
            "expect_done": True,
            "note": "Previously PARTIAL due to API 403. Should pass with retry logic.",
        },
    },
]

# Combined test cases: base + extended
ALL_CASES = BASE_CASES + EXTENDED_CASES
