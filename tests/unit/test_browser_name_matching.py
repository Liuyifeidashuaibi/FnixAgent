"""名称匹配分档 —— 防止"加入购物车"被"加入购物车并结算"截胡。

这组用例守的是一件会造成真实损失的事：在电商/支付页面上，AI 说"点加入购物车"，
页面上同时有"加入购物车并结算"且它在 DOM 里靠前。不加分档的包含匹配会先
命中后者，驱动层一句错都不报，用户看到的却是"我说加购，它直接下单了"。

这类错误的恶劣之处在于**完全静默**：点到了、页面变了、状态也更新了，从
harness 的视角看是一次干净漂亮的成功。只有结果校验能抓住它——而生产环境
里通常没有校验器，所以必须在寻址这一层就拦住。

纯函数测试，不需要浏览器。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.tools.browser_healing import (
    _name_matches,
    _rank_name_match,
    select_by_name,
)
from fnixagent.core.tools.browser_refs import ElementRef


def _ref(name: str, ref: str = "e1") -> ElementRef:
    return ElementRef(ref=ref, role="button", name=name)


# ── 分档 ────────────────────────────────────────────────────────────────


def test_exact_match_ranks_highest() -> None:
    assert _rank_name_match("加入购物车", "加入购物车") == 3


def test_name_containing_query_ranks_second() -> None:
    """查询是元素名的前缀——沾边，但不能和完全相等平起平坐。"""
    assert _rank_name_match("加入购物车并结算", "加入购物车") == 2


def test_query_containing_name_ranks_last() -> None:
    """模糊说法"点那个加入购物车按钮"里的词，兜底档。"""
    assert _rank_name_match("加入购物车", "点那个加入购物车按钮") == 1


def test_unrelated_names_do_not_match() -> None:
    assert _rank_name_match("删除订单", "加入购物车") == 0
    assert _name_matches("删除订单", "加入购物车") is False


def test_single_char_name_is_not_a_fuzzy_match() -> None:
    """护栏：单字元素名不该因为"查询里恰好有这个字"就算命中。"""
    assert _rank_name_match("的", "点那个加入购物车按钮") == 0


def test_blank_inputs_never_match() -> None:
    assert _rank_name_match("", "加入购物车") == 0
    assert _rank_name_match("加入购物车", "") == 0
    assert _rank_name_match("", "") == 0


# ── 候选挑选 ────────────────────────────────────────────────────────────


def test_decoy_before_target_still_selects_target() -> None:
    """核心场景：诱饵在 DOM 里排在前面，也必须选中完全相等的那个。"""
    refs = [_ref("加入购物车并结算", "e1"), _ref("加入购物车", "e2")]
    picked = select_by_name(refs, "加入购物车")

    assert [r.ref for r in picked] == ["e2"], [r.name for r in picked]


def test_shorter_name_wins_within_same_tier() -> None:
    """同一档里越短越贴合——说"订单"时该指向"确认订单"，不是"确认订单并支付"。"""
    refs = [_ref("确认订单并支付", "e1"), _ref("确认订单", "e2")]
    picked = select_by_name(refs, "订单")

    assert picked[0].ref == "e2", [r.name for r in picked]


def test_candidates_stay_within_the_best_tier() -> None:
    """换目标的候选池不能混入低档候选，否则自愈会越换越离谱。"""
    refs = [
        _ref("加入购物车并结算", "e1"),
        _ref("加入购物车", "e2"),
        _ref("加入购物车", "e3"),
    ]
    picked = select_by_name(refs, "加入购物车")

    assert [r.ref for r in picked] == ["e2", "e3"], [r.name for r in picked]


def test_no_match_returns_empty() -> None:
    assert select_by_name([_ref("删除订单")], "加入购物车") == []


def test_disabled_elements_are_still_candidates() -> None:
    """是否禁用由调用方判断——筛选函数不做业务取舍，只管名字。"""
    disabled = ElementRef(ref="e1", role="button", name="加入购物车", states=["disabled"])
    assert select_by_name([disabled], "加入购物车") == [disabled]
