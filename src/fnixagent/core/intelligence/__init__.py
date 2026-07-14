"""
FnixAgent 智能信息采集与自进化系统 (Intelligence & Auto-Evolution)

设计参考顶尖开源项目:
  - Hermes Agent (Nous Research): 技能自动创建 + GEPA遗传帕累托优化 + 双文件记忆 + Nudge Engine
  - OpenClaw: self-improving-agent skill + AutoSkill + ClawHub技能市场
  - SAGE: 强化学习自进化 + skill library
  - GEPA (ICLR 2026 Oral): 遗传帕累托Prompt进化, 比RL好6%, 数据量仅1/35
  - evotest: 进化测试时学习, 自改进Agent系统

架构:
  IntelligenceCollector   → 多源信息采集 (GitHub/arXiv/博客/社区)
  KnowledgeExtractor      → 知识提炼, 相关性评分, 分类排序
  FlywheelKnowledgeBase   → 持久化知识库, 版本管理
  UpgradeEngine           → 差距分析, 升级建议生成, 执行追踪
  SelfEvolutionFlywheel   → 调度引擎, 闭环驱动

使用方式:
  # 手动触发
  python -m fnixagent.core.intelligence.flywheel --frequency daily

  # 在代码中使用
  from fnixagent.core.intelligence import SelfEvolutionFlywheel
  flywheel = SelfEvolutionFlywheel()
  result = await flywheel.run("daily")
"""

from .collector import IntelligenceCollector, IntelligenceItem, CollectionResult, SourceType, Priority, IntelligenceCategory
from .knowledge import KnowledgeExtractor, KnowledgeItem, KnowledgeDigest, FlywheelKnowledgeBase
from .upgrade import UpgradeEngine, UpgradeProposal, UpgradeType, UpgradeImpact
from .flywheel import SelfEvolutionFlywheel, FlywheelState, ScheduleConfig

__all__ = [
    "IntelligenceCollector", "IntelligenceItem", "CollectionResult",
    "SourceType", "Priority", "IntelligenceCategory",
    "KnowledgeExtractor", "KnowledgeItem", "KnowledgeDigest", "FlywheelKnowledgeBase",
    "UpgradeEngine", "UpgradeProposal", "UpgradeType", "UpgradeImpact",
    "SelfEvolutionFlywheel", "FlywheelState", "ScheduleConfig",
]