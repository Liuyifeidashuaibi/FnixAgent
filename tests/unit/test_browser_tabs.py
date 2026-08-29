"""多标签页（N3）：页面池、归属纪律与工具面（真 Chromium，非 mock）。

真人在浏览器里从来不只开一个页面——多页并行（边查边填、对比资料）是"像人
一样用浏览器"的基本面。这组用例守住三件事：

  1. 开/切/关真的能用，且切过去之后所有动作都发生在新页面上；
  2. 归属铁律推广到每个标签页——不归我们开的页（接管的真实渲染窗口/
     用户浏览器页面）绝不关；最后一个标签页也不关；
  3. 工具面（browser_view/browser_act）把多页能力暴露给模型。
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

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.core.tools.browser import BrowserSession, browser_act, browser_view  # noqa: E402

pytestmark = pytest.mark.asyncio

PAGE_A = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>页面A</title></head><body><h1>页面A</h1><p>内容甲</p></body></html>"""
PAGE_B = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>页面B</title></head><body><h1>页面B</h1><p>内容乙</p></body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_tabs_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "a.html").write_text(PAGE_A, encoding="utf-8")
    (tmp / "b.html").write_text(PAGE_B, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture
async def session(server: str) -> Any:
    s = BrowserSession()
    await s.navigate(f"{server}/a.html")
    yield s
    await s.close()


async def test_first_page_is_registered_as_tab(session: Any) -> None:
    """会话首个页面必须登记为 t1——多标签池从第一个页面就存在。"""
    tabs = await session.tab_list()
    assert len(tabs) == 1
    assert tabs[0]["id"] == "t1"
    assert tabs[0]["active"] is True
    assert "页面A" in tabs[0]["title"]


async def test_tab_open_creates_and_switches(session: Any, server: str) -> None:
    """新开标签页必须成为活动页（真人的习惯：新开的页就是正在看的页）。"""
    state = await session.tab_open(f"{server}/b.html")
    assert state.error is None, state.error
    tabs = await session.tab_list()
    assert [t["id"] for t in tabs] == ["t1", "t2"]
    assert [t["active"] for t in tabs] == [False, True]
    assert "页面B" in state.title
    # 快照/正文都必须发生在新页面上
    assert "内容乙" in await session.page_text()


async def test_tab_switch_restores_context(session: Any, server: str) -> None:
    """切回旧标签页后，url/标题/正文全部回到那个页面。"""
    await session.tab_open(f"{server}/b.html")
    state = await session.tab_switch("t1")
    assert state.error is None, state.error
    assert state.url.endswith("/a.html")
    assert "页面A" in state.title
    assert "内容甲" in await session.page_text()


async def test_tabs_are_isolated(session: Any, server: str) -> None:
    """两个标签页互不串扰：各自导航、各自正文。"""
    await session.tab_open(f"{server}/b.html")
    await session.tab_switch("t1")
    assert "内容甲" in await session.page_text()
    await session.tab_switch("t2")
    assert "内容乙" in await session.page_text()


async def test_tab_close_returns_to_remaining(session: Any, server: str) -> None:
    """关掉活动页后必须回到剩余页面，会话继续可用。"""
    await session.tab_open(f"{server}/b.html")
    state = await session.tab_close("t2")
    assert state.error is None, state.error
    tabs = await session.tab_list()
    assert [t["id"] for t in tabs] == ["t1"]
    assert tabs[0]["active"] is True
    assert "页面A" in state.title


async def test_tab_close_refuses_unowned_page(session: Any) -> None:
    """护栏：不归我们的页不许关（归属铁律推广到每个标签页）。

    关掉接管浏览器里用户正在看的页 = 关用户的窗口，比泄漏一个页面严重得多。
    """
    session._tabs["t1"]["owns"] = False  # 模拟接管页：归用户所有
    state = await session.tab_close("t1")
    assert state.error is not None, "不属于自己的页面被关掉了——归属铁律失守"
    assert "无权关闭" in state.error
    # 页面必须还活着
    assert (await session.tab_list())[0]["id"] == "t1"


async def test_tab_close_refuses_last_tab(session: Any) -> None:
    """护栏：最后一个标签页不关——会话没有页面就失去意义。"""
    state = await session.tab_close("t1")
    assert state.error is not None, "最后一个标签页被关掉了"
    assert "最后一个" in state.error
    assert len(await session.tab_list()) == 1


async def test_tab_switch_unknown_id_fails_honestly(session: Any) -> None:
    state = await session.tab_switch("t99")
    assert state.error is not None
    assert "不存在" in state.error


async def test_tool_surface_tabs(server: str) -> None:
    """模型可见的工具面：browser_view(what='tabs') + browser_act tab_*。

    工具面走进程单例——单例是进程级的，前面的用例可能留下 FakePage 残骸
    （本套件按仓库纪律自己清干净：进出都把 _instance 归零）。
    """
    BrowserSession._instance = None
    try:
        view = await browser_view({"what": "tabs"})
        assert view.success is True

        opened = await browser_act({"action": "tab_open", "url": f"{server}/b.html"})
        assert opened.success is True, opened.error
        assert opened.metadata.get("active_tab") == opened.metadata["tabs"][-1]["id"]

        listed = await browser_view({"what": "tabs"})
        assert "当前标签页" in listed.content

        closed = await browser_act({"action": "tab_close"})
        assert closed.success is True, closed.error

        # tab_switch 缺 tab_id 必须如实报错，不许猜
        bad = await browser_act({"action": "tab_switch"})
        assert bad.success is False
    finally:
        session = BrowserSession.instance()
        await session.close()
        BrowserSession._instance = None
