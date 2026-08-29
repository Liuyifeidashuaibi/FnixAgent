"""Phase 4 真实渲染 · attach 归属语义（GUI_DRIVER_ROADMAP.md Phase 4）。

这个文件锁的是一条**容易被写反、写反了又极难发现**的契约：

    cdp-attach 有两种归属，语义相反，绝不能混用。

    builtin（内建真实渲染窗口） → 接管**用户正在看的那个页面**
    user（接管用户日常浏览器）  → 新开**自己的隔离 tab**

混用的后果不是报错，而是"看起来一切正常，其实全错"：

  - 在真实渲染窗口里 new_page()：AI 驱动一个用户看不见的 tab。用户以为自己
    在和 AI 一起看同一个页面，实际上 AI 在另一个页面里点，连"看错了能发现"
    这个最后的人工兜底都没了。**这比截图流更糟**——截图流至少诚实，用户知道
    自己看的是图片。
  - 在用户浏览器里接管可见页面：等于抢走用户的标签页，还顺手继承了用户全部
    登录态。这是 Codex 那条 'No session hijacking' 纪律要防的事。

同理，会话结束时的 page 归属也必须分清楚：真实渲染窗口里那个页面是**用户的
窗口**，关掉它就是白屏；只有自己 new_page() 出来的才归我们关。

这些性质用假对象就能锁住，不需要真 Chromium——它们测的是契约，不是驱动。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from unittest.mock import patch

import pytest

from fnixagent.core.tools.browser import BrowserSession
from fnixagent.core.tools.driver_router import (
    ATTACH_BUILTIN,
    ATTACH_USER,
    CdpTarget,
    DriverRouter,
)

pytestmark = pytest.mark.asyncio


# ── 假对象 ──────────────────────────────────────────────────────────────


class FakePage:
    def __init__(self, name: str = "p") -> None:
        self.name = name
        self.close_calls = 0
        self.init_scripts = 0
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self.close_calls += 1
        self._closed = True

    async def add_init_script(self, script: str) -> None:
        self.init_scripts += 1


class FakeContext:
    def __init__(self, pages: list[FakePage] | None = None) -> None:
        self._pages = list(pages or [])
        self.new_page_calls = 0

    @property
    def pages(self) -> list[FakePage]:
        return self._pages

    async def new_page(self) -> FakePage:
        self.new_page_calls += 1
        page = FakePage(f"new-{self.new_page_calls}")
        self._pages.append(page)
        return page


class DelayedContext(FakeContext):
    """前 N 次访问 pages 都返回空——模拟 Tauri 建窗与首屏渲染的异步延迟。"""

    def __init__(self, page: FakePage, appear_after: int = 3) -> None:
        super().__init__([])
        self._page = page
        self._appear_after = appear_after
        self._reads = 0

    @property
    def pages(self) -> list[FakePage]:
        self._reads += 1
        if self._reads >= self._appear_after:
            return [self._page]
        return []


class FakeBrowser:
    def __init__(self, contexts: list[FakeContext]) -> None:
        self.contexts = contexts


class FakeChromium:
    def __init__(self, ctx: FakeContext) -> None:
        self._ctx = ctx
        self.endpoints: list[str] = []

    async def connect_over_cdp(self, endpoint: str) -> FakeBrowser:
        self.endpoints.append(endpoint)
        return FakeBrowser([self._ctx])


class FakePlaywright:
    def __init__(self, ctx: FakeContext) -> None:
        self.chromium = FakeChromium(ctx)
        self.stopped = False

    async def start(self) -> "FakePlaywright":
        return self

    async def stop(self) -> None:
        self.stopped = True


def _new_session() -> BrowserSession:
    """每个用例一份干净会话——BrowserSession 是进程级单例，必须隔离。"""
    BrowserSession._instance = None
    return BrowserSession.instance()


async def _attach(ctx: FakeContext, kind: str) -> tuple[BrowserSession, FakePlaywright]:
    session = _new_session()
    pw = FakePlaywright(ctx)
    with patch("playwright.async_api.async_playwright", lambda: pw):
        await session._ensure_cdp_attach("http://127.0.0.1:9333", kind)
    return session, pw


# ── builtin：接管用户可见页面 ───────────────────────────────────────────


async def test_builtin_reuses_visible_page() -> None:
    """真实渲染的全部意义：AI 与用户面对同一个页面。"""
    visible = FakePage("visible")
    session, _ = await _attach(FakeContext([visible]), ATTACH_BUILTIN)

    assert session._page is visible
    assert session.attach_kind == ATTACH_BUILTIN


async def test_builtin_never_calls_new_page() -> None:
    """新开 tab 就是让 AI 和用户各看各的——必须零次。"""
    ctx = FakeContext([FakePage("visible")])
    await _attach(ctx, ATTACH_BUILTIN)

    assert ctx.new_page_calls == 0


async def test_builtin_does_not_own_the_page() -> None:
    """那是用户的窗口，不是我们开的，我们没有关闭它的权利。"""
    session, _ = await _attach(FakeContext([FakePage("visible")]), ATTACH_BUILTIN)

    assert session.owns_page is False


async def test_builtin_waits_for_page_to_appear() -> None:
    """connect 成功时 WebView 首屏可能还没挂上，不能立刻退化为 new_page。"""
    visible = FakePage("visible")
    ctx = DelayedContext(visible, appear_after=3)
    session, _ = await _attach(ctx, ATTACH_BUILTIN)

    assert session._page is visible
    assert ctx.new_page_calls == 0


async def test_builtin_close_leaves_page_alone() -> None:
    """关掉它等于把用户的浏览器窗口关掉——比泄漏一个 page 严重得多。"""
    visible = FakePage("visible")
    session, pw = await _attach(FakeContext([visible]), ATTACH_BUILTIN)

    await session.close()

    assert visible.close_calls == 0, "真实渲染窗口的页面被会话关掉了"
    assert pw.stopped is True, "连接本身必须断开"


async def test_builtin_demote_leaves_page_alone() -> None:
    """降级是"静默换一条更稳的路"，不该制造白屏这种新的可见故障。"""
    visible = FakePage("visible")
    session, _ = await _attach(FakeContext([visible]), ATTACH_BUILTIN)

    await session._demote_to_managed()

    assert visible.close_calls == 0
    assert session.mode == "none"


async def test_builtin_fallback_page_is_still_not_owned() -> None:
    """兜底新建的页面也可能就是 WebView 正在显示的那个，同样不归我们关。"""
    ctx = FakeContext([])
    session, _ = await _attach(ctx, ATTACH_BUILTIN)

    assert ctx.new_page_calls == 1, "实在等不到可见页面才允许兜底"
    assert session.owns_page is False


async def test_builtin_installs_probe_on_attached_page() -> None:
    """探针装在用户可见的那个页面上，否则等待与 changed 判定全部落空。"""
    visible = FakePage("visible")
    await _attach(FakeContext([visible]), ATTACH_BUILTIN)

    assert visible.init_scripts == 1


# ── user：自己开隔离 tab ────────────────────────────────────────────────


async def test_user_creates_isolated_tab() -> None:
    """接管用户浏览器时绝不碰已有标签页——No session hijacking。"""
    existing = FakePage("user-tab")
    ctx = FakeContext([existing])
    session, _ = await _attach(ctx, ATTACH_USER)

    assert session._page is not existing
    assert ctx.new_page_calls == 1
    assert session.attach_kind == ATTACH_USER


async def test_user_owns_its_tab() -> None:
    session, _ = await _attach(FakeContext([FakePage("user-tab")]), ATTACH_USER)

    assert session.owns_page is True


async def test_user_close_closes_only_its_own_tab() -> None:
    existing = FakePage("user-tab")
    ctx = FakeContext([existing])
    session, pw = await _attach(ctx, ATTACH_USER)

    await session.close()

    assert existing.close_calls == 0, "碰了用户已有的标签页"
    assert session._page is None or ctx._pages[-1].close_calls == 1
    assert pw.stopped is True


async def test_user_demote_closes_only_its_own_tab() -> None:
    existing = FakePage("user-tab")
    session, _ = await _attach(FakeContext([existing]), ATTACH_USER)

    await session._demote_to_managed()

    assert existing.close_calls == 0


# ── 路由：归属必须和端点一起给出来 ──────────────────────────────────────


def _fake_probe(alive: set[int]):
    def _probe(url: str) -> bool:
        port = int(url.split(":")[2].split("/")[0])
        return port in alive

    return _probe


async def test_probe_marks_builtin_endpoint() -> None:
    r = DriverRouter()
    r.set_builtin_cdp_port(9333)
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe({9222, 9333}),
    ):
        target = await r.probe_cdp_target()

    assert target == CdpTarget("http://127.0.0.1:9333", ATTACH_BUILTIN)
    assert target.is_builtin is True


async def test_probe_marks_user_endpoint() -> None:
    r = DriverRouter()
    r.set_builtin_cdp_port(9333)
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe({9222}),
    ):
        target = await r.probe_cdp_target()

    assert target == CdpTarget("http://127.0.0.1:9222", ATTACH_USER)
    assert target.is_builtin is False


async def test_probe_returns_none_when_nothing_alive() -> None:
    r = DriverRouter()
    r.set_builtin_cdp_port(9333)
    with patch(
        "fnixagent.core.tools.driver_router._probe_endpoint",
        side_effect=_fake_probe(set()),
    ):
        assert await r.probe_cdp_target() is None


async def test_ensure_uses_target_kind_from_router() -> None:
    """端到端串一遍：路由说 builtin，会话就必须按 builtin 的语义 attach。"""
    visible = FakePage("visible")
    ctx = FakeContext([visible])
    pw = FakePlaywright(ctx)
    session = _new_session()
    r = DriverRouter()
    r.set_builtin_cdp_port(9333)

    with (
        patch("fnixagent.core.tools.driver_router._probe_endpoint",
              side_effect=_fake_probe({9333})),
        patch("fnixagent.core.tools.driver_router.get_driver_router",
              return_value=r),
        patch("playwright.async_api.async_playwright", lambda: pw),
    ):
        page = await session._ensure()

    assert page is visible
    assert session.attach_kind == ATTACH_BUILTIN
    assert session.owns_page is False
