"""Phase 4 真实渲染 · 可测部分（不依赖桌面端启动）。

真实渲染窗口本身要跑起来才能验（需 Tauri + WebView2），这里覆盖的是
Python 侧能被单测锁住的两条契约：

  1. 内置窗口端口优先于"接管用户浏览器"端口
  2. 端口为 0/None 时干净地回退，不残留状态

理由是安全与隔离纪律，不是性能：内置窗口是我们自己的，只在自己 new_page()
出来的 tab 里活动；而接管用户浏览器意味着在一个装着用户全部登录态的浏览器
里操作，风险面大得多。这个优先级如果被改回去，必须有测试失败。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from unittest.mock import patch

import pytest

from fnixagent.core.tools.driver_router import DriverRouter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def router() -> DriverRouter:
    r = DriverRouter()
    r.set_builtin_cdp_port(None)
    return r


def _fake_probe(alive: set[int]):
    """构造一个只对存活端口返回 True 的探测函数。"""

    def _probe(url: str) -> bool:
        port = int(url.split(":")[2].split("/")[0])
        return port in alive

    return _probe


async def test_builtin_port_defaults_to_none(router: DriverRouter) -> None:
    assert router.builtin_cdp_port is None


async def test_builtin_port_wins_over_user_browser(router: DriverRouter) -> None:
    """两个端口都活着时，必须选内置窗口——隔离纪律，不是性能考虑。"""
    router.set_builtin_cdp_port(9333)
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe({9222, 9333}),
    ):
        endpoint = await router.probe_cdp()
    assert endpoint == "http://127.0.0.1:9333"


async def test_falls_back_to_user_browser_when_builtin_dead(router: DriverRouter) -> None:
    """内置窗口端口没起来（未开启/已关闭）时，回退到接管用户浏览器。"""
    router.set_builtin_cdp_port(9333)
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe({9222}),
    ):
        endpoint = await router.probe_cdp()
    assert endpoint == "http://127.0.0.1:9222"


async def test_returns_none_when_nothing_alive(router: DriverRouter) -> None:
    router.set_builtin_cdp_port(9333)
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe(set()),
    ):
        assert await router.probe_cdp() is None


async def test_port_zero_clears_state(router: DriverRouter) -> None:
    """前端传 0 表示"不可用"，必须清干净，否则会一直连一个死端口。"""
    router.set_builtin_cdp_port(9333)
    router.set_builtin_cdp_port(0)
    assert router.builtin_cdp_port is None


async def test_probe_without_builtin_uses_only_legacy_ports(router: DriverRouter) -> None:
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe({9223}),
    ):
        endpoint = await router.probe_cdp()
    assert endpoint == "http://127.0.0.1:9223"


async def test_probe_is_scoped_to_localhost_only(router: DriverRouter) -> None:
    """探测地址必须写死 127.0.0.1——CDP 无鉴权，绝不能探到外部地址。"""
    seen: list[str] = []

    def _probe(url: str) -> bool:
        seen.append(url)
        return False

    with patch("fnixagent.core.tools.driver_router._probe_endpoint", side_effect=_probe):
        await router.probe_cdp()
    assert seen
    assert all(u.startswith("http://127.0.0.1:") for u in seen), seen
