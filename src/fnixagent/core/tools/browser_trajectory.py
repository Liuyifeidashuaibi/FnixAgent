"""录制 / 重放（GUI_DRIVER_ROADMAP.md Phase 5）。

用户演示一遍 → 录下动作轨迹（ref + 参数 + 状态断言）→ agent 重放。

三个关键设计，都是前几期踩过的坑里长出来的：

1. **按名字解析 ref，不按编号**
   录制时同时记下 ref 编号（如 @e3）**和**元素名。重放时先拿名字在新快照里
   找，找不到才退回编号。原因：ref 编号是按 DOM 遍历顺序生成的，页面多渲染一
   个元素编号就整体后移——照编号重放，等于把录制瞬间的 DOM 结构当成永久契约，
   那正是"上下文过期（F5）"的典型来源。

2. **每步都带状态断言，断言不符必须停下**
   录制时记下动作**之后**的 URL 与"页面是否真的变了"。重放时逐步比对。
   这里最危险的写法是"重放跑完就算成功"——那正是静默失败（动作报成功、结果
   是错的）。路线文档对静默失败的容忍是 0%，所以断言不符一律停下报失败，
   绝不静默继续。

3. **输入的字面值默认不落盘**
   type 动作录的正是用户敲进去的东西——演示一次登录，那就是密码。默认只记
   "这一步需要输入"而不记内容，重放时由调用方当次传入（可按步骤序号或元素名
   给）。确实要连内容一起录（比如录一段搜索关键词），显式开 capture_values。

轨迹落盘为 v1 JSON，字段与审计流（orchestrator.StepRecord）对齐，一份数据两用。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_logger = logging.getLogger(__name__)

TRAJECTORY_VERSION = 1

# 录制 / 重放都支持的动作（与 browser_act 的 action 集合对齐）
RECORDABLE_ACTIONS = (
    "goto", "click", "type", "scroll",
    "back", "forward", "refresh",
)


def _norm_url(url: str) -> str:
    """URL 归一化——只用于断言比对。

    抹掉 fragment 与末尾斜杠：#锚点 和 /path 与 /path/ 在"页面是不是同一个"
    这个语义上没有区别，但字符串比对会把它们判成不同，导致大量假警报。
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))
    except Exception:  # noqa: BLE001
        return url


@dataclass
class TrajectoryStep:
    """轨迹中的一步。

    assert_url / assert_changed 是**动作之后**的状态，重放时用来判断轨迹
    是否已经和页面对不上了。没有这两个字段，重放就只能"跑完算成功"。
    """

    action: str
    ref: str = ""            # 录制时的编号（重放时仅作回退）
    name: str = ""           # 元素名（重放时优先按它解析）
    role: str = ""
    value: str | None = None  # type 的输入值；None = 需要重放时提供
    submit: bool = False
    url: str = ""            # 动作**之前**的页面 URL
    assert_url: str = ""     # 动作**之后**的 URL（断言用）
    assert_changed: bool = False
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_value(self) -> bool:
        """这一步需要输入，但字面值没有落盘——重放时必须当次提供。"""
        return self.action == "type" and self.value is None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"action": self.action}
        for k in ("ref", "name", "role", "submit", "url", "assert_url", "assert_changed"):
            v = getattr(self, k)
            if v:
                d[k] = v
        if self.value is not None:
            d["value"] = self.value
        if self.params:
            d["params"] = self.params
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrajectoryStep":
        return cls(
            action=str(d.get("action", "")),
            ref=str(d.get("ref", "") or ""),
            name=str(d.get("name", "") or ""),
            role=str(d.get("role", "") or ""),
            value=d.get("value"),  # 缺省 None = 需重放时提供
            submit=bool(d.get("submit", False)),
            url=str(d.get("url", "") or ""),
            assert_url=str(d.get("assert_url", "") or ""),
            assert_changed=bool(d.get("assert_changed", False)),
            params=dict(d.get("params") or {}),
        )


