"""内置浏览器优先策略：搜索关键词内置化 + 系统浏览器唤起拦截。

覆盖 2026-08-29 修复：
  - _normalize_url：搜索关键词（含空格 / 无域名后缀）→ 内置百度搜索，
    域名形态补 https://，完整 URL 原样，危险协议仍拦截。
  - _opens_url_in_system_browser + run_command：start/explorer/xdg-open 等
    唤起系统默认浏览器打开网址的命令被拦截并引导改用 browser_act(action="goto")。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fnixagent.core.tools import browser_policy
from fnixagent.core.tools.browser import _UNTRUSTED_NOTICE, _l1_domain_gate, _normalize_url
from fnixagent.core.tools.workspace import (
    WorkspaceTools,
    _opens_url_in_system_browser,
)


@pytest.fixture(autouse=True)
def _isolated_policy_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把域名信任策略的存储位置指到临时目录。

    不隔离的话这些用例会写**用户真实的** `~/.local/share/fnixagent/
    browser_policy.json`——批准过的域名被永久记住，于是同一套测试第二次
    运行时目标域名已经是"此前已批准"，确认闸不再触发，用例自己把自己跑挂
    （2026-08-29 实测：首次全绿，再跑就红，且用户配置里多出一条
    gate.example.com）。

    单测改写用户配置本身就是缺陷，测试自毁只是它最容易被看见的那一面。
    """
    monkeypatch.setattr(browser_policy, "_POLICY_FILE", tmp_path / "browser_policy.json")

# ── _normalize_url：内置浏览器内完成搜索 ────────────────────────────


def test_normalize_domain_gets_scheme() -> None:
    assert _normalize_url("example.com") == "https://example.com"
    assert _normalize_url("12306.cn") == "https://12306.cn"
    assert _normalize_url("example.com/path?q=1") == "https://example.com/path?q=1"


def test_normalize_full_url_kept() -> None:
    assert _normalize_url("https://example.com/x") == "https://example.com/x"
    assert _normalize_url("http://example.com") == "http://example.com"


def test_normalize_search_keyword_to_builtin_search() -> None:
    # 中文关键词（无域名）→ 内置百度搜索
    url = _normalize_url("北京天气")
    assert url.startswith("https://www.baidu.com/s?wd=")
    assert "%E5%8C%97%E4%BA%AC%E5%A4%A9%E6%B0%94" in url
    # 单个英文单词（无域名后缀）同样视为搜索
    assert _normalize_url("weather").startswith("https://www.baidu.com/s?wd=weather")
    # 含空格的查询短语
    assert _normalize_url("python 教程 入门").startswith("https://www.baidu.com/s?wd=")


def test_normalize_localhost_with_port_is_url_not_search() -> None:
    """本地预览地址（host:port，无域名后缀）必须识别为 URL，不能被当成搜索词。"""
    assert _normalize_url("localhost:5175") == "http://localhost:5175"
    assert _normalize_url("127.0.0.1:8003") == "http://127.0.0.1:8003"
    assert _normalize_url("localhost") == "http://localhost"
    assert _normalize_url("localhost:5175/docs") == "http://localhost:5175/docs"
    assert _normalize_url("::1:8080") == "http://::1:8080"
    # 局域网 IP 带端口仍是普通网址（默认 https）
    assert _normalize_url("192.168.1.10:8080") == "https://192.168.1.10:8080"


def test_normalize_localhost_defaults_to_http_not_https() -> None:
    """本地主机默认 http：本地开发服务没有 TLS，补 https 会直接 SSL 协议错误。"""
    for raw in ("localhost", "localhost:5175", "127.0.0.1:8003", "0.0.0.0:3000"):
        assert _normalize_url(raw).startswith("http://"), raw
    # 公网域名仍走 https
    assert _normalize_url("example.com").startswith("https://")


def test_normalize_blocked_schemes_still_rejected() -> None:
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "about:blank"):
        with pytest.raises(ValueError):
            _normalize_url(bad)


def test_normalize_empty_rejected() -> None:
    with pytest.raises(ValueError):
        _normalize_url("   ")


# ── run_command：禁止唤起系统浏览器打开网址 ──────────────────────────


def test_opens_url_detector_positives() -> None:
    assert _opens_url_in_system_browser("start https://www.bing.com/search?q=x")
    assert _opens_url_in_system_browser('start "标题" https://example.com')
    assert _opens_url_in_system_browser("explorer https://example.com")
    assert _opens_url_in_system_browser("cmd /c start http://example.com")
    assert _opens_url_in_system_browser("Start-Process https://example.com")
    assert _opens_url_in_system_browser("xdg-open https://example.com")
    assert _opens_url_in_system_browser("open https://example.com")
    assert _opens_url_in_system_browser("start www.example.com")


def test_opens_url_detector_negatives() -> None:
    assert not _opens_url_in_system_browser("start notepad")
    assert not _opens_url_in_system_browser("python main.py")
    assert not _opens_url_in_system_browser("curl https://example.com")
    assert not _opens_url_in_system_browser("start calc.exe")
    assert not _opens_url_in_system_browser("echo https://example.com")


async def test_run_command_blocks_system_browser_open(tmp_path: Path) -> None:
    tools = WorkspaceTools(str(tmp_path))
    result = await tools.run_command("start https://example.com")
    assert result.success is False
    assert result.error is not None
    assert "browser_act" in result.error


