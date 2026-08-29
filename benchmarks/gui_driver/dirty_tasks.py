"""脏页面任务集（Phase 6 · 真实网站泛化能力的可度量替代）。

与 Phase 0 那 35 条的区别：

  Phase 0 的站点是**干净的**——元素稳定、位置固定、点了就有反应。它证明的是
  "这条链路上没有系统性缺陷"。
  这一组每条都只脏在一个地方，证明的是"上真实网站会不会崩"。两个数字互不
  替代：干净页面的 100% 不能代表泛化，脏页面的低分也不否定干净页面的成绩。

步骤仍是**意图级**的，不给选择器：

  ("click_near", 锚点文本, 按钮名)
      在快照里找名称含锚点文本的元素，再取阅读顺序上离它最近的那个按钮。
      这正是人读快照时的做法（"商品 12 右边那个加入购物车"），也是模型拿到
      紧凑文本后唯一能做的事——不需要任何 DOM 知识。

  ("scroll_until", 文本, 最多滚几次)
      一直往下滚，直到指定文本出现在快照里。懒加载与无限滚动没有这个动作
      就无法完成，而真实用户/模型就是这么做的。

负例同样必须有：只测正例的话，"什么都点得到、什么都报成功"的驱动能拿满分。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field


def _cart_has(pid: str, qty: int = 1) -> str:
    return (
        "() => { const c = JSON.parse(localStorage.getItem('cart') || '{}'); "
        f"return c['{pid}'] === {qty}; }}"
    )


def _cart_empty() -> str:
    return (
        "() => { const c = JSON.parse(localStorage.getItem('cart') || '{}'); "
        "return Object.keys(c).length === 0; }"
    )


def _added_not_checked_out(pid: str) -> str:
    """加进了购物车，且**没有**误触结算/收藏。

    只看购物车的校验抓不住近似名误点：诱饵按钮要是也顺手加了购物车，
    点错了照样算过。必须同时确认"没走到别的流程上去"。
    """
    return (
        "() => { const c = JSON.parse(localStorage.getItem('cart') || '{}'); "
        f"return c['{pid}'] === 1 "
        "&& localStorage.getItem('checkout') === null "
        "&& localStorage.getItem('wishlist') === null; }"
    )


@dataclass
class DirtyTask:
    id: str
    name: str
    page: str
    steps: list = field(default_factory=list)
    verify_js: str = "() => true"
    expect_failure: bool = False
    # 这一条要压的性质——跑分报告里按性质归类，失败才好归因
    trait: str = ""


TASKS: list[DirtyTask] = [
    DirtyTask(
        "d01", "先关掉 cookie 弹窗再加购", "consent.html",
        [("click", "接受全部", "button"),
         ("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_has("p01"), trait="全屏遮罩",
    ),
    DirtyTask(
        "d02", "懒加载：滚到商品 12 再加购", "lazy.html",
        [("scroll_until", "商品 12", 25),
         ("click_near", "商品 12", "加入购物车")],
        _cart_has("p12"), trait="懒加载",
    ),
    DirtyTask(
        "d03", "无限滚动：找到商品 24 再加购", "infinite.html",
        [("scroll_until", "商品 24", 40),
         ("click_near", "商品 24", "加入购物车")],
        _cart_has("p24"), trait="无限滚动",
    ),
    DirtyTask(
        "d04", "动态重排：列表每 400ms 重建时加购", "rerender.html",
        [("click_near", "机械键盘 87 键", "加入购物车")],
        _cart_has("p05"), trait="DOM 重排",
    ),
    DirtyTask(
        # 锚点跳转把目标顶到视口最上方、正压在固定顶栏底下——真实站点上
        # "点不动的按钮"最经典的成因。解除方式是滚动，不是换目标。
        "d05", "锚点跳转后目标被固定顶栏盖住时加购", "sticky.html",
        [("goto", "sticky.html#p01"),
         ("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_has("p01"), trait="固定层遮挡",
    ),
    DirtyTask(
        "d06", "Shadow DOM：点 Web Components 里的按钮", "shadow.html",
        [("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_has("p01"), trait="Shadow DOM",
    ),
    DirtyTask(
        # 页面把"加入购物车并结算"排在"加入购物车"**前面**——真实电商页面
        # 就是这么排的。不加分档的包含匹配会先命中它，而这一页上"结算"
        # 不会写购物车，于是误点在结果校验里无所遁形。
        "d07", "近似名干扰：目标是「加入购物车」不是「加入购物车并结算」", "decoy.html",
        [("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _added_not_checked_out("p01"), trait="近似名干扰",
    ),
    DirtyTask(
        "d08", "折叠面板：先展开规格参数再加购", "accordion.html",
        [("click", "规格参数", "summary"),
         ("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_has("p01"), trait="折叠面板",
    ),
    DirtyTask(
        # 首屏 1.5 秒内什么都没有。过早下结论说"页面上没东西"就完了。
        "d09", "延迟渲染：等商品出现后再加购", "slow.html",
        [("wait_text", "笔记本电脑 Pro 14"),
         ("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_has("p01"), trait="延迟渲染",
    ),
    DirtyTask(
        # 虚拟列表：行不在 DOM 里就没法编号，滚动时节点又被整个换掉。
        # ref 寻址的天敌，比随时重排更难察觉——DOM 结构看着一直没变。
        "d10", "虚拟列表：滚动到商品 47 再加购", "virtual.html",
        [("scroll_until", "商品 47", 60),
         ("click_near", "商品 47", "加入购物车")],
        _cart_has("p47"), trait="虚拟列表",
    ),

    # ── 负例：必须承认做不到，而不是硬凑一个"成功" ──────────────────
    DirtyTask(
        # 折叠面板没展开，目标根本不在渲染树里。找不到就该说找不到。
        "n04", "折叠面板没展开就想加购——不该成功", "accordion.html",
        [("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_empty(), expect_failure=True, trait="折叠面板",
    ),
    DirtyTask(
        # iframe 是已知的感知盲区。这一条守的不是"能做"，而是**做不到时
        # 不去点一个凑合的替代品**——外层摆着一个同名倾向的按钮，硬凑的话
        # 很容易就"成功"了，而购物车里其实什么都没有。
        "n05", "目标在 iframe 里点不到——不该硬凑成功", "frame.html",
        [("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_empty(), expect_failure=True, trait="iframe 内容",
    ),
    DirtyTask(
        "n01", "不处理弹窗就想加购——不该成功", "consent.html",
        [("click_near", "笔记本电脑 Pro 14", "加入购物车")],
        _cart_empty(), expect_failure=True, trait="全屏遮罩",
    ),
    DirtyTask(
        "n02", "无限滚动里找不存在的第 999 件", "infinite.html",
        [("scroll_until", "商品 999", 12)],
        "() => false", expect_failure=True, trait="无限滚动",
    ),
    DirtyTask(
        "n03", "懒加载页面上找不存在的商品 99", "lazy.html",
        [("scroll_until", "商品 99", 30),
         ("click_near", "商品 99", "加入购物车")],
        "() => false", expect_failure=True, trait="懒加载",
    ),
]
