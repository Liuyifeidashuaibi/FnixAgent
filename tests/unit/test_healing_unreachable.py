"""F8 目标不可达 · 自愈不得换目标（脏页面基线 d05 逼出来的回归锁）。

## 这个测试存在的原因

脏页面基线里有一条"固定顶栏压住按钮"的任务，结果是**静默失败**：步骤全部
成功、驱动层零报错，但加购的是另一件商品。追下去是自愈做了这件事：

    点 A 的按钮 → 被顶栏拦截 → 判 F4（目标选错）→ substitute 换同名候选
    → 点到 B 的按钮 → 成功 → 任务判"完成"

问题出在分类上："够不着"和"选错了"被归成同一类，于是共用"换目标"这一个
恢复动作。但这两件事的正确答案完全相反：

  - 目标选错：换目标是对的（诱饵在前、真按钮在后，逐个试过去才有效）
  - 目标够不着：换目标是**替用户改意图**。页面上总有一堆同名按钮，换一个
    就能点上，于是不再报错——把一次诚实的失败，换成一次无人发现的做错。

所以单列 F8，恢复动作是"解除遮挡后重试同一个目标"，阶梯里**不含**
substitute。这组测试就是为了防止有人把它改回去。

不用真 Chromium：这里锁的是分类与阶梯的决策，不是驱动。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fnixagent.core.tools.browser_healing import BrowserHealer
from fnixagent.core.tools.driver_errors import (
    F4_TOOL_CHOICE,
    F8_UNREACHABLE,
    classify,
)
from fnixagent.core.tools.orchestrator import (
    CLEAR_OBSTRUCTION,
    RECOVERY_LADDER,
    SUBSTITUTE,
)


# ── 分类：够不着 ≠ 选错了 ───────────────────────────────────────────────


def test_intercepted_click_is_unreachable_not_wrong_target() -> None:
    """被别的东西接走事件 = 目标对但够不着，不是目标选错。"""
    assert classify(RuntimeError("<div id='bar'> intercepts pointer events")) == F8_UNREACHABLE


def test_element_not_visible_is_unreachable() -> None:
    assert classify(RuntimeError("element is not visible")) == F8_UNREACHABLE


def test_element_not_stable_is_unreachable() -> None:
    assert classify(RuntimeError("element is not stable")) == F8_UNREACHABLE


def test_missing_element_is_still_wrong_target() -> None:
    """找不到元素才是"目标不对"，别被 F8 抢走。"""
    assert classify(RuntimeError("no element found for selector")) == F4_TOOL_CHOICE


def test_strict_mode_violation_is_still_wrong_target() -> None:
    assert classify(RuntimeError("strict mode violation")) == F4_TOOL_CHOICE


# ── 阶梯：F8 不许换目标 ─────────────────────────────────────────────────


def test_f8_ladder_has_no_substitute() -> None:
    """这条是整个文件的核心：够不着的目标绝不能被换成别的同名元素。"""
    assert SUBSTITUTE not in RECOVERY_LADDER[F8_UNREACHABLE]


def test_f8_ladder_clears_obstruction_first() -> None:
    assert RECOVERY_LADDER[F8_UNREACHABLE][0] == CLEAR_OBSTRUCTION


def test_f4_ladder_still_substitutes() -> None:
    """反向护栏：诱饵场景仍然必须换目标，别一刀切把换目标也禁了。"""
    assert SUBSTITUTE in RECOVERY_LADDER[F4_TOOL_CHOICE]


def test_f8_ladder_ends_with_escalate() -> None:
    """任何故障都不能无限自愈——够不着又解不开，就如实上报。"""
    assert RECOVERY_LADDER[F8_UNREACHABLE][-1] == "escalate"


# ── 钩子：substitute 遇到 F8 要主动让路 ─────────────────────────────────


class _FakeSession:
    """只记录被调用了什么，不真的驱动浏览器。"""

    def __init__(self) -> None:
        self.clicked: list[str] = []
        self.cleared: list[str] = []

    async def click_ref(self, ref: str) -> object:
        self.clicked.append(ref)

        class _S:
            error = None
            changed = True
            url_changed = False
            error_class = ""

        return _S()

    async def clear_obstruction(self, ref: str) -> object:
        self.cleared.append(ref)

        class _S:
            error = None
            changed = False
            url_changed = False
            error_class = ""

        return _S()

    async def snapshot_ref(self) -> object:
        from fnixagent.core.tools.browser_refs import ElementRef, RefSnapshot

        return RefSnapshot(
            url="about:blank",
            title="t",
            refs=[
                ElementRef(ref="e0", role="button", name="加入购物车"),
                ElementRef(ref="e1", role="button", name="加入购物车"),
            ],
        )


async def test_substitute_refuses_when_unreachable() -> None:
    """够不着时不许换目标——换掉就是替用户改意图。"""
    session = _FakeSession()
    healer = BrowserHealer(session)
    await healer._snapshot_or_fetch()

    result = await healer._on_substitute(
        {"target": "e0", "failure_class": F8_UNREACHABLE}
    )

    assert result is None
    assert session.clicked == [], "不可达时 substitute 仍然点了别的元素"


async def test_substitute_still_works_for_wrong_target() -> None:
    """反向护栏：目标选错时该换还得换，否则诱饵场景会退化。"""
    session = _FakeSession()
    healer = BrowserHealer(session)
    await healer._snapshot_or_fetch()
    # 模拟真实调用顺序：click() 已经先试过 e0，才轮到 substitute 找下一个
    healer._tried = {"e0"}

    result = await healer._on_substitute(
        {"target": "e0", "failure_class": F4_TOOL_CHOICE}
    )

    assert result is not None
    assert session.clicked == ["e1"], session.clicked


async def test_clear_obstruction_scrolls_instead_of_clicking() -> None:
    """解除遮挡只滚动，绝不顺手点一下。"""
    session = _FakeSession()
    healer = BrowserHealer(session)

    await healer._on_clear_obstruction({"target": "e0"})

    assert session.cleared == ["e0"]
    assert session.clicked == []


async def test_clear_obstruction_ignores_text_targets() -> None:
    """文本目标没有可滚动的具体元素，这一级无从下手就交给下一级。"""
    healer = BrowserHealer(_FakeSession())

    assert await healer._on_clear_obstruction({"target": "加入购物车"}) is None


async def test_clear_obstruction_reports_scroll_failure() -> None:
    """滚动失败要如实上报，不能装作已经解除了遮挡。"""
    session = _FakeSession()

    async def _boom(ref: str) -> object:
        raise RuntimeError("scroll failed")

    session.clear_obstruction = AsyncMock(side_effect=_boom)  # type: ignore[method-assign]
    healer = BrowserHealer(session)

    result = await healer._on_clear_obstruction({"target": "e0"})

    assert result is not None
    assert result.ok is False
