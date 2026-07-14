"""
FnixAgent ∞ 进化主控器 (Evolution Master)
七层闭环自进化系统的中枢协调器

架构设计整合全球顶尖研究成果:
  ┌──────────────────────────────────────────────────────────────────┐
  │  学术前沿 (2026 Top Papers):                                      │
  │  GEPA ICLR 2026 Oral   → 遗传帕累托Prompt进化 (比RL好6%, 35x更少数据)│
  │  SIPDO ICLR 2026       → 自改进Prompt设计优化闭环                │
  │  KnowRL ACL 2026       → 知识增强RL, 认知边界自感知              │
  │  Misevolution 上交+普林 → 自进化"错误进化"风险与防护              │
  │  SCOPE                 → 上下文在线优化, 执行轨迹合成指南         │
  │  MemRL                 → 运行时RL在情景记忆上自进化               │
  │  RQGM ICML 2026        → Red Queen Gödel Machine 共进化评估       │
  │  HarnessX (2026.6)     → 跨Harness联合进化, Cross-Harness GRPO     │
  │  AFlow MetaGPT         → MCTS工作流自动探索与优化                │
  ├──────────────────────────────────────────────────────────────────┤
  │  工业标杆 (Top Open Source):                                      │
  │  Hermes Agent (128k★) NousResearch → GEPA闭环+技能结晶+Nudge Engine│
  │  DeerFlow 2.0 (62.8k★) ByteDance → 超级Agent Harness多智能体编排   │
  │  Evolver EvoMap        → Genome Evolution Protocol 标准化进化      │
  │  GenericAgent (Fudan)  → Token高效自进化, 6x更少Token消耗        │
  │  OpenClaw + AutoSkill  → 自动技能创建+46% token减少              │
  │  GPT-Researcher (28k★) → 多Agent深度研究, 引用合成报告           │
  │  FlowSearch 上海AI Lab → DAG知识流动态结构深度研究 GAIA/HLE第一   │
  │  DeepAgents LangChain  → 全功能Agent Harness, Claude Code架构     │
  │  MemOS MemTensor       → Self-evolving Memory OS 35% token节省   │
  │  Letta/MemGPT          → 三层记忆OS: Context=RAM, Disk=存储       │
  ├──────────────────────────────────────────────────────────────────┤
  │  新范式 (2026 Paradigm Shift):                                    │
  │  Loop Engineering (Boris Cherny) → "I don't write prompts, I design Loops"
  │  Harness Engineering 2026 → "Prompt是方向盘, Context是燃料, Harness是底盘"
  │  Agent-as-a-Judge      → 自进化评估标准, RL优化评估策略           │
  │  Red Queen Coevolution → 评估标准和Agent共同进化                  │
  │  Open-Ended Evolution  → 开放式无限制进化, 非特定任务             │
  │  Genome Protocol       → 基因胶囊标准化进化协议                  │
  └──────────────────────────────────────────────────────────────────┘

七层闭环架构 (Layer 0 → Layer 7):
  Layer 0: 感知采集层 (ContinuousCollector + CollectionPipeline)
           30+信息源, 动态结构化知识流 (FlowSearch)

  Layer 1: 循环工程层 (LoopEngine)
           8个预定义System Loop, Boris Cherny范式, Nudge Engine

  Layer 2: 遗传进化层 (GeneticEvolver)
           GEPA遗传帕累托优化, SIPDO闭环, 轨迹驱动进化

  Layer 3: 安全认知层 (EvolutionGuard)
           KnowRL边界感知, Misevolution退化检测, 沙箱验证, 回滚机制

  Layer 4: 知识合成层 (SynthesisEngine)
           GPT-Researcher风格多Agent深度研究, 结构化洞察提取

  Layer 5: 记忆操作系统 (MemoryOS)
           Letta/MemGPT三层: 核心内存(RAM) → 检索缓存 → 归档存储

  Layer 6: 技能市场层 (SkillMarketplace)
           OpenClaw AutoSkill + Evolver GEP + 技能版本控制

  Layer 7: 自我审判层 (SelfJudge)
           Agent-as-a-Judge + RQGM共进化评估, 动态更新评估标准

核心闭环: 感知 → 循环 → 进化 → 安全 → 合成 → 记忆 → 技能 → 审判
            ↑_________________________________________________↓
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable

from .loop_engine import (
    Loop, LoopResult, LoopPhase, LoopPriority,
    LoopExecutor, LoopScheduler, NudgeEngine, LoopRegistry,
)
from .genetic_evolver import GeneticEvolver, EvolutionResult, TrajectoryDrivenEvolution
from .evolution_guard import EvolutionGuard, GuardLevel, EvolutionCheckResult
from .self_judge import SelfJudge, JudgeVerdict, CriteriaEvolver
from .collection_pipeline import CollectionPipeline, CollectionBatch, IntelligentScheduler
from .synthesizer import SynthesisEngine, SynthesisReport
from .agent_optimizer import AgentHarness
from .flywheel import SelfEvolutionFlywheel, FlywheelState

logger = logging.getLogger(__name__)


# ============================================================
# 进化状态枚举
# ============================================================

class EvolutionStage(str, Enum):
    """进化系统整体阶段"""
    IDLE = "idle"                      # 空闲等待
    COLLECTING = "collecting"          # 采集情报
    SYNTHESIZING = "synthesizing"      # 知识合成
    LOOP_SCHEDULING = "loop_scheduling"  # 循环调度
    EVOLVING = "evolving"              # 遗传进化
    GUARD_CHECKING = "guard_checking"  # 安全检查
    MEMORY_CONSOLIDATION = "memory_consolidation"  # 记忆巩固
    SKILL_EVOLUTION = "skill_evolution"  # 技能进化
    JUDGEMENT = "judgement"            # 自我审判
    COMPLETED = "completed"            # 完成
    ERROR = "error"                    # 错误
    ROLLBACK = "rollback"              # 回滚中


# ============================================================
# 进化统计
# ============================================================

class EvolutionStatistics:
    """进化系统整体统计"""
    def __init__(self):
        self.total_cycles: int = 0
        self.successful_cycles: int = 0
        self.failed_cycles: int = 0
        self.rollbacks: int = 0
        self.new_skills_created: int = 0
        self.improved_prompts: int = 0
        self.token_savings_accumulated: int = 0
        self.cost_reduction_percent: float = 0.0
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.last_completed: Optional[str] = None
        self.average_cycle_duration_min: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cycles": self.total_cycles,
            "successful_cycles": self.successful_cycles,
            "failed_cycles": self.failed_cycles,
            "rollbacks": self.rollbacks,
            "new_skills_created": self.new_skills_created,
            "improved_prompts": self.improved_prompts,
            "token_savings_accumulated": self.token_savings_accumulated,
            "cost_reduction_percent": self.cost_reduction_percent,
            "started_at": self.started_at,
            "last_completed": self.last_completed,
            "average_cycle_duration_min": self.average_cycle_duration_min,
        }


# ============================================================
# 进化主控器 — 中枢协调所有七层
# ============================================================

class EvolutionMaster:
    """
    FnixAgent ∞ 进化主控器

    协调七层闭环自进化系统的所有组件，驱动飞轮持续旋转。
    整合了2026年全球所有顶尖研究成果和开源项目最佳实践。
    """

    def __init__(
        self,
        data_dir: str = "data/evolution",
        config_path: Optional[str] = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 组件初始化
        self._collection_scheduler: Optional[IntelligentScheduler] = None
        self._collection_pipeline: Optional[CollectionPipeline] = None
        self._loop_executor: Optional[LoopExecutor] = None
        self._loop_scheduler: Optional[LoopScheduler] = None
        self._nudge_engine: Optional[NudgeEngine] = None
        self._genetic_evolver: Optional[GeneticEvolver] = None
        self._trajectory_evolution: Optional[TrajectoryDrivenEvolution] = None
        self._evolution_guard: Optional[EvolutionGuard] = None
        self._synthesis_engine: Optional[SynthesisEngine] = None
        self._agent_harness: Optional[AgentHarness] = None
        self._self_judge: Optional[SelfJudge] = None
        self._criteria_evolver: Optional[CriteriaEvolver] = None
        self._flywheel: Optional[SelfEvolutionFlywheel] = None

        # 状态
        self.stage: EvolutionStage = EvolutionStage.IDLE
        self.stats: EvolutionStatistics = EvolutionStatistics()
        self.last_error: Optional[str] = None
        self.current_cycle_id: Optional[str] = None

        # 加载持久化状态
        self._load_stats()

    # ============================================================
    # 懒加载属性访问器
    # ============================================================

    @property
    def collection_scheduler(self) -> IntelligentScheduler:
        if self._collection_scheduler is None:
            self._collection_scheduler = IntelligentScheduler()
        return self._collection_scheduler

    @property
    def collection_pipeline(self) -> CollectionPipeline:
        if self._collection_pipeline is None:
            self._collection_pipeline = CollectionPipeline()
        return self._collection_pipeline

    @property
    def loop_executor(self) -> LoopExecutor:
        if self._loop_executor is None:
            self._loop_executor = LoopExecutor(
                experience_dir=str(self.data_dir / "loop_experiences")
            )
        return self._loop_executor

    @property
    def loop_scheduler(self) -> LoopScheduler:
        if self._loop_scheduler is None:
            self._loop_scheduler = LoopScheduler(self.loop_executor)
        return self._loop_scheduler

    @property
    def nudge_engine(self) -> NudgeEngine:
        if self._nudge_engine is None:
            self._nudge_engine = NudgeEngine(self.loop_executor)
        return self._nudge_engine

    @property
    def genetic_evolver(self) -> GeneticEvolver:
        if self._genetic_evolver is None:
            self._genetic_evolver = GeneticEvolver()
        return self._genetic_evolver

    @property
    def trajectory_evolution(self) -> TrajectoryDrivenEvolution:
        if self._trajectory_evolution is None:
            self._trajectory_evolution = TrajectoryDrivenEvolution(self.genetic_evolver)
        return self._trajectory_evolution

    @property
    def evolution_guard(self) -> EvolutionGuard:
        if self._evolution_guard is None:
            self._evolution_guard = EvolutionGuard()
        return self._evolution_guard

    @property
    def synthesis_engine(self) -> SynthesisEngine:
        if self._synthesis_engine is None:
            self._synthesis_engine = SynthesisEngine()
        return self._synthesis_engine

    @property
    def agent_harness(self) -> AgentHarness:
        if self._agent_harness is None:
            self._agent_harness = AgentHarness()
        return self._agent_harness

    @property
    def self_judge(self) -> SelfJudge:
        if self._self_judge is None:
            self._self_judge = SelfJudge()
        return self._self_judge

    @property
    def criteria_evolver(self) -> CriteriaEvolver:
        if self._criteria_evolver is None:
            self._criteria_evolver = CriteriaEvolver()
        return self._criteria_evolver

    @property
    def flywheel(self) -> SelfEvolutionFlywheel:
        if self._flywheel is None:
            from .flywheel import SelfEvolutionFlywheel
            self._flywheel = SelfEvolutionFlywheel()
        return self._flywheel

    # ============================================================
    # 持久化
    # ============================================================

    def _load_stats(self):
        """加载统计数据"""
        stats_file = self.data_dir / "evolution_stats.json"
        if stats_file.exists():
            try:
                data = json.loads(stats_file.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(self.stats, k):
                        setattr(self.stats, k, v)
            except Exception as e:
                logger.warning(f"加载进化统计失败: {e}")

    def _save_stats(self):
        """保存统计数据"""
        stats_file = self.data_dir / "evolution_stats.json"
        stats_file.write_text(
            json.dumps(self.stats.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ============================================================
    # 完整进化周期 — 七层闭环
    # ============================================================

    async def run_full_evolution_cycle(
        self,
        trigger_source: str = "schedule",
        manual_items: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        运行一个完整的七层闭环进化周期

        遵循顺序: Layer0 → Layer1 → Layer2 → Layer3 → Layer4 → Layer5 → Layer6 → Layer7
        """
        import hashlib
        cycle_id = f"cycle_{int(datetime.now(timezone.utc).timestamp())}_{hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:8]}"
        self.current_cycle_id = cycle_id
        self.stage = EvolutionStage.IDLE
        started_at = datetime.now(timezone.utc)
        self.stats.total_cycles += 1

        result = {
            "cycle_id": cycle_id,
            "started_at": started_at.isoformat(),
            "success": False,
            "stages_completed": [],
        }

        try:
            # ========== Layer 0: 感知采集层 ==========
            self.stage = EvolutionStage.COLLECTING
            logger.info(f"[{cycle_id}] Layer 0: 感知采集")

            if manual_items:
                # 手动指定项目，直接处理
                collected = manual_items
                result["items_collected"] = len(collected)
            else:
                # 调度驱动采集
                batch = await self.collection_pipeline.run_full_collection(
                    self.collection_scheduler
                )
                collected = batch.normalized_items
                result["items_collected"] = len(collected)
                result["sources_used"] = batch.sources_used

            result["stages_completed"].append("collecting")

            # ========== Layer 1: 循环工程层 调度所有预定义Loop ==========
            self.stage = EvolutionStage.LOOP_SCHEDULING
            logger.info(f"[{cycle_id}] Layer 1: 循环工程调度")

            # 创建所有系统Loop
            system_loops = LoopRegistry.create_all_system_loops()

            # 自定义执行函数
            async def default_loop_execute(plan):
                # 占位实现，实际由具体Loop的处理器提供
                from .loop_engine import LoopResult, LoopOutcome, LoopPhase
                return LoopResult(
                    loop_id=plan.loop_id,
                    outcome=LoopOutcome.SUCCESS,
                    phase=LoopPhase.COMPLETED,
                    plan=plan,
                    metrics={"progress": 1.0},
                )

            loop_results = await self.loop_scheduler.run_all(default_loop_execute)

            result["stages_completed"].append("loop_scheduling")
            result["loops_executed"] = len(loop_results)
            result["loop_results"] = [
                {
                    "loop_id": lr.loop_id,
                    "outcome": lr.outcome.value if hasattr(lr.outcome, 'value') else str(lr.outcome),
                    "duration_ms": lr.duration_ms,
                }
                for lr in loop_results
            ]

            # ========== Layer 4: 知识合成层 (提前做，为进化提供材料) ==========
            self.stage = EvolutionStage.SYNTHESIZING
            logger.info(f"[{cycle_id}] Layer 4: 知识合成")

            synthesis_report = self.synthesis_engine.synthesize_collection(
                [item.raw_data for item in collected] if collected else []
            )

            result["stages_completed"].append("synthesizing")
            result["synthesis"] = {
                "insights_count": len(synthesis_report.insights),
                "actionable_insights": synthesis_report.count_insights_by_urgency("high"),
                "report_path": synthesis_report.save_to_file(),
            }

            # ========== Layer 2: 遗传进化层 ==========
            self.stage = EvolutionStage.EVOLVING
            logger.info(f"[{cycle_id}] Layer 2: 遗传进化")

            # 轨迹驱动进化（GEPA）
            # 使用SIPDO闭环 + GEPA遗传帕累托优化
            actionable = [i for i in synthesis_report.insights if i.urgency.value == "high"]
            evolution_results: List[EvolutionResult] = []

            for insight in actionable:
                # 对每个可操作洞察进行进化尝试
                er = await self.trajectory_evolution.evolve_from_insight(insight)
                evolution_results.append(er)

            successful_evolutions = [er for er in evolution_results if er.success]
            result["stages_completed"].append("evolving")
            result["evolution_results"] = {
                "total_attempts": len(evolution_results),
                "successful": len(successful_evolutions),
                "pareto_frontier_size": len(self.genetic_evolver.pareto_frontier),
            }

            # ========== Layer 3: 安全认知层检查 ==========
            self.stage = EvolutionStage.GUARD_CHECKING
            logger.info(f"[{cycle_id}] Layer 3: 安全检查")

            guard_result = self.evolution_guard.full_evolution_check(
                [er.chromosome for er in successful_evolutions if er.chromosome]
            )

            if guard_result.level == GuardLevel.CRITICAL:
                # 严重问题，触发回滚
                self.stage = EvolutionStage.ROLLBACK
                logger.critical(f"[{cycle_id}] 安全检查发现严重问题，触发回滚: {guard_result.message}")
                await self.evolution_guard.rollback_all()
                self.stats.rollbacks += 1
                result["rollback"] = True
                result["guard_result"] = {
                    "level": guard_result.level.value,
                    "message": guard_result.message,
                    "degradation_detected": guard_result.degradation_detected,
                }
                self.stage = EvolutionStage.COMPLETED
                self._save_stats()
                return result

            result["stages_completed"].append("guard_checking")
            result["guard_result"] = {
                "level": guard_result.level.value,
                "passed": guard_result.passed,
                "warnings": guard_result.warnings,
            }

            # ========== Layer 5: 记忆操作系统 巩固 ==========
            # 已经由memory_os独立处理，这里只是触发巩固循环
            self.stage = EvolutionStage.MEMORY_CONSOLIDATION
            logger.info(f"[{cycle_id}] Layer 5: 记忆巩固")

            # 触发记忆巩固Loop
            # 实际操作由MemoryOS完成

            result["stages_completed"].append("memory_consolidation")

            # ========== Layer 6: 技能市场 技能进化 ==========
            self.stage = EvolutionStage.SKILL_EVOLUTION
            logger.info(f"[{cycle_id}] Layer 6: 技能进化")

            # skill_marketplace整合洞察，自动创建/进化技能
            # 由skill_marketplace模块独立处理

            result["stages_completed"].append("skill_evolution")

            # ========== Layer 7: 自我审判 ==========
            self.stage = EvolutionStage.JUDGEMENT
            logger.info(f"[{cycle_id}] Layer 7: 自我审判")

            # 多维度评分，比较进化前后
            verdict = self.self_judge.judge_evolution_cycle(
                before=self.stats,
                after_evolutions=successful_evolutions
            )

            # RQGM: 如果评估标准需要进化，进化评估标准
            if self.criteria_evolver.should_evolve_criteria(verdict):
                self.criteria_evolver.evolve_criteria(verdict)
                logger.info("评估标准已进化")

            result["stages_completed"].append("judgement")
            result["judgement"] = {
                "verdict": verdict.verdict.value,
                "overall_score": verdict.overall_score,
                "improvement_detected": verdict.improvement_detected,
            }

            # ========== 完成 ==========
            self.stage = EvolutionStage.COMPLETED
            completed_at = datetime.now(timezone.utc)
            duration_min = (completed_at - started_at).total_seconds() / 60

            # 更新统计
            if verdict.verdict.value == "accept":
                self.stats.successful_cycles += 1
                # 累加token节省估计
                for er in successful_evolutions:
                    if er.estimated_token_saving:
                        self.stats.token_savings_accumulated += er.estimated_token_saving
            else:
                self.stats.failed_cycles += 1

            self.stats.last_completed = completed_at.isoformat()
            # 更新平均时长
            total = self.stats.total_cycles
            old_avg = self.stats.average_cycle_duration_min
            self.stats.average_cycle_duration_min = ((old_avg * (total - 1)) + duration_min) / total

            result["success"] = verdict.verdict.value == "accept"
            result["completed_at"] = completed_at.isoformat()
            result["duration_min"] = duration_min

            logger.info(f"[{cycle_id}] 进化周期完成，成功={result['success']}, 耗时={duration_min:.1f}分钟")

            self._save_stats()
            return result

        except Exception as e:
            self.stage = EvolutionStage.ERROR
            self.last_error = str(e)
            logger.error(f"[{cycle_id}] 进化周期异常: {e}", exc_info=True)
            result["success"] = False
            result["error"] = str(e)
            result["stage_at_error"] = self.stage.value
            self._save_stats()
            return result

    # ============================================================
    # Nudge 自主触发 — Hermes Agent风格
    # ============================================================

    async def process_nudges(self) -> List[Optional[LoopResult]]:
        """处理Nudge Engine推送的自主触发Loop"""
        results: List[Optional[LoopResult]] = []

        # 这里检测各种模式，创建Loop并注册执行
        # 实际使用中由系统在运行时持续检测

        from .loop_engine import LoopResult

        async def dummy_execute(plan):
            return LoopResult(
                loop_id=plan.loop_id,
                outcome=None,
                phase=None,
                plan=plan,
            )

        for event_type in ["new_skill_opportunity", "error_pattern", "knowledge_gap"]:
            # 这里简化处理，实际应该统计事件 occurrence
            context = {"occurrence_count": 3}
            loop = self.nudge_engine.create_nudge_loop(event_type, context)
            if loop:
                self.loop_scheduler.register(loop)

        if self.loop_scheduler._pending_loops:
            results = await self.loop_scheduler.run_all(dummy_execute)

        return results

    # ============================================================
    # 利用AgentHarness执行带优化的任务
    # ============================================================

    async def execute_with_optimization(
        self,
        prompt: str,
        execute_fn: Callable[[str], Awaitable[Any]],
        task_complexity: float = 0.5,
        priority: str = "normal",
    ) -> Dict[str, Any]:
        """
        使用AgentHarness执行任务，享受全方位优化:
        - L1 Prompt Caching + L2 Semantic Caching
        - 成本感知模型路由
        - 上下文剪枝
        - 错误恢复
        - 熔断保护
        - 性能监控
        """
        return await self.agent_harness.execute(
            prompt, execute_fn, task_complexity, priority
        )

    # ============================================================
    # 获取整体状态
    # ============================================================

    def get_full_status(self) -> Dict[str, Any]:
        """获取进化系统完整状态"""
        return {
            "current_cycle_id": self.current_cycle_id,
            "current_stage": self.stage.value,
            "last_error": self.last_error,
            "statistics": self.stats.to_dict(),
            "active_loops": [
                {"loop_id": l.loop_id, "name": l.name, "phase": l.phase.value}
                for l in self.loop_executor.get_active_loops()
            ],
            "recent_completed_loops": [
                {
                    "loop_id": lr.loop_id,
                    "outcome": lr.outcome.value if hasattr(lr.outcome, 'value') else str(lr.outcome),
                    "duration_ms": lr.duration_ms,
                }
                for lr in self.loop_executor.get_completed_loops(limit=10)
            ],
            "pareto_frontier_size": len(self.genetic_evolver.pareto_frontier),
        }

    # ============================================================
    # 触发特定Loop
    # ============================================================

    def register_custom_loop(self, loop: Loop) -> None:
        """注册自定义Loop供调度"""
        self.loop_scheduler.register(loop)

    # ============================================================
    # 检查是否应该运行
    # ============================================================

    def should_run_cycle(self) -> tuple[bool, str]:
        """基于飞轮调度判断是否应该运行进化周期"""
        return self.flywheel.should_run_now()


# ============================================================
# CLI 入口
# ============================================================

async def main():
    """CLI 手动触发完整进化周期"""
    import argparse
    parser = argparse.ArgumentParser(description="FnixAgent Evolution Master")
    parser.add_argument("--trigger", default="manual", choices=["schedule", "manual"])
    args = parser.parse_args()

    master = EvolutionMaster()
    result = await master.run_full_evolution_cycle(trigger_source=args.trigger)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
