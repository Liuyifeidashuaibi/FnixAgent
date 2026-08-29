"""Phase 2 验收：auto-wait + 动作后验证（changed / url_changed / error_class）。

核心断言不是"动作没报错"，而是"动作真的改变了页面"——点了没反应必须能被
检测出来（changed=False），否则模型会一路错下去还以为成功了。
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
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.core.tools.browser import BrowserSession  # noqa: E402

PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>动作验证页</title></head><body>
<h1>动作验证页</h1>
<button id='fast' onclick="document.getElementById('out').textContent='fast-done'">立即改变</button>
<button id='slow' onclick="setTimeout(function(){
  document.getElementById('out').textContent='slow-done';}, 700)">延迟改变</button>
<button id='inert'>点了没反应</button>
<a id='link' href='#target'>跳到锚点</a>
<div id='out'>initial</div>
<div id='target'>目标区域</div>
</body></html>"""

# 自续动画页面：rAF 循环不停注册新定时器。用途是验证"定时器排空"这个新信号
# 不会反过来把每一步动作都拖到超时上限——那是引入它时最大的回归风险。
LOOP_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>动画循环页</title></head><body>
<h1>动画循环页</h1>
<button id='go' onclick="document.getElementById('out').textContent='done'">改变</button>
<div id='out'>initial</div>
<script>
  var n = 0;
  function tick() { n++; window.requestAnimationFrame(tick); }
  window.requestAnimationFrame(tick);
</script>
</body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_actions_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "actions.html").write_text(PAGE, encoding="utf-8")
    (tmp / "loop.html").write_text(LOOP_PAGE, encoding="utf-8")
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
    await s.navigate(f"{server}/actions.html")
    yield s
    await s.close()


async def test_click_that_changes_page_marks_changed(session: Any) -> None:
    state = await session.click_text("立即改变")
    assert state.error is None, state.error
    assert state.changed is True
    assert state.last_action == "click_text"


async def test_click_with_no_effect_is_detected(session: Any) -> None:
    """点了没反应必须能被检测出来——这是动作后验证的核心价值。

    旧实现里这种点击"没报错就算成功"，模型会以为操作生效并继续下一步。
    """
    snap = await session.snapshot_ref()
    inert = next(r for r in snap.refs if r.name == "点了没反应")
    state = await session.click_ref(inert.ref)
    assert state.error is None  # 动作本身没失败
    assert state.changed is False  # 但页面根本没变
    out = await session._page.evaluate("() => document.getElementById('out').textContent")
    assert out == "initial"


async def test_state_wait_catches_delayed_change(session: Any) -> None:
    """延迟 700ms 才生效的点击，状态等待必须能等到（固定 sleep 可能漏）。"""
    state = await session.click_text("延迟改变")
    assert state.error is None, state.error
    assert state.changed is True, "延迟变化应被状态等待捕获"
    out = await session._page.evaluate("() => document.getElementById('out').textContent")
    assert out == "slow-done"


async def test_url_changed_flag_on_navigation(session: Any) -> None:
    """锚点跳转不改 DOM 但改 URL，必须被 url_changed 捕获（不能只靠 DOM 签名）。"""
    state = await session.click_text("跳到锚点")
    assert state.error is None, state.error
    assert state.url_changed is True
    assert "#target" in state.url


async def test_error_class_is_set_for_missing_target(session: Any) -> None:
    """找不到目标 → F4（工具选择错误），供编排层换目标或换工具。"""
    state = await session.click_text("这个文本页面上肯定没有")
    assert state.error is not None
    assert state.error_class == "F4", state.error_class


async def test_error_class_empty_on_success(session: Any) -> None:
    state = await session.click_text("立即改变")
    assert state.error is None
    assert state.error_class == ""


async def test_wait_for_text(session: Any) -> None:
    """显式等待：等某段文本出现。"""
    # 先让 out 变空，再延迟写入，验证 wait_for 真的在等
    await session._page.evaluate(
        """() => {
          document.getElementById('out').textContent = '';
          setTimeout(function(){
            document.getElementById('out').textContent = '终于出现了';
          }, 500);
        }"""
    )
    state = await session.wait_for(text="终于出现了", timeout_ms=5000)
    assert state.error is None, state.error


async def test_wait_for_timeout_is_f1(session: Any) -> None:
    state = await session.wait_for(text="永远不会出现的文本", timeout_ms=800)
    assert state.error is not None
    assert state.error_class == "F1", state.error_class


async def test_wait_for_selector(session: Any) -> None:
    state = await session.wait_for(selector="#target", timeout_ms=3000)
    assert state.error is None, state.error


# ── 状态等待的性能护栏 ──────────────────────────────────────────
# 上面几条保证"等得到"，下面两条保证"没白等"。缺了后者，状态等待很容易
# 退化成"永远等到超时上限"——比固定 sleep 还慢，却更难被发现。

async def test_instant_action_is_not_penalized(server: str) -> None:
    """瞬时完成的动作不该被拖慢——状态等待必须比固定 sleep 快。

    改成"等到超时上限"也能通过上面所有断言，所以这条护栏不可省。
    """
    from fnixagent.core.tools import browser as browser_mod

    s = BrowserSession()
    await s.navigate(f"{server}/actions.html")
    try:
        t0 = time.perf_counter()
        state = await s.click_text("立即改变")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert state.error is None, state.error
        assert state.changed is True
        # 无变更页面约 quiet_ms(300) 就返回；留足机器抖动余量
        assert elapsed_ms < browser_mod._SETTLE_TIMEOUT_MS * 0.6, (
            f"瞬时动作耗时 {elapsed_ms:.0f}ms，接近超时上限——状态等待退化了"
        )
    finally:
        await s.close()


async def test_animation_loop_does_not_pin_every_action_to_timeout(server: str) -> None:
    """带持续动画的页面不能把每步动作都拖到超时上限。

    这是引入"定时器排空"信号带来的最大回归风险：rAF 循环会不停注册新定时器，
    若无波次上限保护，等待条件永远不满足。
    """
    from fnixagent.core.tools import browser as browser_mod

    s = BrowserSession()
    await s.navigate(f"{server}/loop.html")
    try:
        t0 = time.perf_counter()
        state = await s.click_text("改变")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert state.error is None, state.error
        assert elapsed_ms < browser_mod._SETTLE_TIMEOUT_MS, (
            f"动画页面动作耗时 {elapsed_ms:.0f}ms，被自续循环钉死在超时上限"
        )
    finally:
        await s.close()
