"""ref 语义快照 — 感知层重构（GUI_DRIVER_ROADMAP.md Phase 1）。

为什么重构：
  旧快照把每个可交互元素描述 2-3 遍（ARIA 树里的 text/textbox 重复，
  坐标列表再列一遍），实测简单表单 15 个元素就要 496 tokens；重型页面
  又被 lines[:80] + 60 元素上限静默截断——979 个元素模型只看得到 6%，
  既贵又不完整（2026-08-29 基线实测）。

新模型：
  - 只收集**可交互元素**，每个元素一行，带确定性 ref（@e1..@eN）
  - 默认只收**视口内**元素：解决重型页面元素爆炸（视口外的按需翻页）
  - 快照时给元素注入 data-fnix-ref 属性，动作时按属性精确解析
  - ref 失效（DOM 重渲染导致属性丢失）不抛异常，而是返回可分类的失败，
    由编排层按 F5 上下文过期处理：重新快照再决策

寻址改用 ref 而非坐标的另一个理由：坐标在页面任何变化（横幅、字体加载、
滚动）后即失效；ref 由快照确定性生成，抗漂移。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 注入到 DOM 的属性，动作阶段据此精确解析元素
REF_ATTR = "data-fnix-ref"
REF_PREFIX = "e"

# 可交互元素选择器（与旧实现的坐标采集保持一致，去掉了过于宽泛的 [onclick]）
_INTERACTIVE_SELECTOR = (
    "a[href], button, input:not([type=hidden]), select, textarea, "
    "[role=button], [role=link], [role=checkbox], [role=radio], "
    "[role=combobox], [role=textbox], [contenteditable=true], "
    "summary, [tabindex]:not([tabindex='-1'])"
)

# 收集脚本：返回视口内可交互元素的结构化描述，并注入 ref 属性。
#
# 三件事是后来被真实页面逼出来的，都不是设计时的构想：
#
#   1. **穿透 open shadow root**。Web Components 的按钮不在 document 树里，
#      querySelectorAll 扫不到——模型看不见就无从点击，表现为"页面上明明有个
#      按钮，AI 说没有"。解析侧不用改：Playwright 的 CSS 引擎本来就穿透
#      open shadow root，所以 `[data-fnix-ref=e7]` 照样能定位。
#   2. **标记被遮挡的元素**。固定顶栏、弹窗遮罩下面的按钮，点下去事件被上面
#      那层接走，驱动层可能一句错都不报——这是静默失败的温床。宁可多给一个
#      标记，让模型/编排层知道"这个元素现在点不到"。
#   3. **报告 iframe 盲区**。同源 iframe 里的元素当前不在 ref 寻址范围内，
#      但必须让调用方**看见这个盲区**，而不是当作世界上没有那些元素。
#
_COLLECT_JS = """([selector, refAttr, viewportOnly, limit]) => {
  const out = [];
  const vw = window.innerWidth || 1280;
  const vh = window.innerHeight || 800;
  let n = 0;

  // 从元素往上走到 document，跨 shadowRoot 时接回宿主——用于判断命中元素
  // 与目标是否"同一个东西"（自身/祖先/后代都算点得到）。
  const ownerChain = (el) => {
    const chain = [];
    let node = el;
    let guard = 0;
    while (node && guard++ < 64) {
      chain.push(node);
      if (node.parentNode) {
        node = node.parentNode;
      } else {
        const root = node.getRootNode ? node.getRootNode() : null;
        node = root && root.host ? root.host : null;
      }
    }
    return chain;
  };

  // 元素中心点真正接到事件的是不是它自己。不是 = 被别人盖住了。
  const isObscured = (el, r) => {
    try {
      const cx = Math.min(Math.max(r.x + r.width / 2, 0), Math.max(vw - 1, 0));
      const cy = Math.min(Math.max(r.y + r.height / 2, 0), Math.max(vh - 1, 0));
      const top = document.elementFromPoint(cx, cy);
      if (!top || top === el) return false;
      const up = ownerChain(el);
      if (up.indexOf(top) >= 0) return false;
      const upTop = ownerChain(top);
      if (upTop.indexOf(el) >= 0) return false;
      return true;
    } catch (e) {
      return false;
    }
  };

  const collectInto = (root, inShadow) => {
    let nodes;
    try {
      nodes = root.querySelectorAll(selector);
    } catch (e) {
      return;
    }
    for (const el of nodes) {
      if (out.length >= limit) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      if (viewportOnly && (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw)) continue;
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      if (parseFloat(style.opacity) === 0) continue;

      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute('role') || (
        tag === 'a' ? 'link' :
        tag === 'input' ? (el.type === 'checkbox' ? 'checkbox' :
                           el.type === 'radio' ? 'radio' :
                           el.type === 'submit' || el.type === 'button' ? 'button' : 'textbox') :
        tag === 'select' ? 'combobox' :
        tag === 'textarea' ? 'textbox' :
        tag === 'button' ? 'button' :
        // summary 是可展开的折叠控件，标成 generic 等于把"点了会展开"这件
        // 事从上下文里删掉——内容藏在折叠面板里时，模型就不知道该先点它。
        tag === 'summary' ? 'summary' :
        (el.isContentEditable ? 'textbox' : 'generic')
      );
      const name = (
        el.getAttribute('aria-label') ||
        el.getAttribute('placeholder') ||
        (el.labels && el.labels.length ? el.labels[0].innerText : '') ||
        el.getAttribute('title') ||
        (el.innerText || '').trim().slice(0, 60) ||
        el.getAttribute('name') || ''
      ).replace(/\\s+/g, ' ').trim();

      const states = [];
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') states.push('disabled');
      if (el.checked) states.push('checked');
      if (el.getAttribute('aria-expanded') === 'true') states.push('expanded');
      if (isObscured(el, r)) states.push('obscured');

      const ref = 'e' + n;
      el.setAttribute(refAttr, ref);

      out.push({
        ref: ref,
        role: role,
        name: name,
        value: (el.value !== undefined && tag !== 'a' && tag !== 'button') ? String(el.value).slice(0, 40) : '',
        states: states,
        in_shadow: inShadow,
        x: Math.round(r.x + r.width / 2),
        y: Math.round(r.y + r.height / 2),
        w: Math.round(r.width),
        h: Math.round(r.height),
      });
      n += 1;
    }

    // 递归 open shadow root。注意扫的是**所有元素**而不是上面命中的那些：
    // <my-widget> 这类宿主本身一个可交互特征都没有（没 tabindex、没 role），
    // 只在匹配结果里找宿主的话，影子树永远进不去。
    let hosts;
    try {
      hosts = root.querySelectorAll('*');
    } catch (e) {
      return;
    }
    for (const host of hosts) {
      if (out.length >= limit) return;
      if (host.shadowRoot) collectInto(host.shadowRoot, true);
    }
  };

  collectInto(document, false);

  // iframe 盲区：当前不枚举 frame 内元素，但必须让调用方知道那里有东西。
  // 静默的感知盲区比显式的能力缺口危险得多。
  const frames = [];
  for (const f of document.querySelectorAll('iframe')) {
    let count = -1;
    try {
      const d = f.contentDocument;
      if (d) count = d.querySelectorAll(selector).length;
    } catch (e) {
      count = -1;
    }
    const r = f.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    frames.push({
      src: (f.getAttribute('src') || '').slice(0, 120),
      reachable: count >= 0,
      count: count,
      w: Math.round(r.width),
      h: Math.round(r.height),
    });
  }

  // Canvas / WebGL 盲区检测。
  //
  // 这是全行业共同的盲区（Playwright MCP 的公开弱点之一）：canvas 里画的
  // 东西没有无障碍树，ref 快照扫不到任何元素。我们解决不了"看懂画布"——
  // 那需要视觉模型——但**必须如实说出这个盲区**。否则模型拿到一个空快照，
  // 只会以为"这个页面上没有东西"，然后编造一个答案。
  const MIN_CANVAS_AREA = 40000;   // 200x200 以上才算"主体内容"
  let canvasCount = 0;
  let canvasLarge = 0;
  let webgl = false;
  for (const c of document.querySelectorAll('canvas')) {
    const r = c.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    canvasCount += 1;
    if (r.width * r.height >= MIN_CANVAS_AREA) canvasLarge += 1;
    if (!webgl) {
      try {
        if (c.getContext('webgl2') || c.getContext('webgl')) webgl = true;
      } catch (e) { /* 上下文已被别的类型占用 */ }
    }
  }

  return {
    refs: out,
    frames: frames,
    canvas: { count: canvasCount, large: canvasLarge, webgl: webgl },
  };
}"""

# 清理旧 ref 属性（避免上一个快照的残留被误解析）。同样要穿透 shadow root，
# 否则上一轮留在 Web Components 内部的 ref 会被下一次动作误命中。
_CLEAR_JS = """(refAttr) => {
  const clearIn = (root) => {
    for (const el of root.querySelectorAll('[' + refAttr + ']')) {
      el.removeAttribute(refAttr);
    }
    for (const host of root.querySelectorAll('*')) {
      if (host.shadowRoot) clearIn(host.shadowRoot);
    }
  };
  clearIn(document);
}"""

# 页面可交互元素总数（含 shadow root 内），用于"视口外还有 N 个"的提示。
# 不统计 iframe 内——那些在 frames 里单独报告。
_TOTAL_JS = """(selector) => {
  let total = 0;
  const walk = (root) => {
    total += root.querySelectorAll(selector).length;
    for (const host of root.querySelectorAll('*')) {
      if (host.shadowRoot) walk(host.shadowRoot);
    }
  };
  walk(document);
  return total;
}"""


class RefStaleError(Exception):
    """ref 已失效——通常是 DOM 重渲染导致注入的属性丢失。

    这是**可恢复**失败，不是崩溃：编排层按 F5（上下文过期）处理，
    重新快照后再决策。设计上刻意让它可被分类，而不是混进通用异常。
    """

    def __init__(self, ref: str, hint: str = "") -> None:
        self.ref = ref
        super().__init__(hint or f"ref {ref} 已失效，请重新获取快照后再操作")


@dataclass
class ElementRef:
    """单个可交互元素的引用。"""

    ref: str
    role: str
    name: str = ""
    value: str = ""
    states: list[str] = field(default_factory=list)
    in_shadow: bool = False
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    @property
    def disabled(self) -> bool:
        return "disabled" in self.states

    @property
    def obscured(self) -> bool:
        """元素中心点被别的层盖住了——点下去事件会被上面那层接走。

        这是静默失败的温床：驱动层可能一句错都不报，页面也"看起来没变化"，
        于是模型以为自己点成功了。标记出来，让上层知道该滚动/关弹窗。
        """
        return "obscured" in self.states

    def to_line(self) -> str:
        """紧凑单行表示——这是 token 效率的关键：每元素一行。"""
        bits = [f"@{self.ref}", self.role]
        # 名称与值都为空时不再补 label，避免重复输出 role 本身
        if self.name:
            bits.append(f'"{self.name}"')
        elif self.value:
            bits.append(f'"{self.value}"')
        if self.name and self.value:
            bits.append(f"={self.value}")
        if self.states:
            bits.append("[" + ",".join(self.states) + "]")
        return " ".join(bits)


@dataclass
class CollectedRefs:
    """`collect_refs` 的结果：元素 + 两处感知盲区的量测。

    单独成类型而不是多返回几个值，是因为"盲区报告"这一项还会继续长：
    canvas、iframe 之后还会有 PDF 内嵌、跨域 frame、WebGL 离屏画布……
    每加一项就改一次调用方的解包顺序，迟早解错。
    """

    refs: list[ElementRef] = field(default_factory=list)
    total_on_page: int = 0
    frames: list[dict] = field(default_factory=list)
    canvas: dict = field(default_factory=dict)


@dataclass
class RefSnapshot:
    """一次快照的结果。"""

    url: str
    title: str
    refs: list[ElementRef] = field(default_factory=list)
    viewport_only: bool = True
    truncated: bool = False  # 达到上限被截断
    total_on_page: int = -1  # 页面可交互元素总数（含视口外）
    # iframe 盲区。当前不枚举 frame 内元素，但**必须**让调用方看见这里有
    # 内容——感知层的静默盲区比显式的能力缺口危险：前者会让模型以为世界上
    # 没有那个按钮，后者至少还能让人去补。
    frames: list[dict] = field(default_factory=list)
    # Canvas / WebGL 盲区。没有无障碍树，ref 寻址天然不可用——必须说出来，
    # 否则空快照会被理解成"页面上没东西"。
    canvas: dict = field(default_factory=dict)

    @property
    def hidden_frame_count(self) -> int:
        """iframe 里当前看不到但确实存在的可交互元素数。"""
        return sum(int(f.get("count") or 0) for f in self.frames if f.get("reachable"))

    def get(self, ref: str) -> ElementRef | None:
        target = ref.lstrip("@")
        for r in self.refs:
            if r.ref == target:
                return r
        return None

    @property
    def has_canvas_blind_spot(self) -> bool:
        """页面主体是不是画在 canvas / WebGL 上（ref 寻址天然不可用）。"""
        return int(self.canvas.get("large") or 0) > 0

    def _empty_reason(self) -> str:
        """快照为空时，说清楚是"页面没东西"还是"我们看不见"。

        这两件事对调用方意味着完全不同的后续动作：前者可以据此下结论，后者
        必须换视觉通道，绝不能当成"页面是空的"。
        """
        if self.has_canvas_blind_spot:
            kind = "WebGL" if self.canvas.get("webgl") else "Canvas"
            return (
                f"  ⚠ 页面主体由 {kind} 绘制，**没有无障碍树**，ref 寻址在这里"
                "不可用——不要据此认为页面上没有内容。需要操作请走视觉通道（截图）。"
            )
        if self.frames:
            return (
                f"  ⚠ 当前视口没有可交互元素，但页面有 {len(self.frames)} 个 iframe，"
                f"内含约 {self.hidden_frame_count} 个可交互元素——内容在框架里，"
                "ref 寻址未覆盖。"
            )
        if self.total_on_page > 0:
            return (
                f"  （页面共约 {self.total_on_page} 个可交互元素，都在视口外或尚未渲染；"
                "滚动后重新快照）"
            )
        if self.total_on_page == 0:
            return "  （页面上没有可交互元素——可能是纯静态页面，或首屏还在加载）"
        return "  （当前视口没有可交互元素）"

    def to_text(self, include_coords: bool = False) -> str:
        """渲染给 LLM 的紧凑文本。

        默认不带坐标——坐标会显著抬高 token 且对 ref 寻址无用，
        需要视觉判断时走带编号截图通道（--annotate 式）。
        """
        lines = [f"URL: {self.url}", f"标题: {self.title}"]
        if not self.refs:
            # 空快照必须解释原因。一个什么都不说的空快照是最危险的返回值：
            # 模型会以为"这个页面上没有东西"，然后据此编造结论。
            lines.append(self._empty_reason())
            return "\n".join(lines)
        lines.append(f"可交互元素（共 {len(self.refs)} 个，用 @ref 操作）:")
        for r in self.refs:
            line = "  " + r.to_line()
            if include_coords:
                line += f" @({r.x},{r.y})"
            lines.append(line)
        if self.truncated:
            lines.append(
                f"  …已达上限；页面共约 {self.total_on_page} 个元素，"
                "滚动后可再次快照查看其余部分"
            )
        elif self.viewport_only and self.total_on_page > len(self.refs):
            lines.append(f"  （视口外还有约 {self.total_on_page - len(self.refs)} 个元素，滚动后可见）")
        # 画布盲区在有元素时也要说。画布页往往配着几个真按钮，快照不为空，
        # 于是上面的空快照分支不触发，模型看到"有几个按钮"就以为自己看清了
        # 整个页面——而真正的主体内容它一个都没见着。
        if self.has_canvas_blind_spot:
            kind = "WebGL" if self.canvas.get("webgl") else "Canvas"
            lines.append(
                f"  ⚠ 页面有一块 {kind} 画布承载主体内容，画布内没有无障碍树，"
                "ref 寻址覆盖不到——不要假设画布里没有可操作的东西"
            )
        if self.frames:
            reachable = [f for f in self.frames if f.get("reachable")]
            cross = [f for f in self.frames if not f.get("reachable")]
            if reachable:
                n = self.hidden_frame_count
                lines.append(
                    f"  ⚠ 页面有 {len(reachable)} 个 iframe，内含约 {n} 个可交互元素，"
                    "当前 ref 寻址未覆盖——需要操作它们时请说明，不要假设它们不存在"
                )
            if cross:
                lines.append(
                    f"  ⚠ 另有 {len(cross)} 个跨域 iframe，内容不可达"
                )
        return "\n".join(lines)


def parse_ref(text: str) -> str | None:
    """从模型输出里提取 ref（容忍 @e7 / e7 / "ref=e7" 等写法）。"""
    if not text:
        return None
    m = re.search(r"@?\b" + REF_PREFIX + r"(\d+)\b", text)
    return f"{REF_PREFIX}{m.group(1)}" if m else None


def locator_for(ref: str) -> str:
    """ref → CSS 选择器（动作阶段用）。"""
    return f'[{REF_ATTR}="{ref.lstrip("@")}"]'


async def collect_refs(
    page: object,
    viewport_only: bool = True,
    limit: int = 60,
) -> CollectedRefs:
    """采集可交互元素并注入 ref 属性。

    穿透 open shadow root：Web Components 的可交互元素不在 document 树里，
    不递归就永远看不见。解析侧无需改动——Playwright 的 CSS 引擎本来就穿透
    open shadow root，`[data-fnix-ref=eN]` 照样定位得到。

    除了元素本身，还回两处**感知盲区的量测**：iframe 内够不到但确实存在的
    元素、以及画在 canvas/WebGL 上根本没有无障碍树的内容。这两处都不在
    ref 寻址范围内，但快照必须把它们说出来——否则空快照会被读成"页面上
    没有东西"，而那正是模型开始编造的时刻。
    """
    await page.evaluate(_CLEAR_JS, REF_ATTR)
    raw = await page.evaluate(
        _COLLECT_JS,
        [_INTERACTIVE_SELECTOR, REF_ATTR, viewport_only, limit],
    )
    items = (raw or {}).get("refs") or []
    frames = list((raw or {}).get("frames") or [])
    canvas = dict((raw or {}).get("canvas") or {})
    refs = [
        ElementRef(
            ref=str(item.get("ref", "")),
            role=str(item.get("role", "generic")),
            name=str(item.get("name", "")),
            value=str(item.get("value", "")),
            states=list(item.get("states", [])),
            in_shadow=bool(item.get("in_shadow", False)),
            x=int(item.get("x", 0)),
            y=int(item.get("y", 0)),
            w=int(item.get("w", 0)),
            h=int(item.get("h", 0)),
        )
        for item in items
    ]
    total = await page.evaluate(_TOTAL_JS, _INTERACTIVE_SELECTOR)
    return CollectedRefs(
        refs=refs,
        total_on_page=int(total or 0),
        frames=frames,
        canvas=canvas,
    )
