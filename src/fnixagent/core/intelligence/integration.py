"""Intelligence 七层集成协调层 — 把孤立模块串成闭环。

核心闭环: 感知 → 循环 → 进化 → 安全 → 合成 → 记忆 → 技能 → 审判
              ↑_________________________________________________↓

本模块是"第二护城河"的调度中枢, 把 intelligence/ 下 14 个孤立模块
通过两个入口接入主路径:
  - pre_task_nudge():  执行前 Nudge 注入 (L1 循环工程 + L5 记忆召回)
  - post_evolution():  MFP 之后的深度进化 (L3 安全 + L7 审判 + L2 进化 + L6 技能 + L5 记忆)

设计原则 (对齐 work_pipeline.py 的容错模式):
  - 所有调用 try/except 包裹, 失败不阻塞主路径
  - 同步方法; async API (EvolutionGuard.post_upgrade_check / GeneticEvolver.evolve)
    通过调用其底层同步方法或跳过, 避免在已有事件循环中 asyncio.run 冲突
  - 零外部依赖, 零 LLM 调用 (GeneticEvolver 需 fitness_fn, 此处跳过真实进化)
  - 中文注释
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .evolution_guard import BenchmarkSnapshot, EvolutionGuard, GuardLevel
from .genetic_evolver import EvolutionConfig, GeneticEvolver
from .loop_engine import LoopExecutor, LoopRegistry, NudgeEngine
from .memory_manager import IntelligenceMemoryManager
from .self_judge import SelfJudge
from .skill_marketplace import SkillMarketplace

_logger = logging.getLogger(__name__)



def _now_iso() -> str:
    """当前 UTC 时间 ISO 字符串"""
    return datetime.now(UTC).isoformat()


def _run_async_safely(coro_factory, *, timeout: float = 5.0) -> Any | None:
    """安全地运行协程: 无事件循环时用 asyncio.run; 有循环则返回 None (跳过)。

    主路径可能在 async 上下文中调用本同步方法, 此时 asyncio.run 会抛
    RuntimeError。为不阻塞主路径, 检测到已有运行循环则直接返回 None。
    """
    try:
        asyncio.get_running_loop()
        # 已有事件循环在跑, 不再用 asyncio.run (会冲突), 选择跳过
        return None
    except RuntimeError:
        pass  # 无运行循环, 可以安全 asyncio.run
    try:
        return asyncio.run(_await_with_timeout(coro_factory(), timeout))
    except Exception:
        return None


async def _await_with_timeout(coro, timeout: float) -> Any | None:
    """带超时的协程执行"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (TimeoutError, Exception):
        return None


