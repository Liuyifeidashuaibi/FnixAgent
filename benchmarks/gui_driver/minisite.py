"""多步任务用的本地站点生成器（GUI_DRIVER_ROADMAP.md Phase 0 遗留项）。

为什么自己造站点而不是用真实网站：
  - **可复现**：真实网站改版、A/B 测试、反爬、网络抖动都会让基线漂。基线漂了
    就无法区分"产品变好了"和"网站变了"
  - **可判定**：每条任务要有**结果校验函数**。真实站点上"是否真的加进了购物车"
    很难稳定断言，自己造的站点可以直接查 DOM / localStorage
  - **覆盖可控**：能刻意埋入难例（同名诱饵按钮、延迟渲染、需点击才可见的分页），
    这些正是 harness 真正会翻车的地方

站点形态刻意做成常见电商流程——搜索 → 列表 → 详情 → 加购 → 结算 → 登录，
因为它天然需要多步、跨页、带状态，能压出单页 fixture 压不出的问题。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
from pathlib import Path

SITE_DIR = Path(__file__).parent / "site"

PRODUCTS = [
    ["p01", "笔记本电脑 Pro 14", "电脑", 7999],
    ["p02", "笔记本电脑 Air 13", "电脑", 5999],
    ["p03", "游戏本 锐龙版", "电脑", 6899],
    ["p04", "无线鼠标 静音版", "配件", 129],
    ["p05", "机械键盘 87 键", "配件", 399],
    ["p06", "显示器 27 寸 4K", "配件", 2199],
    ["p07", "降噪耳机 头戴式", "音频", 1499],
    ["p08", "蓝牙音箱 便携", "音频", 299],
    ["p09", "移动固态硬盘 1T", "存储", 549],
    ["p10", "U盘 128G", "存储", 89],
    ["p11", "USB-C 扩展坞", "配件", 259],
    ["p12", "摄像头 1080P", "配件", 199],
]

VALID_USER = "demo"
VALID_PASS = "fnix2026"

_PAGE_SIZE = 6

_NAV = """
<nav class='nav'>
  <a href='index.html' class='brand'>示例商城</a>
  <a href='index.html'>首页</a>
  <a href='cart.html' id='cart-link'>购物车<span id='cart-count'></span></a>
  <a href='login.html'>登录</a>
  <form class='search' action='search.html' method='get'>
    <input name='q' id='q' placeholder='搜索商品' aria-label='搜索商品'>
    <button type='submit'>搜索</button>
  </form>
