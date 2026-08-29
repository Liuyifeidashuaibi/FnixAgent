"""30 条多步网页任务（GUI_DRIVER_ROADMAP.md Phase 0 遗留项）。

设计要点：

1. **意图级步骤，不给选择器**。步骤只说"点名字里含 X 的元素"，由 runner 自己
   查快照找 ref——这正是模型看到快照后要做的事。若直接写死 selector，
   测的就是 selector 而不是 harness，感知层的好坏完全测不出来。

2. **每条任务带结果校验函数（verify_js）**。它查的是**真实结果**（localStorage
   里的购物车、页面上的文本），不是"动作有没有报错"。这是区分"真成功"与
   "静默失败"的唯一办法——论文里 13.2-17.6% 的静默失败就是因为没有这一层。

3. **刻意埋了三类难例**：
   - 同名诱饵按钮（每个商品两个"加入购物车"，第一个点了不生效）
   - 延迟渲染（详情页 400ms 后才出标题）
   - 需点击才可见的内容（分页第 2 页、搜索结果由 JS 渲染）
   这三类是真实站点上 harness 翻车最集中的地方。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field

# 步骤类型：
#   ("goto", 页面名)                 导航到站内页面
#   ("click", 名称片段[, 角色])       在快照里按名称找元素并点击
#   ("type", 字段提示, 文本)          在快照里找输入框并输入
#   ("select", 字段提示, 值)          下拉选择
#   ("wait_text", 文本)              等某段文本出现（显式等待原语）
#   ("back",)                        浏览器后退
Step = tuple


def _cart_is(expect: dict) -> str:
    """校验购物车内容完全等于期望值。"""
    import json

    return "() => { const c = JSON.parse(localStorage.getItem('cart') || '{}'); " + (
        "const e = " + json.dumps(expect, ensure_ascii=False) + "; "
        "const ks = Object.keys(c).filter(k => c[k] > 0); "
        "const eks = Object.keys(e); "
        "return ks.length === eks.length && eks.every(k => c[k] === e[k]);"
    ) + " }"


def _text_visible(needle: str) -> str:
    return f"() => (document.body.innerText || '').includes({needle!r})"


@dataclass
class Task:
    id: str
    name: str
    start: str
    steps: list[Step] = field(default_factory=list)
    verify_js: str = "() => true"
    # True = 这是一条**不可能完成**的任务，harness 应当报告失败。
    # 只测成功率的评测无法区分"真能干"和"永远说自己干成了"——必须有一组
    # 要求它体面拒绝的题目。
    expect_failure: bool = False


TASKS: list[Task] = [
    # ── 搜索与导航 ────────────────────────────────────────────
    Task("t01", "搜索「笔记本」并确认结果数量", "index.html",
         [("type", "搜索商品", "笔记本"), ("click", "搜索", "button"),
          ("wait_text", "笔记本电脑 Pro 14")],
         _cart_is({}) ),
    Task("t02", "搜索后点进第一个结果", "index.html",
         [("goto", "search.html?q=耳机"), ("wait_text", "降噪耳机 头戴式"),
          ("click", "降噪耳机 头戴式", "link")],
         "() => (document.getElementById('pname')||{}).textContent === '降噪耳机 头戴式'"),
    Task("t03", "搜索不存在的词显示空状态", "index.html",
         [("goto", "search.html?q=zzzzz")],
         "() => (document.getElementById('no-result')||{}).style?.display === 'block'"),
    Task("t04", "翻到第 2 页", "index.html",
         [("click", "第 2 页", "button")],
         "() => document.getElementById('page-2').style.display !== 'none'"),
    Task("t05", "从第 2 页点开商品详情", "index.html",
         [("click", "第 2 页", "button"), ("click", "摄像头 1080P", "link")],
         "() => (document.getElementById('pname')||{}).textContent === '摄像头 1080P'"),
    Task("t06", "详情页返回上一页", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("back",)],
         "() => location.pathname.endsWith('index.html')"),
    Task("t07", "空搜索词显示空状态", "index.html",
         [("goto", "search.html?q=")],
         "() => (document.getElementById('no-result')||{}).style?.display === 'block'"),
    Task("t08", "按分类搜索「配件」", "index.html",
         [("type", "搜索商品", "配件"), ("click", "搜索", "button"),
          ("wait_text", "无线鼠标 静音版")],
         _cart_is({})),

    # ── 加购（含同名诱饵按钮）──────────────────────────────────
    Task("t09", "首页直接加购第一个商品", "index.html",
         [("click", "加入购物车", "button")],
         _cart_is({"p01": 1})),
    Task("t10", "详情页加购", "index.html",
         [("click", "笔记本电脑 Air 13", "link"), ("wait_text", "笔记本电脑 Air 13"),
          ("click", "加入购物车", "button")],
         _cart_is({"p02": 1})),
    # 注：只能用第 1 页可见的商品（前 6 个），否则"快照里找不到"是任务写错而非
    # harness 缺陷——这类假失败会污染基线。第 2 页商品另有 t05/t14 专门覆盖。
    Task("t11", "详情页选数量 2 再加购", "index.html",
         [("click", "无线鼠标 静音版", "link"), ("wait_text", "无线鼠标 静音版"),
          ("select", "数量", "2"), ("click", "加入购物车", "button")],
         _cart_is({"p04": 2})),
    Task("t12", "加购两件不同商品", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button"), ("back",),
          ("click", "机械键盘 87 键", "link"), ("wait_text", "机械键盘 87 键"),
          ("click", "加入购物车", "button")],
         _cart_is({"p01": 1, "p05": 1})),
    Task("t13", "搜索结果页加购", "index.html",
         [("goto", "search.html?q=存储"), ("wait_text", "移动固态硬盘 1T"),
          ("click", "加入购物车", "button")],
         _cart_is({"p09": 1})),
    Task("t14", "第 2 页加购", "index.html",
         [("click", "第 2 页", "button"), ("click", "加入购物车", "button")],
         _cart_is({"p07": 1})),
    Task("t15", "加购后提示文案正确", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button")],
         _text_visible("已加入购物车，当前共 1 件")),

    # ── 购物车操作 ────────────────────────────────────────────
    Task("t16", "加购后去购物车删除", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button"), ("click", "购物车", "link"),
          ("click", "删除", "button")],
         _cart_is({})),
    Task("t17", "空购物车显示空状态", "index.html",
         [("click", "购物车", "link")],
         "() => (document.getElementById('empty-tip')||{}).style?.display === 'block'"),
    Task("t18", "购物车合计金额正确", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button"), ("click", "购物车", "link")],
         _text_visible("合计：¥7999")),
    Task("t19", "删掉其中一件留一件", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button"), ("back",),
          ("click", "机械键盘 87 键", "link"), ("wait_text", "机械键盘 87 键"),
          ("click", "加入购物车", "button"), ("click", "购物车", "link"),
          ("click", "删除", "button")],
         "() => { const c = JSON.parse(localStorage.getItem('cart')||'{}'); "
         "const ks = Object.keys(c).filter(k => c[k] > 0); return ks.length === 1; }"),

    # ── 表单与登录 ────────────────────────────────────────────
    Task("t20", "错误密码登录被拒绝", "index.html",
         [("goto", "login.html"), ("type", "用户名", "demo"), ("type", "密码", "wrong"),
          ("click", "登录", "button")],
         _text_visible("用户名或密码错误")),
    Task("t21", "正确凭据登录成功", "index.html",
         [("goto", "login.html"), ("type", "用户名", "demo"), ("type", "密码", "fnix2026"),
          ("click", "登录", "button")],
         "() => localStorage.getItem('user') === 'demo'"),
    Task("t22", "未登录结算被引导去登录", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button"), ("click", "购物车", "link"),
          ("click", "去结算", "button")],
         "() => location.pathname.endsWith('login.html')"),
    Task("t23", "登录后回到确认页", "index.html",
         [("goto", "login.html?next=confirm.html"), ("type", "用户名", "demo"),
          ("type", "密码", "fnix2026"), ("click", "登录", "button")],
         "() => location.pathname.endsWith('confirm.html')"),
    # 不带 next 参数时登录成功后跳回首页，所以这两条必须显式指定 next，
    # 否则"等不到确认页"是任务写错，不是 harness 问题
    Task("t24", "登录后提交订单", "index.html",
         [("goto", "login.html?next=confirm.html"), ("type", "用户名", "demo"),
          ("type", "密码", "fnix2026"), ("click", "登录", "button"),
          ("wait_text", "收货信息已确认"), ("click", "提交订单", "button")],
         _text_visible("订单已提交，感谢购买")),
    Task("t25", "提交订单后购物车清空", "index.html",
         [("goto", "login.html?next=confirm.html"), ("type", "用户名", "demo"),
          ("type", "密码", "fnix2026"), ("click", "登录", "button"),
          ("wait_text", "收货信息已确认"), ("click", "提交订单", "button")],
         _cart_is({})),
    Task("t26", "未登录访问确认页提示登录", "index.html",
         [("goto", "confirm.html")],
         _text_visible("请先登录后再结算")),

    # ── 端到端长链 ────────────────────────────────────────────
    Task("t27", "搜索 → 详情 → 加购 → 购物车", "index.html",
         [("type", "搜索商品", "电脑"), ("click", "搜索", "button"),
          ("wait_text", "笔记本电脑 Pro 14"), ("click", "笔记本电脑 Pro 14", "link"),
          ("click", "加入购物车", "button"), ("click", "购物车", "link")],
         _cart_is({"p01": 1})),
    Task("t28", "加购 → 结算 → 登录 → 提交", "index.html",
         [("click", "笔记本电脑 Pro 14", "link"), ("wait_text", "笔记本电脑 Pro 14"),
          ("click", "加入购物车", "button"), ("click", "购物车", "link"),
          ("click", "去结算", "button"), ("type", "用户名", "demo"),
          ("type", "密码", "fnix2026"), ("click", "登录", "button"),
          ("wait_text", "收货信息已确认"), ("click", "提交订单", "button")],
         _text_visible("订单已提交，感谢购买")),
    Task("t29", "两次搜索分别加购", "index.html",
         [("type", "搜索商品", "音频"), ("click", "搜索", "button"),
          ("wait_text", "蓝牙音箱 便携"), ("click", "加入购物车", "button"),
          ("click", "首页", "link"), ("type", "搜索商品", "存储"),
          ("click", "搜索", "button"), ("wait_text", "U盘 128G"),
          ("click", "加入购物车", "button")],
         _cart_is({"p07": 1, "p09": 1})),
    Task("t30", "翻页后返回第 1 页再加购", "index.html",
         [("click", "第 2 页", "button"), ("click", "第 1 页", "button"),
          ("click", "加入购物车", "button")],
         _cart_is({"p01": 1})),

    # ── 负例：harness 必须体面拒绝，而不是硬凑一个"成功"──────────
    # 这一组比正例更能说明问题：一个只会报成功的驱动能刷满正例，
    # 但会在负例上暴露——它要么卡死乱点，要么编造结果。
    Task("t31", "点一个根本不存在的商品", "index.html",
         [("click", "量子隐形斗篷", "link")],
         "() => false", expect_failure=True),
    Task("t32", "未登录时点提交订单（按钮不存在）", "index.html",
         [("goto", "confirm.html"), ("click", "提交订单", "button")],
         "() => false", expect_failure=True),
    # t33/t34 与上面不同：步骤本身能跑完（点登录不会报错），要验的是**世界状态
    # 没被改坏**——错误凭据绝不能产生登录态。这类用 verify_js 判定，仍是正例口径。
    Task("t33", "错误密码不应产生登录态", "index.html",
         [("goto", "login.html?next=confirm.html"), ("type", "用户名", "demo"),
          ("type", "密码", "nope"), ("click", "登录", "button")],
         "() => localStorage.getItem('user') === null"),
    Task("t34", "不填密码直接登录不应产生登录态", "index.html",
         [("goto", "login.html"), ("type", "用户名", "demo"),
          ("click", "登录", "button")],
         "() => localStorage.getItem('user') === null"),
    Task("t35", "搜索不到结果时不该硬点第一个", "index.html",
         [("type", "搜索商品", "不存在的商品"), ("click", "搜索", "button"),
          ("click", "加入购物车", "button")],
         "() => false", expect_failure=True),
]


def by_id(task_id: str) -> Task:
    for t in TASKS:
        if t.id == task_id:
            return t
    raise KeyError(task_id)
