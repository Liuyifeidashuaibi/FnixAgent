"""AgenticLoop should surface real LLM error details."""

from __future__ import annotations

import asyncio

from fnixagent.core.agent.loop import AgenticLoop


class _EmptyTools:
    def get_tool_definitions(self):
        return []

    def execute(self, *_a, **_k):
        return "ok"

    def get_tools_description(self):
        return ""


def test_stream_surfaces_quota_error():
    async def boom(_messages, tools=None):
        raise RuntimeError("Free quota exhausted code=AllocationQuota.FreeTierOnly")

    async def _run():
        loop = AgenticLoop(
            llm_call=boom,
            tool_executor=_EmptyTools(),
            workspace_root=".",
            max_steps=2,
            enable_evolution=False,
        )
        events = []
        async for ev in loop.run_stream("hi"):
            events.append(ev)
        return events

    events = asyncio.run(_run())
    err = next((e for e in events if e.get("type") == "error"), None)
    assert err is not None
    assert "Free quota exhausted" in str(err.get("data"))
    assert "LLM 调用失败" in str(err.get("data"))
