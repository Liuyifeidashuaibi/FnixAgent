"""N1 引导层（纯逻辑 + 真 Chromium 各半）：调试端口指引 + 首次选择记忆。

两条纪律的护栏：

  1. 指引命令必须带**独立 user-data-dir**——调试端口开在日常 profile 上等于
     把登录态暴露给本机任意进程，Chrome 136+ 也默认禁止；
  2. 用户选过"只用独立托管浏览器"之后，每次启动都不得再去探测用户浏览器
     （记忆的意义就是不打扰）。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import functools
import http.server
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

from fnixagent.core.tools import browser_policy as bp

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.core.tools.browser import BrowserSession  # noqa: E402

# 本文件混合了纯逻辑（同步）与真机（异步）用例；asyncio_mode=auto 会自动
# 识别异步用例，因此不加模块级 pytestmark（那会把同步用例也标成 asyncio）。


# ── 纯逻辑：指引内容与安全纪律 ──────────────────────────────────────


def test_debug_port_guide_covers_both_browsers_and_platforms() -> None:
    g = bp.debug_port_guide()
    for browser in ("chrome", "edge"):
        for os_key in ("windows", "macos", "linux"):
            cmd = g["browsers"][browser][os_key]
            assert "--remote-debugging-port=9222" in cmd, (browser, os_key, cmd)


def test_debug_port_guide_always_uses_isolated_profile() -> None:
    """安全纪律：每条命令都必须带独立配置目录。"""
    g = bp.debug_port_guide()
    for browser, platforms in g["browsers"].items():
        for os_key, cmd in platforms.items():
            assert "--user-data-dir" in cmd, (
                f"{browser}/{os_key} 缺独立配置目录——把调试端口开在日常 "
                "profile 上会把登录态暴露给本机任意进程"
            )


def test_debug_port_guide_custom_port() -> None:
    g = bp.debug_port_guide(port=9223)
    assert g["port"] == 9223
    assert "--remote-debugging-port=9223" in g["browsers"]["chrome"]["windows"]


def test_l1_choice_validation_rejects_unknown_values() -> None:
    p = bp.BrowserPolicy(l1_choice="bogus")
    assert p.l1_choice == bp.L1_CHOICE_UNSET


def test_l1_choice_persists_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy_file = tmp_path / "browser_policy.json"
    monkeypatch.setattr(bp, "_POLICY_FILE", policy_file)

    bp.save_policy(bp.BrowserPolicy(l1_choice=bp.L1_CHOICE_MANAGED_ONLY))
    loaded = bp.load_policy()
    assert loaded.l1_choice == bp.L1_CHOICE_MANAGED_ONLY


# ── 行为：选择记忆必须真的阻止探测 ──────────────────────────────────


class _ProbeSpyRouter:
    """记录探测是否发生。managed_only 时它一旦探测就是违纪。"""

    def __init__(self) -> None:
        self.probe_calls = 0

    async def probe_cdp_target(self, ports: tuple[int, ...] = (9222, 9223)) -> Any:
        self.probe_calls += 1
        return None  # 没探测到任何目标

    async def reset_failures(self, mode: str | None = None) -> None:
        return None

    async def emit(self, event: Any) -> None:
        return None


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_l1guide_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "index.html").write_text("<title>ok</title>", encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


async def test_managed_only_choice_skips_cdp_probe(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """选过"只用独立托管浏览器"→ 启动链路一次都不许探测用户浏览器。"""
    import fnixagent.core.tools.driver_router as dr

    policy_file = tmp_path / "browser_policy.json"
    monkeypatch.setattr(bp, "_POLICY_FILE", policy_file)
    bp.save_policy(bp.BrowserPolicy(l1_choice=bp.L1_CHOICE_MANAGED_ONLY))

    spy = _ProbeSpyRouter()
    monkeypatch.setattr(dr, "get_driver_router", lambda: spy)

    session = BrowserSession()
    try:
        state = await session.navigate(f"{server}/index.html")
        assert state.error is None, state.error
        assert session.mode == "managed"
        assert spy.probe_calls == 0, (
            f"managed_only 已选择，却仍探测了 {spy.probe_calls} 次用户浏览器"
        )
    finally:
        await session.close()


async def test_unset_choice_still_probes(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """反向护栏：未做过选择时探测照常发生——记忆不该误伤默认路径。"""
    import fnixagent.core.tools.driver_router as dr

    policy_file = tmp_path / "browser_policy.json"
    monkeypatch.setattr(bp, "_POLICY_FILE", policy_file)
    bp.save_policy(bp.BrowserPolicy())  # l1_choice 保持未选择

    spy = _ProbeSpyRouter()
    monkeypatch.setattr(dr, "get_driver_router", lambda: spy)

    session = BrowserSession()
    try:
        state = await session.navigate(f"{server}/index.html")
        assert state.error is None, state.error
        assert spy.probe_calls == 1, "未选择时应当先探测一次用户浏览器"
        # 探测不到目标 → 落托管；状态里应带上调试端口引导
        assert session.mode == "managed"
        assert state.debug_guide, "托管模式应携带调试端口引导"
        assert "browsers" in state.debug_guide
    finally:
        await session.close()
