"""
∞ Loop Engine — 自主闭环工程层 (2026 范式转移)

设计参考:
  - Boris Cherny (Claude Code 之父): "I don't write prompts. I design Loops."
  - Loop Engineering: 触发→执行→评估→重试/结束 闭环机制
  - Hermes Agent: Nudge Engine 自主知识持久化
  - SCOPE: 从执行轨迹在线合成指南

核心思想:
  不再被动收集信息，而是设计自主闭环。每个 Loop 是一个独立的自进化单元，
  包含触发条件、执行计划、结果评估、经验沉淀、重试策略。
  多 Loop 并行执行，失败 Loop 自动根因分析。

架构:
  ┌─────────────────────────────────────────────────────────────┐
  │                    Loop Engine                              │
  ├─────────────────────────────────────────────────────────────┤
  │  Loop Registry    │  Loop Scheduler   │  Loop Executor      │
  │  (Loop 注册中心)   │  (Loop 调度器)    │  (Loop 执行器)      │
  ├─────────────────────────────────────────────────────────────┤
  │  Experience DB    │  Root Cause       │  Nudge Engine       │
  │  (经验数据库)      │  Analyzer         │  (自主推动)         │
  │                   │  (根因分析)        │                     │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


# ============================================================
# Loop 基础模型
# ============================================================

class LoopPhase(str, Enum):
    """Loop 执行阶段"""
    TRIGGERED = "triggered"      # 已触发
    PLANNING = "planning"        # 规划中
    EXECUTING = "executing"      # 执行中
    EVALUATING = "evaluating"    # 评估中
    LEARNING = "learning"        # 经验沉淀中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    RETRYING = "retrying"        # 重试中
    ABORTED = "aborted"          # 已中止


class LoopPriority(str, Enum):
    """Loop 优先级"""
    CRITICAL = "critical"    # 关键 (系统升级、安全修复)
    HIGH = "high"            # 高 (核心能力提升)
    MEDIUM = "medium"        # 中 (功能增强)
    LOW = "low"              # 低 (探索性改进)


class LoopOutcome(str, Enum):
    """Loop 结果"""
    SUCCESS = "success"              # 成功
    PARTIAL_SUCCESS = "partial"      # 部分成功
    FAILURE = "failure"              # 失败
    DEGRADATION = "degradation"      # 退化 (越改越差)
    NO_CHANGE = "no_change"          # 无变化
    NEEDS_HUMAN = "needs_human"      # 需要人工介入


@dataclass
class LoopTrigger:
    """Loop 触发条件"""
    trigger_id: str
    trigger_type: str              # schedule / event / insight / nudge / manual
    condition: str                 # 触发条件描述
    source: str = ""               # 触发来源
    params: dict = field(default_factory=dict)
    fired_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LoopStep:
    """Loop 执行步骤"""
    step_id: str
    description: str
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    expected_output: str = ""
    actual_output: str = ""
    duration_ms: float = 0
    status: str = "pending"        # pending / running / success / failed
    error: str = ""


@dataclass
class LoopPlan:
    """Loop 执行计划"""
    plan_id: str
    loop_id: str
    goal: str                      # 目标描述
    steps: list[LoopStep] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    fallback_strategy: str = ""    # 失败回退策略
    max_retries: int = 3
    timeout_seconds: int = 600
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LoopExperience:
    """Loop 经验沉淀"""
    experience_id: str
    loop_id: str
    lesson: str                    # 核心教训
    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    root_cause: str = ""           # 根因分析
    should_retry: bool = False
    retry_strategy: str = ""
    skill_created: bool = False    # 是否生成了新技能
    skill_id: str = ""
    tags: list[str] = field(default_factory=list)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LoopResult:
    """Loop 执行结果"""
    loop_id: str
    outcome: LoopOutcome
    phase: LoopPhase
    plan: Optional[LoopPlan] = None
    experience: Optional[LoopExperience] = None
    metrics: dict = field(default_factory=dict)  # 量化指标
    artifacts: list[str] = field(default_factory=list)  # 产出物路径
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0
    error: str = ""


# ============================================================
# Loop 定义
# ============================================================

@dataclass
class Loop:
    """一个自主进化循环"""
    loop_id: str
    name: str
    description: str
    category: str                  # intelligence / skill / prompt / memory / security
    priority: LoopPriority
    trigger: LoopTrigger
    plan: Optional[LoopPlan] = None
    result: Optional[LoopResult] = None
    phase: LoopPhase = LoopPhase.TRIGGERED
    retry_count: int = 0
    max_retries: int = 3
    parent_loop_id: str = ""       # 父 Loop (if nested)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================
# Loop 执行器
# ============================================================

class LoopExecutor:
    """
    Loop 执行器 — 核心执行引擎

    每个 Loop 经历: 触发 → 规划 → 执行 → 评估 → 学习 → 完成/重试
    """

    def __init__(self, experience_dir: str = "data/loop_experiences"):
        self.experience_dir = Path(experience_dir)
        self.experience_dir.mkdir(parents=True, exist_ok=True)
        self._active_loops: dict[str, Loop] = {}
        self._completed_loops: list[LoopResult] = []
        self._experiences: dict[str, LoopExperience] = {}
        self._load_experiences()

    def _load_experiences(self):
        """加载历史经验"""
        exp_file = self.experience_dir / "experiences.json"
        if exp_file.exists():
            try:
                data = json.loads(exp_file.read_text(encoding="utf-8"))
                for eid, edata in data.items():
                    self._experiences[eid] = LoopExperience(**edata)
                logger.info(f"加载 {len(self._experiences)} 条历史经验")
            except Exception as e:
                logger.warning(f"经验加载失败: {e}")

    def _save_experiences(self):
        """持久化经验"""
        exp_file = self.experience_dir / "experiences.json"
        data = {eid: {
            "experience_id": exp.experience_id,
            "loop_id": exp.loop_id,
            "lesson": exp.lesson,
            "what_worked": exp.what_worked,
            "what_failed": exp.what_failed,
            "root_cause": exp.root_cause,
            "should_retry": exp.should_retry,
            "retry_strategy": exp.retry_strategy,
            "skill_created": exp.skill_created,
            "skill_id": exp.skill_id,
            "tags": exp.tags,
            "recorded_at": exp.recorded_at,
        } for eid, exp in self._experiences.items()}
        exp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    async def execute_loop(
        self,
        loop: Loop,
        execute_fn: Callable[[LoopPlan], Awaitable[LoopResult]],
        plan_fn: Optional[Callable[[Loop], Awaitable[LoopPlan]]] = None,
    ) -> LoopResult:
        """
        执行一个完整的 Loop

        Args:
            loop: Loop 定义
            execute_fn: 执行函数 (传入计划, 返回结果)
            plan_fn: 可选的规划函数 (传入Loop, 返回计划)
        """
        loop.phase = LoopPhase.PLANNING
        self._active_loops[loop.loop_id] = loop
        started_at = datetime.now(timezone.utc)

        try:
            # Phase 1: 规划
            if plan_fn:
                loop.plan = await plan_fn(loop)
            elif loop.plan is None:
                loop.plan = LoopPlan(
                    plan_id=f"{loop.loop_id}_plan",
                    loop_id=loop.loop_id,
                    goal=loop.description,
                    steps=[LoopStep(step_id="default", description=loop.description)],
                )

            # Phase 2: 执行
            loop.phase = LoopPhase.EXECUTING
            result = await execute_fn(loop.plan)

            # Phase 3: 评估
            loop.phase = LoopPhase.EVALUATING
            result = self._evaluate(loop, result)

            # Phase 4: 学习
            loop.phase = LoopPhase.LEARNING
            experience = self._extract_experience(loop, result)
            self._experiences[experience.experience_id] = experience
            self._save_experiences()
            result.experience = experience

            # 完成
            if result.outcome == LoopOutcome.FAILURE and loop.retry_count < loop.max_retries:
                loop.phase = LoopPhase.RETRYING
                loop.retry_count += 1
                logger.info(f"Loop {loop.loop_id} 重试 {loop.retry_count}/{loop.max_retries}")
                return await self.execute_loop(loop, execute_fn, plan_fn)

            loop.phase = LoopPhase.COMPLETED if result.outcome == LoopOutcome.SUCCESS else LoopPhase.FAILED
            loop.result = result

        except Exception as e:
            loop.phase = LoopPhase.FAILED
            result = LoopResult(
                loop_id=loop.loop_id,
                outcome=LoopOutcome.FAILURE,
                phase=LoopPhase.FAILED,
                error=str(e),
            )
            logger.error(f"Loop {loop.loop_id} 执行异常: {e}\n{traceback.format_exc()}")

        result.started_at = started_at.isoformat()
        result.completed_at = datetime.now(timezone.utc).isoformat()
        result.duration_ms = (datetime.now(timezone.utc) - started_at).total_seconds() * 1000

        self._completed_loops.append(result)
        self._active_loops.pop(loop.loop_id, None)
        return result

    def _evaluate(self, loop: Loop, result: LoopResult) -> LoopResult:
        """评估 Loop 结果"""
        if result.error:
            result.outcome = LoopOutcome.FAILURE
            return result

        # 若有退化指标，标记为退化
        if result.metrics.get("degradation_detected"):
            result.outcome = LoopOutcome.DEGRADATION
            return result

        # 若关键指标有提升
        if result.metrics.get("improvement_score", 0) > 0:
            result.outcome = LoopOutcome.SUCCESS
        elif result.metrics.get("improvement_score", 0) == 0:
            result.outcome = LoopOutcome.NO_CHANGE
        else:
            result.outcome = LoopOutcome.PARTIAL_SUCCESS

        return result

    def _extract_experience(self, loop: Loop, result: LoopResult) -> LoopExperience:
        """从 Loop 结果中提取经验"""
        import hashlib

        exp_id = hashlib.md5(f"{loop.loop_id}_{result.completed_at}".encode()).hexdigest()[:12]

        experience = LoopExperience(
            experience_id=exp_id,
            loop_id=loop.loop_id,
            lesson="",
            what_worked=[],
            what_failed=[],
            root_cause="",
            tags=[loop.category],
        )

        if result.outcome == LoopOutcome.SUCCESS:
            experience.lesson = f"Loop '{loop.name}' 执行成功: {loop.description}"
            experience.what_worked = [f"策略: {loop.description}"]
            experience.should_retry = False

        elif result.outcome == LoopOutcome.FAILURE:
            experience.lesson = f"Loop '{loop.name}' 执行失败"
            experience.what_failed = [result.error or "未知错误"]
            experience.root_cause = self._analyze_root_cause(result)
            experience.should_retry = loop.retry_count < loop.max_retries
            if experience.should_retry:
                experience.retry_strategy = "降低复杂度或调整参数后重试"

        elif result.outcome == LoopOutcome.DEGRADATION:
            experience.lesson = f"Loop '{loop.name}' 导致退化，立即回滚"
            experience.what_failed = ["性能/质量指标下降"]
            experience.root_cause = "进化方向错误或冲突"
            experience.should_retry = False

        return experience

    def _analyze_root_cause(self, result: LoopResult) -> str:
        """根因分析"""
        if "timeout" in (result.error or "").lower():
            return "执行超时: 任务复杂度超出当前能力边界"
        if "connection" in (result.error or "").lower():
            return "外部依赖不可用: 网络或API异常"
        if "memory" in (result.error or "").lower():
            return "资源不足: 内存或上下文溢出"
        if "permission" in (result.error or "").lower():
            return "权限不足: 需要更高权限执行操作"
        return "未知错误: 需要进一步分析"

    def get_similar_experiences(self, loop: Loop, top_k: int = 5) -> list[LoopExperience]:
        """获取相似 Loop 的历史经验 (用于避免重复失败)"""
        results = []
        for exp in self._experiences.values():
            if loop.category in exp.tags:
                results.append(exp)
        # 按时间倒序
        results.sort(key=lambda x: x.recorded_at, reverse=True)
        return results[:top_k]

    def get_active_loops(self) -> list[Loop]:
        """获取当前活跃的 Loop"""
        return list(self._active_loops.values())

    def get_completed_loops(self, limit: int = 50) -> list[LoopResult]:
        """获取已完成的 Loop 结果"""
        return self._completed_loops[-limit:]


# ============================================================
# Loop 调度器
# ============================================================

class LoopScheduler:
    """
    Loop 调度器 — 管理多 Loop 的并行执行和优先级

    设计参考:
      - Hermes Agent: 定时自动化任务
      - OpenAI Agents SDK: 子Agent手递手切换
    """

    def __init__(self, executor: LoopExecutor):
        self.executor = executor
        self._pending_loops: list[Loop] = []
        self._running_loops: dict[str, asyncio.Task] = {}
        self._max_concurrent: int = 5

    def register(self, loop: Loop):
        """注册 Loop"""
        self._pending_loops.append(loop)
        # 按优先级排序
        priority_order = {
            LoopPriority.CRITICAL: 0,
            LoopPriority.HIGH: 1,
            LoopPriority.MEDIUM: 2,
            LoopPriority.LOW: 3,
        }
        self._pending_loops.sort(key=lambda l: priority_order.get(l.priority, 99))

    async def run_all(
        self,
        execute_fn: Callable[[LoopPlan], Awaitable[LoopResult]],
        plan_fn: Optional[Callable[[Loop], Awaitable[LoopPlan]]] = None,
    ) -> list[LoopResult]:
        """
        并行执行所有已注册的 Loop

        控制并发数，高优先级先执行
        """
        results: list[LoopResult] = []

        while self._pending_loops:
            # 计算可用槽位
            available = self._max_concurrent - len(self._running_loops)
            if available <= 0:
                # 等待任意一个完成
                done, _ = await asyncio.wait(
                    self._running_loops.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    result = task.result()
                    results.append(result)
                    # 清理完成的任务
                    self._running_loops = {
                        k: v for k, v in self._running_loops.items()
                        if not v.done()
                    }
                continue

            # 取出待执行的 Loop
            batch = self._pending_loops[:available]
            self._pending_loops = self._pending_loops[available:]

            for loop in batch:
                task = asyncio.create_task(
                    self.executor.execute_loop(loop, execute_fn, plan_fn)
                )
                self._running_loops[loop.loop_id] = task

        # 等待所有剩余任务完成
        if self._running_loops:
            remaining = await asyncio.gather(*self._running_loops.values(), return_exceptions=True)
            for r in remaining:
                if isinstance(r, Exception):
                    logger.error(f"Loop 执行异常: {r}")
                else:
                    results.append(r)

        return results


# ============================================================
# Nudge Engine — 自主推动机制
# ============================================================

class NudgeEngine:
    """
    Nudge Engine — 自主知识持久化推动

    设计参考:
      - Hermes Agent: periodic nudges to persist knowledge
      - agentmemory: 自动捕获学习内容

    当系统检测到有价值的知识未被持久化时，主动推动写入。
    """

    def __init__(self, executor: LoopExecutor):
        self.executor = executor
        self._nudge_thresholds = {
            "new_skill_opportunity": 3,     # 3次成功类似操作 → 生成技能
            "error_pattern": 2,             # 2次相同错误 → 生成警告
            "knowledge_gap": 1,             # 检测到知识缺口 → 立即学习
        }

    def should_nudge(self, event_type: str, occurrence_count: int) -> bool:
        """判断是否需要推向行动"""
        threshold = self._nudge_thresholds.get(event_type, 5)
        return occurrence_count >= threshold

    async def create_nudge_loop(self, event_type: str, context: dict) -> Optional[Loop]:
        """根据事件类型创建推动 Loop"""
        import hashlib

        loop_id = f"nudge_{event_type}_{hashlib.md5(str(context).encode()).hexdigest()[:8]}"

        if event_type == "new_skill_opportunity":
            return Loop(
                loop_id=loop_id,
                name=f"自动技能创建: {context.get('task_name', 'Unknown')}",
                description=f"从 {context.get('occurrence_count', 0)} 次成功操作中提取可复用技能",
                category="skill",
                priority=LoopPriority.HIGH,
                trigger=LoopTrigger(
                    trigger_id=f"nudge_{loop_id}",
                    trigger_type="nudge",
                    condition="多次成功类似操作",
                    params=context,
                ),
            )

        elif event_type == "error_pattern":
            return Loop(
                loop_id=loop_id,
                name=f"错误模式分析: {context.get('error_type', 'Unknown')}",
                description=f"分析重复出现的错误模式并生成修复方案",
                category="intelligence",
                priority=LoopPriority.CRITICAL,
                trigger=LoopTrigger(
                    trigger_id=f"nudge_{loop_id}",
                    trigger_type="nudge",
                    condition="重复错误模式",
                    params=context,
                ),
            )

        elif event_type == "knowledge_gap":
            return Loop(
                loop_id=loop_id,
                name=f"知识缺口填补: {context.get('topic', 'Unknown')}",
                description=f"检测到知识缺口，主动学习 {context.get('topic', '')}",
                category="intelligence",
                priority=LoopPriority.HIGH,
                trigger=LoopTrigger(
                    trigger_id=f"nudge_{loop_id}",
                    trigger_type="nudge",
                    condition="知识缺口检测",
                    params=context,
                ),
            )

        return None


# ============================================================
# Loop 注册中心
# ============================================================

class LoopRegistry:
    """
    Loop 注册中心 — 管理所有预定义的 Loop 模板

    系统预装以下 Loop 类型:
      - intelligence_gathering: 情报采集 Loop
      - knowledge_synthesis: 知识合成 Loop
      - prompt_evolution: Prompt 进化 Loop
      - skill_creation: 技能创建 Loop
      - memory_consolidation: 记忆巩固 Loop
      - security_audit: 安全审计 Loop
      - performance_benchmark: 性能基准 Loop
    """

    SYSTEM_LOOPS = {
        "intelligence_gathering": {
            "name": "情报采集",
            "description": "从多源采集最新 AI 情报，语义去重后入库",
            "category": "intelligence",
            "priority": LoopPriority.HIGH,
            "trigger_type": "schedule",
            "trigger_condition": "每6小时",
        },
        "knowledge_synthesis": {
            "name": "知识合成",
            "description": "LLM 深度分析采集情报，生成结构化洞察和升级建议",
            "category": "intelligence",
            "priority": LoopPriority.HIGH,
            "trigger_type": "schedule",
            "trigger_condition": "每日",
        },
        "prompt_evolution": {
            "name": "Prompt 进化",
            "description": "GEPA 遗传帕累托优化系统 Prompt，提升质量和效率",
            "category": "prompt",
            "priority": LoopPriority.MEDIUM,
            "trigger_type": "event",
            "trigger_condition": "新洞察积累 > 10 条",
        },
        "skill_creation": {
            "name": "技能创建",
            "description": "从成功任务中自动提取可复用技能",
            "category": "skill",
            "priority": LoopPriority.MEDIUM,
            "trigger_type": "nudge",
            "trigger_condition": "3次成功类似操作",
        },
        "memory_consolidation": {
            "name": "记忆巩固",
            "description": "将短期记忆转为长期记忆，去重压缩",
            "category": "memory",
            "priority": LoopPriority.MEDIUM,
            "trigger_type": "schedule",
            "trigger_condition": "每12小时",
        },
        "security_audit": {
            "name": "安全审计",
            "description": "检查系统安全性，检测异常行为",
            "category": "security",
            "priority": LoopPriority.CRITICAL,
            "trigger_type": "schedule",
            "trigger_condition": "每日",
        },
        "performance_benchmark": {
            "name": "性能基准",
            "description": "运行基准测试，检测性能退化",
            "category": "intelligence",
            "priority": LoopPriority.LOW,
            "trigger_type": "schedule",
            "trigger_condition": "每周",
        },
        "evolution_guard": {
            "name": "进化安全守卫",
            "description": "检测自进化是否导致能力退化或错误积累",
            "category": "security",
            "priority": LoopPriority.CRITICAL,
            "trigger_type": "event",
            "trigger_condition": "每次升级后",
        },
    }

    @classmethod
    def create_system_loop(cls, loop_key: str) -> Optional[Loop]:
        """创建系统预定义 Loop"""
        import hashlib

        if loop_key not in cls.SYSTEM_LOOPS:
            return None

        config = cls.SYSTEM_LOOPS[loop_key]
        loop_id = f"sys_{loop_key}_{hashlib.md5(loop_key.encode()).hexdigest()[:8]}"

        return Loop(
            loop_id=loop_id,
            name=config["name"],
            description=config["description"],
            category=config["category"],
            priority=config["priority"],
            trigger=LoopTrigger(
                trigger_id=f"trigger_{loop_id}",
                trigger_type=config["trigger_type"],
                condition=config["trigger_condition"],
            ),
        )

    @classmethod
    def create_all_system_loops(cls) -> list[Loop]:
        """创建所有系统预定义 Loop"""
        loops = []
        for key in cls.SYSTEM_LOOPS:
            loop = cls.create_system_loop(key)
            if loop:
                loops.append(loop)
        return loops