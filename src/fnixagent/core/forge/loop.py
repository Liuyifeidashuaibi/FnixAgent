"""FnixForge — 测评 → 诊断 → 修复 → 复测 编排器。

一条命令 `fnixagent forge <项目目录>` 背后跑的就是这个循环:

  round 0: 全量测评（基线）
  round n: 诊断失败 → LLM 提补丁 → 落盘 → **全量复测**（不只重跑失败题，
           还要确认没有回归）→ 裁决 keep / rollback

事件以 NDJSON 形式回调:
  {"event": "round_start" | "task_start" | "task_end" | "round_end"
         | "diagnosed" | "fix_proposed" | "fix_decision" | "done", ...}

模式:
  forge test —— 只测不修（pure benchmark）
  forge fix  —— 测 + 修 + 复测闭环（生产级打磨）
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fnixagent.core.forge.adapters import AdapterConfig
from fnixagent.core.forge.diagnose import build_diagnosis
from fnixagent.core.forge.fixer import (
    FixAttempt,
    GitGuard,
    apply_edits,
    decide,
    propose_fix_sync,
)
from fnixagent.core.forge.runner import ForgeRunner, locate_suite
from fnixagent.core.forge.scorer import aggregate, production_readiness
from fnixagent.core.forge.spec import ForgeTask, load_suite

_logger = logging.getLogger(__name__)

EventSink = Callable[[dict[str, Any]], None]

@dataclass
class RoundResult:
    round: int
    aggregate: dict[str, Any] = field(default_factory=dict)
    diagnosis: dict[str, Any] = field(default_factory=dict)
    fix: dict[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round,
            "aggregate": self.aggregate,
            "diagnosis": self.diagnosis,
            "fix": self.fix,
            "elapsed_s": round(self.elapsed_s, 2),
        }

@dataclass
class ForgeLoopResult:
    target_root: str
    suite: str
    mode: str                          # test | fix
    rounds: list[RoundResult] = field(default_factory=list)
    final: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_root": self.target_root,
            "suite": self.suite,
            "mode": self.mode,
            "rounds": [r.to_dict() for r in self.rounds],
            "final": self.final,
            "readiness": self.readiness,
            "total_rounds": len(self.rounds),
            "elapsed_s": round(time.time() - self.started_at, 2),
        }

class ForgeLoop:
    def __init__(
        self,
        target_root: Path | str,
        *,
        suite: str = "core",
        mode: str = "fix",               # test | fix
        max_rounds: int = 3,
        adapter_config: AdapterConfig | None = None,
        adapter=None,
        keep_sandboxes: bool = False,
        fix_threshold: float = 90.0,
        llm=None,
        on_event: EventSink | None = None,
    ) -> None:
        self.target_root = Path(target_root).resolve()
        self.suite = suite
        self.mode = mode
        self.max_rounds = max(1, int(max_rounds))
        self.adapter_config = adapter_config
        self.adapter = adapter
        self.keep_sandboxes = keep_sandboxes
        self.fix_threshold = fix_threshold
        self.llm = llm
        self.on_event = on_event

    # ------------------------------------------------------------------

    def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", round(time.time(), 3))
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                _logger.warning("event sink failed", exc_info=True)

    def _run_round(self, tasks: list[ForgeTask], runner: ForgeRunner) -> tuple[list, dict]:
        records = runner.run_suite(tasks, on_event=self._emit)
        agg = aggregate([r.score for r in records])
        return records, agg

    def run(self) -> ForgeLoopResult:
        result = ForgeLoopResult(
            target_root=str(self.target_root), suite=self.suite, mode=self.mode
        )
        suite_dir = locate_suite(self.suite)
        tasks = load_suite(suite_dir)
        if not tasks:
            raise RuntimeError(f"套件 {self.suite!r} 中没有任何任务")

        runner = ForgeRunner(
            self.target_root,
            self.adapter_config,
            adapter=self.adapter,
            keep_sandboxes=self.keep_sandboxes,
        )
        guard = GitGuard(self.target_root) if self.mode == "fix" else None
        baseline_commit = guard.ensure() if guard else ""

        all_passed = False
        for round_idx in range(self.max_rounds):
            t0 = time.perf_counter()
            self._emit({"event": "round_start", "round": round_idx, "tasks": len(tasks)})
            records, agg = self._run_round(tasks, runner)
            rr = RoundResult(round=round_idx, aggregate=agg)
            self._emit({"event": "round_end", "round": round_idx,
                        "overall": agg["overall_score"],
                        "passed": agg["passed"], "total": agg["tasks"]})

            readiness = production_readiness(agg, self.fix_threshold)
            if agg["passed"] == agg["tasks"]:
                all_passed = True
                rr.elapsed_s = time.perf_counter() - t0
                result.rounds.append(rr)
                break

            if self.mode != "fix" or round_idx == self.max_rounds - 1:
                rr.elapsed_s = time.perf_counter() - t0
                result.rounds.append(rr)
                break

            # ---- 诊断 ----
            diagnosis = build_diagnosis(records, self.target_root)
            rr.diagnosis = diagnosis
            self._emit({
                "event": "diagnosed", "round": round_idx,
                "clusters": len(diagnosis["clusters"]),
                "relevant_files": [f["path"] for f in diagnosis["relevant_files"]],
            })

            # ---- 修复 ----
            attempt = FixAttempt(round=round_idx, baseline=guard.current_head())
            try:
                edits, perr, raw = propose_fix_sync(diagnosis, self.target_root, llm=self.llm)
                attempt.llm_raw_chars = len(raw or "")
                if perr:
                    attempt.proposal_error = perr
                    attempt.decision = "aborted"
                elif not edits:
                    attempt.proposal_error = "LLM 输出无法解析为文件块"
                    attempt.decision = "aborted"
                else:
                    attempt.edits = edits
                    attempt.applied_paths = apply_edits(self.target_root, edits)
                    self._emit({
                        "event": "fix_proposed", "round": round_idx,
                        "paths": attempt.applied_paths,
                    })

                    # ---- 复测（全量回归） ----
                    before_pass = agg["passed"]
                    re_records, re_agg = self._run_round(tasks, runner)
                    regressed = any(
                        rec.score.passed and not re_rec.score.passed
                        for rec, re_rec in zip(records, re_records)
                    )
                    decision, note = decide(before_pass, re_agg["passed"], regressed)
                    attempt.decision = decision
                    attempt.note = note
                    if decision == "kept":
                        attempt.committed = guard.commit(
                            f"fnix-forge: round {round_idx} fix "
                            f"({before_pass}->{re_agg['passed']} passed)"
                        )
                    else:
                        guard.rollback(attempt.baseline)
                    self._emit({
                        "event": "fix_decision", "round": round_idx,
                        "decision": decision, "note": note,
                        "before_pass": before_pass, "after_pass": re_agg["passed"],
                    })
                    # 修复被保留时，本轮成绩以复测结果为准；回滚则保留原成绩
                    if decision == "kept":
                        rr.aggregate = re_agg
                        records = re_records
            except Exception as e:
                _logger.exception("fix round %s crashed", round_idx)
                attempt.proposal_error = f"{type(e).__name__}: {e}"
                attempt.decision = "aborted"
                guard.rollback(attempt.baseline)
            rr.fix = attempt.to_dict()
            rr.elapsed_s = time.perf_counter() - t0
            result.rounds.append(rr)

        final_agg = result.rounds[-1].aggregate if result.rounds else {}
        result.final = final_agg
        result.readiness = production_readiness(final_agg, self.fix_threshold)
        result.readiness["all_passed"] = all_passed
        if baseline_commit:
            result.readiness["baseline_commit"] = baseline_commit
        self._emit({
            "event": "done",
            "mode": self.mode,
            "rounds": len(result.rounds),
            "overall_score": result.final.get("overall_score", 0.0),
            "passed": result.final.get("passed", 0),
            "tasks": result.final.get("tasks", 0),
            "production_ready": result.readiness.get("ready", False),
        })
        return result

def ndjson_sink(fp) -> EventSink:
    """把事件流写成 NDJSON 行（供 CLI 实时显示 / API SSE 推送）。"""
    def sink(event: dict[str, Any]) -> None:
        fp.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        fp.flush()
    return sink