</nav>
"""

_STYLE = """
<style>
  body{font-family:system-ui;margin:0;color:#1a1a1a}
  .nav{display:flex;gap:14px;align-items:center;padding:12px 20px;background:#f5f5f5;
       border-bottom:1px solid #e5e5e5}
  .nav .brand{font-weight:600;margin-right:8px}
  .nav .search{margin-left:auto}
  main{padding:20px;max-width:960px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
  .card{border:1px solid #e5e5e5;border-radius:8px;padding:12px}
  .card h3{margin:0 0 6px;font-size:15px}
  .price{color:#c0392b;font-weight:600}
  .row{display:flex;gap:10px;align-items:center;margin:10px 0}
  button{cursor:pointer;padding:6px 12px;border:1px solid #ccc;border-radius:6px;background:#fff}
  button.primary{background:#2563eb;color:#fff;border-color:#2563eb}
  input,select{padding:6px 8px;border:1px solid #ccc;border-radius:6px}
  .pager{margin:18px 0;display:flex;gap:8px}
  .empty{padding:30px;color:#666;border:1px dashed #ccc;border-radius:8px}
  .banner{background:#fff7ed;border:1px solid #fdba74;padding:10px 12px;border-radius:6px;margin:10px 0}
  table{border-collapse:collapse;width:100%}
  td,th{border-bottom:1px solid #eee;padding:8px;text-align:left}
</style>
"""

_JS_CART = """
<script>
  function readCart() {
    try { return JSON.parse(localStorage.getItem('cart') || '{}'); } catch (e) { return {}; }
  }
  function cartCount() { var c = readCart(), n = 0; for (var k in c) { n += c[k]; } return n; }
  function updateBadge() {
    var el = document.getElementById('cart-count');
    if (el) { el.textContent = '(' + cartCount() + ')'; }
  }
  function writeCart(c) {
    localStorage.setItem('cart', JSON.stringify(c));
    updateBadge();
  }
  function addToCart(id, n) {
    var c = readCart();
    c[id] = (c[id] || 0) + (n || 1);
    writeCart(c);
    var msg = document.getElementById('added-msg');
    if (msg) { msg.textContent = '已加入购物车，当前共 ' + cartCount() + ' 件'; }
  }
  function isLoggedIn() { return localStorage.getItem('user') !== null; }
  document.addEventListener('DOMContentLoaded', updateBadge);
  updateBadge();
</script>
"""


def _shell(title: str, body: str) -> str:
    # 顺序很关键：_JS_CART 定义的 readCart / isLoggedIn 必须**先于**页面自身的
    # 脚本加载。放到 </body> 之前的话，cart.html 的 render() 与 confirm.html 的
    # 登录态判断会在函数定义前执行，抛 ReferenceError——表现为页面一片空白，
    # 而且没有任何报错，是极难定位的一类假失败。
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{title}</title>{_STYLE}</head><body>"
        f"{_JS_CART}{_NAV}<main>{body}</main></body></html>"
    )


def _card(pid: str, name: str, price: int) -> str:
    """商品卡片。刻意放两个同名"加入购物车"按钮：第一个是诱饵（点了不生效），
    第二个才真正生效——用来检验自愈层能否从"点了没反应"中恢复。"""
    return (
        f"<div class='card'><h3><a href='product.html?id={pid}'>{name}</a></h3>"
        f"<div class='price'>¥{price}</div>"
        "<div class='row'>"
        f"<button class='decoy' data-decoy='{pid}'>加入购物车</button>"
        f"<button class='primary' onclick=\"addToCart('{pid}',1)\">加入购物车</button>"
        "</div></div>"
    )


_PRODUCTS_JS = "var PRODUCTS = " + json.dumps(PRODUCTS, ensure_ascii=False) + ";"


def build_index() -> str:
    p1 = "".join(_card(p[0], p[1], p[3]) for p in PRODUCTS[:_PAGE_SIZE])
    p2 = "".join(_card(p[0], p[1], p[3]) for p in PRODUCTS[_PAGE_SIZE:])
    body = (
        "<h1>全部商品</h1>"
        "<div class='banner'>提示：每页 6 件，共 2 页。</div>"
        f"<div id='page-1' class='grid'>{p1}</div>"
        f"<div id='page-2' class='grid' style='display:none'>{p2}</div>"
        "<div class='pager'>"
        "<button id='pg1' onclick='showPage(1)'>第 1 页</button>"
        "<button id='pg2' onclick='showPage(2)'>第 2 页</button>"
        "</div>"
        "<script>"
        "function showPage(n){"
        " document.getElementById('page-1').style.display=(n===1?'grid':'none');"
        " document.getElementById('page-2').style.display=(n===2?'grid':'none');}"
        "</script>"
    )
    return _shell("示例商城 · 首页", body)


def build_search() -> str:
    body = (
        "<h1>搜索结果</h1>"
        "<div id='result' class='grid'></div>"
        "<div id='no-result' class='empty' style='display:none'>没有找到相关商品</div>"
        "<script>" + _PRODUCTS_JS + """
        var q = new URLSearchParams(location.search).get('q') || '';
        var hits = PRODUCTS.filter(function (p) {
          return p[1].indexOf(q) >= 0 || p[2].indexOf(q) >= 0;
        });
        var box = document.getElementById('result');
        var none = document.getElementById('no-result');
        if (!q || hits.length === 0) {
          none.style.display = 'block';
        } else {
          hits.forEach(function (p) {
            var d = document.createElement('div');
            d.className = 'card';
            d.innerHTML = "<h3><a href='product.html?id=" + p[0] + "'>" + p[1] + "</a></h3>"
              + "<div class='price'>" + p[3] + "</div>"
              + "<div class='row'><button class='decoy'>加入购物车</button>"
              + "<button class='primary' onclick=\\"addToCart('" + p[0] + "',1)\\">加入购物车</button>"
              + "</div>";
            box.appendChild(d);
          });
        }
        """ + "</script>"
    )
    return _shell("示例商城 · 搜索", body)


def build_product() -> str:
    # 详情延迟 400ms 渲染——难例：快照取早了只能看到"加载中…"
    body = (
        "<div id='loading' class='empty'>加载中…</div>"
        "<div id='detail' style='display:none'>"
        "<h1 id='pname'></h1>"
        "<div class='price' id='pprice'></div>"
        "<div class='row'>数量："
        "<select id='qty' aria-label='数量'>"
        "<option value='1'>1</option><option value='2'>2</option><option value='3'>3</option>"
        "</select></div>"
        "<div class='row'>"
        "<button class='decoy'>加入购物车</button>"
        "<button class='primary' id='add'>加入购物车</button>"
        "</div>"
        "<p id='added-msg'></p>"
        "</div>"
        "<script>" + _PRODUCTS_JS + """
        var id = new URLSearchParams(location.search).get('id') || 'p01';
        var p = PRODUCTS.filter(function (x) { return x[0] === id; })[0] || PRODUCTS[0];
        setTimeout(function () {
          document.getElementById('loading').style.display = 'none';
          document.getElementById('detail').style.display = 'block';
          document.getElementById('pname').textContent = p[1];
          document.getElementById('pprice').textContent = '¥' + p[3];
          document.getElementById('add').onclick = function () {
            var n = parseInt(document.getElementById('qty').value, 10) || 1;
            addToCart(p[0], n);
          };
          document.title = p[1] + ' - 示例商城';
        }, 400);
        """ + "</script>"
    )
    return _shell("示例商城 · 商品详情", body)


def build_cart() -> str:
    body = (
        "<h1>购物车</h1>"
        "<table><thead><tr><th>商品</th><th>数量</th><th>操作</th></tr></thead>"
        "<tbody id='rows'></tbody></table>"
        "<p id='empty-tip' class='empty' style='display:none'>购物车是空的</p>"
        "<div class='row'><strong id='total'></strong></div>"
        "<div class='row'><button class='primary' id='checkout'>去结算</button></div>"
        "<script>" + _PRODUCTS_JS + """
        function render() {
          var c = readCart();
          var rows = document.getElementById('rows');
          var tip = document.getElementById('empty-tip');
          rows.innerHTML = '';
          var keys = Object.keys(c).filter(function (k) { return c[k] > 0; });
          tip.style.display = keys.length ? 'none' : 'block';
          var total = 0;
          keys.forEach(function (k) {
            var p = PRODUCTS.filter(function (x) { return x[0] === k; })[0];
            if (!p) { return; }
            total += p[3] * c[k];
            var tr = document.createElement('tr');
            tr.innerHTML = "<td class='pname'>" + p[1] + "</td>"
              + "<td class='qty'>" + c[k] + "</td>"
              + "<td><button onclick=\\"removeItem('" + k + "')\\">删除</button></td>";
            rows.appendChild(tr);
          });
          document.getElementById('total').textContent = '合计：¥' + total;
        }
        function removeItem(k) { var c = readCart(); delete c[k]; writeCart(c); render(); }
        document.getElementById('checkout').onclick = function () {
          if (!isLoggedIn()) { location.href = 'login.html?next=confirm.html'; }
          else { location.href = 'confirm.html'; }
        };
        render();
        """ + "</script>"
    )
    return _shell("示例商城 · 购物车", body)


def build_login() -> str:
    body = (
        "<h1>登录</h1>"
        "<div class='row'><label for='user'>用户名</label>"
        "<input id='user' name='user' placeholder='用户名'></div>"
        "<div class='row'><label for='pass'>密码</label>"
        "<input id='pass' name='pass' type='password' placeholder='密码'></div>"
        "<div class='row'><button class='primary' id='do-login'>登录</button></div>"
        "<p id='msg'></p>"
        "<script>"
        f"var U={VALID_USER!r}, P={VALID_PASS!r};"
        """
        document.getElementById('do-login').onclick = function () {
          var u = document.getElementById('user').value;
          var p = document.getElementById('pass').value;
          if (u === U && p === P) {
            localStorage.setItem('user', u);
            var next = new URLSearchParams(location.search).get('next') || 'index.html';
            location.href = next;
          } else {
            document.getElementById('msg').textContent = '用户名或密码错误';
          }
        };
        """ + "</script>"
    )
    return _shell("示例商城 · 登录", body)


def build_confirm() -> str:
    body = (
        "<h1>确认订单</h1>"
        "<div id='need-login' class='empty' style='display:none'>请先登录后再结算</div>"
        "<div id='ok' style='display:none'>"
        "<p>收货信息已确认。</p>"
        "<div class='row'><button class='primary' id='place'>提交订单</button></div>"
        "<p id='done'></p>"
        "</div>"
        "<script>"
        """
        if (!isLoggedIn()) {
          document.getElementById('need-login').style.display = 'block';
        } else {
          document.getElementById('ok').style.display = 'block';
          document.getElementById('place').onclick = function () {
            writeCart({});
            document.getElementById('done').textContent = '订单已提交，感谢购买';
          };
        }
        """ + "</script>"
    )
    return _shell("示例商城 · 确认订单", body)


_PAGES = {
    "index.html": build_index,
    "search.html": build_search,
    "product.html": build_product,
    "cart.html": build_cart,
    "login.html": build_login,
    "confirm.html": build_confirm,
}


def ensure_site() -> list[str]:
    """生成站点文件，返回发生变更的文件名。"""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    changed = []
    for name, builder in _PAGES.items():
        html = builder()
        path = SITE_DIR / name
        if not path.exists() or path.read_text(encoding="utf-8") != html:
            path.write_text(html, encoding="utf-8")
            changed.append(name)
    return changed
