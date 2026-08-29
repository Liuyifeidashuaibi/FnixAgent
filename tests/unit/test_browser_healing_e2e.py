"""Phase 3 端到端：自愈编排器接真实浏览器（真 Chromium，非 mock）。

这里验证的是策略单测验证不了的东西——钩子在真实 DOM 上真的能救回来：

  1. 点了没反应 → 自动换目标 → 成功（静默失败被拦截并自愈）
  2. ref 失效（DOM 重渲染）→ 重新快照 → 按名字找回新 ref → 成功
  3. 彻底无解 → 终止并上报，而不是无限重试
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, distribution, or use is strictly prohibited.

from __future__ import annotations

import functools
import http.server
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.core.tools.browser import BrowserSession  # noqa: E402
from fnixagent.core.tools.browser_healing import BrowserHealer  # noqa: E402
from fnixagent.core.tools.driver_errors import F4_TOOL_CHOICE  # noqa: E402
from fnixagent.core.tools.orchestrator import REFRESH, SUBSTITUTE  # noqa: E402

pytestmark = pytest.mark.asyncio

# 陷阱页：
#  - #decoy 长得像目标但点了没反应（模型若只看文本极易点错）
#  - #real  才是真正生效的按钮
#  - #rerender 点击后整块重渲染，旧 ref 全部失效
TRAP_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>自愈验证页</title></head><body>
<h1>自愈验证页</h1>
<div id='zone'>
  <button id='decoy'>提交申请</button>
  <button id='real'>提交申请</button>
  <button id='rerender'>重渲染</button>
</div>
<button id='nothing'>点了没反应</button>
<div id='out'>initial</div>
<script>
  function setOut(v) { document.getElementById('out').textContent = v; }
  document.getElementById('real').addEventListener('click', function () {
    setOut('submitted');
  });
  document.getElementById('rerender').addEventListener('click', function () {
    // 整块替换：此前注入的 data-fnix-ref 全部消失，旧 ref 一律失效
    var zone = document.getElementById('zone');
    zone.innerHTML = '';
    var b = document.createElement('button');
    b.id = 'real2';
    b.textContent = '提交申请';
    b.addEventListener('click', function () { setOut('rerendered'); });
    zone.appendChild(b);
  });
</script>
</body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_healing_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "healing.html").write_text(TRAP_PAGE, encoding="utf-8")
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
    await s.navigate(f"{server}/healing.html")
    yield s
    await s.close()


async def _out(session: Any) -> str:
    return str(await session._page.evaluate("() => document.getElementById('out').textContent"))


async def test_plain_click_without_healing_silently_fails(session: Any) -> None:
    """对照：不经自愈层时，点错目标会被当成成功——这就是静默失败。

    先证明问题真实存在，再证明自愈层解决了它。没有这个对照，
    "自愈有效"就只是自说自话。
    """
    snap = await session.snapshot_ref()
    decoy = next(r for r in snap.refs if r.name == "提交申请")
    state = await session.click_ref(decoy.ref)

    assert state.error is None, state.error  # 没报错
    assert state.changed is False  # 但页面根本没变
    assert await _out(session) == "initial"  # 模型会误以为提交成功


async def test_healer_recovers_from_inert_target(session: Any) -> None:
    """点中了没反应的同名按钮 → 自动换到真正生效的那个。

    页面上有两个同名按钮，第一个是诱饵。自愈层必须发现"点了没反应"，
    换目标后命中真正的按钮。
    """
    healer = BrowserHealer(session)
    snap = await session.snapshot_ref()
    same_name = [r for r in snap.refs if r.name == "提交申请"]
    assert len(same_name) >= 2, "fixture 应提供至少两个同名按钮"

    # 故意从诱饵开始：它的 ref 更小（DOM 顺序在前）
    result = await healer.click(ref=same_name[0].ref)

    assert result.ok is True, f"自愈未成功: {result.error}"
    assert await _out(session) == "submitted"
    assert SUBSTITUTE in result.recovery_used, (
        f"应通过换目标恢复，实际用了 {result.recovery_used}"
    )
    assert any(r.failure_class == F4_TOOL_CHOICE for r in result.records), (
        "无效点击应被归为 F4（目标选错）"
    )


async def test_healer_recovers_from_stale_ref(session: Any) -> None:
    """DOM 重渲染导致 ref 全部失效 → 重新快照 → 按元素名找回新目标。

    验证 refresh 钩子的关键细节：重新快照后 ref 编号会变，必须按**名字**
    映射，直接复用旧编号等于白刷新。
    """
    healer = BrowserHealer(session)
    # 先建一次快照，拿到重渲染按钮的 ref
    snap = await session.snapshot_ref()
    rerender = next(r for r in snap.refs if r.name == "重渲染")
    healer._snapshot = snap

    # 点重渲染：页面结构整体替换，此前的 ref 全部失效
    await session.click_ref(rerender.ref)

    # 换一个在重渲染后已经失效的旧 ref 去点，应触发 F5 → refresh
    stale = next((r for r in snap.refs if r.name == "提交申请"), None)
    assert stale is not None
    result = await healer.click(ref=stale.ref)

    assert result.ok is True, f"自愈未成功: {result.error}"
    assert await _out(session) == "rerendered"
    assert REFRESH in result.recovery_used, (
        f"应通过刷新上下文恢复，实际用了 {result.recovery_used}"
    )


async def test_healer_escalates_when_nothing_can_help(session: Any) -> None:
    """确实无解时必须停下并上报，而不是把预算烧完还假装努力过。

    页面上的"点了没反应"按钮无论换什么目标都不会生效——但 substitute 会
    尝试换目标，所以这里额外限制预算，确认它最终仍会收敛到上报。
    """
    from fnixagent.core.tools.orchestrator import Budget

    healer = BrowserHealer(session, budget=Budget(substitute=1, refresh=1, total=2))
    result = await healer.click(text="点了没反应")

    assert result.ok is False
    assert result.escalated is True, "无解时必须上报，不能返回成功"
    assert await _out(session) == "initial"
    # 关键：不是无限重试
    assert len(result.records) <= 3, f"尝试了 {len(result.records)} 次仍未收敛"


async def test_successful_click_needs_no_recovery(session: Any) -> None:
    """一次就成功的动作不该产生任何恢复开销。"""
    healer = BrowserHealer(session)
    snap = await session.snapshot_ref()
    real = [r for r in snap.refs if r.name == "提交申请"]
    # 第二个同名按钮才是生效的那个
    result = await healer.click(ref=real[-1].ref)

    assert result.ok is True
    assert result.recovery_used == [], "首次成功不该触发任何恢复"
    assert result.attempts == 1


async def test_healer_records_are_serialisable_for_audit(session: Any) -> None:
    """留痕要能直接落审计流——字段名与类型必须稳定。"""
    healer = BrowserHealer(session)
    await healer.click(text="点了没反应")

    assert len(healer.records) >= 1
    for rec in healer.records:
        d = rec.to_dict()
        assert set(d) == {
            "step", "action", "attempt", "ok", "failure_class",
            "recovery_action", "budget_left", "elapsed_ms", "error",
        }
        assert isinstance(d["ok"], bool)
        assert isinstance(d["budget_left"], int)


# ── expect：把"成功长什么样"交给调用方 ────────────────────────────────
#
# changed 闸门只能证明"页面动了"，证明不了"动对了"。点了"加入购物车并结算"，
# 页面当然也会动——这类错误 changed 拦不住，只有调用方说出预期才拦得住。
# 这组用例守的就是这条通道：生产里真的能用，而不是只存在于单测的参数里。

EXPECT_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>预期验证页</title></head><body>
<h1>商品</h1>
<button id='add'>加入购物车</button>
<button id='buy'>加入购物车并结算</button>
<div id='out'>ready</div>
<script>
  function setOut(v) { document.getElementById('out').textContent = v; }
  document.getElementById('add').addEventListener('click', function () {
    setOut('已加入购物车');
  });
  document.getElementById('buy').addEventListener('click', function () {
    // 页面同样会变——changed 闸门完全抓不到这次点错
    setOut('已直达结算');
  });
</script>
</body></html>"""


