"""AG-UI mapper unit tests."""

from fnixagent.core.ag_ui.mapper import encode_sse, map_work_chunk, run_started


def test_run_started():
    s = run_started("run-1")
    assert s.startswith("data: ")
    assert "RUN_STARTED" in s


def test_map_thought():
    # thought/thinking → THINKING_CONTENT（AG-UI 思考通道，前端折叠展示）
    ev = map_work_chunk("thought", "planning...", "run-1")
    assert ev["type"] == "THINKING_CONTENT"
    assert "planning" in ev["delta"]
    assert ev["messageId"].endswith("-thinking")


def test_map_tool():
    ev = map_work_chunk("action", {"name": "read_file"}, "run-1")
    assert ev["type"] == "TOOL_CALL_START"
    assert ev["toolCallName"] == "read_file"


def test_encode_sse_roundtrip():
    ev = map_work_chunk("error", "boom", "r")
    line = encode_sse(ev)
    assert line.endswith("\n\n")
