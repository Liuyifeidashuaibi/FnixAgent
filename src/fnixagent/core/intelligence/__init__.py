"""
FnixAgent ∞ 自进化飞轮 v2.0 — 七层闭环进化体系 (Intelligence & Auto-Evolution)

设计思路全球顶尖项目与前沿论文:
  ┌──────────────────────────────────────────────────────────────────┐
  │  学术前沿:                                                       │
  │  遗传优化 (ICLR 2026 Oral)    → 遗传帕累托Prompt进化, 比RL好6%       │
  │  SIPDO (ICLR 2026)        → 自改进Prompt设计优化闭环             │
  │  KnowRL (ACL 2026)        → 知识增强RL, 模型认知边界自感知       │
  │  Misevolution (上交+普林)  → 自进化"错误进化"风险                │
  │  SCOPE                     → 上下文在线优化, 轨迹合成指南        │
  │  MemRL (2026)             → 运行时RL在情景记忆上自进化            │
  ├──────────────────────────────────────────────────────────────────┤
  │  工业标杆:                                                       │
  │  行业领先方案     → 闭环学习+自动技能+Nudge+训练框架 RL   │
  │  行业实践                 → 自动技能创建+技能市场+Capability Evolver │
  │  OpenAI Agents SDK        → MCP原生+沙盒+子Agent handoff         │
  │  MCP (97M下载/月)         → Agent工具调用标准协议                │
  │  agentmemory (23k★)       → 持久化记忆引擎, 自动捕获             │
  │  记忆服务层/记忆服务             → Agent OS: Context=RAM, 外部=Disk     │
  ├──────────────────────────────────────────────────────────────────┤
  │  新范式:                                                         │
  │  Loop Engineering (Boris) → "不给AI写提示词, 设计Loop驱动AI"     │
  │  Agent-as-a-Judge          → 自进化评估标准, RL优化评估策略      │
  │  研究助手 (28k★)    → 多Agent协同, 分阶段研究              │
  └──────────────────────────────────────────────────────────────────┘

架构 (七层体系):
  ┌──────────────────────────────────────────────────────────────────┐
  │  Layer 7: 自我审判层 (SelfJudge)          ← Agent-as-a-Judge    │
  │  CriteriaEvolver │ MultiDimensionScorer │ ComparativeJudge      │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 6: 技能市场层 (Skill Marketplace)   ← 技能市场    │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 5: 记忆层 (MemoryManager)            ← 记忆服务层/记忆服务        │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 4: 知识合成层 (SynthesisEngine)     ← 研究助手      │
  │  RuleBasedExtractor → LLMSynthesizer → SynthesisReport          │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 3: 安全认知层 (EvolutionGuard)      ← KnowRL+Misevolution │
  │  BoundaryAwareness │ DegradationDetector │ SandboxValidator     │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 2: 遗传进化层 (GeneticEvolver)      ← 遗传优化+SIPDO         │
  │  Gene Encoder │ ParetoFrontier │ Tournament │ Crossover │ Mutate │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 1: 循环工程层 (LoopEngine)          ← 循环工程范式   │
  │  LoopExecutor │ LoopScheduler │ NudgeEngine │ LoopRegistry      │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 0: 宇宙感知层 (ContinuousCollector)  ← 14+信息源          │
  │  GitHub │ arXiv │ Semantic Scholar │ RSS │ MCP │ 论文 │ 新闻    │
  └──────────────────────────────────────────────────────────────────┘

  核心闭环: 感知 → 循环 → 进化 → 安全 → 合成 → 记忆 → 技能 → 审判
            ↑_________________________________________________↓

使用方式:
  from fnixagent.core.intelligence import (
      SelfEvolutionFlywheel,  # 飞轮调度
      LoopEngine,             # 循环工程
      GeneticEvolver,         # 遗传进化
      EvolutionGuard,         # 安全守卫
      SelfJudge,              # 自我审判
      ContinuousCollector,    # 连续采集
      SynthesisEngine,        # 知识合成
      SkillMarketplace,       # 技能市场
      AgentHarness,           # 全方位优化引擎
  )
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from .agent_optimizer import (
    AgentHarness,
    CacheEntry,
    CacheStrategy,
    CircuitState,
    CostCircuitBreaker,
    ErrorCategory,
    ErrorRecoveryEngine,
    ModelConfig,
    ModelRouter,
    ModelTier,
    ParallelExecutor,
    PerformanceMonitor,
    PerformanceSnapshot,
    TaskNode,
    TaskStatus,
    TokenOptimizer,
)
from .collection_pipeline import (
    SOURCES,
    SUPPLEMENTARY_SOURCES,
    AgentRole,
    AgentTask,
    CollectionBatch,
    CollectionMethod,
    DataNormalizer,
    IntelligentScheduler,
    MultiAgentOrchestrator,
    NormalizedItem,
    RawItem,
    ScheduleFrequency,
    SourceConfig,
    SourceTier,
    UnifiedCollector,
)
from .collector import (
    CollectionResult,
    IntelligenceCategory,
    IntelligenceCollector,
    IntelligenceItem,
    Priority,
    SourceType,
)
from .continuous_collector import (
    ArxivEnhancedCollector,
    ContinuousCollector,
    GitHubDeepCollector,
    RSSFeedCollector,
    SemanticScholarCollector,
    SourceCategory,
    SourceItem,
)
from .evolution_guard import (
    BenchmarkSnapshot,
    BoundaryAwareness,
    DegradationDetector,
    DegradationType,
    EvolutionGuard,
    GuardLevel,
    RollbackManager,
    SandboxValidator,
)
from .flywheel import FlywheelState, ScheduleConfig, SelfEvolutionFlywheel
from .genetic_evolver import (
    Chromosome,
    EvolutionConfig,
    EvolutionResult,
    Gene,
    GeneticEvolver,
    GeneticOperators,
    GeneType,
    ParetoFrontier,
    TrajectoryDrivenEvolution,
)
from .integration import IntelligenceIntegrator
from .knowledge import FlywheelKnowledgeBase, KnowledgeDigest, KnowledgeExtractor, KnowledgeItem
from .loop_engine import (
    Loop,
    LoopExecutor,
    LoopExperience,
    LoopOutcome,
    LoopPhase,
    LoopPlan,
    LoopPriority,
    LoopRegistry,
    LoopResult,
    LoopScheduler,
    LoopStep,
    LoopTrigger,
    NudgeEngine,
)
from .memory_manager import IntelligenceMemoryManager, MemoryEntry
from .self_judge import (
    ComparativeJudge,
    CriteriaEvolver,
    EvaluateDimension,
    EvolvingCriteria,
    JudgeVerdict,
    MultiDimensionScorer,
    RegressionDetector,
    SelfJudge,
)
from .self_optimizing import (
    FewShotExample,
    SelfOptimizingLibrary,
    extract_examples_from_trace,
    success_score,
)
from .skill_marketplace import (
    Skill,
    SkillCategory,
    SkillEvolutionFactory,
    SkillGene,
    SkillMarketplace,
    SkillStatus,
)
from .synthesizer import (
    ExtractedInsight,
    InsightType,
    LLMSynthesizer,
    RuleBasedExtractor,
    SynthesisEngine,
    SynthesisReport,
)
from .upgrade import UpgradeEngine, UpgradeImpact, UpgradeProposal, UpgradeType

__all__ = [
    # === 基础采集 ===
    "IntelligenceCollector",
    "IntelligenceItem",
    "CollectionResult",
    "SourceType",
    "Priority",
    "IntelligenceCategory",
    # === 知识+升级 ===
    "KnowledgeExtractor",
    "KnowledgeItem",
    "KnowledgeDigest",
    "FlywheelKnowledgeBase",
    "UpgradeEngine",
    "UpgradeProposal",
    "UpgradeType",
    "UpgradeImpact",
    # === 飞轮调度 ===
    "SelfEvolutionFlywheel",
    "FlywheelState",
    "ScheduleConfig",
    # === 连续采集引擎 ===
    "SourceCategory",
    "SourceItem",
    "GitHubDeepCollector",
    "SemanticScholarCollector",
    "ArxivEnhancedCollector",
    "RSSFeedCollector",
    "ContinuousCollector",
    # === LLM 合成引擎 ===
    "InsightType",
    "ExtractedInsight",
    "SynthesisReport",
    "RuleBasedExtractor",
    "LLMSynthesizer",
    "SynthesisEngine",
    # === v2.0: Loop 循环工程层 ===
    "LoopPhase",
    "LoopPriority",
    "LoopOutcome",
    "Loop",
    "LoopTrigger",
    "LoopStep",
    "LoopPlan",
    "LoopExperience",
    "LoopResult",
    "LoopExecutor",
    "LoopScheduler",
    "NudgeEngine",
    "LoopRegistry",
    # === v2.0: Genetic 遗传进化层 ===
    "GeneType",
    "Gene",
    "Chromosome",
    "ParetoFrontier",
    "GeneticOperators",
    "EvolutionConfig",
    "EvolutionResult",
    "GeneticEvolver",
    "TrajectoryDrivenEvolution",
    # === v2.0: Evolution Guard 安全认知层 ===
    "GuardLevel",
    "DegradationType",
    "BenchmarkSnapshot",
    "BoundaryAwareness",
    "DegradationDetector",
    "SandboxValidator",
    "RollbackManager",
    "EvolutionGuard",
    # === v2.0: Self-Judge 自我审判层 ===
    "EvaluateDimension",
    "EvolvingCriteria",
    "JudgeVerdict",
    "MultiDimensionScorer",
    "ComparativeJudge",
    "RegressionDetector",
    "CriteriaEvolver",
    "SelfJudge",
    # === v2.0: Collection Pipeline 采集管道 ===
    "SourceTier",
    "CollectionMethod",
    "SourceConfig",
    "SOURCES",
    "SUPPLEMENTARY_SOURCES",
    "RawItem",
    "NormalizedItem",
    "CollectionBatch",
    "DataNormalizer",
    "UnifiedCollector",
    "AgentRole",
    "AgentTask",
    "MultiAgentOrchestrator",
    "ScheduleFrequency",
    "IntelligentScheduler",
    # === v2.0: Agent Optimizer 全方位优化引擎 ===
    "CacheStrategy",
    "CacheEntry",
    "TokenOptimizer",
    "ModelTier",
    "ModelConfig",
    "ModelRouter",
    "TaskStatus",
    "TaskNode",
    "ParallelExecutor",
    "CircuitState",
    "CostCircuitBreaker",
    "ErrorCategory",
    "ErrorRecoveryEngine",
    "PerformanceSnapshot",
    "PerformanceMonitor",
    "AgentHarness",
    # === v2.0: Skill Marketplace 技能市场 ===
    "SkillStatus",
    "SkillCategory",
    "SkillGene",
    "Skill",
    "SkillMarketplace",
    "SkillEvolutionFactory",
    # === Spec 6: Self-Optimizing 离线轨迹优化 ===
    "FewShotExample",
    "SelfOptimizingLibrary",
    "success_score",
    "extract_examples_from_trace",
    # === v2.0: L5 记忆层 + 七层集成协调层 ===
    "IntelligenceMemoryManager",
    "MemoryEntry",
    "IntelligenceIntegrator",
]
