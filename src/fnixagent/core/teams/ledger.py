"""团队双账本 — 借鉴 Magentic-One 的编排骨架(ArXiv:2411.04468)。

Task Ledger(外循环): 任务级长期记忆 —— 已确认事实 / 待查事实 / 推导事实 / 教育性猜测 / 计划。
Progress Ledger(内循环): 每轮协作后的结构化自省, 回答五问:
    1. 总目标是否已满足?      (is_request_satisfied)
    2. 团队是否在无效绕圈?    (is_in_loop)
    3. 是否在取得实质进展?    (is_progress_being_made)
    4. 卡死计数是否超阈值?    (stall_exceeded)
    5. 对主 Agent 的建议动作? (recommendation)

与原版差异: 原版由 Orchestrator 用一次 LLM 调用产出进度账本;
本实现的默认判定是确定性启发式(零成本、可测试), 可选注入 llm_judge
做语义级评估 —— 失败静默回退启发式(项目 fail-open 风格)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from typing import Any


class TaskLedgerStore:
    """任务账本持久化({team_dir}/ledger.json)。"""

    def __init__(self, team_dir: str) -> None:
        self._path = os.path.join(str(team_dir), "ledger.json")
        self._lock = threading.Lock()
        os.makedirs(str(team_dir), exist_ok=True)
        if not os.path.exists(self._path):
            self._write(
                {
                    "facts_verified": [],
                    "facts_to_lookup": [],
                    "facts_to_derive": [],
                    "educated_guesses": [],
                    "plan": "",
                    "updated_at": time.time(),
                }
            )

    def _read(self) -> dict[str, Any]:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path)

    def get(self) -> dict[str, Any]:
        return self._read()

    def update(
        self,
        *,
        facts_verified: list[str] | None = None,
        educated_guesses: list[str] | None = None,
        plan: str | None = None,
    ) -> dict[str, Any]:
        """增量更新账本(None 字段保持不变)。"""
        with self._lock:
            data = self._read()
            if facts_verified is not None:
                data["facts_verified"] = [str(x)[:500] for x in facts_verified][:50]
            if educated_guesses is not None:
                data["educated_guesses"] = [str(x)[:500] for x in educated_guesses][:50]
            if plan is not None:
                data["plan"] = str(plan)[:8000]
            data["updated_at"] = time.time()
            self._write(data)
            return data

    def append_lookups(self, items: list[str]) -> None:
        """追加"待查事实"(失败信息等新线索, Magentic 外循环输入)。"""
        with self._lock:
            data = self._read()
            merged = [str(x) for x in data.get("facts_to_lookup", [])]
            for it in items:
                merged.append(str(it)[:300])
            data["facts_to_lookup"] = merged[-30:]
            data["updated_at"] = time.time()
            self._write(data)


class ProgressLedger:
    """一轮协作后的进度判定结果。"""

    def __init__(
        self,
        *,
        is_request_satisfied: bool,
        is_in_loop: bool,
        is_progress_being_made: bool,
        stall_counter: int,
        stall_exceeded: bool,
        recommendation: str,
        source: str = "heuristic",
    ) -> None:
        self.is_request_satisfied = is_request_satisfied
        self.is_in_loop = is_in_loop
        self.is_progress_being_made = is_progress_being_made
        self.stall_counter = stall_counter
        self.stall_exceeded = stall_exceeded
        self.recommendation = recommendation
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_request_satisfied": self.is_request_satisfied,
            "is_in_loop": self.is_in_loop,
            "is_progress_being_made": self.is_progress_being_made,
            "stall_counter": self.stall_counter,
            "stall_exceeded": self.stall_exceeded,
            "recommendation": self.recommendation,
            "source": self.source,
        }


class TeamOrchestratorLedger:
    """跨波次(fan_out 调用间)的进度追踪与卡死检测。

    用法(主循环多次调用 fan_out 时):
        ledger.note_wave(results)          # 每波结束记录
        verdict = ledger.evaluate(stats)   # 取得五问判定
        if verdict.stall_exceeded: ...     # 主 Agent 应重规划(Magentic: 阈值≤2)
    """

    def __init__(
        self,
        team_dir: str,
        *,
        max_stall_rounds: int = 2,
        llm_judge: Callable[[dict], dict] | None = None,
    ) -> None:
        """
        Args:
            team_dir: 团队目录(账本持久化位置)
            max_stall_rounds: 连续无进展波次阈值(超过则 stall_exceeded)
            llm_judge: 可选 (payload)->dict 的语义评审器, 需返回含
                satisfied/in_loop/progressing/recommendation 键的 dict。
        """
        self.task_ledger = TaskLedgerStore(team_dir)
        self.max_stall_rounds = max(1, int(max_stall_rounds))
        self.llm_judge = llm_judge
        self._stall_counter = 0
        self._last_completed = 0
        self._last_failed = 0
        self._wave_count = 0
        self._lock = threading.Lock()

    # -- 波次记录 -------------------------------------------------------------

    def note_wave(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """记录一波 fan_out 的结果, 返回该波的统计快照。"""
        with self._lock:
            self._wave_count += 1
            success = sum(1 for r in results if r.get("status") == "success")
            failed = sum(1 for r in results if r.get("status") == "failed")
            skipped = sum(1 for r in results if r.get("status") == "skipped")
            snapshot = {
                "wave": self._wave_count,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "timestamp": time.time(),
            }
            # 失败自动进任务账本的"待查事实"(Magentic: 新信息驱动外循环更新)
            if failed:
                lookups = [
                    str(r.get("error", ""))[:300]
                    for r in results
                    if r.get("status") == "failed" and r.get("error")
                ]
                if lookups:
                    self.task_ledger.append_lookups(lookups)
            return snapshot

    # -- 进度判定 ----------------------------------------------------------------

    def evaluate(self, stats: dict[str, Any]) -> ProgressLedger:
        """对当前团队状态产出进度账本(先启发式, 有 judge 则融合)。"""
        completed = int(stats.get("by_status", {}).get("completed", 0))
        failed = int(stats.get("by_status", {}).get("failed", 0))
        total = int(stats.get("total", 0))

        progressing = completed > self._last_completed
        if progressing:
            self._stall_counter = 0
        else:
            self._stall_counter += 1
        self._last_completed = completed
        self._last_failed = failed

        satisfied = total > 0 and completed >= total - failed and failed == 0
        in_loop = self._stall_counter >= 2 and not progressing
        stall_exceeded = self._stall_counter > self.max_stall_rounds

        if satisfied:
            rec = "全部任务完成, 可汇合收尾"
        elif stall_exceeded:
            rec = (
                f"连续 {self._stall_counter} 波无实质进展, 建议重规划: "
                "拆小任务/更换角色/补充上下文后再派发"
            )
        elif in_loop:
            rec = "疑似绕圈, 下一波建议调整任务定义或角色"
        elif progressing:
            rec = "进展正常, 继续下一波"
        else:
            rec = "首波执行中"

        verdict = ProgressLedger(
            is_request_satisfied=satisfied,
            is_in_loop=in_loop,
            is_progress_being_made=progressing,
            stall_counter=self._stall_counter,
            stall_exceeded=stall_exceeded,
            recommendation=rec,
            source="heuristic",
        )

        # 可选语义评审(失败静默回退启发式结论)
        if self.llm_judge is not None:
            try:
                payload = {
                    "stats": stats,
                    "wave_count": self._wave_count,
                    "stall_counter": self._stall_counter,
                    "task_ledger": self.task_ledger.get(),
                }
                judged = self.llm_judge(payload)
                if isinstance(judged, dict) and judged.get("recommendation"):
                    verdict.source = "llm_blend"
                    verdict.recommendation = str(judged["recommendation"])[:500]
                    for key, attr in (
                        ("satisfied", "is_request_satisfied"),
                        ("in_loop", "is_in_loop"),
                        ("progressing", "is_progress_being_made"),
                    ):
                        if key in judged:
                            setattr(verdict, attr, bool(judged[key]))
            except Exception:  # noqa: S110 — 语义评审失败静默回退启发式结论
                pass
        return verdict

    def reset_stall(self) -> None:
        """重规划后由主 Agent 调用, 归零卡死计数。"""
        with self._lock:
            self._stall_counter = 0


__all__ = ["ProgressLedger", "TaskLedgerStore", "TeamOrchestratorLedger"]
