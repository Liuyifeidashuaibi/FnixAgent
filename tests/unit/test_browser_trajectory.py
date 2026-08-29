"""Phase 5 录制/重放：单测 + 真实浏览器端到端。

路线文档的执行纪律第 2 条：每期改动必须有单测 + 一条端到端实测证据。
所以这里既有确定性假会话跑策略，也有真 Chromium 跑登录流程——
只跑假会话的话，"元素名解析""状态断言"这些和真实 DOM 打交道的行为
等于没验证。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import functools
import http.server
import json
import socket
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.core.tools.browser import BrowserSession  # noqa: E402
from fnixagent.core.tools.browser_refs import REF_ATTR  # noqa: E402
from fnixagent.core.tools.browser_trajectory import (  # noqa: E402
    TRAJECTORY_VERSION,
    Trajectory,
    TrajectoryRecorder,
    TrajectoryReplayer,
    TrajectoryStep,
    _norm_url,
)

pytestmark = pytest.mark.asyncio

# ── 确定性假会话（策略层用，不碰浏览器，毫秒级）────────────────────


class _El:
    def __init__(self, ref: str, role: str, name: str) -> None:
        self.ref, self.role, self.name = ref, role, name
        self.value = ""


class _Snap:
    def __init__(self, url: str, els: list[_El]) -> None:
        self.url, self.refs = url, els

    def get(self, ref: str) -> Any:
        t = str(ref).lstrip("@")
        for r in self.refs:
            if r.ref == t:
                return r
        return None


class _State:
    def __init__(
        self,
        url: str,
        changed: bool = False,
        url_changed: bool = False,
        error: str | None = None,
    ) -> None:
        self.url, self.changed, self.url_changed, self.error = url, changed, url_changed, error


class _FakeSession:
    """元素用 (role, name) 列表定义，ref 编号按列表顺序生成。

    这样可以制造真实世界里最常见的漂移：**页面前插了一个元素，编号整体
    后移，但元素名没变**。重放必须靠名字找回目标，而不是照抄编号。
    """

    def __init__(self, url: str = "http://t.test/") -> None:
        self.url = url
        self.specs: list[tuple[str, str]] = []
        self.typed: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        self.click_changes = True
        self.click_error = ""

    def insert_front(self, role: str, name: str) -> None:
        """在 DOM 前面插一个元素——此后所有 ref 编号 +1。"""
        self.specs.insert(0, (role, name))

    async def snapshot_ref(self, viewport_only: bool = True, limit: int = 60) -> _Snap:
        return _Snap(self.url, [_El(f"e{i + 1}", r, n) for i, (r, n) in enumerate(self.specs)])

    async def navigate(self, raw_url: str, confirmation_id: str | None = None) -> _State:
        self.url = raw_url
        return _State(raw_url, changed=True, url_changed=True)

    async def click_ref(self, ref: str) -> _State:
        self.clicked.append(ref)
        return _State(self.url, changed=self.click_changes, error=self.click_error or None)

    async def click_text(self, text: str) -> _State:
        self.clicked.append(f"text:{text}")
        return _State(self.url, changed=self.click_changes)

    async def type_ref(self, ref: str, text: str, submit: bool = False) -> _State:
        self.typed.append((ref, text))
        return _State(self.url, changed=False)

    async def type_into(self, text: str, selector_or_label: str, submit: bool = False) -> _State:
        self.typed.append((selector_or_label, text))
        return _State(self.url, changed=False)

    async def scroll(self, direction: str = "down", amount: int = 480) -> _State:
        return _State(self.url, changed=False)

    async def history(self, op: str) -> _State:
        return _State(self.url, changed=True)


@pytest.fixture
def sess() -> _FakeSession:
    s = _FakeSession()
    s.specs = [("link", "首页"), ("button", "登录"), ("textbox", "用户名"), ("textbox", "密码")]
    return s


# ── 录制 ────────────────────────────────────────────────────────


async def test_record_captures_ref_name_and_post_state(sess: _FakeSession) -> None:
    rec = TrajectoryRecorder(sess, name="登录演示")
    await rec.record("goto", url="http://t.test/login")
    await rec.record("type", ref="@e3", text="demo")
    await rec.record("click", ref="@e2")

    steps = rec.trajectory.steps
    assert [s.action for s in steps] == ["goto", "type", "click"]
    # 元素名必须录下来——重放靠它重新定位，编号会漂移
    assert steps[1].name == "用户名" and steps[1].role == "textbox"
    assert steps[2].name == "登录" and steps[2].ref == "e2"
    # 每步都带动作之后的状态断言
    assert steps[1].assert_changed is False
    assert steps[2].assert_changed is True
    assert steps[2].assert_url == "http://t.test/login"


async def test_typed_value_not_persisted_by_default(sess: _FakeSession) -> None:
    """默认不把输入内容落盘——演示一次登录，这里就是密码。"""
    rec = TrajectoryRecorder(sess)
    await rec.record("type", ref="@e4", text="fnix2026-super-secret")

    step = rec.trajectory.steps[0]
    assert step.value is None
    assert step.needs_value is True

    # 落盘文件里不能出现明文
    p = rec.trajectory.save(Path(__file__).parent / "_traj_tmp" / "secret.json")
    raw = p.read_text(encoding="utf-8")
    assert "fnix2026-super-secret" not in raw
    assert json.loads(raw)["steps"][0].get("value") is None


async def test_capture_values_persists_literal_when_opted_in(sess: _FakeSession) -> None:
    rec = TrajectoryRecorder(sess, capture_values=True)
    await rec.record("type", ref="@e3", text="搜索关键词")

    step = rec.trajectory.steps[0]
    assert step.value == "搜索关键词"
    assert step.needs_value is False


# ── 重放：定位 ──────────────────────────────────────────────────


async def test_replay_resolves_by_name_when_ref_numbers_drift(sess: _FakeSession) -> None:
    """页面前插一个元素后编号整体后移；重放必须按名字找回，而不是点错人。"""
    rec = TrajectoryRecorder(sess)
    await rec.record("click", ref="@e2")  # "登录" 按钮
    traj = rec.trajectory
    assert traj.steps[0].name == "登录"

    sess.insert_front("banner", "公告")  # 所有编号 +1
    sess.clicked.clear()

    res = await TrajectoryReplayer(sess).replay(traj)
    assert res.ok, res.error
    assert res.steps_ok == 1
    # 解析到的是漂移后的新编号 e3，而不是录制时的 e2（e2 现在是"公告"）
    assert sess.clicked == ["e3"]


async def test_replay_falls_back_to_recorded_ref_when_name_vanishes(sess: _FakeSession) -> None:
    """名字彻底不存在时退回录制编号——赌一把，但要在警告里说清楚。"""
    traj = Trajectory(steps=[TrajectoryStep(action="click", ref="e2", name="已下线的按钮")])
    sess.clicked.clear()

    res = await TrajectoryReplayer(sess).replay(traj)
    assert res.ok, res.error
    assert sess.clicked == ["e2"]


# ── 重放：状态断言（静默失败闸门）──────────────────────────────


async def test_replay_stops_when_action_does_nothing(sess: _FakeSession) -> None:
    """录制时页面变了、重放时纹丝不动 = 点了个没反应的东西。

    这是静默失败最典型的形态：驱动层不报错，但目标早就失效了。
    重放必须在这一步停下报失败，绝不能"跑完算成功"。
    """
    rec = TrajectoryRecorder(sess)
    await rec.record("click", ref="@e2")  # assert_changed=True

    sess.click_changes = False  # 重放时点了没反应
    res = await TrajectoryReplayer(sess).replay(rec.trajectory)

    assert res.ok is False
    assert res.failed_step == 0
    assert "毫无反应" in res.error
    assert res.assert_failures[0]["kind"] == "no_change"
    assert res.assert_failures[0]["fatal"] is True


async def test_replay_stops_on_url_mismatch(sess: _FakeSession) -> None:
    traj = Trajectory(
        steps=[TrajectoryStep(action="goto", params={"url": "http://t.test/a"}, assert_url="http://t.test/a")]
    )

    class _Stuck(_FakeSession):
        async def navigate(self, raw_url: str, confirmation_id: str | None = None) -> _State:
            return _State("http://t.test/elsewhere", changed=True, url_changed=True)

    res = await TrajectoryReplayer(_Stuck()).replay(traj)
    assert res.ok is False
    assert res.assert_failures[0]["kind"] == "url_mismatch"


async def test_extra_change_is_only_a_warning(sess: _FakeSession) -> None:
    """录制时没变、重放时变了：只提示，不判失败。

    页面多跑了个动画或异步模块就会出现这种情况，直接判失败会误杀。
    """
    traj = Trajectory(steps=[TrajectoryStep(action="click", ref="e2", name="登录", assert_changed=False)])
    sess.click_changes = True

    res = await TrajectoryReplayer(sess).replay(traj)
    assert res.ok is True
    assert res.steps_ok == 1
    assert len(res.warnings) == 1
    assert res.assert_failures[0]["fatal"] is False


async def test_url_normalization_ignores_trailing_slash_and_fragment() -> None:
    assert _norm_url("http://t.test/a/") == _norm_url("http://t.test/a")
    assert _norm_url("http://t.test/a#x") == _norm_url("http://t.test/a")
    assert _norm_url("http://t.test/a?q=1") != _norm_url("http://t.test/a")


# ── 重放：输入值 ────────────────────────────────────────────────


async def test_replay_requires_value_when_not_captured(sess: _FakeSession) -> None:
    """没录字面值又没在重放时给，必须明确报错并指明是哪一步——不能悄悄填空。"""
    traj = Trajectory(steps=[TrajectoryStep(action="type", ref="e3", name="用户名")])

    res = await TrajectoryReplayer(sess).replay(traj)
    assert res.ok is False
    assert "需要输入" in res.error
    assert "用户名" in res.error


async def test_replay_does_not_swallow_failed_healer_result(sess: _FakeSession) -> None:
    """回归：自愈失败时 value=None 不能被重放当成"没有状态可断言"而放过。"""
    from types import SimpleNamespace

    class _FailedHealer:
        async def click(self, *, ref: str) -> Any:
            return SimpleNamespace(ok=False, value=None, error="目标已消失")

    traj = Trajectory(
        steps=[TrajectoryStep(action="click", ref="e2", name="登录", assert_changed=False)]
    )
    res = await TrajectoryReplayer(sess, healer=_FailedHealer()).replay(traj)

    assert res.ok is False
    assert res.failed_step == 0
    assert "目标已消失" in res.error


async def test_replay_value_can_be_keyed_by_index_or_name(sess: _FakeSession) -> None:
    traj = Trajectory(
        steps=[
            TrajectoryStep(action="type", ref="e3", name="用户名"),
            TrajectoryStep(action="type", ref="e4", name="密码"),
        ]
    )
    # 一个按序号给、一个按元素名给，两种都要能用
    res = await TrajectoryReplayer(sess, values={0: "demo", "密码": "fnix2026"}).replay(traj)

    assert res.ok, res.error
    assert sess.typed == [("e3", "demo"), ("e4", "fnix2026")]


# ── 落盘 ────────────────────────────────────────────────────────


async def test_trajectory_json_roundtrip(sess: _FakeSession) -> None:
    rec = TrajectoryRecorder(sess, name="登录演示", capture_values=False)
    await rec.record("goto", url="http://t.test/login")
    await rec.record("type", ref="@e3", text="demo")
    await rec.record("click", ref="@e2")
    await rec.record("scroll", direction="down", amount=600)

    p = Path(__file__).parent / "_traj_tmp"
    path = rec.trajectory.save(p / "login.json")
    loaded = Trajectory.load(path)

    assert loaded.name == "登录演示"
    assert loaded.version == TRAJECTORY_VERSION
    assert len(loaded) == 4
    assert loaded.steps[1].name == "用户名"
    assert loaded.steps[1].needs_value is True
    assert loaded.steps[3].params == {"direction": "down", "amount": 600}
    # 重放录回来的轨迹仍然能跑通
    res = await TrajectoryReplayer(sess, values={"用户名": "demo"}).replay(loaded)
    assert res.ok, res.error


async def test_trajectory_version_mismatch_is_rejected() -> None:
    from fnixagent.core.tools.browser_trajectory import TRAJECTORY_VERSION as V

    with pytest.raises(ValueError, match="轨迹版本不兼容"):
        Trajectory.from_dict({"version": V + 99, "steps": []})


# ── 端到端：真 Chromium + 自建站点 ──────────────────────────────

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks" / "gui_driver"))


@pytest.fixture(scope="module")
def minisite_server() -> Any:
    try:
        from minisite import SITE_DIR, ensure_site
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"自建站点不可用: {e}")

    ensure_site()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture
async def real_session(minisite_server: str) -> Any:
    s = BrowserSession()
    yield s
    await s.close()


async def test_e2e_record_login_then_replay_actually_logs_in(
    real_session: Any, minisite_server: str
) -> None:
    """真浏览器端到端：演示一遍登录 → 重放 → 确实登录成功。

    这是 Phase 5 录制/重放的实测证据。断言的不是"重放没报错"，
    而是"重放后用户真的处于登录态"——只断言前者的话，等于没验证效果。
    """
    base = minisite_server
    await real_session.navigate(f"{base}/index.html")

    # ── 录制：用户演示一遍登录 ──
    rec = TrajectoryRecorder(real_session, name="登录演示")
    await rec.record("goto", url=f"{base}/login.html?next=index.html")
    snap = await real_session.snapshot_ref()
    user_ref = next(r for r in snap.refs if r.name == "用户名").ref
    pass_ref = next(r for r in snap.refs if r.name == "密码").ref
    login_ref = next(r for r in snap.refs if r.name == "登录" and r.role == "button").ref

    await rec.record("type", ref=f"@{user_ref}", text="demo")
    await rec.record("type", ref=f"@{pass_ref}", text="fnix2026")
    await rec.record("click", ref=f"@{login_ref}")

    traj = rec.trajectory
    assert len(traj) == 4
    # 密码不该出现在轨迹里（默认不落盘）
    assert all(s.value is None for s in traj.steps if s.action == "type")

    # ── 重放：先登出，再从干净状态重放 ──
    await real_session._page.evaluate("() => localStorage.removeItem('user')")
    assert await _logged_in(real_session) is False, "前置条件：应处于未登录态"

    await real_session.navigate(f"{base}/login.html?next=index.html")
    res = await TrajectoryReplayer(
        real_session, values={"用户名": "demo", "密码": "fnix2026"}
    ).replay(traj)

    assert res.ok, f"重放失败: {res.error}（断言明细: {res.assert_failures}）"
    assert res.steps_ok == 4, f"应有 4 步全部通过，实际 {res.steps_ok}"
    assert await _logged_in(real_session) is True, "重放后应真的处于登录态"


async def _goto_product(session: Any, base: str) -> None:
    """进商品页并等详情渲染完（站点刻意延迟 400ms）。"""
    await session.navigate(f"{base}/product.html?id=p01")
    await session.wait_for(text="加入购物车")


async def _cart(session: Any) -> dict[str, Any]:
    return dict(await session._page.evaluate("() => JSON.parse(localStorage.getItem('cart') || '{}')"))


async def _record_add_to_cart(session: Any, base: str) -> Trajectory:
    """演示一遍"加入购物车"：点真正生效的那个按钮（id=add）。"""
    await _goto_product(session, base)
    snap = await session.snapshot_ref()
    add_btns = [r for r in snap.refs if r.name == "加入购物车"]
    assert len(add_btns) >= 2, "商品页应至少有两个同名按钮（含诱饵）"

    # 取带 id=add 的那个（真正生效的），而不是 DOM 里靠前但没有处理函数的诱饵
    real = await session._page.evaluate(
        f"() => document.getElementById('add').getAttribute({REF_ATTR!r})"
    )
    assert real, "快照应已给可交互元素注入 ref 属性"
    rec = TrajectoryRecorder(session, name="加入购物车")
    await rec.record("click", ref=f"@{real}")
    assert rec.trajectory.steps[0].assert_changed is True, "点真按钮应记录到页面变化"
    return rec.trajectory


async def test_e2e_replay_stops_on_inert_target(real_session: Any, minisite_server: str) -> None:
    """真浏览器：重放漂到同名诱饵（点了没反应）必须被状态断言拦下。

    商品页有两个同名"加入购物车"，DOM 里靠前的是诱饵（没有处理函数）。
    重放按名字解析时会命中第一个——也就是诱饵。此时驱动层不报错，
    只有"录制时页面变了、重放时没变"这条断言能发现它。
    没有这条断言，重放就会"静静成功"，而购物车里其实什么都没有。
    """
    traj = await _record_add_to_cart(real_session, minisite_server)

    # 干净状态重来一遍
    await real_session._page.evaluate("() => localStorage.removeItem('cart')")
    await _goto_product(real_session, minisite_server)

    res = await TrajectoryReplayer(real_session).replay(traj)  # 不带自愈层

    assert res.ok is False, "重放点到了诱饵却报成功——状态断言失效了"
    assert res.failed_step == 0
    assert res.assert_failures[0]["kind"] == "no_change"
    assert res.assert_failures[0]["fatal"] is True
    assert await _cart(real_session) == {}, "购物车本就不该被加入任何东西"


async def test_e2e_replay_with_healer_recovers_and_cart_actually_updates(
    real_session: Any, minisite_server: str
) -> None:
    """承接上一个用例：接上自愈层后，同样的轨迹能救回来且购物车真的变了。

    断言的是"购物车里确实有 p01"，而不只是"重放没报错"——
    只断言后者，等于把静默失败又放过去了。
    """
    from fnixagent.core.tools.browser_healing import BrowserHealer

    traj = await _record_add_to_cart(real_session, minisite_server)

    await real_session._page.evaluate("() => localStorage.removeItem('cart')")
    await _goto_product(real_session, minisite_server)

    healer = BrowserHealer(real_session)
    res = await TrajectoryReplayer(real_session, healer=healer).replay(traj)

    assert res.ok, f"接自愈层后应能恢复，实际失败: {res.error}"
    assert res.steps_ok == 1
    assert (await _cart(real_session)).get("p01") == 1, "购物车里应真的多出一件 p01"


async def _logged_in(session: Any) -> bool:
    return bool(
        await session._page.evaluate("() => !!localStorage.getItem('user')")
    )
