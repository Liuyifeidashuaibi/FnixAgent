"""Craft deliverables must land under .fnix/artifacts/."""

from __future__ import annotations

from pathlib import Path

from fnixagent.harness.paths import coerce_craft_artifact_path
from fnixagent.services.work_pipeline import normalize_evolution_event


def test_coerce_craft_artifact_path_nested_and_idempotent():
    assert coerce_craft_artifact_path("hello.html") == ".fnix/artifacts/hello.html"
    assert coerce_craft_artifact_path("reports/week.xlsx") == ".fnix/artifacts/reports/week.xlsx"
    assert (
        coerce_craft_artifact_path(".fnix/artifacts/hello_site/index.html")
        == ".fnix/artifacts/hello_site/index.html"
    )
    assert coerce_craft_artifact_path("artifacts/a.md") == ".fnix/artifacts/a.md"
    assert coerce_craft_artifact_path("./memo.md") == ".fnix/artifacts/memo.md"


def test_write_file_craft_artifacts_redirect(tmp_path: Path):
    from fnixagent.core.tools.workspace import WorkspaceTools

    tools = WorkspaceTools(str(tmp_path))
    html = (
        "<!doctype html><html><head><title>Hello Fnix</title></head>"
        "<body><h1>Hello Fnix</h1><p>welcome</p></body></html>"
    )
    res = tools.write_file("hello.html", html, craft_artifacts=True)
    assert res.success, res.error
    assert (tmp_path / ".fnix" / "artifacts" / "hello.html").is_file()
    assert not (tmp_path / "hello.html").exists()


def test_normalize_evolution_merges_and_flags():
    boot = normalize_evolution_event({"ktg": True, "stp": True, "mfp": False, "step": "boot"})
    assert boot["ktg"] is True
    planned = normalize_evolution_event(
        {"step": "planned", "ktg_paths": 2, "ktg_nodes": 5, "reasoning_mode": "react"},
        prev=boot,
    )
    assert planned["ktg_paths"] == 2
    assert planned["ktg"] is True
    assert planned["stp"] is True
    assert planned["reasoning_mode"] == "react"
    done = normalize_evolution_event({"step": "done", "mfp_result": {"ok": True}}, prev=planned)
    assert done["mfp"] is True
    assert done["ktg_paths"] == 2
