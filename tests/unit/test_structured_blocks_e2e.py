"""端到端验证：AG-UI 结构化事件全链路 (loop.py → RunEngine → 前端 block)

验证目标 (对标 AG-UI 16 种标准事件 + Claude Code block-by-block 渲染):
  1. AgenticLoop.run_stream 发射 step_start / step_end / file_change 事件
  2. 事件顺序正确: step_start → thinking → action/tool_call → observation/tool_result
                   → file_change → step_end → text → done
  3. RunEngine.run_stream 正常包装为 RunEvent (AG-UI 信封)
  4. to_work_dict() / to_code_ndjson() 序列化保留结构化字段

设计：
  - Mock LLM: 第 1 轮返回 write_file tool_call, 第 2 轮返回最终 text
  - Mock tool_executor: 返回成功 + diff 内容
  - 收集所有 RunEvent, 验证类型序列 + 关键字段
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from fnixagent.core.agent.loop import AgenticLoop
from fnixagent.core.run.engine import RunEngine


def _make_mock_llm():
    """两轮 mock: 第 1 轮 tool_call(write_file), 第 2 轮 final text."""
    calls = {"n": 0}

    async def _llm(messages, tools=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": json.dumps(
                                            {
                                                "file_path": "/tmp/test_blocks_demo.html",
                                                "content": "<html><body>demo</body></html>",
                                            }
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
        # 第 2 轮: 最终文本响应
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "已将源码写入 `/tmp/test_blocks_demo.html`，可直接打开验证。",
                    },
                }
            ],
            "usage": {"prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180},
        }

    return _llm


class _MockToolExecutor:
    async def execute(self, tool_name: str, args: dict) -> str:
        if tool_name == "write_file":
            return "OK: wrote 1 file (35 bytes)"
        return f"[失败] unknown tool {tool_name}"


def _collect_events(loop: AgenticLoop, user_input: str) -> list[dict[str, Any]]:
    """同步收集 run_stream 的所有事件 (raw dict)."""

    async def _collect():
        out = []
        async for ev in loop.run_stream(user_input):
            if isinstance(ev, dict):
                out.append(ev)
            else:
                out.append({"type": "text", "data": str(ev)})
        return out

    return asyncio.run(_collect())


def test_loop_emits_step_start_step_end_file_change():
    """验证 AgenticLoop 发射 step_start / step_end / file_change 事件."""
    loop = AgenticLoop(
        llm_call=_make_mock_llm(),
        tool_executor=_MockToolExecutor(),
        workspace_root="/tmp",
        max_steps=5,
        enable_reflection=False,
        enable_evolution=False,
    )
    events = _collect_events(loop, "写一个简单的 HTML demo")

    types = [e.get("type") for e in events]

    # 必须包含 step_start (至少 2 次: 第 1 轮 tool_call + 第 2 轮 final)
    assert "step_start" in types, f"missing step_start in {types}"
    step_start_count = types.count("step_start")
    assert step_start_count >= 2, f"expected >=2 step_start, got {step_start_count}"

    # 必须包含 step_end (至少 1 次: 最终返回前)
    assert "step_end" in types, f"missing step_end in {types}"

    # 必须包含 file_change (write_file 工具触发)
    assert "file_change" in types, f"missing file_change in {types}"

    # 验证事件顺序: step_start 必须在该步骤的其他事件之前
    first_step_start = types.index("step_start")
    # step_start 后面应该跟着 thinking (Spec 2 思考链可见)
    assert "thinking" in types[first_step_start:], "thinking should follow step_start"

    # file_change 应该在 tool_result 之后 (工具执行完才 emit file_change)
    if "tool_result" in types:
        assert types.index("file_change") > types.index("tool_result"), (
            "file_change should come after tool_result"
        )

    # step_end 应该在 done 之前 (最终步骤完成 → done)
    if "done" in types:
        last_step_end = len(types) - 1 - types[::-1].index("step_end")
        done_idx = types.index("done")
        assert last_step_end < done_idx, "step_end should come before done"

    # 验证 step_start 的 data 结构
    step_start_ev = next(e for e in events if e.get("type") == "step_start")
    data = step_start_ev.get("data", {})
    assert data.get("step") == 1, f"first step_start should be step 1, got {data.get('step')}"
    assert data.get("total") == 5, f"total should be 5, got {data.get('total')}"
    assert "description" in data, "step_start should have description"

    # 验证 file_change 的 data 结构
    file_change_ev = next(e for e in events if e.get("type") == "file_change")
    fc_data = file_change_ev.get("data", {})
    assert fc_data.get("path") == "/tmp/test_blocks_demo.html", (
        f"file_change path mismatch: {fc_data.get('path')}"
    )
    assert fc_data.get("action") == "write_file"
    assert fc_data.get("preview") is True

    # 验证 step_end 的 data 结构 (isComplete 由前端从 type=step_end 推断)
    step_end_ev = next(e for e in events if e.get("type") == "step_end")
    se_data = step_end_ev.get("data", {})
    assert se_data.get("step") >= 1
    assert se_data.get("total") == 5


def test_run_engine_wraps_structured_events(tmp_path):
    """验证 RunEngine 正常包装 step_start / step_end / file_change 为 RunEvent."""
    from fnixagent.core.run import RunCheckpointStore

    async def _source():
        yield {"type": "step_start", "data": {"step": 1, "total": 3, "description": "Step 1/3"}}
        yield {"type": "thinking", "data": "planning..."}
        yield {"type": "action", "data": {"name": "write_file", "args": {"file_path": "/x.py"}}}
        yield {"type": "tool_result", "data": "OK"}
        yield {
            "type": "file_change",
            "data": {"path": "/x.py", "action": "write_file", "diff": "+new", "preview": True},
        }
        yield {
            "type": "step_end",
            "data": {"step": 1, "total": 3, "description": "Step 1/3 (done)"},
        }
        yield {"type": "text", "data": "done"}
        yield {"type": "done", "data": {"steps": 1, "duration_ms": 100}}

    store = RunCheckpointStore(db_path=tmp_path / "runs.sqlite3")
    engine = RunEngine(store=store)

    async def _collect():
        out = []
        async for ev in engine.run_stream(_source(), channel="work", run_id="r-test"):
            out.append(ev)
        return out

    events = asyncio.run(_collect())
    types = [e.type for e in events]

    # 验证所有事件类型都被正确包装
    assert "step_start" in types
    assert "step_end" in types
    assert "file_change" in types
    assert "thinking" in types
    assert "action" in types
    assert "tool_result" in types
    assert "text" in types
    assert "done" in types

    # 验证 to_work_dict() 序列化保留 data 字段
    step_start = next(e for e in events if e.type == "step_start")
    wd = step_start.to_work_dict()
    assert wd["type"] == "step_start"
    assert wd["data"]["step"] == 1
    assert wd["data"]["total"] == 3
    assert wd["runId"] == "r-test"

    # 验证 to_code_ndjson() 把 step_start.data 放到 step 字段 (Code 模式兼容)
    code_ndjson = step_start.to_code_ndjson()
    assert code_ndjson["type"] == "step_start"
    assert code_ndjson["step"]["step"] == 1
    assert code_ndjson["step"]["total"] == 3

    # 验证 file_change 在 Code 模式下展平 (path/action/diff 在顶层)
    file_change = next(e for e in events if e.type == "file_change")
    fc_code = file_change.to_code_ndjson()
    assert fc_code["type"] == "file_change"
    assert fc_code["path"] == "/x.py"
    assert fc_code["action"] == "write_file"
    assert fc_code["diff"] == "+new"


def test_step_end_replaces_step_start_in_frontend_merge():
    """验证前端 appendBlock 合并策略: progress block 始终替换上一个 progress.

    这是单进度条 UX 的关键: 不堆叠多个 ProgressStrip, 只更新当前步骤.
    """

    # 模拟前端 structuredBlocks.ts 的 appendBlock 逻辑 (Python 等价实现)
    def append_block(blocks, new_block):
        if not blocks:
            return [new_block]
        last = blocks[-1]
        # text / thinking 流式合并
        if new_block["kind"] in ("text", "thinking") and last["kind"] == new_block["kind"]:
            return [*blocks[:-1], {**last, "content": last["content"] + new_block["content"]}]
        # progress 始终替换 (单一进度条 UX)
        if new_block["kind"] == "progress" and last["kind"] == "progress":
            return [*blocks[:-1], new_block]
        return [*blocks, new_block]

    # 模拟事件序列: step_start(1) → step_start(2) → step_end(2)
    blocks = []
    blocks = append_block(
        blocks,
        {
            "kind": "progress",
            "currentStep": 1,
            "totalSteps": 5,
            "description": "Step 1/5",
            "isComplete": False,
        },
    )
    assert len(blocks) == 1
    assert blocks[0]["currentStep"] == 1
    assert blocks[0]["isComplete"] is False

    blocks = append_block(
        blocks,
        {
            "kind": "progress",
            "currentStep": 2,
            "totalSteps": 5,
            "description": "Step 2/5",
            "isComplete": False,
        },
    )
    assert len(blocks) == 1, "progress should replace, not append"
    assert blocks[0]["currentStep"] == 2

    blocks = append_block(
        blocks,
        {
            "kind": "progress",
            "currentStep": 2,
            "totalSteps": 5,
            "description": "Step 2/5 (done)",
            "isComplete": True,
        },
    )
    assert len(blocks) == 1, "step_end should replace step_start"
    assert blocks[0]["isComplete"] is True

    # 中间穿插 text block 不影响 progress 替换
    blocks = append_block(blocks, {"kind": "text", "content": "hello"})
    assert len(blocks) == 2  # progress + text

    blocks = append_block(
        blocks,
        {
            "kind": "progress",
            "currentStep": 3,
            "totalSteps": 5,
            "description": "Step 3/5",
            "isComplete": False,
        },
    )
    assert len(blocks) == 3, "new progress after text should append"
    assert blocks[-1]["currentStep"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
