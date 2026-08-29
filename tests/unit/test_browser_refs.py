"""ref 语义快照单测（GUI_DRIVER_ROADMAP.md Phase 1）。

覆盖纯函数与数据结构；端到端采集与点击由 test_browser_refs_e2e 覆盖。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import pytest

from fnixagent.core.tools.browser_refs import (
    REF_ATTR,
    ElementRef,
    RefSnapshot,
    RefStaleError,
    locator_for,
    parse_ref,
)


# ── parse_ref：容忍模型各种写法 ──────────────────────────────────


def test_parse_ref_forms() -> None:
    assert parse_ref("@e7") == "e7"
    assert parse_ref("e7") == "e7"
    assert parse_ref("请点击 @e12 这个按钮") == "e12"
    assert parse_ref('{"ref": "@e3"}') == "e3"


def test_parse_ref_invalid() -> None:
    assert parse_ref("") is None
    assert parse_ref("点击提交按钮") is None
    assert parse_ref(None) is None  # type: ignore[arg-type]


def test_locator_for() -> None:
    assert locator_for("@e5") == f'[{REF_ATTR}="e5"]'
    assert locator_for("e5") == f'[{REF_ATTR}="e5"]'


# ── ElementRef：紧凑单行表示 ─────────────────────────────────────


def test_ref_line_compact() -> None:
    r = ElementRef(ref="e1", role="button", name="提交")
    assert r.to_line() == '@e1 button "提交"'


def test_ref_line_with_value_and_state() -> None:
    r = ElementRef(ref="e2", role="textbox", name="姓名", value="张三", states=["disabled"])
    line = r.to_line()
    assert "@e2" in line and "张三" in line and "[disabled]" in line
    assert r.disabled is True


def test_ref_line_falls_back_to_role() -> None:
    r = ElementRef(ref="e0", role="generic")
    assert r.to_line() == "@e0 generic"


# ── RefSnapshot：渲染与查找 ──────────────────────────────────────


def _snap(n: int = 3, total: int = 3) -> RefSnapshot:
    return RefSnapshot(
        url="http://x/",
        title="t",
        refs=[ElementRef(ref=f"e{i}", role="button", name=f"b{i}") for i in range(n)],
        total_on_page=total,
    )


def test_snapshot_text_lists_each_ref() -> None:
    text = _snap().to_text()
    assert "@e0" in text and "@e2" in text
    assert "URL: http://x/" in text
    # 每个元素一行，不重复描述（旧实现会描述 2-3 遍）
    assert len([ln for ln in text.splitlines() if "@e0" in ln]) == 1


def test_snapshot_no_coords_by_default() -> None:
    s = RefSnapshot(
        url="u", title="t",
        refs=[ElementRef(ref="e1", role="button", name="b", x=10, y=20)],
    )
    assert "(10,20)" not in s.to_text()
    assert "(10,20)" in s.to_text(include_coords=True)


def test_snapshot_hints_offscreen_elements() -> None:
    """视口外元素不得静默丢掉，必须告知数量以便滚动后再取。"""
    text = _snap(n=3, total=90).to_text()
    assert "87" in text  # 90 - 3


def test_snapshot_marks_truncation() -> None:
    s = _snap(n=60, total=979)
    s.truncated = True
    text = s.to_text()
    assert "已达上限" in text


def test_snapshot_empty() -> None:
    assert "没有可交互元素" in RefSnapshot(url="u", title="t").to_text()


def test_snapshot_get() -> None:
    s = _snap()
    assert s.get("@e1") is not None
    assert s.get("e1") is not None
    assert s.get("@e99") is None


# ── RefStaleError：可分类的可恢复失败 ────────────────────────────


def test_ref_stale_error_message() -> None:
    e = RefStaleError("e7")
    assert "e7" in str(e)
    assert e.ref == "e7"
    with pytest.raises(RefStaleError):
        raise RefStaleError("e1", "自定义提示")
