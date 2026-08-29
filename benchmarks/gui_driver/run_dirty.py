"""脏页面跑分（Phase 6）——回答"上真实网站会不会崩"。

口径与 Phase 0 完全一致，一个数都不减：

  **成功率**    verifier 判定真实结果达成（查 localStorage，不查"有没有报错"）
  **静默失败率** 全部步骤都"没报错"，但 verifier 说结果不对
  **谎报数**    负例被报成成功——不可能完成的任务说成做完了

第三个数最关键。只测正例的评测无法区分"真能干"和"永远说自己干成了"，而后者
在用户那里的表现就是 Agent 兴高采烈地汇报"已经加进购物车了"，其实什么都没做。

执行策略同样是**固定策略**：只消费快照 + 按名称匹配，不使用选择器、不查 DOM
结构。BYOK 模式下模型由用户提供，harness 的度量必须把模型变量固定住。
click_near 用的是"阅读顺序上离锚点最近的按钮"——这正是人读紧凑快照时的做法，
与模型所见信息等价。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import functools
import http.server
import json
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import dirtysite
from dirty_tasks import TASKS, DirtyTask
from run_tasks import Policy  # 复用 Phase 0 的策略基类与它的意图级原语

_STEP_TIMEOUT = 30.0
_SCROLL_PAUSE = 0.25


@dataclass
class StepResult:
    index: int
    kind: str
    ok: bool
    detail: str = ""
    elapsed_ms: float = 0.0
    recovery: list[str] = field(default_factory=list)


@dataclass
class DirtyResult:
    task_id: str
    name: str
    trait: str
    steps_ok: bool
    verified: bool
    error: str = ""
    expect_failure: bool = False
    elapsed_ms: float = 0.0
    steps: list[StepResult] = field(default_factory=list)
    recovery_used: list[str] = field(default_factory=list)

    @property
    def silent_failure(self) -> bool:
        return (not self.expect_failure) and self.steps_ok and not self.verified

    @property
    def lied(self) -> bool:
        return self.expect_failure and self.steps_ok


class DirtyPolicy(Policy):
    """在 Phase 0 策略上加两个脏页面必需的原语。

    都是意图级的：一个真人看着页面也会这么做，不需要任何 DOM 知识。
    """

    def _pick_near(
        self, snap: Any, anchor: str, button: str
    ) -> tuple[Any | None, str]:
        """在一帧快照里定位"锚点之后最贴合的那个按钮"。

        抽出来给 click_near 与 scroll_click_near 共用——两边必须逐帧一致，
        否则"找到的标准"和"点到的标准"会在重排页上悄悄分叉。
        """
        from fnixagent.core.tools.browser_healing import _rank_name_match

        ordered = sorted(snap.refs, key=lambda r: (r.y, r.x))
        anchor_idx = -1
        for i, r in enumerate(ordered):
            if anchor and anchor in (r.name or ""):
                anchor_idx = i
                break
        if anchor_idx < 0:
            return None, f"快照里找不到「{anchor}」"

        # 锚点之后的候选要**先排档位再取第一个**。照 DOM 顺序取第一个包含
        # 匹配的话，"加入购物车"会被排版在前面的"加入购物车并结算"截胡——
        # 那是真实电商页面上的常见排版，也是会真扣款的一类误点。
        candidates = [
            (_rank_name_match(r.name or "", button), -len(r.name or ""), r)
            for r in ordered[anchor_idx + 1:]
            if _rank_name_match(r.name or "", button) > 0 and not r.disabled
        ]
        if not candidates:
            return None, f"「{anchor}」之后找不到「{button}」"
        candidates.sort(key=lambda t: (-t[0], -t[1]))
        return candidates[0][2], ""

    async def click_near(
        self, anchor: str, button: str, retries: int = 3
    ) -> tuple[bool, str, list[str]]:
        """点"锚点旁边那个按钮"——读快照时的自然做法。

        重排型页面会在"取完快照"与"执行点击"之间把 DOM 重建，ref 作废是页面
        的固有性质，不是策略选错了目标。人在这种情况下的动作是"重新看一眼再
        点"，策略也这么干——重试有界（retries），每次都基于全新快照按锚点
        重新定位，绝不拿旧 ref 硬点（那正是 F5 明确禁止的）。

        两条实测出来的纪律：

        - **重试敢开 3 次，前提是编排层不猜**。retries 一度被压回 1 当绕过：
          旧接线下失败触发的 F5 会走到 substitute，在列表页的同名按钮里轮换，
          点到别的商品还要报成功（静默失败，2026-08-30 实测复现）。编排层把
          F5 阶梯改成不含 substitute、refresh 拒绝歧义重映射之后，失败会如实
          升级，重试才重新成为正当的恢复手段。
        - **锚点不在视口快照里时退回全页快照再找**。失败点击的滚动与页面重建
          都可能把目标暂时挪出视口，"不在视口"不等于"不存在"——重新定位这一
          步不能被滚动位置摆布。
        """
        from fnixagent.core.tools.driver_errors import F1_TIMEOUT, F5_STALE_CONTEXT

        last_err = "未开始"
        recs: list[str] = []
        for attempt in range(max(1, retries)):
            snap = await self.session.snapshot_ref()
            target, err = self._pick_near(snap, anchor, button)
            if target is None:
                full = await self.session.snapshot_ref(viewport_only=False, limit=400)
                target, err_full = self._pick_near(full, anchor, button)
                if target is None:
                    last_err = f"{err}（全页快照也未找到：{err_full}）"
                    await asyncio.sleep(_SCROLL_PAUSE)
                    continue
            result = await self.healer.click(ref=target.ref)
            recs.extend(result.recovery_used)
            if result.ok:
                return True, result.error, recs
            last_err = result.error
            # 确定性失败不值得重试：够不着 / 结果矛盾 / 原地打转，不会因"再看
            # 一眼"而变好，重试只是烧步骤超时；F5（失去踪迹）与超时值得再来
            # 一轮——全新快照是一次真正意义上的新机会。
            if result.failure_class not in ("", F1_TIMEOUT, F5_STALE_CONTEXT):
                break
            await asyncio.sleep(_SCROLL_PAUSE)
        return False, last_err, recs

    async def scroll_click_near(
        self, anchor: str, button: str, max_scrolls: int
    ) -> tuple[bool, str, list[str]]:
        """扫掠到目标后在**同一帧快照**里完成点击——消灭两步之间的 TOCTOU。

        scroll_until + click_near 分两步走时，中间隔着一次动作后等待；在每秒
        都在重排的叠加页上，这段时间足够目标被搬出视口（实测：1.5s 重排周期
        下命中率不到一半）。合并成一步：每帧快照先看锚点与按钮是否同时在场，
        在就直接点（点失利也走 healer 自愈），不在才继续扫掠。扫掠纪律与
        scroll_until 相同：贴底/贴顶即掉头。
        """
        direction = "down"
        last_err = f"滚动 {max_scrolls} 次（含往返扫掠）仍未出现「{anchor}」"
        recs: list[str] = []
        for i in range(max_scrolls):
            snap = await self.session.snapshot_ref()
            target, err = self._pick_near(snap, anchor, button)
            if target is not None:
                result = await self.healer.click(ref=target.ref)
                recs.extend(result.recovery_used)
                if result.ok:
                    return True, f"滚动 {i} 次后找到并点击成功", recs
                last_err = result.error
                # 点击失败的帧里目标明明在场——ref 多半已被重排作废，继续扫
            else:
                last_err = err
            await self.session.scroll(direction, 900)
            await asyncio.sleep(_SCROLL_PAUSE)
            try:
                pos = await self.session.scroll_offsets()
            except Exception:  # noqa: BLE001
                continue
            if direction == "down" and pos.get("at_bottom"):
                direction = "up"
            elif direction == "up" and pos.get("at_top"):
                direction = "down"
        return False, last_err, recs

    async def scroll_until(self, text: str, max_scrolls: int) -> tuple[bool, str, list[str]]:
        """往返扫掠，直到文本出现在快照里。

        懒加载和无限滚动没有滚动这个动作就无解——内容根本还没被创建出来。
        但"一路只朝下"在重排型页面是死路：目标可能已经渲染过，却被重排搬
        回了视口上方，继续朝下滚永远不会再见到它。贴着底/顶就掉头再扫一遍，
        扫满预算还没找到才算真不在——这与人在长页上找东西的姿势一致。

        "贴底没有"问 scroll_offsets 的布局事实，不靠 DOM 变没变来猜。
        """
        direction = "down"
        for i in range(max_scrolls):
            snap = await self.session.snapshot_ref()
            if any(text in (r.name or "") for r in snap.refs):
                return True, f"滚动 {i} 次后找到", []
            if any(text in (r.value or "") for r in snap.refs):
                return True, f"滚动 {i} 次后找到", []
            # 刻意不回退到"正文里有没有"：懒加载元素会因为 rootMargin 提前
            # 渲染，正文里有 ≠ 眼睛看得到。以正文为准会让下一步的点击去点一个
            # 根本不在视口里的目标，失败原因还很难查。
            await self.session.scroll(direction, 900)
            await asyncio.sleep(_SCROLL_PAUSE)
            try:
                pos = await self.session.scroll_offsets()
            except Exception:  # noqa: BLE001
                continue  # 位置读不到不换向，维持原方向把预算花完
            if direction == "down" and pos.get("at_bottom"):
                direction = "up"
            elif direction == "up" and pos.get("at_top"):
                direction = "down"
        return False, f"滚动 {max_scrolls} 次（含往返扫掠）仍未出现「{text}」", []

    async def upload_to(self, needle: str, filename: str) -> tuple[bool, str, list[str]]:
        """把本地文件交给名称含 needle 的控件。

        不判断控件类型是不是 file input——那是被测对象该自己说实话的地
        方：对普通按钮执行 set_input_files，驱动层必须报错，而不是没动作
        却被当成功。fixtures 目录内的文件名是刻意的：测试数据和页面一起
        进版本库，基线才真的可复现。
        """
        from fnixagent.core.tools.browser_healing import select_by_name

        snap = await self.session.snapshot_ref()
        pool = [el for el in select_by_name(snap.refs, needle) if not el.disabled]
        if not pool:
            return False, f"快照里找不到「{needle}」", []
        path = (Path(__file__).parent / "fixtures" / filename).resolve()
        if not path.is_file():
            return False, f"fixture 不存在: {path}", []
        try:
            state = await self.session.upload_ref(pool[0].ref, str(path))
        except Exception as e:  # noqa: BLE001
            return False, f"上传异常: {e}", []
        return (not state.error), (state.error or ""), []

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def serve_site() -> http.server.ThreadingHTTPServer:
    port = _free_port()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(dirtysite.SITE_DIR)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    httpd.port = port  # type: ignore[attr-defined]
    return httpd


async def run_task(session: Any, base: str, task: DirtyTask) -> DirtyResult:
    policy = DirtyPolicy(session)
    steps: list[StepResult] = []
    recovery: list[str] = []
    steps_ok = True
    error = ""

    # 任务之间必须清空购物车，否则基线不可信
    await session.navigate(f"{base}/{task.page}")
    try:
        await session._page.evaluate("() => { localStorage.clear(); }")
        await session.navigate(f"{base}/{task.page}")
    except Exception as e:  # noqa: BLE001
        return DirtyResult(task.id, task.name, task.trait, False, False, f"起始导航失败: {e}")

    t0 = time.perf_counter()
    for i, step in enumerate(task.steps):
        kind = step[0]
        ts = time.perf_counter()
        try:
            if kind == "goto":
                await session.navigate(f"{base}/{step[1]}")
                ok, detail, rec = True, "", []
            elif kind == "click":
                ok, detail, rec = await asyncio.wait_for(
                    policy.click(step[1], step[2] if len(step) > 2 else ""),
                    timeout=_STEP_TIMEOUT,
                )
            elif kind == "click_near":
                ok, detail, rec = await asyncio.wait_for(
                    policy.click_near(step[1], step[2]), timeout=_STEP_TIMEOUT
                )
            elif kind == "scroll_until":
                ok, detail, rec = await policy.scroll_until(step[1], step[2])
            elif kind == "scroll_click_near":
                ok, detail, rec = await asyncio.wait_for(
                    policy.scroll_click_near(step[1], step[2], step[3]),
                    timeout=_STEP_TIMEOUT,
                )
            elif kind == "upload":
                ok, detail, rec = await asyncio.wait_for(
                    policy.upload_to(step[1], step[2]), timeout=_STEP_TIMEOUT
                )
            elif kind == "wait_text":
                state = await session.wait_for(text=step[1], timeout_ms=6000)
                ok, detail, rec = (not state.error), (state.error or ""), []
            else:
                ok, detail, rec = False, f"未知步骤类型 {kind}", []
        except asyncio.TimeoutError:
            ok, detail, rec = False, f"步骤超时（{_STEP_TIMEOUT}s）", []
        except Exception as e:  # noqa: BLE001
            ok, detail, rec = False, f"步骤异常: {e}", []

        recovery += rec
        elapsed = (time.perf_counter() - ts) * 1000
        steps.append(StepResult(i, kind, ok, detail, round(elapsed, 1), list(rec)))
        if not ok:
            steps_ok = False
            error = detail
            break

    verified = False
    if task.expect_failure:
        verified = not steps_ok
        if steps_ok:
            error = "不可能完成的任务被报成了成功（谎报）"
    elif steps_ok:
        try:
            verified = bool(await session._page.evaluate(task.verify_js))
        except Exception as e:  # noqa: BLE001
            verified = False
            error = f"校验异常: {e}"

    return DirtyResult(
        task_id=task.id,
        name=task.name,
        trait=task.trait,
        steps_ok=steps_ok,
        verified=verified,
        error=error,
        expect_failure=task.expect_failure,
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        steps=steps,
        recovery_used=recovery,
    )


async def main(only: str | None = None) -> dict:
    changed = dirtysite.ensure_site()
    if changed:
        print(f"[site] 生成/更新 {len(changed)} 个页面: {', '.join(changed)}")
    httpd = serve_site()
    base = f"http://127.0.0.1:{httpd.port}"
    print(f"[server] 脏页面站点 {base}\n")

    from fnixagent.core.tools.browser import BrowserSession

    session = BrowserSession()
    results: list[DirtyResult] = []
    try:
        for task in TASKS:
            if only and task.id != only:
                continue
            r = await run_task(session, base, task)
            results.append(r)
            flag = ("谎报" if r.lied else "OK  " if r.verified
                    else "静默" if r.silent_failure else "FAIL")
            mark = "负例" if r.expect_failure else "    "
            print(f"  {flag} {mark} {r.task_id} {r.name[:26]:<28} "
                  f"{r.elapsed_ms:>7.0f}ms {r.error[:44]}")
        await session.close()
    finally:
        httpd.shutdown()

    pos = [r for r in results if not r.expect_failure]
    neg = [r for r in results if r.expect_failure]
    silent = sum(1 for r in results if r.silent_failure)
    lied = sum(1 for r in results if r.lied)

    by_trait: dict[str, dict[str, int]] = {}
    for r in results:
        slot = by_trait.setdefault(r.trait, {"total": 0, "verified": 0, "lied": 0})
        slot["total"] += 1
        slot["verified"] += 1 if r.verified else 0
        slot["lied"] += 1 if r.lied else 0

    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "positive_tasks": len(pos),
        "negative_tasks": len(neg),
        "positive_success_rate_pct": (
            round(sum(1 for r in pos if r.verified) / len(pos) * 100, 1) if pos else 0.0
        ),
        "correct_reject_rate_pct": (
            round(sum(1 for r in neg if r.verified) / len(neg) * 100, 1) if neg else 0.0
        ),
        "silent_failures": silent,
        "silent_failure_rate_pct": round(silent / len(pos) * 100, 1) if pos else 0.0,
        "lied": lied,
        "avg_task_ms": round(sum(r.elapsed_ms for r in results) / len(results), 1) if results else 0,
        "recovery_used_total": sum(len(r.recovery_used) for r in results),
        "by_trait": by_trait,
        "tasks": [
            {
                "id": r.task_id,
                "name": r.name,
                "trait": r.trait,
                "steps_ok": r.steps_ok,
                "verified": r.verified,
                "silent_failure": r.silent_failure,
                "expect_failure": r.expect_failure,
                "error": r.error,
                "elapsed_ms": r.elapsed_ms,
                "recovery": r.recovery_used,
            }
            for r in results
        ],
    }
    out_path = Path(__file__).parent / "dirty_baseline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n── 脏页面基线（真实网站泛化能力的可控代理指标）──")
    print(f"  正例成功率:   {out['positive_success_rate_pct']}%  "
          f"({sum(1 for r in pos if r.verified)}/{len(pos)})")
    print(f"  静默失败率:   {out['silent_failure_rate_pct']}%  ({silent}/{len(pos)})")
    print(f"  负例正确拒绝: {out['correct_reject_rate_pct']}%  "
          f"({sum(1 for r in neg if r.verified)}/{len(neg)})")
    print(f"  谎报成功:     {lied} 条" + ("  ← 严重：不可能的任务被说成做完了" if lied else ""))
    print(f"  平均任务耗时: {out['avg_task_ms']}ms")
    print(f"  自愈触发次数: {out['recovery_used_total']}")
    print("\n  按性质拆分:")
    for trait, s in by_trait.items():
        print(f"    {trait:<12} {s['verified']}/{s['total']} 通过"
              + (f"  谎报 {s['lied']}" if s["lied"] else ""))
    print(f"\n已写入 {out_path}")
    return out


if __name__ == "__main__":
    import sys

    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