class IntelligenceIntegrator:
    """Intelligence 七层集成协调器。

    使用方式:
      >>> integrator = IntelligenceIntegrator(workspace)
      >>> nudge = integrator.pre_task_nudge(user_input, ctx)
      >>> result = integrator.post_evolution(trace_record, mfp_result)
      >>> report = integrator.get_intelligence_report()
    """

    def __init__(self, workspace: str, state_dir: str = "data/intelligence"):
        self.workspace = str(Path(workspace or "").expanduser().resolve())
        self.state_dir = Path(state_dir)
        # 各子模块状态目录 (统一收纳在 state_dir 下, 避免 data/ 散落)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # L5 记忆层: 优先用 workspace 下 .fnix (与 self_optimizing 一致)
        self.memory = IntelligenceMemoryManager(self.workspace)

        # L1 循环工程层
        self.loop_executor = LoopExecutor(experience_dir=str(self.state_dir / "loop_experiences"))
        self.nudge_engine = NudgeEngine(self.loop_executor)

        # L3 安全认知层
        self.guard = EvolutionGuard(state_dir=str(self.state_dir / "evolution_guard"))

        # L7 自我审判层
        self.judge = SelfJudge()

        # L2 遗传进化层 (仅实例化, 真实进化需 fitness_fn, 此处不触发)
        self.evolver = GeneticEvolver(
            config=EvolutionConfig(),
            state_dir=str(self.state_dir / "evolution_state"),
        )

        # L6 技能市场层
        self.skill_market = SkillMarketplace(storage_dir=str(self.state_dir / "skills"))

        # 记录本协调器的运行历史 (供 get_intelligence_report 汇总)
        self._history: list[dict] = []
        self._init_baseline()

    def _init_baseline(self) -> None:
        """初始化 EvolutionGuard 基线 (仅一次, 失败静默)"""
        try:
            baseline = BenchmarkSnapshot(
                snapshot_id="baseline",
                version="init",
                created_at=_now_iso(),
                metrics={
                    "task_completion_rate": 0.8,
                    "error_rate": 0.1,
                    "response_quality": 0.75,
                    "hallucination_rate": 0.05,
                },
            )
            self.guard.set_baseline(baseline)
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

    # ============================================================
    # 执行前: Nudge 注入 (L1 循环工程 + L5 记忆召回)
    # ============================================================

    def pre_task_nudge(self, user_input: str, ctx: dict) -> str:
        """执行前: LoopEngine Nudge 注入, 返回 nudge 文本 (可空)。

        结合 L5 记忆召回 + L1 NudgeEngine 判断是否需要推动:
          - 召回相关历史记忆, 若有则注入"参考过往经验"提示
          - 若检测到重复任务模式, 触发技能创建 Nudge
        所有失败静默, 返回空字符串不阻塞主路径。
        """
        if not user_input:
            return ""
        parts: list[str] = []
        # 一次召回, 同时供 L5 记忆注入和 L1 重复检测使用 (避免双重 recall 浪费)
        recalled: list[dict] = []
        try:
            recalled = self.memory.recall(user_input, top_k=5)
        except Exception:
            recalled = []

        try:
            # L5 记忆召回: 找相关历史经验
            if recalled:
                parts.append("\n\n## Intelligence Nudge (L5 记忆层)")
                parts.append("检测到与历史任务相关, 参考以下经验:")
                for i, m in enumerate(recalled[:2], 1):
                    parts.append(
                        f"{i}. [{m.get('memory_type', 'episodic')}] {m.get('content', '')[:200]}"
                    )
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        try:
            # L1 NudgeEngine: 检测重复任务模式 → 推动技能创建
            occurrence_count = len(recalled)
            if self.nudge_engine.should_nudge("new_skill_opportunity", occurrence_count):
                parts.append("\n## Intelligence Nudge (L1 循环工程层)")
                parts.append(f"检测到 {occurrence_count} 次类似操作, 建议沉淀为可复用技能。")
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        try:
            # L1 LoopRegistry: 注入系统预定义 Loop 提示 (轻量, 不实际执行)
            sys_loop = LoopRegistry.create_system_loop("skill_creation")
            if sys_loop is not None:
                parts.append(f"\n<!-- Loop 提示: {sys_loop.name} — {sys_loop.description} -->")
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        return "\n".join(parts) if parts else ""

    # ============================================================
    # MFP 之后: 深度进化协调 (L3 安全 + L7 审判 + L2 进化 + L6 技能 + L5 记忆)
    # ============================================================

    def post_evolution(
        self,
        trace_record: dict,
        mfp_result: dict,
    ) -> dict:
        """MFP 飞轮之后的深度进化协调。

        流程:
          1. L3 EvolutionGuard: 检测升级后是否退化 (同步调用底层 detector)
          2. L7 SelfJudge: 评估本次进化周期
          3. 若退化: 跳过后续进化, 记录告警
          4. 若安全: L2 GeneticEvolver 可选进化 (需 fitness_fn, 此处跳过)
          5. L6 SkillMarketplace: 从成功 trace 创建技能
          6. L5 IntelligenceMemoryManager: 沉淀本次进化经验
        返回: {guard_level, judge_verdict, evolved, skill_created, memory_saved}
        所有失败静默, 不阻塞主路径。
        """
        result: dict[str, Any] = {
            "guard_level": "unknown",
            "judge_verdict": None,
            "evolved": False,
            "skill_created": False,
            "memory_saved": False,
            "degraded": False,
        }

        success = bool(trace_record.get("success", False))
        user_input = str(trace_record.get("user_input", "") or "")
        tool_calls = trace_record.get("tool_calls", []) or []
        try:
            duration_ms = float(trace_record.get("duration_ms", 0) or 0)
        except (TypeError, ValueError):
            duration_ms = 0.0
        workspace_kind = str(trace_record.get("workspace_kind", "general") or "general")

        # ---- 1. L3 安全认知层: 升级后退化检测 ----
        guard_level_str = "safe"
        try:
            snapshot = self._build_snapshot(trace_record, mfp_result)
            # 直接调用底层同步方法, 避免 async 冲突 (复刻 post_upgrade_check 逻辑)
            check_result = self.guard.detector.check_snapshot(snapshot)
            guard_level = check_result.get("guard_level", GuardLevel.SAFE)
            guard_level_str = (
                guard_level.value if hasattr(guard_level, "value") else str(guard_level)
            )
            result["guard_level"] = guard_level_str
            result["degraded"] = guard_level_str in (
                GuardLevel.ROLLBACK_REQUIRED.value,
                GuardLevel.CRITICAL.value,
            )
            # 检测循环进化
            try:
                if self.guard.detector.detect_circular_evolution():
                    result["degraded"] = True
                    result["circular_evolution"] = True
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        # ---- 2. L7 自我审判层: 评估进化周期 ----
        try:
            before_stats = {
                "success": success,
                "tool_calls": len(tool_calls),
                "duration_ms": duration_ms,
            }
            # mfp_result 作为 "after_evolutions" 的简化代理
            after_evolutions = []
            if mfp_result:
                after_evolutions = [mfp_result]
            verdict = self.judge.judge_evolution_cycle(before_stats, after_evolutions)
            result["judge_verdict"] = {
                "passed": getattr(verdict, "passed", False),
                "verdict": getattr(verdict, "verdict", ""),
                "overall_score": getattr(verdict, "overall_score", 0.0),
            }
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        # ---- 3. 若退化: 跳过后续进化, 记录告警 ----
        if result["degraded"]:
            try:
                self.memory.add_memory(
                    key=f"degradation_alert_{int(time.time())}",
                    content=(
                        f"检测到退化 (guard_level={guard_level_str}), "
                        f"任务: {user_input[:200]}, 已跳过进化"
                    ),
                    memory_type="episodic",
                    importance=0.9,
                )
                result["memory_saved"] = True
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
            self._history.append(
                {
                    "ts": _now_iso(),
                    "step": "post_evolution",
                    **result,
                }
            )
            return result

        # ---- 4. L2 遗传进化层: 可选进化 (需 async fitness_fn, 此处跳过真实进化) ----
        # GeneticEvolver.evolve 需要 async fitness_fn (依赖 LLM), 主路径零 LLM,
        # 故仅尝试用 asyncio 安全运行; 无 fitness_fn 则跳过 (不阻塞)。
        try:
            # 提供一个轻量同步 fitness (转为 async) 仅验证管线连通, 不做真实优化
            async def _trivial_fitness(chromo) -> dict:
                return {"quality": 0.7, "efficiency": 0.6}

            evolved_result = _run_async_safely(
                lambda: self.evolver.evolve(
                    initial_content=user_input[:500] or "system_prompt",
                    gene_type="system_prompt",
                    fitness_fn=_trivial_fitness,
                    max_generations=1,
                ),
                timeout=3.0,
            )
            if evolved_result is not None:
                result["evolved"] = bool(getattr(evolved_result, "success", False))
        except Exception:
            result["evolved"] = False

        # ---- 5. L6 技能市场层: 从成功 trace 创建技能 ----
        try:
            if success:
                exec_trace = " -> ".join(str(t.get("name", "")) for t in tool_calls[:10])
                skill = self.skill_market.detect_and_create(
                    task_description=user_input[:200],
                    execution_trace=exec_trace,
                    success=success,
                    token_saved=0,
                )
                result["skill_created"] = skill is not None
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        # ---- 6. L5 记忆层: 沉淀本次进化经验 ----
        try:
            importance = 0.7 if success else 0.4
            content = (
                f"任务: {user_input[:300]} | 成功: {success} | "
                f"工具数: {len(tool_calls)} | 耗时: {duration_ms}ms | "
                f"guard: {guard_level_str} | workspace: {workspace_kind}"
            )
            saved = self.memory.add_memory(
                key=user_input.strip()[:100] or f"task_{int(time.time())}",
                content=content,
                memory_type="episodic",
                importance=importance,
            )
            result["memory_saved"] = saved is not None
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        self._history.append(
            {
                "ts": _now_iso(),
                "step": "post_evolution",
                **result,
            }
        )
        return result

    # ============================================================
    # 辅助: 构建 BenchmarkSnapshot
    # ============================================================

    def _build_snapshot(self, trace_record: dict, mfp_result: dict) -> BenchmarkSnapshot:
        """从 trace_record + mfp_result 构建 BenchmarkSnapshot"""
        success = bool(trace_record.get("success", False))
        tool_calls = trace_record.get("tool_calls", []) or []
        duration_ms = float(trace_record.get("duration_ms", 0) or 0)

        # 工具成功率
        if tool_calls:
            ok = sum(1 for t in tool_calls if t.get("success", True))
            tool_success_rate = ok / len(tool_calls)
        else:
            tool_success_rate = 1.0 if success else 0.0

        # 派生指标 (与 DegradationDetector.check_snapshot 的 keys 对齐)
        metrics = {
            "task_completion_rate": 1.0 if success else 0.0,
            "error_rate": 0.0 if success else 0.5,
            "response_quality": 0.8 if success else 0.4,
            "tool_call_success_rate": tool_success_rate,
            "avg_latency_ms": duration_ms,
            "hallucination_rate": 0.05,
        }
        # 合并 mfp_result 提供的指标 (若有)
        try:
            if isinstance(mfp_result, dict):
                for k in ("response_quality", "task_completion_rate"):
                    v = mfp_result.get(k)
                    if isinstance(v, (int, float)):
                        metrics[k] = float(v)
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        snap_id = hashlib.md5(
            f"{trace_record.get('user_input', '')}_{time.time()}".encode()
        ).hexdigest()[:12]
        return BenchmarkSnapshot(
            snapshot_id=snap_id,
            version="post_task",
            created_at=_now_iso(),
            metrics=metrics,
        )

    # ============================================================
    # 汇总报告
    # ============================================================

    def get_intelligence_report(self) -> dict:
        """汇总七层 Intelligence 运行报告"""
        report: dict[str, Any] = {
            "workspace": self.workspace,
            "total_cycles": len(self._history),
        }
        try:
            report["memory_stats"] = self.memory.get_stats()
        except Exception:
            report["memory_stats"] = {"error": "unavailable"}
        try:
            report["guard_health"] = self.guard.get_health_report()
        except Exception:
            report["guard_health"] = {"error": "unavailable"}
        try:
            report["judge_report"] = self.judge.get_report()
        except Exception:
            report["judge_report"] = {"error": "unavailable"}
        try:
            report["skill_stats"] = self.skill_market.get_stats()
        except Exception:
            report["skill_stats"] = {"error": "unavailable"}
        # 最近 5 次进化周期摘要
        report["recent_cycles"] = self._history[-5:]
        return report


__all__ = [
    "IntelligenceIntegrator",
]
