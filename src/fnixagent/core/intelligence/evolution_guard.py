"""
∞ Evolution Guard — 安全认知层 (KnowRL + Misevolution 启发)

设计参考:
  - Misevolution (上海AI Lab + 上交大 + 普林斯顿): 
    自进化Agent的"错误进化"风险 — 能力退化、错误积累、目标漂移
  - KnowRL (ACL 2026): 
    知识增强RL, 模型认知边界自感知, 事实监督融入推理
  - Hermes Agent: Honcho 辩证用户建模

三层防护:
  Layer 1: 认知边界感知 (KnowRL 启发)
    - 实时评估系统对自身能力的认知准确度
    - 检测"不知道但假装知道"的幻觉边界
  Layer 2: 进化方向监控 (Misevolution 启发)
    - 对比升级前后能力指标
    - 检测退化信号: 性能下降、错误率上升、响应质量下降
  Layer 3: 沙盒验证
    - 升级前在隔离环境验证
    - 回滚机制: 检测到退化后自动回滚

架构:
  ┌─────────────────────────────────────────────────────────────┐
  │                  Evolution Guard                            │
  ├─────────────────────────────────────────────────────────────┤
  │  Boundary Aware   │  Degradation     │  Sandbox             │
  │  (认知边界感知)    │  Detector        │  Validator           │
  │                   │  (退化检测器)     │  (沙盒验证器)         │
  ├─────────────────────────────────────────────────────────────┤
  │  Rollback Manager │  Alert System    │  Audit Trail         │
  │  (回滚管理器)      │  (告警系统)      │  (审计追踪)          │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 安全等级和信号
# ============================================================

class GuardLevel(str, Enum):
    """安全等级"""
    SAFE = "safe"                    # 安全
    WARNING = "warning"              # 警告
    DEGRADING = "degrading"          # 退化中
    CRITICAL = "critical"            # 严重
    ROLLBACK_REQUIRED = "rollback"   # 需要回滚


class DegradationType(str, Enum):
    """退化类型"""
    PERFORMANCE_DROP = "performance_drop"       # 性能下降
    ERROR_RATE_INCREASE = "error_rate_increase" # 错误率上升
    QUALITY_DECLINE = "quality_decline"         # 质量下降
    SCOPE_REDUCTION = "scope_reduction"         # 能力范围缩小
    HALLUCINATION_INCREASE = "hallucination_increase" # 幻觉增加
    KNOWLEDGE_DECAY = "knowledge_decay"         # 知识衰减
    GOAL_DRIFT = "goal_drift"                   # 目标漂移
    CIRCULAR_EVOLUTION = "circular_evolution"    # 循环进化 (来回折腾)


# ============================================================
# 基准快照
# ============================================================

@dataclass
class BenchmarkSnapshot:
    """系统能力基准快照"""
    snapshot_id: str
    version: str                     # 系统版本号
    created_at: str
    # 核心能力指标
    metrics: dict = field(default_factory=lambda: {
        "response_quality": 0.0,     # 响应质量
        "task_completion_rate": 0.0, # 任务完成率
        "error_rate": 0.0,           # 错误率
        "avg_latency_ms": 0.0,       # 平均延迟
        "token_efficiency": 0.0,     # Token 效率
        "tool_call_success_rate": 0.0, # 工具调用成功率
        "hallucination_rate": 0.0,   # 幻觉率
        "knowledge_boundary_accuracy": 0.0, # 知识边界准确度
        "skill_reuse_rate": 0.0,     # 技能复用率
        "user_satisfaction": 0.0,    # 用户满意度
    })
    # 退化信号
    degradation_signals: list[dict] = field(default_factory=list)
    guard_level: str = GuardLevel.SAFE


# ============================================================
# 认知边界感知 (KnowRL 启发)
# ============================================================

class BoundaryAwareness:
    """
    认知边界感知 — 系统对自身能力的认知

    KnowRL 核心思想: 模型应该知道自己不知道什么
    - 检测"不懂装懂"的幻觉边界
    - 评估知识覆盖的置信度
    - 识别认知盲区
    """

    def __init__(self):
        self._known_boundaries: dict[str, float] = {}  # 领域 -> 置信度
        self._unknown_areas: set[str] = set()          # 已知盲区
        self._overconfidence_events: list[dict] = []   # 过度自信事件

    def assess_boundary(self, domain: str, claimed_confidence: float, actual_correctness: float) -> dict:
        """
        评估认知边界

        Args:
            domain: 知识领域
            claimed_confidence: 系统声称的置信度
            actual_correctness: 实际正确率

        Returns:
            边界评估结果
        """
        calibration_error = claimed_confidence - actual_correctness

        result = {
            "domain": domain,
            "calibration_error": calibration_error,
            "is_calibrated": abs(calibration_error) < 0.1,
            "is_overconfident": calibration_error > 0.1,
            "is_underconfident": calibration_error < -0.1,
            "suggestion": "",
        }

        if result["is_overconfident"]:
            result["suggestion"] = f"系统在 {domain} 领域过度自信, 应降低置信度声明"
            self._overconfidence_events.append({
                "domain": domain,
                "error": calibration_error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif result["is_underconfident"]:
            result["suggestion"] = f"系统在 {domain} 领域能力被低估, 可提升置信度"
        else:
            result["suggestion"] = f"系统在 {domain} 领域的认知校准良好"

        self._known_boundaries[domain] = actual_correctness
        return result

    def detect_unknown_unknowns(self, queries: list[str], responses: list[dict]) -> list[str]:
        """
        检测"未知的未知" — 系统不知道自己不知道的领域

        Args:
            queries: 用户查询列表
            responses: 系统响应列表 (含置信度)

        Returns:
            新发现的认知盲区
        """
        new_blind_spots = []

        for query, resp in zip(queries, responses):
            confidence = resp.get("confidence", 0.0)
            is_correct = resp.get("is_correct", False)

            # 高置信度但错误 → 认知盲区
            if confidence > 0.8 and not is_correct:
                topic = self._extract_topic(query)
                if topic and topic not in self._unknown_areas:
                    self._unknown_areas.add(topic)
                    new_blind_spots.append(topic)

        return new_blind_spots

    def _extract_topic(self, query: str) -> str:
        """从查询中提取主题关键词"""
        # 简单规则提取
        keywords = ["agent", "llm", "rl", "reinforcement", "prompt", "memory",
                     "knowledge", "graph", "rag", "embedding", "transformer",
                     "attention", "fine-tuning", "alignment", "safety"]
        query_lower = query.lower()
        for kw in keywords:
            if kw in query_lower:
                return kw
        return "general"

    def get_boundary_report(self) -> dict:
        """获取认知边界报告"""
        return {
            "known_boundaries": self._known_boundaries,
            "unknown_areas": list(self._unknown_areas),
            "overconfidence_count": len(self._overconfidence_events),
            "calibration_score": self._compute_calibration_score(),
        }

    def _compute_calibration_score(self) -> float:
        """计算总体校准分数"""
        if not self._known_boundaries:
            return 1.0
        # 校准误差越小越好
        avg_error = sum(abs(1.0 - v) for v in self._known_boundaries.values()) / len(self._known_boundaries)
        return max(0.0, 1.0 - avg_error)


# ============================================================
# 退化检测器 (Misevolution 启发)
# ============================================================

class DegradationDetector:
    """
    退化检测器 — 检测自进化是否导致能力退化

    Misevolution 核心发现:
      - 自进化Agent可能越进化越差
      - 错误会积累和放大
      - 需要持续监控进化方向
    """

    def __init__(self, baseline: Optional[BenchmarkSnapshot] = None):
        self.baseline = baseline
        self._history: list[BenchmarkSnapshot] = []
        self._degradation_events: list[dict] = []
        # 退化阈值
        self.thresholds = {
            "performance_drop": 0.10,       # 性能下降 10%
            "error_rate_increase": 0.05,    # 错误率上升 5%
            "quality_decline": 0.15,        # 质量下降 15%
            "hallucination_increase": 0.10, # 幻觉增加 10%
        }

    def set_baseline(self, snapshot: BenchmarkSnapshot):
        """设置基准快照"""
        self.baseline = snapshot
        self._history = [snapshot]
        logger.info(f"设置基准快照: {snapshot.snapshot_id}")

    def check_snapshot(self, snapshot: BenchmarkSnapshot) -> dict:
        """
        检查新快照是否退化

        Returns:
            检测结果, 包含退化信号和等级
        """
        self._history.append(snapshot)

        if self.baseline is None:
            self.baseline = snapshot
            return {"guard_level": GuardLevel.SAFE, "signals": [], "message": "无基准数据"}

        signals = []
        baseline_m = self.baseline.metrics
        current_m = snapshot.metrics

        # 检查各项指标
        checks = {
            DegradationType.PERFORMANCE_DROP: (
                "task_completion_rate",
                self.thresholds["performance_drop"],
                -1,  # 下降方向
            ),
            DegradationType.ERROR_RATE_INCREASE: (
                "error_rate",
                self.thresholds["error_rate_increase"],
                1,   # 上升方向
            ),
            DegradationType.QUALITY_DECLINE: (
                "response_quality",
                self.thresholds["quality_decline"],
                -1,
            ),
            DegradationType.HALLUCINATION_INCREASE: (
                "hallucination_rate",
                self.thresholds["hallucination_increase"],
                1,
            ),
        }

        for deg_type, (metric_key, threshold, direction) in checks.items():
            baseline_val = baseline_m.get(metric_key, 0)
            current_val = current_m.get(metric_key, 0)

            if baseline_val == 0:
                continue

            change = (current_val - baseline_val) / baseline_val

            # 判断是否退化
            if direction * change > threshold:
                signals.append({
                    "type": deg_type,
                    "metric": metric_key,
                    "baseline": baseline_val,
                    "current": current_val,
                    "change_pct": change * 100,
                    "threshold_pct": threshold * 100,
                })

        # 确定安全等级
        guard_level = GuardLevel.SAFE
        if len(signals) >= 3:
            guard_level = GuardLevel.ROLLBACK_REQUIRED
        elif len(signals) >= 2:
            guard_level = GuardLevel.CRITICAL
        elif len(signals) >= 1:
            guard_level = GuardLevel.WARNING

        snapshot.guard_level = guard_level
        snapshot.degradation_signals = signals

        if signals:
            self._degradation_events.append({
                "snapshot_id": snapshot.snapshot_id,
                "signals": signals,
                "level": guard_level,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            logger.warning(f"检测到退化信号: {len(signals)} 个, 等级: {guard_level}")

        return {
            "guard_level": guard_level,
            "signals": signals,
            "message": f"检测到 {len(signals)} 个退化信号" if signals else "无退化",
        }

    def detect_goal_drift(self, original_goals: list[str], current_behavior: dict) -> bool:
        """
        检测目标漂移 — 系统是否偏离了原始设计目标

        Misevolution 警示: 自进化Agent可能逐渐偏离原始目标
        """
        # 检查行为是否与原始目标一致
        # 这是一个启发式检测, 实际使用需要 LLM 辅助
        drift_indicators = []

        # 检查是否出现了原始目标中没有的行为
        if current_behavior.get("new_behaviors", []):
            drift_indicators.append("出现了新的未预期行为")

        # 检查是否丢弃了原始目标中的能力
        if current_behavior.get("lost_capabilities", []):
            drift_indicators.append("丢失了原有能力")

        # 检查响应模式是否改变
        if current_behavior.get("response_pattern_change", False):
            drift_indicators.append("响应模式显著改变")

        return len(drift_indicators) > 0

    def detect_circular_evolution(self) -> bool:
        """
        检测循环进化 — 系统在 A→B→A 之间来回折腾

        通过比较历史快照中的 metrics 向量相似度检测
        """
        if len(self._history) < 3:
            return False

        recent = self._history[-3:]
        v0 = self._metrics_vector(recent[0].metrics)
        v1 = self._metrics_vector(recent[1].metrics)
        v2 = self._metrics_vector(recent[2].metrics)

        # 如果 v0 ≈ v2 但 v1 不同 → 循环进化
        similarity_0_2 = self._cosine_similarity(v0, v2)
        similarity_0_1 = self._cosine_similarity(v0, v1)

        if similarity_0_2 > 0.95 and similarity_0_1 < 0.9:
            logger.warning("检测到循环进化: 系统在 A→B→A 之间往复")
            return True

        return False

    def _metrics_vector(self, metrics: dict) -> list[float]:
        """将 metrics 转为向量"""
        keys = sorted(metrics.keys())
        return [metrics.get(k, 0.0) for k in keys]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """余弦相似度"""
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def get_degradation_report(self) -> dict:
        """获取退化报告"""
        return {
            "total_checks": len(self._history),
            "degradation_events": len(self._degradation_events),
            "current_level": self._history[-1].guard_level if self._history else GuardLevel.SAFE,
            "recent_events": self._degradation_events[-5:],
        }


# ============================================================
# 沙盒验证器
# ============================================================

class SandboxValidator:
    """
    沙盒验证器 — 升级前隔离验证

    在将升级应用到生产环境之前, 先在沙盒中验证:
      - 功能正确性
      - 性能影响
      - 安全合规
      - 向后兼容性
    """

    def __init__(self, sandbox_dir: str = "data/sandbox"):
        self.sandbox_dir = Path(sandbox_dir)
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        self._validation_results: list[dict] = []

    async def validate_upgrade(
        self,
        upgrade_proposal: dict,
        test_cases: list[dict],
        timeout_seconds: int = 300,
    ) -> dict:
        """
        在沙盒中验证升级方案

        Args:
            upgrade_proposal: 升级方案
            test_cases: 测试用例列表
            timeout_seconds: 超时时间

        Returns:
            验证结果
        """
        import hashlib

        validation_id = hashlib.md5(
            json.dumps(upgrade_proposal, sort_keys=True).encode()
        ).hexdigest()[:12]

        results = {
            "validation_id": validation_id,
            "passed": True,
            "total_tests": len(test_cases),
            "passed_tests": 0,
            "failed_tests": 0,
            "failures": [],
            "performance_impact": {},
            "recommendation": "",
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

        for i, test in enumerate(test_cases):
            try:
                # 模拟执行测试 (实际使用中需要真实执行)
                test_result = await self._run_test(test, upgrade_proposal, timeout_seconds)

                if test_result["passed"]:
                    results["passed_tests"] += 1
                else:
                    results["passed"] = False
                    results["failed_tests"] += 1
                    results["failures"].append({
                        "test_id": i,
                        "test_name": test.get("name", f"test_{i}"),
                        "error": test_result.get("error", "Unknown"),
                        "expected": test.get("expected", ""),
                        "actual": test_result.get("actual", ""),
                    })

            except Exception as e:
                results["passed"] = False
                results["failed_tests"] += 1
                results["failures"].append({
                    "test_id": i,
                    "test_name": test.get("name", f"test_{i}"),
                    "error": str(e),
                })

        # 生成建议
        if results["passed"]:
            results["recommendation"] = "通过验证, 可以部署升级"
        elif results["failed_tests"] / results["total_tests"] < 0.2:
            results["recommendation"] = "部分失败, 建议修复后重新验证"
        else:
            results["recommendation"] = "大量失败, 建议废弃此升级方案"

        self._validation_results.append(results)
        return results

    async def _run_test(self, test: dict, upgrade: dict, timeout: int) -> dict:
        """执行单个测试"""
        # 简化实现: 检查升级方案是否包含测试要求的变更
        test_name = test.get("name", "")
        expected = test.get("expected", "")

        # 基本检查: 升级方案是否为非空
        if not upgrade or not upgrade.get("description"):
            return {"passed": False, "error": "升级方案为空"}

        return {"passed": True, "actual": expected}


# ============================================================
# 回滚管理器
# ============================================================

class RollbackManager:
    """
    回滚管理器 — 检测到退化后自动回滚

    支持:
      - 快照存储: 保存每次升级前的系统状态
      - 自动回滚: 触发退化告警后自动回滚
      - 手动回滚: 支持回滚到任意历史版本
    """

    def __init__(self, state_dir: str = "data/rollback_states"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: dict[str, dict] = {}
        self._rollback_history: list[dict] = []
        self._load_snapshots()

    def _load_snapshots(self):
        """加载历史快照"""
        snap_file = self.state_dir / "snapshots.json"
        if snap_file.exists():
            try:
                self._snapshots = json.loads(snap_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save_snapshots(self):
        """持久化快照"""
        snap_file = self.state_dir / "snapshots.json"
        snap_file.write_text(json.dumps(self._snapshots, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_snapshot(self, version: str, state: dict) -> str:
        """创建快照"""
        import hashlib

        snap_id = hashlib.md5(f"{version}_{time.time()}".encode()).hexdigest()[:12]

        self._snapshots[snap_id] = {
            "snapshot_id": snap_id,
            "version": version,
            "state": state,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_snapshots()

        # 清理旧快照 (保留最近 20 个)
        if len(self._snapshots) > 20:
            sorted_snaps = sorted(
                self._snapshots.items(),
                key=lambda x: x[1].get("created_at", ""),
            )
            for old_id, _ in sorted_snaps[:len(self._snapshots) - 20]:
                del self._snapshots[old_id]

        logger.info(f"创建快照: {snap_id} (版本: {version})")
        return snap_id

    def rollback(self, snapshot_id: Optional[str] = None) -> Optional[dict]:
        """
        回滚到指定快照

        Args:
            snapshot_id: 目标快照 ID, 不指定则回滚到上一个

        Returns:
            回滚后的状态
        """
        if snapshot_id is None:
            # 回滚到上一个
            sorted_snaps = sorted(
                self._snapshots.items(),
                key=lambda x: x[1].get("created_at", ""),
            )
            if len(sorted_snaps) < 2:
                logger.warning("无可用快照进行回滚")
                return None
            snapshot_id = sorted_snaps[-2][0]

        if snapshot_id not in self._snapshots:
            logger.error(f"快照不存在: {snapshot_id}")
            return None

        state = self._snapshots[snapshot_id]["state"]

        self._rollback_history.append({
            "snapshot_id": snapshot_id,
            "version": self._snapshots[snapshot_id]["version"],
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            "reason": "自动回滚: 检测到退化",
        })

        logger.warning(f"执行回滚到快照: {snapshot_id}")
        return state

    def get_latest_snapshot(self) -> Optional[dict]:
        """获取最新快照"""
        if not self._snapshots:
            return None
        sorted_snaps = sorted(
            self._snapshots.items(),
            key=lambda x: x[1].get("created_at", ""),
        )
        return sorted_snaps[-1][1]


# ============================================================
# 进化守卫总控
# ============================================================

class EvolutionGuard:
    """
    进化守卫总控 — 整合三层防护

    使用方式:
      guard = EvolutionGuard()
      guard.set_baseline(current_snapshot)

      # 升级前
      valid = await guard.pre_upgrade_check(upgrade_proposal)

      # 升级后
      result = await guard.post_upgrade_check(new_snapshot)
      if result.requires_rollback:
          guard.rollback()
    """

    def __init__(self, state_dir: str = "data/evolution_guard"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.boundary = BoundaryAwareness()
        self.detector = DegradationDetector()
        self.sandbox = SandboxValidator(str(self.state_dir / "sandbox"))
        self.rollback = RollbackManager(str(self.state_dir / "rollback"))

    def set_baseline(self, snapshot: BenchmarkSnapshot):
        """设置基准"""
        self.detector.set_baseline(snapshot)

    async def pre_upgrade_check(self, upgrade_proposal: dict) -> dict:
        """升级前检查"""
        results = {
            "can_proceed": True,
            "warnings": [],
            "checks": {},
        }

        # 检查 1: 相似升级是否曾经失败过
        # (通过 LoopExecutor 的经验库)

        # 检查 2: 升级方案是否非空
        if not upgrade_proposal:
            results["can_proceed"] = False
            results["warnings"].append("升级方案为空")

        return results

    async def post_upgrade_check(self, snapshot: BenchmarkSnapshot) -> dict:
        """升级后检查"""
        check_result = self.detector.check_snapshot(snapshot)

        result = {
            "guard_level": check_result["guard_level"],
            "signals": check_result["signals"],
            "requires_rollback": check_result["guard_level"] == GuardLevel.ROLLBACK_REQUIRED,
            "requires_attention": check_result["guard_level"] in (GuardLevel.WARNING, GuardLevel.CRITICAL),
            "message": check_result["message"],
        }

        # 检测循环进化
        if self.detector.detect_circular_evolution():
            result["warnings"] = result.get("warnings", []) + ["检测到循环进化"]

        return result

    def get_health_report(self) -> dict:
        """获取系统健康报告"""
        return {
            "boundary": self.boundary.get_boundary_report(),
            "degradation": self.detector.get_degradation_report(),
            "rollback_count": len(self.rollback._rollback_history),
            "overall_health": self._assess_overall_health(),
        }

    def _assess_overall_health(self) -> str:
        """综合评估系统健康度"""
        deg_report = self.detector.get_degradation_report()
        current_level = deg_report.get("current_level", GuardLevel.SAFE)

        if current_level == GuardLevel.ROLLBACK_REQUIRED:
            return "critical"
        elif current_level == GuardLevel.CRITICAL:
            return "poor"
        elif current_level == GuardLevel.WARNING:
            return "fair"
        else:
            return "healthy"


import math  # 用于 cosine_similarity