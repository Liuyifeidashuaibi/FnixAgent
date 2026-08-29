"""域名信任策略的接口层（审计补漏）。

判定逻辑早就接在 `navigate` 上了，但**一个配置接口都没有**——用户只能手工去
改 `~/.local/share/fnixagent/browser_policy.json`。文档写的是"用户可配置的
受信任域列表"，代码里却是"用户得会找隐藏文件并手写 JSON"。

这组用例守的是"名副其实"：策略必须能被读、被改、被试算，而且改完立即生效。
handler 直接 await 调用（与 test_browser_trajectory_api.py 同理，避免
TestClient 每请求一个事件循环弄坏异步对象）。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

import pytest

from fnixagent.api.routers import browser as browser_router
from fnixagent.api.routers.browser import DomainPolicyPatch, DomainRequest
from fnixagent.core.tools import browser_policy
from fnixagent.core.tools.browser_policy import ALLOW, DENY

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _isolated_policy_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """策略落临时目录——不隔离就会写用户真实配置（详见 test_builtin_browser_policy.py）。"""
    target = tmp_path / "browser_policy.json"
    monkeypatch.setattr(browser_policy, "_POLICY_FILE", target)


# ── 读 ─────────────────────────────────────────────────────────────────


async def test_get_returns_policy_with_mode_labels() -> None:
    """设置面板要能直接消费：策略本体 + 各模式的人话说明。"""
    out = await browser_router.domain_policy_get()

    assert out["ok"] is True
    assert out["policy"]["mode"] == "ask_new"
    labels = {m["id"]: m["label"] for m in out["modes"]}
    assert set(labels) == {"ask_new", "allowlist", "denylist", "open"}
    assert all(labels.values()), "每个模式都要有人话说明，不能让界面显示空白"


async def test_get_states_the_two_hard_rules() -> None:
    """两条硬规则必须在界面上说清楚。

    否则用户配了 allowlist 会发现本地开发全挂，然后以为功能坏了——本机地址
    永不拦截这条是刻意设计，不说出来就是坑。
    """
    out = await browser_router.domain_policy_get()

    joined = " ".join(out["rules"]).lower()
    assert "localhost" in joined or "本机" in joined
    assert "拒绝" in joined


# ── 改 ─────────────────────────────────────────────────────────────────


async def test_put_switches_mode_and_persists() -> None:
    out = await browser_router.domain_policy_put(DomainPolicyPatch(mode="allowlist"))

    assert out["ok"] is True
    assert out["policy"]["mode"] == "allowlist"
    # 落盘了才算配置，否则刷新页面就回到默认
    assert browser_policy.load_policy().mode == "allowlist"


async def test_put_updates_lists_and_normalises_case() -> None:
    await browser_router.domain_policy_put(
        DomainPolicyPatch(allowed=["Internal.Corp.com", " *.docs.example "])
    )
    p = browser_policy.load_policy()

    assert p.allowed == ["internal.corp.com", "*.docs.example"], p.allowed


async def test_put_leaves_untouched_fields_alone() -> None:
    """只传 mode 时不能把名单清空——局部更新接口把没传的字段抹掉是最常见的坑。"""
    await browser_router.domain_policy_put(DomainPolicyPatch(denied=["evil.example"]))
    await browser_router.domain_policy_put(DomainPolicyPatch(mode="denylist"))

    p = browser_policy.load_policy()
    assert p.mode == "denylist"
    assert p.denied == ["evil.example"], p.denied


async def test_approve_and_revoke_round_trip() -> None:
    await browser_router.domain_policy_approve(DomainRequest(domain="shop.example.com"))
    p = browser_policy.load_policy()
    assert "shop.example.com" in p.approved

    out = await browser_router.domain_policy_revoke(DomainRequest(domain="shop.example.com"))
    assert out["removed"] is True
    assert "shop.example.com" not in browser_policy.load_policy().approved


async def test_revoke_unknown_domain_is_not_an_error() -> None:
    out = await browser_router.domain_policy_revoke(DomainRequest(domain="never-seen.example"))
    assert out["ok"] is True
    assert out["removed"] is False


async def test_approve_is_idempotent() -> None:
    for _ in range(3):
        await browser_router.domain_policy_approve(DomainRequest(domain="dup.example"))
    p = browser_policy.load_policy()
    assert p.approved.count("dup.example") == 1, p.approved


# ── 试算 ───────────────────────────────────────────────────────────────


async def test_check_reports_current_verdict_without_changing_state() -> None:
    """试算不能改状态——它是给用户配白名单前预览用的，不是执行动作。"""
    before = (await browser_router.domain_policy_get())["policy"]
    out = await browser_router.domain_policy_check(DomainRequest(domain="unknown.example"))
    after = (await browser_router.domain_policy_get())["policy"]

    assert out["verdict"] == "ask", out
    assert out["reason"], "必须给出人能看懂的理由"
    assert before == after, "试算改了策略状态"


async def test_check_reflects_a_just_configured_allowlist() -> None:
    """配完 allowlist，试算要立刻反映——这才叫"改完立即生效"。"""
    await browser_router.domain_policy_put(
        DomainPolicyPatch(mode="allowlist", allowed=["corp.example.com"])
    )

    inside = await browser_router.domain_policy_check(DomainRequest(domain="corp.example.com"))
    outside = await browser_router.domain_policy_check(DomainRequest(domain="other.example"))

    assert inside["verdict"] == ALLOW, inside
    assert outside["verdict"] == DENY, outside


async def test_check_never_denies_localhost() -> None:
    """本机地址在任何模式下都放行——本地开发与跑基准都靠这条。"""
    await browser_router.domain_policy_put(DomainPolicyPatch(mode="allowlist", allowed=[]))

    out = await browser_router.domain_policy_check(DomainRequest(domain="127.0.0.1:8003"))
    assert out["verdict"] == ALLOW, out
