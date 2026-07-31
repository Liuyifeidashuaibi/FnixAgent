"""Tests for Fnix Code Benchmark framework."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fnixagent.core.code.benchmark.checks import run_check
from fnixagent.core.code.benchmark.generator import generate_tasks
from fnixagent.core.code.benchmark.runner import materialize_workspace, run_checks
from fnixagent.core.code.benchmark.schema import load_task, validate_task
from fnixagent.core.code.benchmark.scorer import TaskRunMeta, score_task

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "code"


def test_seed_tasks_validate():
    seed_dir = BENCH / "seed"
    if not seed_dir.is_dir():
        pytest.skip("no seed tasks")
    for p in seed_dir.glob("*.json"):
        task = load_task(p)
        assert not validate_task(task), p.name


def test_bugfix_subtract_dry_checks():
    p = BENCH / "seed" / "seed.bugfix.subtract.json"
    if not p.is_file():
        pytest.skip("seed missing")
    task = load_task(p)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ws = materialize_workspace(task, Path(tmp))
        target = ws / "math_utils.py"
        target.write_text("def subtract(a, b):\n    return a - b\n", encoding="utf-8")
        meta = TaskRunMeta()
        results = run_checks(task, ws, meta)
        scored = score_task(task, results, meta)
        assert scored.hard_pass
        assert scored.task_score >= 80


def test_generator_produces_valid_tasks():
    tasks = generate_tasks(5, seed=1)
    assert len(tasks) == 5
    for t in tasks:
        assert t["checks"]
        assert t["capability"]


def test_manifest_exists_after_generate():
    manifest = BENCH / "manifest.json"
    if not manifest.is_file():
        pytest.skip("run generate-code-tasks.py first")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["total"] >= len(list((BENCH / "seed").glob("*.json")))


def test_file_exists_check(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1", encoding="utf-8")
    r = run_check(tmp_path, "file_exists", {"path": "a.py"})
    assert r.ok
