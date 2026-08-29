"""多步任务跑分与静默失败度量（GUI_DRIVER_ROADMAP.md Phase 0 遗留指标）。

跑分输出两个数字，缺一不可：

  **任务成功率**   verifier 判定真实结果达成
  **静默失败率**   全部步骤都"没报错"，但 verifier 说结果不对

第二个才是要命的。只有第一个数字的话，一个把失败全吞掉、永远报成功的驱动
能拿满分——现实中它表现为"Agent 兴高采烈地说做完了，其实什么都没做"。

论文（arXiv 2606.01416）里非验证方法 13.2-17.6% 的返回属于"看似合理但错误"，
正是这个口径。

关于执行策略：这里用**固定策略（scripted policy）**代替模型来消费快照。
理由是——BYOK 模式下模型由用户提供，harness 的度量必须把模型变量固定住，
否则测出来的是模型能力而不是 harness 能力。策略只能看到快照和名称匹配，
与模型看到的信息等价。
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

from minisite import SITE_DIR, ensure_site
from tasks import TASKS, Task

# 单步超时（秒）——策略本身不应慢，超时说明 harness 卡住了
_STEP_TIMEOUT = 25.0


@dataclass
class StepResult:
    index: int
    kind: str
    ok: bool
    detail: str = ""
    elapsed_ms: float = 0.0
    recovery: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    task_id: str
    name: str
    steps_ok: bool          # 所有步骤"没报错"（驱动自报）
    verified: bool          # verifier 判定真实结果达成（负例：是否正确拒绝）
    error: str = ""
    expect_failure: bool = False
    elapsed_ms: float = 0.0
    steps: list[StepResult] = field(default_factory=list)
    recovery_used: list[str] = field(default_factory=list)

    @property
    def silent_failure(self) -> bool:
        """自报成功但结果不对——静默失败的定义。

        负例不参与：它们本来就该失败，"自报成功"另有 `lied` 口径统计。
        """
        if self.expect_failure:
            return False
        return self.steps_ok and not self.verified

    @property
    def lied(self) -> bool:
        """负例上谎报成功——把不可能完成的任务说成做完了。"""
        return self.expect_failure and self.steps_ok


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def serve_site() -> tuple[http.server.ThreadingHTTPServer, int]:
    port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


class Policy:
    """固定策略：只消费快照与名称匹配，不使用任何选择器/硬编码 ref。

    故意不做得更聪明——策略越聪明，越容易掩盖 harness 的缺陷。它的职责是
    "像模型一样读快照并下达意图"，其余全交给 harness。
    """

    def __init__(self, session: Any) -> None:
        self.session = session
        self._healer = None

    @property
    def healer(self) -> Any:
        if self._healer is None:
            from fnixagent.core.tools.browser_healing import BrowserHealer

            self._healer = BrowserHealer(self.session)
        return self._healer

    async def find(self, needle: str, role: str = "") -> Any:
        """在快照里按名称找元素。找不到返回 None（由调用方判失败）。

        匹配口径与生产自愈层（`browser_healing.select_by_name`）保持同一套：
        完全相等优先，其次包含，同档取名字更短的。跑分策略如果比生产路径
        更宽松或更严格，量到的就不是同一个产品——那一头改了口径，这一头
        的数字却纹丝不动，是最容易骗过自己的地方。
        """
        from fnixagent.core.tools.browser_healing import select_by_name

        snap = await self.session.snapshot_ref()
        for r in select_by_name(snap.refs, needle):
            if role and r.role != role:
                continue
            if r.disabled:
                continue
            return r
        return None

    async def click(self, needle: str, role: str = "") -> tuple[bool, str, list[str]]:
        el = await self.find(needle, role)
        if el is None:
            return False, f"快照里找不到名称含「{needle}」" + (f"的 {role}" if role else ""), []
        result = await self.healer.click(ref=el.ref)
        return result.ok, result.error, list(result.recovery_used)

    async def type_into(self, hint: str, text: str) -> tuple[bool, str, list[str]]:
        el = await self.find(hint)
        if el is None:
            return False, f"快照里找不到输入框「{hint}」", []
        state = await self.session.type_ref(el.ref, text)
        return (not state.error), (state.error or ""), []

    async def select(self, hint: str, value: str) -> tuple[bool, str, list[str]]:
        el = await self.find(hint)
        if el is None:
            return False, f"快照里找不到下拉框「{hint}」", []
        from fnixagent.core.tools.browser_refs import locator_for

        try:
            await self.session._page.select_option(locator_for(el.ref), value, timeout=5000)
        except Exception as e:  # noqa: BLE001
            return False, f"选择失败: {e}", []
        return True, "", []


async def _reset_state(session: Any, base: str) -> None:
    """清空登录态与购物车——任务之间必须隔离，否则基线不可信。"""
    await session.navigate(f"{base}/index.html")
    try:
        await session._page.evaluate("() => { localStorage.clear(); }")
    except Exception:  # noqa: BLE001
        pass


async def run_task(session: Any, base: str, task: Task) -> TaskResult:
    await _reset_state(session, base)
    policy = Policy(session)
    steps: list[StepResult] = []
    recovery: list[str] = []
    steps_ok = True
    error = ""

    t0 = time.perf_counter()
    try:
        await session.navigate(f"{base}/{task.start}")
    except Exception as e:  # noqa: BLE001
        return TaskResult(task.id, task.name, False, False, f"起始导航失败: {e}")

    for i, step in enumerate(task.steps):
        kind = step[0]
        ts = time.perf_counter()
        try:
            if kind == "goto":
                await session.navigate(f"{base}/{step[1]}")
                ok, detail = True, ""
            elif kind == "click":
                role = step[2] if len(step) > 2 else ""
                ok, detail, rec = await asyncio.wait_for(
                    policy.click(step[1], role), timeout=_STEP_TIMEOUT
                )
                recovery += rec
            elif kind == "type":
                ok, detail, rec = await asyncio.wait_for(
                    policy.type_into(step[1], step[2]), timeout=_STEP_TIMEOUT
                )
                recovery += rec
            elif kind == "select":
                ok, detail, rec = await asyncio.wait_for(
                    policy.select(step[1], step[2]), timeout=_STEP_TIMEOUT
                )
                recovery += rec
            elif kind == "wait_text":
                state = await session.wait_for(text=step[1], timeout_ms=6000)
                ok, detail = (not state.error), (state.error or "")
            elif kind == "back":
                state = await session.history("back")
                ok, detail = (not state.error), (state.error or "")
            else:
                ok, detail = False, f"未知步骤类型 {kind}"
        except asyncio.TimeoutError:
            ok, detail = False, f"步骤超时（{_STEP_TIMEOUT}s）"
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"步骤异常: {e}"

        elapsed = (time.perf_counter() - ts) * 1000
        steps.append(StepResult(i, kind, ok, detail, round(elapsed, 1)))
        if not ok:
            steps_ok = False
            error = detail
            break

    # 结果校验：查真实结果，不查"动作有没有报错"
    verified = False
    if task.expect_failure:
        # 负例的判定口径相反：**必须承认失败**。若它把不可能的任务也报成成功，
        # 说明编排层在编造结果——比失败危险得多。
        verified = not steps_ok
        if steps_ok:
            error = "不可能完成的任务被报成了成功（谎报）"
    elif steps_ok:
        try:
            verified = bool(await session._page.evaluate(task.verify_js))
        except Exception as e:  # noqa: BLE001
            verified = False
            error = f"校验异常: {e}"

    return TaskResult(
        task_id=task.id,
        name=task.name,
        steps_ok=steps_ok,
        verified=verified,
        error=error,
        expect_failure=task.expect_failure,
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 1),
        steps=steps,
        recovery_used=recovery,
    )


async def main(only: str | None = None) -> dict:
    changed = ensure_site()
    if changed:
        print(f"[site] 生成/更新 {len(changed)} 个页面: {', '.join(changed)}")
    httpd, port = serve_site()
    base = f"http://127.0.0.1:{port}"
    print(f"[server] 站点 {base}\n")

    from fnixagent.core.tools.browser import BrowserSession

    session = BrowserSession()
    results: list[TaskResult] = []
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
                  f"{r.elapsed_ms:>7.0f}ms {r.error[:40]}")
        await session.close()
    finally:
        httpd.shutdown()

    n = len(results)
    pos = [r for r in results if not r.expect_failure]
    neg = [r for r in results if r.expect_failure]
    verified = sum(1 for r in results if r.verified)
    silent = sum(1 for r in results if r.silent_failure)
    lied = sum(1 for r in results if r.lied)
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": n,
        "positive_tasks": len(pos),
        "negative_tasks": len(neg),
        "verified": verified,
        "success_rate_pct": round(verified / n * 100, 1) if n else 0.0,
        "positive_success_rate_pct": (
            round(sum(1 for r in pos if r.verified) / len(pos) * 100, 1) if pos else 0.0
        ),
        "correct_reject_rate_pct": (
            round(sum(1 for r in neg if r.verified) / len(neg) * 100, 1) if neg else 0.0
        ),
        "silent_failures": silent,
        "silent_failure_rate_pct": round(silent / len(pos) * 100, 1) if pos else 0.0,
        "lied": lied,
        "avg_task_ms": round(sum(r.elapsed_ms for r in results) / n, 1) if n else 0.0,
        "recovery_used_total": sum(len(r.recovery_used) for r in results),
        "tasks": [
            {
                "id": r.task_id,
                "name": r.name,
                "steps_ok": r.steps_ok,
                "verified": r.verified,
                "silent_failure": r.silent_failure,
                "error": r.error,
                "elapsed_ms": r.elapsed_ms,
                "recovery": r.recovery_used,
            }
            for r in results
        ],
    }
    out_path = Path(__file__).parent / "task_baseline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n── 任务级基线 ──")
    print(f"  正例成功率:   {out['positive_success_rate_pct']}%  "
          f"({sum(1 for r in pos if r.verified)}/{len(pos)})")
    print(f"  静默失败率:   {out['silent_failure_rate_pct']}%  ({silent}/{len(pos)})")
    print(f"  负例正确拒绝: {out['correct_reject_rate_pct']}%  "
          f"({sum(1 for r in neg if r.verified)}/{len(neg)})")
    print(f"  谎报成功:     {lied} 条" + ("  ← 严重：不可能的任务被说成做完了" if lied else ""))
    print(f"  平均任务耗时: {out['avg_task_ms']}ms")
    print(f"  自愈触发次数: {out['recovery_used_total']}")
    print(f"\n已写入 {out_path}")
    return out


if __name__ == "__main__":
    import sys

    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
