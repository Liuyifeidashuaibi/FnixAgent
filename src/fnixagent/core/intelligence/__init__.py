"""
FnixAgent ∞ 自进化飞轮 v2.0 — 七层闭环进化体系 (Intelligence & Auto-Evolution)

设计参考全球顶尖项目与前沿论文:
  ┌──────────────────────────────────────────────────────────────────┐
  │  学术前沿:                                                       │
  │  GEPA (ICLR 2026 Oral)    → 遗传帕累托Prompt进化, 比RL好6%       │
  │  SIPDO (ICLR 2026)        → 自改进Prompt设计优化闭环             │
  │  KnowRL (ACL 2026)        → 知识增强RL, 模型认知边界自感知       │
  │  Misevolution (上交+普林)  → 自进化"错误进化"风险                │
  │  SCOPE                     → 上下文在线优化, 轨迹合成指南        │
  │  MemRL (2026)             → 运行时RL在情景记忆上自进化            │
  ├──────────────────────────────────────────────────────────────────┤
  │  工业标杆:                                                       │
  │  Hermes Agent (128k★)     → 闭环学习+自动技能+Nudge+Atropos RL   │
  │  OpenClaw                 → AutoSkill+ClawHub+Capability Evolver │
  │  OpenAI Agents SDK        → MCP原生+沙盒+子Agent handoff         │
  │  MCP (97M下载/月)         → Agent工具调用标准协议                │
  │  agentmemory (23k★)       → 持久化记忆引擎, 自动捕获             │
  │  Letta/MemGPT             → Agent OS: Context=RAM, 外部=Disk     │
  ├──────────────────────────────────────────────────────────────────┤
  │  新范式:                                                         │
  │  Loop Engineering (Boris) → "不给AI写提示词, 设计Loop驱动AI"     │
  │  Agent-as-a-Judge          → 自进化评估标准, RL优化评估策略      │
  │  GPT-Researcher (28k★)    → 多Agent协同, 分阶段研究              │
  └──────────────────────────────────────────────────────────────────┘

架构 (七层体系):
  ┌──────────────────────────────────────────────────────────────────┐
  │  Layer 7: 自我审判层 (SelfJudge)          ← Agent-as-a-Judge    │
  │  CriteriaEvolver │ MultiDimensionScorer │ ComparativeJudge      │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 6: 技能市场层 (Skill Marketplace)   ← OpenClaw ClawHub    │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 5: 记忆操作系统 (Memory OS)         ← Letta/MemGPT        │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 4: 知识合成层 (SynthesisEngine)     ← GPT-Researcher      │
  │  RuleBasedExtractor → LLMSynthesizer → SynthesisReport          │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 3: 安全认知层 (EvolutionGuard)      ← KnowRL+Misevolution │
  │  BoundaryAwareness │ DegradationDetector │ SandboxValidator     │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 2: 遗传进化层 (GeneticEvolver)      ← GEPA+SIPDO         │
  │  Gene Encoder │ ParetoFrontier │ Tournament │ Crossover │ Mutate │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 1: 循环工程层 (LoopEngine)          ← Boris Cherny 范式   │
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
  )
"""

from .collector import IntelligenceCollector, IntelligenceItem, CollectionResult, SourceType, Priority, IntelligenceCategory
from .knowledge import KnowledgeExtractor, KnowledgeItem, KnowledgeDigest, FlywheelKnowledgeBase
from .upgrade import UpgradeEngine, UpgradeProposal, UpgradeType, UpgradeImpact
from .flywheel import SelfEvolutionFlywheel, FlywheelState, ScheduleConfig
from .continuous_collector import (
    SourceCategory, SourceItem,
    GitHubDeepCollector, SemanticScholarCollector,
    ArxivEnhancedCollector, RSSFeedCollector,
    ContinuousCollector,
)
from .synthesizer import (
    InsightType, ExtractedInsight, SynthesisReport,
    RuleBasedExtractor, LLMSynthesizer, SynthesisEngine,
)
from .loop_engine import (
    LoopPhase, LoopPriority, LoopOutcome,
    Loop, LoopTrigger, LoopStep, LoopPlan,
    LoopExperience, LoopResult,
    LoopExecutor, LoopScheduler, NudgeEngine, LoopRegistry,
)
from .genetic_evolver import (
    GeneType, Gene, Chromosome,
    ParetoFrontier, GeneticOperators,
    EvolutionConfig, EvolutionResult,
    GeneticEvolver, TrajectoryDrivenEvolution,
)
from .evolution_guard import (
    GuardLevel, DegradationType, BenchmarkSnapshot,
    BoundaryAwareness, DegradationDetector,
    SandboxValidator, RollbackManager, EvolutionGuard,
)
from .self_judge import (
    EvaluateDimension, EvolvingCriteria, JudgeVerdict,
    MultiDimensionScorer, ComparativeJudge,
    RegressionDetector, CriteriaEvolver, SelfJudge,
)

__all__ = [
    # === 基础采集 ===
    "IntelligenceCollector", "IntelligenceItem", "CollectionResult",
    "SourceType", "Priority", "IntelligenceCategory",
    # === 知识+升级 ===
    "KnowledgeExtractor", "KnowledgeItem", "KnowledgeDigest", "FlywheelKnowledgeBase",
    "UpgradeEngine", "UpgradeProposal", "UpgradeType", "UpgradeImpact",
    # === 飞轮调度 ===
    "SelfEvolutionFlywheel", "FlywheelState", "ScheduleConfig",
    # === 连续采集引擎 ===
    "SourceCategory", "SourceItem",
    "GitHubDeepCollector", "SemanticScholarCollector",
    "ArxivEnhancedCollector", "RSSFeedCollector",
    "ContinuousCollector",
    # === LLM 合成引擎 ===
    "InsightType", "ExtractedInsight", "SynthesisReport",
    "RuleBasedExtractor", "LLMSynthesizer", "SynthesisEngine",
    # === v2.0: Loop 循环工程层 ===
    "LoopPhase", "LoopPriority", "LoopOutcome",
    "Loop", "LoopTrigger", "LoopStep", "LoopPlan",
    "LoopExperience", "LoopResult",
    "LoopExecutor", "LoopScheduler", "NudgeEngine", "LoopRegistry",
    # === v2.0: Genetic 遗传进化层 ===
    "GeneType", "Gene", "Chromosome",
    "ParetoFrontier", "GeneticOperators",
    "EvolutionConfig", "EvolutionResult",
    "GeneticEvolver", "TrajectoryDrivenEvolution",
    # === v2.0: Evolution Guard 安全认知层 ===
    "GuardLevel", "DegradationType", "BenchmarkSnapshot",
    "BoundaryAwareness", "DegradationDetector",
    "SandboxValidator", "RollbackManager", "EvolutionGuard",
    # === v2.0: Self-Judge 自我审判层 ===
    "EvaluateDimension", "EvolvingCriteria", "JudgeVerdict",
    "MultiDimensionScorer", "ComparativeJudge",
    "RegressionDetector", "CriteriaEvolver", "SelfJudge",
]