"""后台 Work 入队（不跑完整 LLM）。"""

from __future__ import annotations

from pathlib import Path

from fnixagent.core.scheduler.priority_queue import get_priority_queue, reset_priority_queue
from fnixagent.harness.work_jobs import enqueue_work_job
from fnixagent.harness.workspace import ensure_project_layout


def test_enqueue_work_job(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "home"))
    reset_priority_queue()
    ws = tmp_path / "proj"
    ws.mkdir()
    ensure_project_layout(str(ws))

    result = enqueue_work_job(
        user_input="写一份简短周报",
        workspace=str(ws),
        session_id="job-test-1",
        user_id="test",
        llm=None,
    )
    assert result["ok"] is True
    assert result["session_id"] == "job-test-1"
    q = get_priority_queue()
    item = q.get(timeout=0.1)
    assert item is not None
    assert item.task_type == "work"
    assert item.payload["session_id"] == "job-test-1"
    reset_priority_queue()
