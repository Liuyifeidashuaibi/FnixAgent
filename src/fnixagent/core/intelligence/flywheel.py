"""
自进化飞轮调度 — 定时触发，采集→提炼→生成升级建议，形成闭环

飞轮架构（借鉴自顶尖开源项目设计）：

```
采集阶段 (Collector)
  ↓
提炼阶段 (Extractor/KnowledgeBase)
  ↓
升级建议生成 (UpgradeEngine)
  ↓
审批 → 实现 → 沉淀 → 下一轮循环
```

调度频率:
  - 每天: GitHub Trending + arXiv 新论文 + Hacker News
  - 每周: 监控仓库发布 + 技术博客 + Reddit 讨论
  - 每月: 会议论文 + 协议更新 + 领域全景

v2.0 集成: 与 EvolutionMaster 进化主控器配合，形成完整七层闭环
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from croniter import croniter
from pydantic import BaseModel

from .collector import IntelligenceCollector
from .knowledge import KnowledgeExtractor, FlywheelKnowledgeBase
from .upgrade import UpgradeEngine, UpgradeProposal

if TYPE_CHECKING:
    from .evolution_master import EvolutionMaster

logger = logging.getLogger(__name__)


# ============================================================
# 调度频率
# ============================================================

class ScheduleConfig(BaseModel):
    """飞轮调度配置"""
    daily_cron: str = "0 6 * * *"      # 每天早上 6:00 UTC+8
    weekly_cron: str = "0 8 * * 1"    # 每周一早上 8:00
    monthly_cron: str = "0 10 1 * *"  # 每月第一天 10:00
    max_items_per_run: int = 50
    enabled: bool = True


# ============================================================
# 飞轮状态
# ============================================================

class FlywheelState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COLLECTING = "collecting"
    EXTRACTING = "extracting"
    GENERATING_PROPOSALS = "generating_proposals"
    COMPLETED = "completed"
    ERROR = "error"


# ============================================================
# 主飞轮控制器
# ============================================================

class SelfEvolutionFlywheel:
    """自进化飞轮 — 持续收集情报 → 提炼知识 → 生成升级建议 → 闭环驱动"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        config: Optional[ScheduleConfig] = None,
    ):
        self.config = config or ScheduleConfig()
        self.state = FlywheelState.IDLE
        self.last_run: Optional[str] = None
        self.last_error: Optional[str] = None
        self._collector: Optional[IntelligenceCollector] = None
        self._extractor: Optional[KnowledgeExtractor] = None
        self._kb: Optional[FlywheelKnowledgeBase] = None
        self._upgrade_engine: Optional[UpgradeEngine] = None

    @property
    def kb(self) -> FlywheelKnowledgeBase:
        if self._kb is None:
            self._kb = FlywheelKnowledgeBase()
        return self._kb

    @property
    def upgrade_engine(self) -> UpgradeEngine:
        if self._upgrade_engine is None:
            self._upgrade_engine = UpgradeEngine(self.kb)
        return self._upgrade_engine

    @property
    def collector(self) -> IntelligenceCollector:
        if self._collector is None:
            self._collector = IntelligenceCollector()
        return self._collector

    @property
    def extractor(self) -> KnowledgeExtractor:
        if self._extractor is None:
            self._extractor = KnowledgeExtractor()
        return self._extractor

    async def run(self, frequency: str = "daily") -> dict:
        """运行一次飞轮周期"""
        if not self.config.enabled:
            return {"status": "disabled", "message": "Flywheel disabled"}

        self.state = FlywheelState.RUNNING
        logger.info(f"Starting {frequency} flywheel cycle")

        try:
            # 1. 采集
            self.state = FlywheelState.COLLECTING
            total_items = await self.collector.collect_and_save(frequency)
            logger.info(f"Collected {total_items} items")

            # 2. 提炼
            self.state = FlywheelState.EXTRACTING
            last_collect_file = self._get_latest_collect(frequency)
            with open(last_collect_file, "r", encoding="utf-8") as f:
                collected = json.load(f)
            digest = self.extractor.extract_from_collection(collected)
            digest_path = self.extractor.save_digest(digest)
            logger.info(f"Extracted digest: {digest.total_items} items, {digest.actionable_items} actionable")

            # 3. 生成升级建议
            self.state = FlywheelState.GENERATING_PROPOSALS
            pending = [
                k for k in digest.critical_items + digest.high_items
                if k.relevance_score >= 0.5
            ]
            proposals = self.upgrade_engine.generate_batch(pending)

            # 完成
            self.state = FlywheelState.COMPLETED
            self.last_run = datetime.now(timezone.utc).isoformat()
            result = {
                "status": "completed",
                "frequency": frequency,
                "total_items_collected": total_items,
                "total_items_relevant": digest.total_items,
                "proposals_generated": len(proposals),
                "critical_proposals": [p.proposal_id for p in proposals if p.impact.value == "critical"],
                "digest_path": digest_path,
                "proposals": [p.proposal_id for p in proposals],
                "last_run": self.last_run,
            }
            logger.info(f"Flywheel completed: {len(proposals)} proposals generated")
            return result

        except Exception as e:
            self.state = FlywheelState.ERROR
            self.last_error = str(e)
            logger.error(f"Flywheel error: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }
        finally:
            if self._collector:
                await self._collector.close()

    def _get_latest_collect(self, frequency: str) -> Path:
        intelligence_dir = Path(__file__).parent.parent.parent.parent / "assets" / "intelligence"
        files = sorted(
            intelligence_dir.glob(f"intelligence_{frequency}_*.json"),
            reverse=True,
            key=lambda p: p.stat().st_mtime
        )
        return files[0]

    def should_run_now(self) -> tuple[bool, str]:
        """判断当前是否应该触发运行"""
        if not self.config.enabled:
            return False, "disabled"

        # 检查上次运行时间
        if self.last_run is None:
            return True, "never run before"

        # 根据频率判断
        import datetime as dt_module
        last_dt = datetime.fromisoformat(self.last_run)
        now = datetime.now(timezone.utc)
        delta = now - last_dt

        if delta < timedelta(hours=12):
            return False, f"last run {delta.total_seconds() / 3600:.1f}h ago, too soon"

        if delta > timedelta(days=31):
            return True, "monthly overdue"
        if delta > timedelta(days=7):
            return True, "weekly overdue"
        # 每天至少一次
        if delta > timedelta(hours=24):
            return True, "daily overdue"

        return False, f"last run {delta.total_seconds() / 3600:.1f}h ago"

    def get_next_run_time(self, base_time: Optional[datetime] = None) -> datetime:
        """计算下次运行时间"""
        base = base_time or datetime.now(timezone.utc)
        next_times = []

        # daily
        iter_daily = croniter(self.config.daily_cron, base)
        next_times.append(iter_daily.get_next(datetime))

        # weekly
        iter_weekly = croniter(self.config.weekly_cron, base)
        next_times.append(iter_weekly.get_next(datetime))

        # monthly
        iter_monthly = croniter(self.config.monthly_cron, base)
        next_times.append(iter_monthly.get_next(datetime))

        return min(next_times)

    def get_statistics(self) -> dict:
        """飞轮整体统计"""
        return {
            "state": self.state.value,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "knowledge_stats": self.kb.get_statistics(),
            "upgrade_stats": self.upgrade_engine.get_statistics(),
            "config": self.config.model_dump(),
        }

    # ============================================================
    # v2.0: 进化主控器集成
    # ============================================================

    async def run_with_evolution_master(self, frequency: str = "daily") -> dict:
        """
        使用进化主控器运行完整七层闭环进化周期

        这是推荐的运行方式，整合了所有2026年前沿进化算法：
        - Layer 0: 感知采集 (30+信息源)
        - Layer 1: 循环工程 (8个预定义Loop)
        - Layer 2: 遗传进化 (GEPA遗传帕累托)
        - Layer 3: 安全检查 (KnowRL+Misevolution)
        - Layer 4: 知识合成 (GPT-Researcher风格)
        - Layer 5: 记忆巩固 (Letta/MemGPT三层)
        - Layer 6: 技能进化 (OpenClaw AutoSkill)
        - Layer 7: 自我审判 (Agent-as-a-Judge+RQGM)
        """
        from .evolution_master import EvolutionMaster

        master = EvolutionMaster(
            data_dir=str(Path(__file__).parent.parent.parent.parent / "data" / "evolution")
        )
        return await master.run_full_evolution_cycle(
            trigger_source="schedule"
        )


# ============================================================
# 入口
# ============================================================

async def main():
    """CLI 入口：手动触发一次飞轮"""
    import argparse
    parser = argparse.ArgumentParser(description="FnixAgent Self-Evolution Flywheel")
    parser.add_argument("--frequency", "-f", default="daily", choices=["daily", "weekly", "monthly"])
    args = parser.parse_args()

    flywheel = SelfEvolutionFlywheel()
    result = await flywheel.run(args.frequency)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())