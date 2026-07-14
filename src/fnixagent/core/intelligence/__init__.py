"""
FnixAgent 智能信息采集与自进化系统 (Intelligence & Auto-Evolution)

设计参考全球顶尖开源项目:
  - Hermes Agent (Nous Research): 技能自动创建 + GEPA遗传帕累托优化 + 双文件记忆 + Nudge Engine
  - OpenClaw: self-improving-agent skill + AutoSkill + ClawHub技能市场
  - SAGE: 强化学习自进化 + skill library
  - GEPA (ICLR 2026 Oral): 遗传帕累托Prompt进化, 比RL好6%, 数据量仅1/35
  - GPT-Researcher (Columbia U, 28k stars): 多Agent协同, 分阶段研究, Tavily+LLM
  - AI-Researcher (HKU): 全自主科研, arXiv/IEEE/ACM/GitHub/HuggingFace多源
  - PaperOrchestra (Google): 多Agent论文写作, 专业分工

架构 (三层体系):
  ┌──────────────────────────────────────────────────────────────────┐
  │  Layer 1: 采集层 (ContinuousCollector)                           │
  │  GitHubDeepCollector │ SemanticScholar │ ArxivEnhanced │ RSS    │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 2: 合成层 (SynthesisEngine)                                │
  │  RuleBasedExtractor → LLMSynthesizer → SynthesisReport          │
  ├──────────────────────────────────────────────────────────────────┤
  │  Layer 3: 进化层 (SelfEvolutionFlywheel)                          │
  │  KnowledgeExtractor → UpgradeEngine → KTG注入 → STP更新 → MFP    │
  └──────────────────────────────────────────────────────────────────┘

使用方式:
  # 手动触发全量采集
  python -m fnixagent.core.intelligence.flywheel --frequency daily

  # 在代码中使用
  from fnixagent.core.intelligence import SelfEvolutionFlywheel
  from fnixagent.core.intelligence import ContinuousCollector
  from fnixagent.core.intelligence import SynthesisEngine

  flywheel = SelfEvolutionFlywheel()
  result = await flywheel.run("daily")

  # 单独运行采集+合成
  collector = ContinuousCollector()
  sources = await collector.collect_daily()
  engine = SynthesisEngine()
  report = await engine.synthesize(sources)
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

__all__ = [
    # 基础采集
    "IntelligenceCollector", "IntelligenceItem", "CollectionResult",
    "SourceType", "Priority", "IntelligenceCategory",
    # 知识+升级
    "KnowledgeExtractor", "KnowledgeItem", "KnowledgeDigest", "FlywheelKnowledgeBase",
    "UpgradeEngine", "UpgradeProposal", "UpgradeType", "UpgradeImpact",
    # 飞轮调度
    "SelfEvolutionFlywheel", "FlywheelState", "ScheduleConfig",
    # 连续采集引擎
    "SourceCategory", "SourceItem",
    "GitHubDeepCollector", "SemanticScholarCollector",
    "ArxivEnhancedCollector", "RSSFeedCollector",
    "ContinuousCollector",
    # LLM 合成引擎
    "InsightType", "ExtractedInsight", "SynthesisReport",
    "RuleBasedExtractor", "LLMSynthesizer", "SynthesisEngine",
]