@dataclass
class Trajectory:
    """一条可落盘的轨迹。"""

    name: str = ""
    start_url: str = ""
    steps: list[TrajectoryStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    version: int = TRAJECTORY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "start_url": self.start_url,
            "created_at": self.created_at,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Trajectory":
        ver = int(d.get("version", 0))
        if ver != TRAJECTORY_VERSION:
            raise ValueError(f"轨迹版本不兼容: {ver}（当前支持 {TRAJECTORY_VERSION}）")
        return cls(
            name=str(d.get("name", "") or ""),
            start_url=str(d.get("start_url", "") or ""),
            steps=[TrajectoryStep.from_dict(s) for s in d.get("steps", [])],
            created_at=float(d.get("created_at", time.time())),
            version=ver,
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Trajectory":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def __len__(self) -> int:
        return len(self.steps)


class TrajectoryRecorder:
    """把一串动作连同"每步之后的页面状态"录下来。

    用法（与 browser_act 的 action 集合一致）：

        rec = TrajectoryRecorder(session, name="登录演示")
        await rec.record("goto", url="https://x.test/login")
        await rec.record("type", ref="@e2", text="user@example.com")
        await rec.record("click", ref="@e5")
        rec.trajectory.save("login.traj.json")
    """

    def __init__(
        self,
        session: Any,
        name: str = "",
        *,
        capture_values: bool = False,
    ) -> None:
        self._session = session
        self._capture_values = capture_values
        self._traj = Trajectory(name=name or f"traj-{int(time.time())}")

    @property
    def trajectory(self) -> Trajectory:
        return self._traj

    async def record(self, action: str, **params: Any) -> Any:
        """执行一步并录入轨迹。返回驱动层的状态对象（BrowserState）。"""
        if action not in RECORDABLE_ACTIONS:
            raise ValueError(
                f"不可录制的 action: {action!r}；可选: {', '.join(RECORDABLE_ACTIONS)}"
            )

        before = await self._current_url()
        # click/type 需要元素名——重放时靠它重新定位，编号会漂移
        name, role = "", ""
        ref = str(params.get("ref") or "").lstrip("@")
        if ref and action in ("click", "type"):
            name, role = await self._describe(ref)

        state = await self._execute(action, params)

        step = TrajectoryStep(
            action=action,
            ref=ref,
            name=name,
            role=role,
            url=before,
            assert_url=_norm_url(getattr(state, "url", "") or ""),
            assert_changed=bool(
                getattr(state, "changed", False) or getattr(state, "url_changed", False)
            ),
        )
        if action == "type":
            # 字面值默认不落盘：演示登录时这里就是密码
            step.value = str(params.get("text", "")) if self._capture_values else None
            step.submit = bool(params.get("submit", False))
        if action == "scroll":
            step.params = {
                "direction": str(params.get("direction", "down")),
                "amount": int(params.get("amount", 480)),
            }
        if action == "goto":
            step.params = {"url": str(params.get("url", ""))}
            if not self._traj.start_url:
                self._traj.start_url = str(params.get("url", ""))

        self._traj.steps.append(step)
        return state

    # ── 内部 ────────────────────────────────────────────────────
    async def _current_url(self) -> str:
        try:
            snap = await self._session.snapshot_ref()
            return _norm_url(getattr(snap, "url", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    async def _describe(self, ref: str) -> tuple[str, str]:
        """ref → (元素名, 角色)。拿不到就算了，重放时退回按编号。"""
        try:
            snap = await self._session.snapshot_ref()
            el = snap.get(ref)
            if el is not None:
                return str(getattr(el, "name", "") or ""), str(getattr(el, "role", "") or "")
        except Exception:  # noqa: BLE001
            pass
        return "", ""

    async def _execute(self, action: str, params: dict[str, Any]) -> Any:
        s = self._session
        if action == "goto":
            return await s.navigate(str(params.get("url", "")))
        if action == "click":
            ref = str(params.get("ref") or "").lstrip("@")
            if ref:
                return await s.click_ref(ref)
            return await s.click_text(str(params.get("text", "")))
        if action == "type":
            ref = str(params.get("ref") or "").lstrip("@")
            text = str(params.get("text", ""))
            submit = bool(params.get("submit", False))
            if ref:
                return await s.type_ref(ref, text, submit)
            return await s.type_into(text, str(params.get("into", "")), submit)
        if action == "scroll":
            return await s.scroll(
                str(params.get("direction", "down")), int(params.get("amount", 480))
            )
        return await s.history(action)  # back / forward / refresh


@dataclass
class ReplayResult:
    ok: bool
    steps_ok: int = 0
    total: int = 0
    failed_step: int | None = None
    error: str = ""
    # 断言不符的明细：静默失败就是从这里暴露的
    assert_failures: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class TrajectoryReplayer:
    """重放一条轨迹。

    每一步都做两件事：按**名字**重新定位元素（编号会漂移），以及比对动作之后
    的页面状态与录制时是否一致。任何一步断言不符就停下——重放的价值不在"跑完"，
    在于"跑完且每一步都和演示时一样"。
    """

    def __init__(
        self,
        session: Any,
        *,
        values: dict[Any, str] | None = None,
        healer: Any | None = None,
    ) -> None:
        self._session = session
        self._values = dict(values or {})
        self._healer = healer

    async def replay(self, traj: Trajectory) -> ReplayResult:
        total = len(traj.steps)
        result = ReplayResult(ok=True, total=total)

        for i, step in enumerate(traj.steps):
            try:
                state = await self._execute_step(i, step)
            except Exception as exc:  # noqa: BLE001
                result.ok = False
                result.failed_step = i
                result.error = f"第 {i + 1} 步（{step.action}）执行异常: {exc}"
                return result

            err = getattr(state, "error", None)
            if err:
                result.ok = False
                result.failed_step = i
                result.error = f"第 {i + 1} 步（{step.action}）失败: {err}"
                return result

            divergence = self._check(i, step, state)
            if divergence is not None and divergence["fatal"]:
                result.ok = False
                result.failed_step = i
                result.error = divergence["detail"]
                result.assert_failures.append(divergence)
                return result
            if divergence is not None:
                result.warnings.append(divergence["detail"])
                result.assert_failures.append(divergence)

            result.steps_ok += 1

        return result

    # ── 内部 ────────────────────────────────────────────────────
    async def _resolve_ref(self, step: TrajectoryStep) -> str:
        """按名字在新快照里找回元素编号；找不到再退回录制时的编号。"""
        if not step.ref and not step.name:
            return ""
        try:
            snap = await self._session.snapshot_ref()
        except Exception:  # noqa: BLE001
            return step.ref

        if step.name:
            cands = [r for r in snap.refs if (r.name or "") == step.name]
            if len(cands) == 1:
                return cands[0].ref
            if len(cands) > 1:
                # 同名多个：用角色再筛一次，仍不唯一就取第一个（页面本来就有
                # 同名元素，录制时也是这么选的）
                same_role = [c for c in cands if (c.role or "") == step.role]
                return (same_role or cands)[0].ref
            # 名字一个都没匹配上：DOM 变了，退回录制编号赌一把
            _logger.info("重放：元素名 %r 已不存在，退回录制编号 @%s", step.name, step.ref)
        return step.ref

    def _value_for(self, i: int, step: TrajectoryStep) -> str:
        """type 步的输入值：优先用调用方当次提供的，其次录制时留下的字面值。"""
        if step.value is not None:
            return step.value
        for key in (i, str(i), step.name, f"{step.role}:{step.name}"):
            if key in self._values:
                return str(self._values[key])
        raise ValueError(
            f"第 {i + 1} 步需要输入（目标: {step.name or step.ref or '?'}），"
            "但录制时未保存字面值（默认不落盘密码等敏感输入）。"
            "请在 replay 时通过 values 提供，例如 values={{{}}}"
            .format(i if i in self._values else repr(i))
        )

    async def _execute_step(self, i: int, step: TrajectoryStep) -> Any:
        s = self._session
        if step.action == "goto":
            return await s.navigate(str(step.params.get("url", "")))
        if step.action == "click":
            ref = await self._resolve_ref(step)
            if not ref:
                raise ValueError("click 步缺少可解析的目标（既无 name 也无 ref）")
            if self._healer is not None:
                # 走自愈层：点空了会自动换同名候选，而不是把失败吞掉
                res = await self._healer.click(ref=ref)
                if not res.ok:
                    # OrchestratorResult.value 在失败时可能是 None；直接返回它
                    # 会让下面的断言把失败误当成"没有更多状态可比对"。
                    # 轨迹重放的契约是失败必须显式停下，不能静默继续。
                    raise RuntimeError(res.error or "自愈层未能完成 click")
                return res.value
            return await s.click_ref(ref)
        if step.action == "type":
            ref = await self._resolve_ref(step)
            return await s.type_ref(ref, self._value_for(i, step), step.submit)
        if step.action == "scroll":
            return await s.scroll(
                str(step.params.get("direction", "down")), int(step.params.get("amount", 480))
            )
        return await s.history(step.action)  # back / forward / refresh

    @staticmethod
    def _check(i: int, step: TrajectoryStep, state: Any) -> dict[str, Any] | None:
        """比对动作后的页面状态与录制时是否一致。

        只有一种情况定为致命：**录制时页面变了、重放时没变**。这就是"点了没
        反应"的签名，是静默失败最典型的形态，必须停下来报失败。
        反方向（录制时没变、重放时变了）只记警告——可能是页面多了个动画或
        异步模块，不足以判定轨迹失效。
        """
        got_url = _norm_url(getattr(state, "url", "") or "")
        want_url = _norm_url(step.assert_url)
        got_changed = bool(
            getattr(state, "changed", False) or getattr(state, "url_changed", False)
        )

        if want_url and got_url and want_url != got_url:
            return {
                "step": i,
                "fatal": True,
                "kind": "url_mismatch",
                "detail": (
                    f"第 {i + 1} 步（{step.action}）后页面与录制时不一致："
                    f"期望 {want_url}，实际 {got_url}"
                ),
            }

        if step.assert_changed and not got_changed:
            return {
                "step": i,
                "fatal": True,
                "kind": "no_change",
                "detail": (
                    f"第 {i + 1} 步（{step.action}）录制时页面发生了变化，"
                    "重放时页面毫无反应——目标可能已经失效，停止重放"
                ),
            }

        if got_changed and not step.assert_changed:
            return {
                "step": i,
                "fatal": False,
                "kind": "extra_change",
                "detail": f"第 {i + 1} 步（{step.action}）重放时页面变化比录制时更多（仅提示）",
            }

        return None