async def test_run_command_guard_not_overblocking(tmp_path: Path) -> None:
    """普通命令不应被内置浏览器守卫误拦（守卫只在 URL 唤起场景触发）。

    注：实际 spawn 可能受执行环境限制（例如受限沙箱禁止 powershell 派生），
    本用例只断言未触发内置浏览器引导——命令正常放行到执行层。
    """
    tools = WorkspaceTools(str(tmp_path))
    result = await tools.run_command("echo ok")
    if result.error is not None:
        assert "browser_act" not in result.error


# ── L1 新域确认闸（设计文档 §4.1：接管用户浏览器时首访新域名需确认） ──


def _seq_cid_factory():
    n = 0

    def _factory() -> str:
        nonlocal n
        n += 1
        return f"cid-{n}"

    return _factory


def test_l1_gate_managed_mode_always_passes() -> None:
    approved: set[str] = set()
    pending: dict[str, tuple[str, float]] = {}
    proceed, cid, msg = _l1_domain_gate(
        "managed", "https://new-domain.example.com/", approved, pending, None, _seq_cid_factory()
    )
    assert proceed is True and cid is None and msg is None


def test_l1_gate_blocks_new_domain_then_single_consume() -> None:
    approved: set[str] = set()
    pending: dict[str, tuple[str, float]] = {}
    factory = _seq_cid_factory()
    # 首访新域 → 拦截 + 发令牌
    proceed, cid, msg = _l1_domain_gate(
        "cdp-attach", "https://mail.example.com/", approved, pending, None, factory
    )
    assert proceed is False and cid == "cid-1" and "确认" in (msg or "")
    # 无效令牌 → 仍拦截（新令牌）
    proceed2, cid2, _ = _l1_domain_gate(
        "cdp-attach", "https://mail.example.com/", approved, pending, "wrong", factory
    )
    assert proceed2 is False and cid2 == "cid-2"
    # 有效令牌 → 放行 + 域名计入已批准（本会话不再询问）
    proceed3, cid3, _ = _l1_domain_gate(
        "cdp-attach", "https://mail.example.com/", approved, pending, "cid-2", factory
    )
    assert proceed3 is True and cid3 is None
    assert "mail.example.com" in approved
    proceed4, _, _ = _l1_domain_gate(
        "cdp-attach", "https://mail.example.com/inbox", approved, pending, None, factory
    )
    assert proceed4 is True  # 已批准域名免确认


def test_l1_gate_token_not_reusable_for_other_domain() -> None:
    approved: set[str] = set()
    pending: dict[str, tuple[str, float]] = {}
    factory = _seq_cid_factory()
    _, cid_a, _ = _l1_domain_gate(
        "cdp-attach", "https://a.com/", approved, pending, None, factory
    )
    # 用 a.com 的令牌访问 b.com → 不放行
    proceed, _, _ = _l1_domain_gate(
        "cdp-attach", "https://b.com/", approved, pending, cid_a, factory
    )
    assert proceed is False


def test_untrusted_notice_present_in_constants() -> None:
    assert "不可信" in _UNTRUSTED_NOTICE


# ── 拦截态必须能被前端轮询到（version 递增） ────────────────────────


class _FakePage:
    """最小页面桩：让 navigate 能在不拉起真实 Chromium 的情况下跑完状态机。"""

    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **_kw: object) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_load_state(self, *_a: object, **_kw: object) -> None:
        return None

    async def title(self) -> str:
        return "fake"

    async def screenshot(self, **_kw: object) -> bytes:
        return b"\xff\xd8\xff"


def _session_in_cdp_mode() -> tuple[Any, _FakePage]:
    from fnixagent.core.tools.browser import BrowserSession

    session = BrowserSession()
    page = _FakePage()
    session._page = page  # 绕过 _ensure() 的真实拉起
    session._mode = "cdp-attach"
    return session, page


async def test_navigate_gate_bumps_version_and_keeps_pending_url() -> None:
    """拦截态必须递增 version 并保留目标地址。

    前端按 version 增量轮询（unchanged 时丢弃响应），不 bump 则 AI 触发的
    拦截永远推不到前端，确认闸形同虚设；没有 pending_url 则前端无法重试。
    """
    session, _ = _session_in_cdp_mode()
    before = session._state.version
    st = await session.navigate("https://gate.example.com/")
    assert st.requires_confirmation is True
    assert st.confirmation_id is not None
    assert st.version > before
    assert st.pending_url == "https://gate.example.com/"
    assert st.error is not None and "确认" in st.error


async def test_navigate_gate_approve_retry_consumes_token_once() -> None:
    """批准后带令牌重试：放行、清空拦截态、令牌单次消费。"""
    session, page = _session_in_cdp_mode()
    st = await session.navigate("https://gate.example.com/")
    cid = st.confirmation_id
    assert cid is not None

    # 批准 → 带令牌重试
    st2 = await session.navigate("https://gate.example.com/", confirmation_id=cid)
    assert st2.requires_confirmation is False
    assert st2.confirmation_id is None
    assert st2.pending_url == ""
    assert st2.error is None
    assert page.goto_calls == ["https://gate.example.com/"]
    # 同域名后续访问免确认
    st3 = await session.navigate("https://gate.example.com/inbox")
    assert st3.requires_confirmation is False
    assert len(page.goto_calls) == 2