@pytest.fixture(scope="module")
def expect_server() -> Any:
    tmp = Path(__file__).parent / "_healing_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "expect.html").write_text(EXPECT_PAGE, encoding="utf-8")
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
async def expect_session(expect_server: str) -> Any:
    s = BrowserSession()
    await s.navigate(f"{expect_server}/expect.html")
    yield s
    await s.close()


async def _out_text(session: Any) -> str:
    return str(await session._page.evaluate("() => document.getElementById('out').textContent"))


async def test_expect_text_met_counts_as_success(expect_session: Any) -> None:
    healer = BrowserHealer(expect_session)
    result = await healer.click(text="加入购物车", expect_text="已加入购物车")

    assert result.ok is True, result.error
    assert await _out_text(expect_session) == "已加入购物车"


async def test_changed_alone_cannot_catch_a_wrong_but_reactive_click(
    expect_session: Any,
) -> None:
    """对照组：诱饵也会让页面变化，所以 changed 闸门抓不到这次点错。

    先证明 changed 不够，再证明 expect 够——没有这个对照，下一条用例的
    价值说不清。
    """
    healer = BrowserHealer(expect_session)
    # 诱饵按钮：点了页面确实变了，changed=True，但走的是结算流程
    result = await healer.click(text="加入购物车并结算")

    assert result.ok is True, "诱饵确实让页面变了，changed 闸门本就该放行"
    assert await _out_text(expect_session) == "已直达结算"


async def test_expect_text_unmet_is_reported_not_swallowed(expect_session: Any) -> None:
    """核心：点了、页面变了，但预期没出现 → 必须如实判失败。

    这是"成功是真成功"在生产里真正落地的一条。少了它，上面那个对照组的
    误点就会被一路当成成功汇报下去。
    """
    healer = BrowserHealer(expect_session)
    result = await healer.click(text="加入购物车并结算", expect_text="已加入购物车")

    assert result.ok is False, "预期未达成却报了成功——这正是要拦的谎报"
    assert result.escalated is True
    assert "验证" in (result.error or ""), result.error
    # 页面确实变了，所以这不是"点了没反应"，是"动了但动错了"
    assert await _out_text(expect_session) == "已直达结算"


async def test_without_expect_behaviour_is_unchanged(expect_session: Any) -> None:
    """护栏：不传 expect 时不能改变既有行为——新闸门不该动到没用它的人。"""
    healer = BrowserHealer(expect_session)
    result = await healer.click(text="加入购物车")

    assert result.ok is True, result.error
    assert result.recovery_used == []
