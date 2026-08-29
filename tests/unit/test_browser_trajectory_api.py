"""Phase 5 录制/重放的接口层测试。

handler 是**直接 await 调用**而不是走 TestClient——Playwright 的异步对象绑定在
创建它的事件循环上，TestClient 每个请求一个循环会把它弄坏。直接调用 handler
既跑到了真实的接口代码，又和浏览器处在同一个循环里。

录制/重放的行为本身由 test_browser_trajectory.py 的真浏览器用例覆盖，
这里验证的是接口层的职责：录制会话生命周期、落盘/读取、以及 id 的路径安全。
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
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.api.routers import browser as browser_router  # noqa: E402
from fnixagent.core.tools.browser import BrowserSession  # noqa: E402
from fnixagent.core.tools.browser_trajectory import Trajectory  # noqa: E402

pytestmark = pytest.mark.asyncio

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


@pytest.fixture(autouse=True)
def traj_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """轨迹落盘到临时目录，别污染用户 home。"""
    d = tmp_path / "trajectories"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(browser_router, "_TRAJ_DIR", d)
    monkeypatch.setattr(browser_router, "_RECORDERS", {})
    return d


@pytest.fixture
async def session(monkeypatch: pytest.MonkeyPatch) -> Any:
    s = BrowserSession()
    monkeypatch.setattr(browser_router, "_session", s)
    yield s
    await s.close()


# ── 安全 ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    ["../../etc/passwd", "a/b", "", ".", "..", "foo bar", "x" * 200, "a\\b", "a;b"],
)
async def test_trajectory_id_rejects_path_traversal(bad: str) -> None:
    """轨迹 id 会被拼进文件路径——必须挡住穿越与非法字符。"""
    with pytest.raises(ValueError):
        browser_router._traj_path(bad)


async def test_trajectory_id_accepts_safe_names() -> None:
    for good in ["login", "traj-1", "a_b.c", "Trajectory2"]:
        p = browser_router._traj_path(good)
        assert p.parent == browser_router._TRAJ_DIR
        assert p.name == f"{good}.json"


async def test_chinese_named_trajectories_do_not_collide() -> None:
    """回归：中文名如果只做字符清洗，两个不同名字会落成同一个 id 互相覆盖。

    "登录演示" 与 "搜索流程" 清洗后都是空串。id 必须带录制会话号兜底，
    ASCII 名保持可读、中文名退化成 traj-<rid>，两种都不撞车。
    """
    a = browser_router._traj_id_for("登录演示", "aaa111222333")
    b = browser_router._traj_id_for("搜索流程", "bbb444555666")
    assert a != b, f"中文名轨迹 id 撞车: {a}"
    # 两个 id 都必须能通过白名单校验（否则保存时会被拒）
    browser_router._traj_path(a)
    browser_router._traj_path(b)

    # ASCII 名保留可读性
    assert browser_router._traj_id_for("login-flow", "ccc777888999") == "login-flow-ccc777888999"


# ── 录制会话生命周期 ────────────────────────────────────────────


async def test_record_session_lifecycle(session: Any, minisite_server: str) -> None:
    base = minisite_server
    await session.navigate(f"{base}/login.html?next=index.html")

    started = await browser_router.trajectory_record_start(
        browser_router.RecordStartRequest(name="登录演示")
    )
    rid = started["record_id"]
    assert started["ok"] is True

    r = await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="goto", url=f"{base}/login.html?next=index.html")
    )
    assert r["ok"] is True and r["step_count"] == 1

    snap = await session.snapshot_ref()
    user_ref = next(x for x in snap.refs if x.name == "用户名").ref
    pass_ref = next(x for x in snap.refs if x.name == "密码").ref
    login_ref = next(x for x in snap.refs if x.name == "登录" and x.role == "button").ref

    await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="type", ref=f"@{user_ref}", text="demo")
    )
    await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="type", ref=f"@{pass_ref}", text="fnix2026")
    )
    await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="click", ref=f"@{login_ref}")
    )

    stopped = await browser_router.trajectory_record_stop(rid)
    assert stopped["ok"] is True
    assert stopped["step_count"] == 4
    tid = stopped["trajectory_id"]
    assert Path(stopped["path"]).exists()

    # 密码不能出现在落盘文件里
    raw = Path(stopped["path"]).read_text(encoding="utf-8")
    assert "fnix2026" not in raw

    # 录制会话已结束，再录应报错而不是静默追加
    again = await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="refresh")
    )
    assert again["ok"] is False

    # 列表与读取
    listed = await browser_router.trajectory_list()
    assert any(i["id"] == tid for i in listed["items"])
    got = await browser_router.trajectory_get(tid)
    assert got["ok"] is True and len(got["trajectory"]["steps"]) == 4


async def test_replay_via_api_logs_in(session: Any, minisite_server: str, traj_dir: Path) -> None:
    """接口层重放：跑完必须真的登录成功，而不只是返回 ok。"""
    base = minisite_server
    await session.navigate(f"{base}/index.html")

    started = await browser_router.trajectory_record_start(
        browser_router.RecordStartRequest(name="登录演示")
    )
    rid = started["record_id"]
    await session.navigate(f"{base}/login.html?next=index.html")
    await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="goto", url=f"{base}/login.html?next=index.html")
    )
    snap = await session.snapshot_ref()
    for label, val in (("用户名", "demo"), ("密码", "fnix2026")):
        ref = next(x for x in snap.refs if x.name == label).ref
        await browser_router.trajectory_record_step(
            rid, browser_router.RecordStepRequest(action="type", ref=f"@{ref}", text=val)
        )
    login_ref = next(x for x in snap.refs if x.name == "登录" and x.role == "button").ref
    await browser_router.trajectory_record_step(
        rid, browser_router.RecordStepRequest(action="click", ref=f"@{login_ref}")
    )
    stopped = await browser_router.trajectory_record_stop(rid)

    # 重来一次：清登录态，回到登录页，然后重放
    await session._page.evaluate("() => localStorage.removeItem('user')")
    await session.navigate(f"{base}/login.html?next=index.html")
    assert not await session._page.evaluate("() => !!localStorage.getItem('user')")

    res = await browser_router.trajectory_replay(
        browser_router.ReplayRequest(
            trajectory_id=stopped["trajectory_id"],
            values={"用户名": "demo", "密码": "fnix2026"},
        )
    )
    assert res["ok"], f"重放失败: {res['error']}（{res['assert_failures']}）"
    assert res["steps_ok"] == 4
    assert await session._page.evaluate("() => !!localStorage.getItem('user')"), "应真的登录成功"


async def test_replay_reports_missing_input_clearly(
    session: Any, minisite_server: str, traj_dir: Path
) -> None:
    """缺输入值时必须明确报出是哪一步缺，而不是拿空串糊过去。"""
    traj = Trajectory(name="需要输入").from_dict(
        {
            "version": 1,
            "steps": [{"action": "type", "name": "密码", "role": "textbox"}],
        }
    )
    p = traj_dir / "needs-input.json"
    traj.save(p)

    res = await browser_router.trajectory_replay(
        browser_router.ReplayRequest(trajectory_id="needs-input")
    )
    assert res["ok"] is False
    assert "需要输入" in res["error"]


async def test_replay_unknown_trajectory_returns_error(session: Any) -> None:
    res = await browser_router.trajectory_replay(
        browser_router.ReplayRequest(trajectory_id="no-such-trajectory")
    )
    assert res["ok"] is False and "不存在" in res["error"]


async def test_delete_trajectory(session: Any, traj_dir: Path) -> None:
    Trajectory(name="可删除").save(traj_dir / "deletable.json")

    ok = await browser_router.trajectory_delete("deletable")
    assert ok["ok"] is True
    assert not (traj_dir / "deletable.json").exists()

    missing = await browser_router.trajectory_delete("deletable")
    assert missing["ok"] is False
