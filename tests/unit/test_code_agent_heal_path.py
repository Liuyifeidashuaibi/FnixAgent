"""Unit tests for Code Agent heal fallbacks and path contract."""

from __future__ import annotations

from fnixagent.core.code.agent import CodingAgent, CodingTask, TaskStep


def test_normalize_code_target_strips_artifacts():
    assert CodingAgent._normalize_code_target(".fnix/artifacts/fib.py") == "fib.py"
    assert CodingAgent._normalize_code_target(".fnix/artifacts/pkg/test_fib.py") == "test_fib.py"
    assert CodingAgent._normalize_code_target("calc.py") == "calc.py"
    assert CodingAgent._normalize_code_target("src/util.py") == "src/util.py"


def test_infer_required_files():
    files = CodingAgent._infer_required_files("Create fib.py and test_fib.py with pytest.")
    assert "fib.py" in files
    assert "test_fib.py" in files


def test_scaffold_fib_and_calc():
    fib = CodingAgent._scaffold_file_content("fib.py")
    assert "def fib" in fib
    calc = CodingAgent._scaffold_file_content("calc.py")
    assert "def add" in calc and "def multiply" in calc
    main = CodingAgent._scaffold_file_content("main.py", "Implement main.py Hello Alice greet")
    assert "Hello" in main


def test_augment_plan_adds_missing_writes():
    agent = CodingAgent.__new__(CodingAgent)
    task = CodingTask(description="Create fib.py and test_fib.py")
    plan = [
        TaskStep(id="1", description="read something", action="read", target="README.md"),
        TaskStep(id="2", description="run tests", action="test", target=""),
    ]
    out = agent._augment_plan_with_required_files(task, plan)
    writes = [s.target for s in out if s.action == "write"]
    assert "fib.py" in writes
    assert "test_fib.py" in writes
    # writes before test
    test_idx = next(i for i, s in enumerate(out) if s.action == "test")
    assert all(out.index(s) < test_idx for s in out if s.action == "write")


def test_edit_fallback_adds_missing_colon():
    import asyncio
    import tempfile
    from pathlib import Path

    from fnixagent.core.code.agent import TaskStep
    from fnixagent.core.code.tools import CodeTools

    async def _run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.py").write_text("def double(x)\n    return x * 2\n", encoding="utf-8")
            tools = CodeTools(str(root))
            tools.preview_mode = False
            agent = CodingAgent.__new__(CodingAgent)
            agent._tools = tools
            step = TaskStep(
                id="1",
                description="Fix syntax error missing colon",
                action="edit",
                target="broken.py",
            )
            result = await agent._edit_fallback(step)  # noqa: SLF001
            assert result.success
            text = (root / "broken.py").read_text(encoding="utf-8")
            assert "def double(x):" in text

    asyncio.run(_run())
