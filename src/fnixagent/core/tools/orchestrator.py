"""自愈编排器（GUI_DRIVER_ROADMAP.md Phase 3 核心）。

依据 arXiv 2606.01416《Self-Healing Agentic Orchestrators》，9000 次注入故障的
实测结论：

    静态工作流        70.1%
    纯重试            94.5%
    全量重规划        93.8%
    先分类再定向恢复  98.8%   ← 本模块实现的对象

而且**只有分类恢复把静默失败从 13.2-17.6% 压到 0%**——纯重试做不到，因为重试
解决的是"偶发"，解决不了"选错目标""上下文过期"这类方向性错误。

所以本模块的价值不在"多试几次"，而在**每次失败都被归到正确的类别，并采取
该类别对应的恢复动作**。

设计取舍：编排器不认识浏览器，也不认识模型。它通过钩子（hook）消费外部能力：

    refresh    重新取上下文（浏览器场景 = 重新快照）
    substitute 换一种做法（换目标 / 换工具）
    replan     推倒重来（交回模型重新决策）
    escalate   终止并上报用户

这样它既能单测（钩子用假实现），又不与任何具体驱动耦合。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from fnixagent.core.tools.driver_errors import (
    F1_TIMEOUT,
    F2_ARGUMENT,
    F3_OUTPUT,
    F4_TOOL_CHOICE,
    F5_STALE_CONTEXT,
    F6_CONTRADICTION,
    F7_CONTROL_LOOP,
    F8_UNREACHABLE,
    classify,
)
from fnixagent.core.tools.retry import RetryPolicy

_logger = logging.getLogger(__name__)

# ── 恢复动作 ────────────────────────────────────────────────────
RETRY = "retry"          # 指数退避重试同一个动作
FIX_ARGS = "fix_args"    # 本地修正参数后重试（不消耗模型）
RESCHEMA = "reschema"    # 带 schema 重问
SUBSTITUTE = "substitute"  # 更换工具或目标
REFRESH = "refresh"      # 刷新上下文后重新决策
REPLAN = "replan"        # 重新规划
ESCALATE = "escalate"    # 终止并上报用户
# 解除遮挡：把目标挪到能点的位置，然后重试**同一个**目标。
# 与 SUBSTITUTE 的区别是本质性的——够不着的目标不该被换掉。换掉就是替用户
# 改意图，而且改完零报错（实测：加购 A 变成加购 B，任务被判成功）。
CLEAR_OBSTRUCTION = "clear_obstruction"

RECOVERY_LABELS = {
    RETRY: "指数退避重试",
    FIX_ARGS: "本地修正参数",
    RESCHEMA: "带 schema 重问",
    SUBSTITUTE: "更换工具或目标",
    REFRESH: "刷新上下文",
    REPLAN: "重新规划",
    ESCALATE: "终止并上报",
    CLEAR_OBSTRUCTION: "解除遮挡后重试原目标",
}

# ── 故障 → 恢复动作阶梯 ─────────────────────────────────────────
# 为什么是阶梯而不是单一动作：论文里"定向恢复"的关键不只是选对第一动作，
# 还包括**第一动作无效后往哪里退**。重试三次还超时的动作，继续重试是浪费；
# 正确做法是刷新上下文看看页面是否已经变了，再不行就换目标，最后才上报。
#
# 阶梯的最后一级统一是 ESCALATE——任何故障都不能无限自愈，必须有终点。
RECOVERY_LADDER: dict[str, tuple[str, ...]] = {
    F1_TIMEOUT: (RETRY, REFRESH, ESCALATE),
    F2_ARGUMENT: (FIX_ARGS, REPLAN, ESCALATE),
    F3_OUTPUT: (RESCHEMA, REPLAN, ESCALATE),
    F4_TOOL_CHOICE: (SUBSTITUTE, REFRESH, REPLAN, ESCALATE),
    # 上下文过期：**刻意不含 SUBSTITUTE**。
    #
    # 过期 ≠ 选错：目标只是失去了踪迹，没有任何证据说明它"不对"。此时在同名
    # 候选里轮换是纯赌博——列表页上同名按钮个个是真的、各属于不同实体
    # （每个商品的"加入购物车"），轮换必定点到另一个实体的按钮：页面变了、
    # 一个错都不报，一次诚实的失败就此变成无人发现的做错（400ms 整块重建页
    # 实测，d04）。
    #
    # 唯一仍在"找原目标"的恢复是 refresh 的按名重映射（歧义纪律见
    # _on_refresh）；映射不了就如实上报——知道锚点的调用方（策略层）拿全新
    # 快照能重新定位。SUBSTITUTE 留给 F4（目标已被证明无效）专用。
    F5_STALE_CONTEXT: (REFRESH, REPLAN, ESCALATE),
    # 证据矛盾（结果没通过验证器）：**刻意不含 REFRESH**。
    #
    # 这里踩过一次：动作本身已经成功了（changed=True），只是结果不对。带
    # REFRESH 的话，刷新上下文会把同一个动作再执行一次——而同一个动作第二次
    # 执行，页面当然不再变化，于是 F6 被改判成 F4「点了没反应」。用户看到的
    # 就成了误导：真相是"点了但做错了"，报出来的却是"点了没反应"，照着后者
    # 去查只会越查越偏。
    #
    # 结果不对这件事，刷新上下文救不了，也不该由驱动层自己重试掩盖——如实
    # 上报，让知道预期是什么的那一层去决定。
    F6_CONTRADICTION: (REPLAN, ESCALATE),
    F7_CONTROL_LOOP: (ESCALATE,),
    # 目标不可达：先解除遮挡重试**原目标**；刷新只是换个角度再看一眼
    # （页面可能已经变了，遮挡可能自己消失了）；最后如实上报"点不到"。
    # 刻意不含 SUBSTITUTE——换目标会把"够不着"伪装成"做完了别的"。
    F8_UNREACHABLE: (CLEAR_OBSTRUCTION, REFRESH, ESCALATE),
}

# 没有分类信息时的兜底阶梯（异常没落到 F1-F7 里，先当成超时处理）
_UNKNOWN_LADDER = (RETRY, REFRESH, ESCALATE)

# 退避策略：与既有 retry.py 保持同一套数值，不另起炉灶
_BACKOFF_POLICY = RetryPolicy(
    max_attempts=8,
    initial_delay=0.4,
    max_delay=4.0,
    backoff_factor=2.0,
)


@dataclass
class Budget:
    """恢复预算。

    论文的关键约束：**失败的恢复尝试同样消耗预算**。否则"重试"就成了免费
    动作，编排器会退化成无限重试——那正是纯重试只有 94.5% 的原因。

    每类恢复动作独立上限，另设总量上限兜底。总量先耗尽时，后续一律 ESCALATE。
    """

    retry: int = 2
    fix_args: int = 1
    reschema: int = 1
    substitute: int = 2
    refresh: int = 2
    replan: int = 1
    escalate: int = 1
    total: int = 6

    _used: dict[str, int] = field(default_factory=dict)

    def remaining(self, action: str) -> int:
        cap = int(getattr(self, action, 0))
        return max(0, cap - self._used.get(action, 0))

    @property
    def total_remaining(self) -> int:
        return max(0, self.total - sum(self._used.values()))

    def spend(self, action: str) -> None:
        self._used[action] = self._used.get(action, 0) + 1

    def snapshot(self) -> dict[str, int]:
        return dict(self._used)


@dataclass
class StepOutcome:
    """一次动作尝试的结果。统一形状，编排器才好分类。"""

    ok: bool
    value: Any = None
    error: str = ""
    failure_class: str = ""
    raw: Any = None

    @classmethod
    def from_exception(cls, exc: BaseException, hint: str = "") -> "StepOutcome":
        return cls(
            ok=False,
            error=str(exc),
            failure_class=classify(exc, hint),
            raw=exc,
        )


@dataclass
class StepRecord:
    """可观测：每步留痕，与审计流合并（路线文档 Phase 3 要求）。"""

    step: int
    action: str
    attempt: int
    ok: bool
    failure_class: str = ""
    recovery_action: str = ""
    budget_left: int = 0
    elapsed_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "attempt": self.attempt,
            "ok": self.ok,
            "failure_class": self.failure_class,
            "recovery_action": self.recovery_action,
            "budget_left": self.budget_left,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "error": self.error,
        }


@dataclass
class OrchestratorResult:
    ok: bool
    value: Any = None
    error: str = ""
    failure_class: str = ""
    recovery_used: list[str] = field(default_factory=list)
    records: list[StepRecord] = field(default_factory=list)
    escalated: bool = False

    @property
    def attempts(self) -> int:
        return len(self.records)


# 钩子类型：接收当前尝试的上下文，返回一次新的尝试结果
RecoveryHook = Callable[[dict[str, Any]], Awaitable[StepOutcome | None]]


class SelfHealingOrchestrator:
    """把一次动作包进"分类 → 定向恢复 → 预算 → 留痕"的闭环。

    典型用法（浏览器场景）：

        orch = SelfHealingOrchestrator(
            refresh=lambda ctx: snapshot_then_retry(ctx),
            substitute=lambda ctx: try_alternative_target(ctx),
            replan=lambda ctx: ask_model_again(ctx),
            escalate=lambda ctx: report_to_user(ctx),
        )
        result = await orch.execute("click", lambda: session.click_ref(ref))
    """

    def __init__(
        self,
        *,
        refresh: RecoveryHook | None = None,
        substitute: RecoveryHook | None = None,
        replan: RecoveryHook | None = None,
        escalate: RecoveryHook | None = None,
        fix_args: RecoveryHook | None = None,
        reschema: RecoveryHook | None = None,
        clear_obstruction: RecoveryHook | None = None,
        budget: Budget | None = None,
        loop_threshold: int = 3,
        on_record: Callable[[StepRecord], None] | None = None,
    ) -> None:
        self._hooks: dict[str, RecoveryHook | None] = {
            REFRESH: refresh,
            SUBSTITUTE: substitute,
            REPLAN: replan,
            ESCALATE: escalate,
            FIX_ARGS: fix_args,
            RESCHEMA: reschema,
            CLEAR_OBSTRUCTION: clear_obstruction,
        }
        self._budget = budget or Budget()
        # 同一个动作+目标反复用同一种恢复动作到这个次数即判定原地打转（F7）
        self._loop_threshold = loop_threshold
        self._on_record = on_record
        self._records: list[StepRecord] = []
        # (action, target, recovery)——按"实际采取的恢复动作"计数，见 _is_looping
        self._history: list[tuple[str, str, str]] = []
        self._dead_rungs: set[str] = set()

    # ── 主入口 ──────────────────────────────────────────────────
    async def execute(
        self,
        action: str,
        call: Callable[[], Awaitable[StepOutcome]],
        *,
        target: str = "",
        verifier: Callable[[Any], bool] | None = None,
        budget: Budget | None = None,
    ) -> OrchestratorResult:
        """执行一次动作，失败时按故障分类定向恢复，直到成功或预算耗尽。

        `verifier` 是静默失败的最后一道闸：动作没抛异常、甚至 changed=True，
        但结果不满足预期时，仍然判失败。论文中正是验证器把静默失败压到 0。
        """
        # 未显式传 budget 时复用编排器自身的预算——它是**任务级**的，跨步骤
        # 累计。这是刻意的：论文的预算约束是"失败的恢复尝试同样消耗预算"，
        # 若每步重置就形同无预算。开新任务请调 reset()。
        budget = budget or self._budget
        step = 0
        attempt = 0
        # 本轮已证明"帮不上忙"的恢复动作（钩子返回 None），不再重复扣预算
        self._dead_rungs = set()

        ctx: dict[str, Any] = {"action": action, "target": target, "attempt": 0}

        while True:
            step += 1
            attempt += 1
            ctx["attempt"] = attempt
            t0 = time.perf_counter()
            try:
                outcome = await call()
            except BaseException as exc:  # noqa: BLE001
                outcome = StepOutcome.from_exception(exc, hint=action)
            elapsed = (time.perf_counter() - t0) * 1000

            # 静默失败闸门：动作说成功但结果不对，仍然按失败处理
            failure_class = outcome.failure_class
            if outcome.ok and verifier is not None:
                try:
                    # 校验器可以是同步也可以是异步：真实的校验往往要回页面
                    # 再看一眼（"加入购物车之后页面上该出现'已加入'"），
                    # 而那是一次 await。只支持同步的话，最有价值的那类
                    # 校验就写不出来，verifier 参数会长期空转。
                    checked = verifier(outcome.value)
                    if inspect.isawaitable(checked):
                        checked = await checked
                    verified = bool(checked)
                except Exception as exc:  # noqa: BLE001
                    verified = False
                    outcome = StepOutcome(ok=False, error=f"验证器异常: {exc}", raw=outcome.value)
                if not verified:
                    failure_class = F6_CONTRADICTION
                    if not outcome.error:
                        outcome = replace(outcome, ok=False, error="结果未通过验证器")

            if outcome.ok:
                rec = StepRecord(step, action, attempt, True, budget_left=budget.total_remaining,
                                 elapsed_ms=elapsed)
                self._emit(rec)
                return OrchestratorResult(
                    ok=True,
                    value=outcome.value,
                    recovery_used=[r.recovery_action for r in self._records if r.recovery_action],
                    records=list(self._records),
                )

            # 失败：先分类，再选阶梯
            if not failure_class:
                failure_class = classify(None, hint=outcome.error) or F1_TIMEOUT
            ladder = list(RECOVERY_LADDER.get(failure_class, _UNKNOWN_LADDER))
            recovery = self._pick_recovery(ladder, budget)
            if recovery is not None:
                self._history.append((action, target, recovery))
            if self._is_looping():
                failure_class = F7_CONTROL_LOOP
                recovery = ESCALATE

            rec = StepRecord(
                step, action, attempt, False, failure_class, recovery or "",
                budget.total_remaining, elapsed, outcome.error,
            )
            self._emit(rec)

            if recovery is None or recovery == ESCALATE:
                return await self._escalate(
                    ctx, action, failure_class, outcome, budget
                )

            budget.spend(recovery)
            if recovery == RETRY:
                # 一次 RETRY 预算就是"再执行一次"的许可，所以这里必须继续
                await asyncio.sleep(_BACKOFF_POLICY.compute_delay(attempt))
                continue

            # 其余恢复动作交给对应钩子；钩子返回 None 表示它也没辙
            hook = self._hooks.get(recovery)
            retried: StepOutcome | None = None
            if hook is not None:
                try:
                    retried = await hook({**ctx, "failure_class": failure_class,
                                          "outcome": outcome, "recovery": recovery})
                except BaseException as exc:  # noqa: BLE001
                    retried = StepOutcome.from_exception(exc, hint=recovery)
            if retried is not None and retried.ok:
                ok_rec = StepRecord(step, action, attempt, True, failure_class, recovery,
                                    budget.total_remaining)
                self._emit(ok_rec)
                return OrchestratorResult(
                    ok=True,
                    value=retried.value,
                    recovery_used=[r.recovery_action for r in self._records if r.recovery_action],
                    records=list(self._records),
                )
            if retried is None:
                # 钩子明确表示"这条路走不通"（没实现或没有候选目标）。
                # 标记为死路，避免同一级反复扣预算——那会把真正的后路饿死。
                self._dead_rungs.add(recovery)
            if budget.total_remaining <= 0:
                # 预算刚好被这次恢复花光——再执行一次动作毫无意义，直接上报。
                # （少了这个判断，编排器会在预算耗尽后多跑一次动作才上级）
                return await self._escalate(
                    ctx, action, failure_class, retried or outcome, budget
                )
            # 恢复没成功：把结果固定住交给下一轮重新分类并走阶梯下一级。
            # 不重新执行原动作——钩子已经代表这次尝试了。
            call = _const_call(retried or outcome)

    # ── 内部 ────────────────────────────────────────────────────
    def reset(self) -> None:
        """开新任务时重置预算与轨迹。预算是任务级的，不重置会一路 ESCALATE。"""
        self._budget._used.clear()
        self._records.clear()
        self._history.clear()
        self._dead_rungs.clear()

    def _emit(self, rec: StepRecord) -> None:
        self._records.append(rec)
        if self._on_record is not None:
            try:
                self._on_record(rec)
            except Exception:  # noqa: BLE001
                _logger.exception("orchestrator record hook failed")

    def _is_looping(self) -> bool:
        """原地打转判定：同一动作+目标连续用同一种恢复动作到阈值仍未成功。

        按"采取的恢复动作"而不是"故障分类"计数，是因为阶梯本身就允许同一类
        故障换不同动作重试——换动作说明在收敛，重复同一个动作才叫打转。
        （早期版本按故障分类计数，导致 F4 的三级阶梯走到第二级就被误判成
        打转并强制上报，阶梯形同虚设。）
        """
        if len(self._history) < self._loop_threshold:
            return False
        window = self._history[-self._loop_threshold:]
        first = window[0]
        return all(h == first for h in window)

    def _pick_recovery(self, ladder: Sequence[str], budget: Budget) -> str | None:
        """在阶梯上找第一个还有预算、接了实现、且未被证明无效的动作。

        预算耗尽返回 None（由调用方转 ESCALATE），而不是退到最后一级——
        退到最后一级会掩盖"预算已经花光"这个事实。

        **没有接实现的动作直接跳过，不占预算。** 这一条是审计找出来的：
        阶梯表里 F2 是 (FIX_ARGS, REPLAN, ESCALATE)，而浏览器接线只注册了
        refresh / substitute / clear_obstruction 三个钩子——于是 F2 的每一级
        都会先扣一格预算、再发现无事可做。预算是任务级的稀缺资源，被空气烧掉
        之后，同一任务里真正能救的故障（F5 的刷新、F8 的解除遮挡）就没预算了。

        论文说"失败的恢复也消耗预算"，指的是**执行了但没成功**；根本没执行的
        不在此列。
        """
        if budget.total_remaining <= 0:
            return None
        for action in ladder:
            if action == ESCALATE:
                return ESCALATE
            if action in self._dead_rungs:
                continue
            # RETRY 是内联实现的（不走钩子），不能被误判成没接线
            if action != RETRY and self._hooks.get(action) is None:
                continue
            if budget.remaining(action) > 0:
                return action
        return None

    @property
    def unwired_recoveries(self) -> tuple[str, ...]:
        """阶梯表里出现、但这一路接线没接实现的恢复动作。

        这些阶梯看起来在工作，实际每一级都只是烧一格预算。暴露成属性而不是
        等审计时才发现——"名义完成"就该在代码里被看见。
        """
        used = {a for ladder in RECOVERY_LADDER.values() for a in ladder}
        return tuple(
            sorted(a for a in used if a not in (RETRY, ESCALATE) and self._hooks.get(a) is None)
        )

    async def _escalate(
        self,
        ctx: dict[str, Any],
        action: str,
        failure_class: str,
        outcome: StepOutcome,
        budget: Budget,
    ) -> OrchestratorResult:
        hook = self._hooks.get(ESCALATE)
        if hook is not None:
            try:
                await hook({**ctx, "failure_class": failure_class, "outcome": outcome,
                            "recovery": ESCALATE})
            except Exception:  # noqa: BLE001
                _logger.exception("escalate hook failed")
        return OrchestratorResult(
            ok=False,
            error=outcome.error or f"{action} 失败且预算耗尽",
            failure_class=failure_class,
            recovery_used=[r.recovery_action for r in self._records if r.recovery_action],
            records=list(self._records),
            escalated=True,
        )


def _const_call(outcome: StepOutcome) -> Callable[[], Awaitable[StepOutcome]]:
    """把一次已有结果包装成 call 签名，用于把钩子结果交回主循环再分类。"""
    async def _call() -> StepOutcome:
        return outcome
    return _call
