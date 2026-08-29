"""浏览器自愈动作层（GUI_DRIVER_ROADMAP.md Phase 3 的落地接线）。

把 Phase 2 的**动作后验证**与 Phase 3 的**定向恢复**接起来——这两件事分开
都只能解决一半问题：

  - 只有动作后验证：知道"点了没反应"，但不知道下一步怎么办
  - 只有定向恢复：能按异常分类恢复，但拦不住"没抛异常的无效点击"

接线后形成闭环：

    click → changed=False → 判 F4（目标选错）→ substitute 换目标 → 再验证

这正是论文里静默失败被压到 0 的机制：无效动作不再是"看起来成功了"。

恢复钩子（对应 roadmap §Phase 3 的七类 → 八动作）：

  refresh    重新快照，按**元素名**重新映射到新 ref 后再点（应对 F5 上下文过期）
  substitute 换一个**同名候选**再点（应对 F4 目标选错 / 点了没反应）

刻意不做 replan：重规划需要模型参与，属于 L4 编排层的职责，不该由驱动层
代劳。驱动层做到"能自愈的自愈，不能自愈的带上完整诊断信息上报"。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fnixagent.core.tools.browser_refs import RefSnapshot
from fnixagent.core.tools.driver_errors import (
    F4_TOOL_CHOICE,
    F5_STALE_CONTEXT,
    F8_UNREACHABLE,
)
from fnixagent.core.tools.orchestrator import (
    CLEAR_OBSTRUCTION,
    REFRESH,
    Budget,
    OrchestratorResult,
    SelfHealingOrchestrator,
    StepOutcome,
    StepRecord,
)

_logger = logging.getLogger(__name__)

# expect_text 的等待上限。给足一点：真实页面点完常有动画与延迟渲染，
# 卡太紧会把正常的成功判成失败，那条闸门的信誉一旦坏了就没人再信它。
_EXPECT_TIMEOUT_MS = 4000


class BrowserHealer:
    """给浏览器动作套上自愈能力。

    用法：

        healer = BrowserHealer(session)
        result = await healer.click(ref="@e7")      # ref 寻址（推荐）
        result = await healer.click(text="提交")     # 文本寻址（兜底）

    两种寻址不是二选一，而是互为 substitute 恢复路径：ref 失效或点了没反应
    时自动改用文本，反之亦然。
    """

    def __init__(
        self,
        session: Any,
        *,
        budget: Budget | None = None,
        on_record: Callable[[StepRecord], None] | None = None,
    ) -> None:
        self._session = session
        self._snapshot: RefSnapshot | None = None
        self._tried: set[str] = set()
        self._orch = SelfHealingOrchestrator(
            refresh=self._on_refresh,
            substitute=self._on_substitute,
            clear_obstruction=self._on_clear_obstruction,
            budget=budget,
            on_record=on_record,
        )

    # ── 公开动作 ────────────────────────────────────────────────
    async def click(
        self,
        *,
        ref: str | None = None,
        text: str | None = None,
        require_change: bool = True,
        expect_text: str | None = None,
    ) -> OrchestratorResult:
        """点击，失败时自愈。

        `require_change` 是静默失败闸门：点了页面毫无反应（changed=False 且
        url 未变）时判失败，归到 F4（目标选错）触发换目标，而不是当成成功。

        `expect_text` 是**更强的一道闸**，也是"成功是真成功"在生产里真正落地
        的地方。`require_change` 只能证明"页面动了"，证明不了"动对了"——点了
        "加入购物车并结算"，页面当然也会动。传 `expect_text="已加入购物车"`，
        点击后必须看到这段文本才算成功，否则归 F6（证据矛盾）如实上报。

        只有调用方知道成功长什么样，所以这一层必须把口子开出去：驱动层替
        调用方猜预期，等于把"不说谎"这条承诺换成一次猜测。

        文本寻址会先解析成 ref 再点击——这样"换目标"才有可枚举的候选集。
        直接用 click_text 的话，Playwright 的 `.first` 每次都命中同一个元素，
        文本替换根本换不掉目标（实测：页面上有两个同名按钮，一个生效一个
        是诱饵，文本替换会一直点诱饵）。
        """
        if not ref and not text:
            raise ValueError("click 需要 ref 或 text 之一")
        verifier = self._text_verifier(expect_text)

        self._tried = set()
        if ref:
            primary = ref.lstrip("@")
        else:
            snap = await self._snapshot_or_fetch()
            # 按贴合度挑候选：名字完全对得上的优先，避免"加入购物车"被
            # 前面的"加入购物车并结算"截胡（详见 _rank_name_match 的说明）。
            pool = [r.ref for r in select_by_name(snap.refs, str(text))] if snap else []
            if not pool:
                # 快照里没有同名元素：退回文本点击，让驱动层自己报错并被分类
                return await self._orch.execute(
                    "click_text",
                    lambda: self._click_by_text(str(text), require_change),
                    target=str(text),
                    verifier=verifier,
                )
            primary = pool[0]
        self._tried.add(primary)

        async def _call() -> StepOutcome:
            state = await self._session.click_ref(primary)
            return _outcome_from(state, target=primary, require_change=require_change)

        return await self._orch.execute("click_ref", _call, target=primary, verifier=verifier)

    async def type_text(
        self,
        ref: str,
        text: str,
        *,
        submit: bool = False,
        expect_text: str | None = None,
    ) -> OrchestratorResult:
        """按 ref 输入，失败时自愈。"""

        async def _call() -> StepOutcome:
            state = await self._session.type_ref(ref, text, submit=submit)
            # 输入动作不一定改变页面结构（可能只改 value），故不做 changed 强制
            return _outcome_from(state, target=ref, require_change=False)

        return await self._orch.execute(
            "type_ref", _call, target=ref, verifier=self._text_verifier(expect_text)
        )

    def _text_verifier(self, expect_text: str | None) -> Any:
        """把"成功之后页面上该出现什么"编译成一个校验器。

        不传就是 None（保持既有行为），传了才在动作之后回页面确认一遍。
        用 `wait_for` 而不是立刻取快照，是因为真实页面点完常有延迟渲染——
        立刻看会误判成失败，而那会制造一批假警报，反而害了这条闸门的信誉。
        """
        if not expect_text:
            return None

        async def _verify(_state: Any) -> bool:
            st = await self._session.wait_for(text=expect_text, timeout_ms=_EXPECT_TIMEOUT_MS)
            return not st.error

        return _verify

    @property
    def records(self) -> list[StepRecord]:
        return list(self._orch._records)

    def reset(self) -> None:
        self._orch.reset()
        self._snapshot = None
        self._tried = set()

    # ── 内部 ────────────────────────────────────────────────────
    async def _snapshot_or_fetch(self) -> RefSnapshot | None:
        if self._snapshot is None:
            try:
                self._snapshot = await self._session.snapshot_ref()
            except Exception:  # noqa: BLE001
                return None
        return self._snapshot

    async def _click_by_text(self, text: str, require_change: bool) -> StepOutcome:
        state = await self._session.click_text(text)
        return _outcome_from(state, target=text, require_change=require_change)

    # ── 恢复钩子 ────────────────────────────────────────────────
    async def _on_refresh(self, ctx: dict[str, Any]) -> StepOutcome | None:
        """F5 上下文过期：重新快照，按 ref 名重新解析后再点一次。

        ref 的数字编号会随 DOM 变化漂移，所以重新快照后不能直接复用旧编号，
        要用**元素名**把旧目标映射到新编号——否则刷新等于白刷。

        两条纪律，都是脏页面（整块重排）实测出来的：

        1. **名字从哪儿来**。ref 路径的点击从不给 `self._snapshot` 赋值，旧实现
           在这里拿不到旧目标的名字，refresh 一律空手而归。会话保留着最近一次
           快照（`_last_snapshot`），回退到它去找"旧目标是谁"。
        2. **同名歧义不许猜**。重映射只在**恰好一个**同名候选时进行。列表页上
           每个商品的按钮都叫"加入购物车"，旧目标失效后随便挑一个同名按钮点
           下去，加的可能是别的商品——动作不报错、页面还变了，这是最典型的
           静默失败。宁可如实上报"映射不了"，让带锚点上下文的那一层（策略的
           重新定位）来决定，也不在这里赌。**找不到 ≠ 可以换一个凑合。**
        """
        ref = _as_ref(ctx.get("target"))
        old_name = ""
        if ref:
            # 先用自愈层自己缓存的快照，再回退到会话最近一次快照
            src = self._snapshot or getattr(self._session, "_last_snapshot", None)
            if src is not None:
                el = src.get(ref)
                old_name = el.name if el else ""

        try:
            self._snapshot = await self._session.snapshot_ref()
        except Exception as exc:  # noqa: BLE001
            return StepOutcome.from_exception(exc, hint=REFRESH)

        if not (old_name and self._snapshot):
            return None

        # 按名字找新编号。只在**唯一**命中时重映射——多个同名候选说明无法从
        # "名字"区分到底是哪一个，猜测 = 拿别的实体冒充原目标（见 docstring）。
        matches = [el for el in self._snapshot.refs if el.name and el.name == old_name]
        if len(matches) == 1:
            state = await self._session.click_ref(matches[0].ref)
            return _outcome_from(state, target=matches[0].ref, require_change=True)
        if len(matches) > 1:
            _logger.info(
                "refresh 无法重映射：旧目标「%s」在新快照里有 %d 个同名候选，"
                "拒绝猜测、交由上层重新定位", old_name, len(matches),
            )
        return None

    async def _on_clear_obstruction(self, ctx: dict[str, Any]) -> StepOutcome | None:
        """F8 目标不可达：把目标挪到能点的位置，重试**同一个**目标。

        只做滚动这一件用户自己也做得到的事。刻意不做两件看起来更"聪明"的事：

        - **不换目标**。够不着不等于选错了。页面上往往有一堆同名按钮，换一
          个就能点上，于是动作不再报错、任务被判成功——但加购的是别的商品。
          这是把一次诚实的失败，换成一次无人发现的做错。
        - **不用 JS 直接触发 click**。那会绕过真实用户能收到的所有事件，让
          AI 走一条用户永远走不通的路，静默失败换成另一种静默失败。

        返回 None 表示这一级无从下手，交给阶梯的下一级（refresh / escalate）。
        """
        ref = _as_ref(ctx.get("target"))
        if not ref:
            return None
        try:
            state = await self._session.clear_obstruction(ref)
        except Exception as exc:  # noqa: BLE001
            return StepOutcome.from_exception(exc, hint=CLEAR_OBSTRUCTION)
        if getattr(state, "error", None):
            return StepOutcome(
                ok=False,
                error=str(state.error),
                raw=state,
            )
        return None

    async def _on_substitute(self, ctx: dict[str, Any]) -> StepOutcome | None:
        """F4 目标选错：换一个**同名候选**再试。

        候选集 = 快照里与原目标同名的其他元素。为什么是同名候选而不是"换
        寻址方式"：页面上排前面的同名按钮常常正是干扰项（诱饵在前、真按钮
        在后），逐个试过去才可能命中真正生效的那个。而换成文本点击会因为
        Playwright 的 `.first` 每次都命中同一个诱饵——等于没换。

        返回 None 表示候选已用尽，这一级确实用完了。
        """
        target = str(ctx.get("target") or "")
        # 够不着的目标一律不换。换掉它等于替用户改意图，而且改完零报错。
        if _is_unreachable(ctx):
            _logger.info(
                "substitute 跳过：目标 %s 属于不可达（%s），换目标会把"
                "「够不着」伪装成「做成了别的」", target, ctx.get("failure_class"),
            )
            return None
        # 失去踪迹的目标也不换。上下文过期 ≠ 选错了，没有任何证据说明原目标
        # "不对"；在同名候选里轮换是拿别的实体冒充原目标（列表页实测会加错
        # 商品且零报错）。F5 的正路是按名重映射（见 _on_refresh），映射不了
        # 就如实上报，由带锚点信息的调用方重新定位。
        if _is_stale(ctx):
            _logger.info(
                "substitute 跳过：目标 %s 属于上下文过期（%s），换同名候选不是"
                "自愈而是猜测", target, ctx.get("failure_class"),
            )
            return None
        snap = await self._snapshot_or_fetch()
        if not snap:
            return None

        ref = _as_ref(target)
        if ref:
            el = snap.get(ref)
            name = el.name if el else ""
            if not name:
                return None
            pool = [r.ref for r in snap.refs if r.name == name]
        else:
            pool = [r.ref for r in select_by_name(snap.refs, target)]

        for cand in pool:
            if cand in self._tried:
                continue
            self._tried.add(cand)
            state = await self._session.click_ref(cand)
            return _outcome_from(state, target=cand, require_change=True)
        return None


def _is_unreachable(ctx: dict[str, Any]) -> bool:
    """这次失败是不是"目标存在但够不着"。

    判定依据是分类结果而不只是异常文本：文本匹配会漏（Playwright 各版本措辞
    不同），而分类已经把 F8 与 F4 分开，编排层也据此选了阶梯。
    """
    if str(ctx.get("failure_class") or "") == F8_UNREACHABLE:
        return True
    outcome = ctx.get("outcome")
    return str(getattr(outcome, "failure_class", "") or "") == F8_UNREACHABLE


def _is_stale(ctx: dict[str, Any]) -> bool:
    """这次失败是不是"上下文过期"（ref 失效 / 页面已重渲染）。

    与 `_is_unreachable` 同理：判定依据是分类结果而非异常文本。上下文过期
    与"目标选错"是两回事——前者只是失去了目标踪迹，后者才有"换一个"的理由。
    """
    if str(ctx.get("failure_class") or "") == F5_STALE_CONTEXT:
        return True
    outcome = ctx.get("outcome")
    return str(getattr(outcome, "failure_class", "") or "") == F5_STALE_CONTEXT


def _as_ref(target: Any) -> str | None:
    """判断 target 是不是 ref（@e7 / e7）。"""
    if not isinstance(target, str):
        return None
    t = target.strip().lstrip("@")
    return t if t.startswith("e") and t[1:].isdigit() else None


def _rank_name_match(name: str, needle: str) -> int:
    """元素名与查询文本的匹配档位，0 表示完全不匹配。

    分档而不是布尔值，是因为**不加区分的双向包含会点错按钮**：

        AI 说"加入购物车"，页面上有"加入购物车并结算"和"加入购物车"，
        而前者在 DOM 里靠前——双向包含让两者同等匹配，于是先点中"并结算"。
        驱动层一个错都不会报，用户看到的却是"我说加购，它直接给我下单了"。
        在真实电商/支付页面上这是会造成实际损失的错误，且完全静默。

    三档，顺序不能反：

      3  完全相等
      2  元素名包含查询（"加入购物车" ⊂ "加入购物车并结算"）
      1  查询包含元素名（"点那个加入购物车按钮" 这种模糊说法里的词）
         要求元素名至少 2 字，否则单字会命中一堆无关元素

    同档内按名字短的优先：越短说明越贴合查询，而不是"查询碰巧是它的前缀"。
    """
    n = (name or "").strip()
    q = (needle or "").strip()
    if not n or not q:
        return 0
    if n == q:
        return 3
    if q in n:
        return 2
    if len(n) >= 2 and n in q:
        return 1
    return 0


def _name_matches(name: str, needle: str) -> bool:
    """是否匹配（分档判定的布尔视图）。"""
    return _rank_name_match(name, needle) > 0


def select_by_name(refs: list[Any], needle: str) -> list[Any]:
    """按名称挑出最贴切的一组候选，按贴合度从高到低排。

    只返回**同一档位**的候选：自愈的"换目标"阶梯就是在这个集合里轮换，
    把"完全相等"和"勉强沾边"混在一个池子里，换目标只会越换越离谱。
    """
    scored: list[tuple[int, int, Any]] = []
    for r in refs:
        score = _rank_name_match(getattr(r, "name", "") or "", needle)
        if score > 0:
            scored.append((score, -len(str(getattr(r, "name", "") or "")), r))
    if not scored:
        return []
    scored.sort(key=lambda t: (-t[0], -t[1]))
    best = scored[0][0]
    return [t[2] for t in scored if t[0] == best]


def _outcome_from(state: Any, *, target: str, require_change: bool) -> StepOutcome:
    """BrowserState → StepOutcome，把驱动层的信号翻译成编排层可分类的结果。"""
    error = getattr(state, "error", None)
    if error:
        return StepOutcome(
            ok=False,
            error=str(error),
            failure_class=getattr(state, "error_class", "") or "",
            raw=state,
        )
    if require_change and not (getattr(state, "changed", False) or getattr(state, "url_changed", False)):
        # 动作没抛异常，但页面毫无反应——这正是静默失败的典型形态。
        # 归到 F4（目标选错）：重试同一个目标毫无意义，该换目标。
        return StepOutcome(
            ok=False,
            error=f"点击 {target} 后页面无任何变化（可能点到了错误的目标）",
            failure_class=F4_TOOL_CHOICE,
            raw=state,
        )
    return StepOutcome(ok=True, value=state, raw=state)
