"""Phase 3 自愈编排器 · 策略层单测（不依赖浏览器）。

测的是**定向恢复**这个主张本身：

  1. 同一故障走对恢复动作，而不是一律重试
  2. 预算会耗尽，且失败的恢复尝试也消耗预算
  3. 原地打转能被识别并终止（F7）
  4. 验证器能拦住"没抛异常但结果不对"的静默失败

这四条不成立的话，编排器就退化成 retry 装饰器——那正是论文里只有 94.5%
且静默失败压不下去的做法。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from fnixagent.core.tools.driver_errors import (
    F1_TIMEOUT,
    F2_ARGUMENT,
    F4_TOOL_CHOICE,
    F5_STALE_CONTEXT,
    F7_CONTROL_LOOP,
)
from fnixagent.core.tools.orchestrator import (
    CLEAR_OBSTRUCTION,
    ESCALATE,
    F6_CONTRADICTION,
    FIX_ARGS,
    REFRESH,
    REPLAN,
    RECOVERY_LADDER,
    RESCHEMA,
    RETRY,
    SUBSTITUTE,
    Budget,
    SelfHealingOrchestrator,
    StepOutcome,
)

pytestmark = pytest.mark.asyncio


class Recorder:
    """记录钩子被调用的顺序，用于断言"走的是哪条路"。"""

    def __init__(self, outcome: StepOutcome | None = None) -> None:
        self.calls: list[str] = []
        self._outcome = outcome

    def hook(self, name: str) -> Any:
        async def _h(ctx: dict[str, Any]) -> StepOutcome | None:
            self.calls.append(name)
            return self._outcome
        return _h


async def test_success_on_first_try_needs_no_recovery() -> None:
    orch = SelfHealingOrchestrator()
    result = await orch.execute("click", lambda: asyncio.sleep(0, StepOutcome(ok=True, value="ok")))
    assert result.ok is True
    assert result.value == "ok"
    assert result.attempts == 1
    assert result.recovery_used == []


async def test_f1_goes_to_retry_before_anything_else() -> None:
    """超时先重试——这是唯一"重试有意义"的故障类。"""
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        if calls["n"] < 2:
            return StepOutcome(ok=False, error="Timeout 5000ms exceeded", failure_class=F1_TIMEOUT)
        return StepOutcome(ok=True, value="done")

    rec = Recorder()
    orch = SelfHealingOrchestrator(refresh=rec.hook("refresh"), substitute=rec.hook("substitute"))
    result = await orch.execute("click", _call)

    assert result.ok is True
    # 重试就够了，不该惊动 refresh/substitute
    assert rec.calls == []
    assert result.recovery_used == [RETRY]


async def test_f4_goes_to_substitute_not_retry() -> None:
    """选错目标时重试同一个目标是浪费——必须换目标。

    这条是"分类恢复"区别于"纯重试"的核心：两者在 F1 上行为一致，
    在 F4 上分道扬镳。
    """
    rec = Recorder(outcome=StepOutcome(ok=True, value="via-alternative"))
    orch = SelfHealingOrchestrator(
        substitute=rec.hook(SUBSTITUTE), refresh=rec.hook(REFRESH), replan=rec.hook(REPLAN)
    )
    result = await orch.execute(
        "click",
        lambda: asyncio.sleep(
            0, StepOutcome(ok=False, error="no element found", failure_class=F4_TOOL_CHOICE)
        ),
    )

    assert result.ok is True
    assert rec.calls == [SUBSTITUTE], f"F4 应先走 substitute，实际走了 {rec.calls}"


async def test_f5_goes_to_refresh() -> None:
    """ref 失效（上下文过期）时该重新取快照，而不是重试或换目标。"""
    rec = Recorder(outcome=StepOutcome(ok=True, value="after-refresh"))
    orch = SelfHealingOrchestrator(
        refresh=rec.hook(REFRESH), substitute=rec.hook(SUBSTITUTE), replan=rec.hook(REPLAN)
    )
    result = await orch.execute(
        "click_ref",
        lambda: asyncio.sleep(
            0, StepOutcome(ok=False, error="stale ref", failure_class=F5_STALE_CONTEXT)
        ),
    )

    assert result.ok is True
    assert rec.calls == [REFRESH]


async def test_failed_recovery_consumes_budget() -> None:
    """失败的恢复尝试同样扣预算——否则重试就成了免费动作。

    这是论文里"纯重试只有 94.5%"的直接原因：不计费的重试让编排器无限打转。
    """
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(ok=False, error="timeout", failure_class=F1_TIMEOUT)

    rec = Recorder()  # 所有钩子返回 None = 恢复也没辙
    budget = Budget(retry=2, refresh=1, total=3)
    orch = SelfHealingOrchestrator(refresh=rec.hook(REFRESH), budget=budget)
    result = await orch.execute("click", _call)

    assert result.ok is False
    assert result.escalated is True
    # 预算 3：retry ×2 + refresh ×1，之后必须停止，不能继续
    assert budget.total_remaining == 0
    assert calls["n"] == 3, f"预算耗尽后仍执行了 {calls['n']} 次"
    assert result.recovery_used == [RETRY, RETRY, REFRESH]


async def test_unwired_recovery_rungs_do_not_burn_budget() -> None:
    """阶梯上没接实现的动作必须跳过，不能先扣预算再发现无事可做。

    审计发现（2026-08-29）：BrowserHealer 只注册了 refresh / substitute /
    clear_obstruction 三个钩子，而 F2 的阶梯是 (FIX_ARGS, REPLAN, ESCALATE)。
    修之前，F2 会把预算交给两个根本没有实现的动作，烧完才上报——同一任务里
    真正能救的 F5/F8 就没预算了。

    论文说"失败的恢复也消耗预算"，指的是执行了但没成功；根本没执行的不算。
    """
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(ok=False, error="invalid argument", failure_class=F2_ARGUMENT)

    # 一个钩子都不接：F2 阶梯上的 FIX_ARGS / REPLAN 都是空转
    budget = Budget(fix_args=2, replan=2, total=4)
    orch = SelfHealingOrchestrator(budget=budget)
    result = await orch.execute("click", _call)

    assert result.ok is False
    assert result.escalated is True
    # 关键：预算一格都没被空气烧掉
    assert budget.total_remaining == 4, f"未接线的阶梯烧掉了 {4 - budget.total_remaining} 格预算"
    # 中间一级都没走——直接上报，而不是烧完空转的阶梯再上报
    assert result.recovery_used == [ESCALATE], f"实际走了: {result.recovery_used}"
    assert calls["n"] == 1, f"空转的阶梯不该反复执行动作，实际 {calls['n']} 次"


async def test_unwired_recoveries_are_visible_instead_of_silent() -> None:
    """哪些阶梯是"名义完成"必须能从代码里查出来，而不是靠人工审计。"""
    orch = SelfHealingOrchestrator()
    # 一个钩子都没接：除 RETRY/ESCALATE 外的动作全是未接线
    assert set(orch.unwired_recoveries) == {FIX_ARGS, RESCHEMA, REPLAN, REFRESH,
                                            SUBSTITUTE, CLEAR_OBSTRUCTION}

    # 接上 refresh / substitute / clear_obstruction（浏览器接线的实际形态）
    wired = SelfHealingOrchestrator(
        refresh=Recorder().hook(REFRESH),
        substitute=Recorder().hook(SUBSTITUTE),
        clear_obstruction=Recorder().hook(CLEAR_OBSTRUCTION),
    )
    assert set(wired.unwired_recoveries) == {FIX_ARGS, RESCHEMA, REPLAN}


async def test_wired_rung_still_consumes_budget_when_it_fails() -> None:
    """护栏：接了实现但失败的恢复，预算照扣——不能因为上一条改动而变成免费。"""
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(ok=False, error="timeout", failure_class=F1_TIMEOUT)

    rec = Recorder()  # refresh 接了实现，但返回 None = 没辙
    budget = Budget(retry=1, refresh=1, total=2)
    orch = SelfHealingOrchestrator(refresh=rec.hook(REFRESH), budget=budget)
    result = await orch.execute("click", _call)

    assert result.ok is False
    assert budget.total_remaining == 0, "接了实现却失败，预算必须照扣"
    assert rec.calls == [REFRESH]


async def test_ladder_falls_through_when_action_has_no_budget() -> None:
    """某一级预算耗尽，应落到阶梯的下一级，而不是直接放弃。"""
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(ok=False, error="no element found", failure_class=F4_TOOL_CHOICE)

    rec = Recorder(outcome=StepOutcome(ok=True, value="rescued-by-refresh"))
    # substitute 预算归零，但 refresh 还有
    budget = Budget(substitute=0, refresh=2, replan=0, total=4)
    orch = SelfHealingOrchestrator(
        substitute=rec.hook(SUBSTITUTE), refresh=rec.hook(REFRESH), budget=budget
    )
    result = await orch.execute("click", _call)

    assert result.ok is True
    assert rec.calls == [REFRESH], f"应跳过无预算的 substitute 走 refresh，实际 {rec.calls}"


async def test_control_loop_is_detected_and_escalated() -> None:
    """同一个动作反复用同一种恢复动作 → 判定原地打转，终止并上报。

    钩子返回"尝试过但失败"（非 None）是关键：返回 None 表示这一级帮不上忙，
    编排器会把它标记为死路并走下一级——那是有序探索，不是打转。只有同一级
    反复投入预算却毫无进展，才该被判 F7。
    """
    escalated: list[dict[str, Any]] = []

    async def _escalate(ctx: dict[str, Any]) -> None:
        escalated.append(ctx)

    # 每次都"试了但没成"——这才是真正的原地打转
    rec = Recorder(outcome=StepOutcome(ok=False, error="still stale",
                                       failure_class=F5_STALE_CONTEXT))
    orch = SelfHealingOrchestrator(
        refresh=rec.hook(REFRESH), escalate=_escalate, budget=Budget(refresh=10, total=10)
    )
    result = await orch.execute(
        "click",
        lambda: asyncio.sleep(
            0, StepOutcome(ok=False, error="stale ref", failure_class=F5_STALE_CONTEXT)
        ),
    )

    assert result.ok is False
    assert result.failure_class == F7_CONTROL_LOOP
    assert result.escalated is True
    assert len(escalated) == 1
    # 打转必须在阈值处停下，而不是把 10 次预算花光
    assert len(rec.calls) <= 3, f"打转未被及时终止，refresh 被调用了 {len(rec.calls)} 次"


async def test_dead_rung_is_not_retried() -> None:
    """钩子明确表示帮不上忙（返回 None）的那一级，不该反复扣预算。

    少了这条，F5 的三级阶梯里 refresh 会把自己的 2 次预算花光才轮到
    substitute——后面的路被前面的死路饿死。
    """
    calls: list[str] = []
    budget = Budget(refresh=2, substitute=2, replan=2, total=6)

    def _none_hook(name: str) -> Any:
        async def _h(ctx: dict[str, Any]) -> None:
            calls.append(name)
            return None
        return _h

    orch = SelfHealingOrchestrator(
        refresh=_none_hook(REFRESH),
        substitute=_none_hook(SUBSTITUTE),
        replan=_none_hook(REPLAN),
        budget=budget,
    )
    result = await orch.execute(
        "click",
        lambda: asyncio.sleep(
            0, StepOutcome(ok=False, error="stale", failure_class=F5_STALE_CONTEXT)
        ),
    )

    assert result.ok is False
    assert result.escalated is True
    # 三级各试一次即收敛，而不是把 refresh 的 2 次预算耗完
    assert calls == [REFRESH, SUBSTITUTE, REPLAN], f"死路被重复尝试: {calls}"


async def test_verifier_blocks_silent_failure() -> None:
    """动作没抛异常、自称成功，但结果不对 —— 必须被验证器拦下。

    论文中静默失败 13.2-17.6% 全来自这类"看似成功实则错误"的返回，
    纯重试对它们完全无能为力。
    """
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        # 动作本身永远"成功"，但返回的是错误内容
        return StepOutcome(ok=True, value={"text": "初始内容"})

    rec = Recorder(outcome=StepOutcome(ok=True, value={"text": "已更新"}))
    orch = SelfHealingOrchestrator(replan=rec.hook(REPLAN), refresh=rec.hook(REFRESH))
    result = await orch.execute(
        "click",
        _call,
        verifier=lambda v: isinstance(v, dict) and v.get("text") == "已更新",
    )

    assert result.ok is True
    assert result.value == {"text": "已更新"}
    assert rec.calls == [REPLAN], "未通过验证应归 F6 并走重规划"
    assert F6_CONTRADICTION in {r.failure_class for r in result.records}


async def test_verifier_failure_escalates_when_unrecoverable() -> None:
    """验证不通过且恢复无门时，不能返回"成功了"——那正是静默失败的定义。"""
    orch = SelfHealingOrchestrator(budget=Budget(replan=0, refresh=0, total=1))
    result = await orch.execute(
        "click",
        lambda: asyncio.sleep(0, StepOutcome(ok=True, value={"text": "没变"})),
        verifier=lambda v: isinstance(v, dict) and v.get("text") == "已更新",
    )

    assert result.ok is False, "验证失败却返回成功 = 静默失败"
    assert result.escalated is True
    assert result.failure_class == F6_CONTRADICTION


async def test_f6_ladder_excludes_refresh_by_design() -> None:
    """元约束：「结果不对」的阶梯里刻意没有 REFRESH。

    踩过的坑：动作本身已成功（changed=True），只是结果没通过验证器。若
    阶梯带 REFRESH，重新快照会把同一个动作再执行一次——第二次执行页面
    当然不再变化，F6 就被改判成 F4「点了没反应」。用户照着「没反应」去
    查，永远查不到真相（点了，但做错了）。这是把「如实上报」换成「误导性
    上报」，比不报更坏。
    """
    ladder = RECOVERY_LADDER[F6_CONTRADICTION]
    assert REFRESH not in ladder, (
        "F6（结果不对）不能被刷新上下文伪装成「点了没反应」，REFRESH 不得出现在其阶梯里"
    )
    assert ladder[0] == REPLAN, "结果对不对得上，只有知道预期的那一层能救，第一级应是 REPLAN"

async def test_verifier_failure_is_not_reclassified_as_no_response() -> None:
    """行为护栏：验证不通过时，refresh 钩子被注册了也绝不能被调到。

    这是上面元约束的行为面：就算接线里同时存在 refresh 钩子，F6 的恢复
    也不许走它——走一次，原动作就被重复执行一次，「结果不对」下游就被
    翻译成「点了没反应」。
    """
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        # 动作每次都"成功"，但结果永远不对
        return StepOutcome(ok=True, value={"text": "没变"})

    rec = Recorder(outcome=StepOutcome(ok=True, value={"text": "已更新"}))
    orch = SelfHealingOrchestrator(
        refresh=rec.hook(REFRESH),
        budget=Budget(refresh=10, replan=0, total=2),
    )
    result = await orch.execute(
        "click",
        _call,
        verifier=lambda v: isinstance(v, dict) and v.get("text") == "已更新",
    )

    assert REFRESH not in rec.calls, f"F6 不允许调用 refresh 钩子，实际: {rec.calls}"
    assert calls["n"] == 1, f"同一个动作被重复执行 = 又被测了一遍：{calls}"
    assert result.ok is False and result.escalated is True
    # 全程保持 F6 的本来面目，不许中途被翻译成「点了没反应」
    classes = {r.failure_class for r in result.records}
    assert classes == {F6_CONTRADICTION}, f"故障类被中途改写: {classes}"

async def test_escalate_hook_receives_diagnostic_context() -> None:
    """上报时必须带上足够信息，否则用户/上层无法判断下一步。"""
    seen: list[dict[str, Any]] = []

    async def _escalate(ctx: dict[str, Any]) -> None:
        seen.append(ctx)

    orch = SelfHealingOrchestrator(escalate=_escalate, budget=Budget(total=0))
    result = await orch.execute(
        "click_ref",
        lambda: asyncio.sleep(
            0, StepOutcome(ok=False, error="stale ref", failure_class=F5_STALE_CONTEXT)
        ),
        target="@e7",
    )

    assert result.escalated is True
    ctx = seen[0]
    assert ctx["action"] == "click_ref"
    assert ctx["target"] == "@e7"
    assert ctx["failure_class"] == F5_STALE_CONTEXT


async def test_records_capture_full_recovery_trace() -> None:
    """可观测：每步都要能回答"失败在哪一类、做了什么恢复、还剩多少预算"。"""
    calls = {"n": 0}

    async def _call() -> StepOutcome:
        calls["n"] += 1
        if calls["n"] <= 2:
            return StepOutcome(ok=False, error="timeout", failure_class=F1_TIMEOUT)
        return StepOutcome(ok=True, value="ok")

    orch = SelfHealingOrchestrator()
    result = await orch.execute("click", _call)

    failed = [r for r in result.records if not r.ok]
    assert len(failed) == 2
    for r in failed:
        assert r.failure_class == F1_TIMEOUT
        assert r.recovery_action == RETRY
        assert r.budget_left >= 0
    assert result.records[-1].ok is True
    # 记录可序列化（要落审计流）
    for r in result.records:
        assert isinstance(r.to_dict(), dict)


async def test_ladder_always_terminates_in_escalate() -> None:
    """元约束：任何故障类的阶梯终点都是 ESCALATE。

    少了这一条，未来新增故障类时可能写出没有出口的阶梯，编排器就会失去
    "终止并上报"的能力——宁可上报也不能无限自愈。
    """
    for code, ladder in RECOVERY_LADDER.items():
        assert ladder, f"{code} 阶梯为空"
        assert ladder[-1] == ESCALATE, f"{code} 的阶梯没有以 ESCALATE 收尾: {ladder}"


async def test_budget_is_task_scoped_and_resettable() -> None:
    """预算跨步骤累计，reset() 后才释放——避免每步重置导致预算形同虚设。"""
    orch = SelfHealingOrchestrator(budget=Budget(retry=1, total=1))
    calls = {"n": 0}

    async def _fail() -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(ok=False, error="timeout", failure_class=F1_TIMEOUT)

    await orch.execute("click", _fail)
    assert orch._budget.total_remaining == 0

    # 预算耗尽后，即使换一个动作也必须立刻上报
    result = await orch.execute("scroll", _fail)
    assert result.escalated is True
    assert result.records[-1].recovery_action == ""

    orch.reset()
    assert orch._budget.total_remaining == 1
    assert orch._records == []


async def test_unclassified_failure_defaults_to_timeout_ladder() -> None:
    """异常没落进 F1-F7 时不能失控——按最保守的超时处理。"""
    rec = Recorder(outcome=StepOutcome(ok=True, value="ok"))
    orch = SelfHealingOrchestrator(refresh=rec.hook(REFRESH))
    result = await orch.execute(
        "click",
        lambda: asyncio.sleep(0, StepOutcome(ok=False, error="某种从未见过的错误")),
    )

    assert result.ok is True
    assert result.records[0].failure_class == F1_TIMEOUT
    assert rec.calls == [REFRESH]
