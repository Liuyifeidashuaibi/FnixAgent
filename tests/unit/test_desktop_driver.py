"""desktop 驱动单元测试 — 离线可跑（用 fake cua-driver，不真初始化原生运行时）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio

import pytest

from fnixagent.core.tools import desktop as dmod


class FakeImage:
    def __init__(self, data_base64: str):
        self.data_base64 = data_base64
        self.mime_type = "image/png"


class FakeResult:
    def __init__(self, text="ok", is_error=False, error_code=None, degraded=False, images=None, structured_json=None):
        self.text = text
        self.is_error = is_error
        self.error_code = error_code
        self.degraded = degraded
        self.images = images or []
        self.structured_json = structured_json


class FakeDriver:
    def __init__(self, result: FakeResult | None = None):
        self.result = result or FakeResult()
        self.calls: list[tuple[str, str]] = []

    async def call_tool(self, tool, args_json):
        self.calls.append((tool, args_json))
        return self.result


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("FNIX_DESKTOP_CONFIRM", "1")
    dmod.DesktopDriver._instance = None
    yield
    dmod.DesktopDriver._instance = None


def _mk(fake: FakeDriver) -> dmod.DesktopDriver:
    d = dmod.DesktopDriver.instance()
    d._d = fake
    d._mode = "embedded"
    return d


def test_click_success_extracts_screenshot():
    fake = FakeDriver(FakeResult(text="clicked", images=[FakeImage("QUJDRA==")]))

    async def run():
        d = _mk(fake)
        res = await d.call("click", {"x": 1, "y": 2, "scope": "desktop"})
        assert res.ok
        assert res.screenshot_b64 == "QUJDRA=="

    asyncio.run(run())


def test_degraded_passthrough():
    fake = FakeDriver(FakeResult(text="部分控件树不可用", degraded=True))

    async def run():
        d = _mk(fake)
        res = await d.call("get_window_state", {"pid": 1, "window_id": 2})
        assert res.ok
        assert res.degraded is True

    asyncio.run(run())


def test_build_args_click_adds_desktop_scope():
    assert dmod._build_args("desktop_click", {"x": 10, "y": 20}) == {"x": 10, "y": 20, "scope": "desktop"}
    assert dmod._build_args("desktop_click", {}) is None


def test_build_args_kill_requires_pid():
    assert dmod._build_args("desktop_kill", {"pid": 123}) == {"pid": 123}
    assert dmod._build_args("desktop_kill", {}) is None


def test_launch_requires_confirmation_then_consume():
    fake = FakeDriver(FakeResult(text="launched"))

    async def run():
        d = _mk(fake)
        # 第一次：未确认 → 拦截
        res1 = await d.call("launch_app", {"name": "notepad"}, high_risk=True)
        assert not res1.ok
        assert res1.requires_confirmation is True
        assert res1.confirmation_id
        # 确认放行
        d.confirm(res1.confirmation_id, True)
        # 第二次：已确认 → 放行（单次消费）
        res2 = await d.call("launch_app", {"name": "notepad"}, high_risk=True)
        assert res2.ok
        # 第三次：又需要确认
        res3 = await d.call("launch_app", {"name": "notepad"}, high_risk=True)
        assert res3.requires_confirmation is True

    asyncio.run(run())


def test_confirmation_disabled_by_env(monkeypatch):
    monkeypatch.setenv("FNIX_DESKTOP_CONFIRM", "0")
    fake = FakeDriver(FakeResult(text="launched"))

    async def run():
        d = _mk(fake)
        res = await d.call("launch_app", {"name": "notepad"}, high_risk=True)
        assert res.ok

    asyncio.run(run())


def test_route_unknown_op():
    async def run():
        d = _mk(FakeDriver())
        res = await d.route("desktop_nope", {})
        assert not res.ok

    asyncio.run(run())


def test_route_missing_pid_for_kill():
    async def run():
        d = _mk(FakeDriver())
        res = await d.route("desktop_kill", {})
        assert not res.ok
        assert "参数" in (res.error or "")

    asyncio.run(run())
