"""driver_router 单元测试 — 离线可跑（不真连 CDP，不启动浏览器）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio

import pytest

from fnixagent.core.tools import driver_router as dr


@pytest.fixture(autouse=True)
def _isolated_router(tmp_path, monkeypatch):
    """每个测试重建单例，并把审计落盘重定向到临时目录。"""
    monkeypatch.setattr(dr, "_AUDIT_FILE", tmp_path / "driver_events.jsonl")
    dr.reset_driver_router_for_tests()
    yield
    dr.reset_driver_router_for_tests()


def test_probe_cdp_timeout_returns_none(monkeypatch):
    async def run():
        monkeypatch.setattr(dr, "_probe_endpoint", lambda url: False)
        assert await dr.get_driver_router().probe_cdp() is None

    asyncio.run(run())


def test_probe_cdp_found_returns_endpoint(monkeypatch):
    async def run():
        monkeypatch.setattr(dr, "_probe_endpoint", lambda url: True)
        assert await dr.get_driver_router().probe_cdp() == "http://127.0.0.1:9222"

    asyncio.run(run())


def test_emit_ring_buffer_caps_at_max():
    async def run():
        r = dr.get_driver_router()
        total = dr._MAX_EVENTS + 10
        for i in range(total):
            await r.emit(dr.DriverEvent(id=0, ts=0.0, action=f"op{i}"))
        events, last_id = await r.recent_events(0)
        assert len(events) == dr._MAX_EVENTS
        # 环形缓冲丢掉了最早的 10 条
        assert events[0]["action"] == "op10"
        assert events[-1]["action"] == f"op{total - 1}"
        assert last_id == events[-1]["id"]

    asyncio.run(run())


def test_recent_events_incremental():
    async def run():
        r = dr.get_driver_router()
        await r.emit(dr.DriverEvent(id=0, ts=0.0, action="a"))
        await r.emit(dr.DriverEvent(id=0, ts=0.0, action="b"))
        events, last_id = await r.recent_events(1)
        assert [e["action"] for e in events] == ["b"]
        assert last_id == 2

    asyncio.run(run())


def test_audit_file_written(tmp_path):
    async def run():
        r = dr.get_driver_router()
        await r.emit(dr.DriverEvent(id=0, ts=0.0, action="click", ok=True))
        lines = (tmp_path / "driver_events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert '"action": "click"' in lines[0]

    asyncio.run(run())


def test_record_failure_threshold():
    async def run():
        r = dr.get_driver_router()
        assert not await r.record_failure("cdp-attach")
        assert await r.record_failure("cdp-attach")  # 达阈值 2
        await r.reset_failures()
        assert not await r.record_failure("cdp-attach")

    asyncio.run(run())


def test_execute_missing_op():
    async def run():
        res = await dr.get_driver_router().execute({})
        assert not res.ok
        assert "op" in (res.error or "")

    asyncio.run(run())


def test_execute_unknown_op():
    async def run():
        res = await dr.get_driver_router().execute({"op": "no_such_op"})
        assert not res.ok

    asyncio.run(run())


def test_execute_desktop_op_without_handler():
    async def run():
        res = await dr.get_driver_router().execute({"op": "desktop_click", "x": 1, "y": 2})
        assert not res.ok
        assert "桌面驱动未注册" in (res.error or "")

    asyncio.run(run())


def test_kernel_computer_use_missing_op():
    from fnixagent.core.agent.kernel import AgentKernel
    from fnixagent.core.agent.syscall import SyscallRequest, SyscallType

    k = AgentKernel(enable_scheduler_loop=False)
    req = SyscallRequest(syscall=SyscallType.COMPUTER_USE, args={})

    async def run():
        resp = await k._handle_computer_use(req)
        assert not resp.success
        assert "op" in (resp.error or "")

    asyncio.run(run())
