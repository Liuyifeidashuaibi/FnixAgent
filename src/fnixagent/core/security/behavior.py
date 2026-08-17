"""
UEBA 行为基线引擎 (User & Entity Behavior Analytics) - P2 安全模块。

参考 Elastic ML Job + UEBA 的设计思路:
  - 滑动窗口统计每用户/Agent 的行为特征(调用频次/时段/工具组合/数据量)
  - 孤立森林(IsolationForest)离线训练,在线预测
  - 多维风险评分(频次异常 0.3 + 时段异常 0.3 + 数据量异常 0.4)
  - 超 0.8 触发 step-up MFA,超 0.95 直接阻断

特性:
  1. sklearn 不可用时降级到统计基线(均值 + 3σ)
  2. 活跃时段检查(凌晨 2-5 点调用算异常)
  3. 异常记录到审计日志 behavior.anomaly
  4. 线程安全(threading.Lock 保护窗口与基线)

设计原则:
  - 所有异常不外泄,捕获后返回合理默认值(allow)
  - 不修改 office/base.py 与其他现有源文件
  - 可选依赖 sklearn 缺失时自动降级
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import math
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# 尝试导入 sklearn(可选依赖,缺失时降级到统计方法)
try:
    from sklearn.ensemble import IsolationForest  # type: ignore[import-not-found]

    _SKLEARN_AVAILABLE: bool = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    IsolationForest = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# 审计钩子(异常吞掉,不影响主流程)
# ---------------------------------------------------------------------------

def _audit_behavior_anomaly(
    user_id: str,
    score: float,
    recommendation: str,
    reasons: list[str],
) -> None:
    """将行为异常写入审计日志(异常吞掉)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(
            action="behavior.anomaly",
            detail={
                "user_id": user_id,
                "score": round(float(score), 4),
                "recommendation": recommendation,
                "reasons": reasons,
            },
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class BehaviorFeatures:
    """单次行为特征。

    Attributes:
        user_id:        用户/Agent 标识
        timestamp:      事件时间戳(unix 秒)
        call_count_1h:  过去 1 小时调用次数
        call_count_24h: 过去 24 小时调用次数
        hour_of_day:    小时(0-23)
        tools_used:     使用的工具列表
        data_volume_kb: 数据量(KB)
    """

    user_id: str
    timestamp: float
    call_count_1h: int = 0
    call_count_24h: int = 0
    hour_of_day: int = 0
    tools_used: list[str] = field(default_factory=list)
    data_volume_kb: float = 0.0

@dataclass
class BehaviorBaseline:
    """用户行为基线。

    Attributes:
        user_id:           用户标识
        mean_calls_1h:     1 小时调用次数均值
        std_calls_1h:      1 小时调用次数标准差
        mean_data_volume:  数据量均值(KB)
        std_data_volume:   数据量标准差(KB)
        active_hours:      活跃时段(0-23 列表)
        trained_at:        训练时间(ISO 字符串)
    """

    user_id: str
    mean_calls_1h: float = 0.0
    std_calls_1h: float = 0.0
    mean_data_volume: float = 0.0
    std_data_volume: float = 0.0
    active_hours: list[int] = field(default_factory=list)
    trained_at: str = ""

@dataclass
class AnomalyScore:
    """行为异常评分结果。

    Attributes:
        user_id:        用户标识
        score:          异常评分(0.0-1.0,越高越异常)
        reasons:        异常原因列表
        recommendation: 处置建议 allow/monitor/challenge_mfa/block
        features:       触发评分的行为特征
    """

    user_id: str
    score: float
    reasons: list[str] = field(default_factory=list)
    recommendation: str = "allow"
    features: BehaviorFeatures | None = None

# ---------------------------------------------------------------------------
# BehaviorAnalyzer
# ---------------------------------------------------------------------------

class BehaviorAnalyzer:
    """UEBA 行为基线分析器。

    用法:
        analyzer = BehaviorAnalyzer(use_ml=True)
        analyzer.record(features)
        baseline = analyzer.train_baseline("alice")
        score = analyzer.analyze(features)
        if score.recommendation == "challenge_mfa":
            # 触发 step-up MFA
            ...
    """

    # 滑动窗口大小(每用户保留最近 N 条行为)
    WINDOW_SIZE: int = 1000
    # 触发 MFA 阈值
    ANOMALY_THRESHOLD: float = 0.8
    # 阻断阈值
    BLOCK_THRESHOLD: float = 0.95
    # 非工作时段(凌晨 2-5 点视为可疑)
    OFF_HOURS: tuple[int, ...] = (2, 3, 4)
    # 统计方法:超过均值 + N 倍标准差视为异常
    SIGMA_MULTIPLIER: float = 3.0
    # 风险评分权重(频次 0.3 + 时段 0.3 + 数据量 0.4)
    WEIGHT_FREQ: float = 0.3
    WEIGHT_TIME: float = 0.3
    WEIGHT_DATA: float = 0.4

    def __init__(self, use_ml: bool = True) -> None:
        # 是否启用 ML 路径(sklearn 不可用时强制降级)
        self._use_ml: bool = use_ml and _SKLEARN_AVAILABLE
        if use_ml and not _SKLEARN_AVAILABLE:
            logger.warning("[behavior] sklearn 不可用,降级到统计基线方法")
        # 滑动窗口:user_id -> deque[BehaviorFeatures]
        self._windows: dict[str, deque[BehaviorFeatures]] = defaultdict(
            lambda: deque(maxlen=self.WINDOW_SIZE)
        )
        # 用户基线缓存:user_id -> BehaviorBaseline
        self._baselines: dict[str, BehaviorBaseline] = {}
        # 已训练的 IsolationForest 模型:user_id -> model
        self._models: dict[str, object] = {}
        # 异常记录(最近 N 条)
        self._anomalies: list[AnomalyScore] = []
        self._lock = threading.Lock()

    # -- 公开接口 ----------------------------------------------------------

    def record(self, features: BehaviorFeatures) -> None:
        """记录一次行为(写入滑动窗口)。"""
        try:
            with self._lock:
                self._windows[features.user_id].append(features)
        except Exception as exc:
            logger.warning("[behavior] 记录行为失败: %s", exc)

    def train_baseline(self, user_id: str) -> BehaviorBaseline:
        """基于滑动窗口训练用户行为基线。

        Args:
            user_id: 用户标识

        Returns:
            BehaviorBaseline(窗口为空时返回零值基线)
        """
        try:
            with self._lock:
                window = list(self._windows.get(user_id, []))
            if not window:
                baseline = BehaviorBaseline(
                    user_id=user_id,
                    trained_at=datetime.utcnow().isoformat(),
                )
                with self._lock:
                    self._baselines[user_id] = baseline
                return baseline

            calls_1h = [f.call_count_1h for f in window]
            data_vols = [f.data_volume_kb for f in window]
            hours = [f.hour_of_day for f in window]

            mean_calls = self._mean(calls_1h)
            std_calls = self._std(calls_1h, mean_calls)
            mean_data = self._mean(data_vols)
            std_data = self._std(data_vols, mean_data)
            # 活跃时段:出现频次 >= 2 的小时(避免单次噪声)
            hour_counts: dict[int, int] = {}
            for h in hours:
                hour_counts[h] = hour_counts.get(h, 0) + 1
            active_hours = sorted(h for h, c in hour_counts.items() if c >= 2)

            baseline = BehaviorBaseline(
                user_id=user_id,
                mean_calls_1h=mean_calls,
                std_calls_1h=std_calls,
                mean_data_volume=mean_data,
                std_data_volume=std_data,
                active_hours=active_hours,
                trained_at=datetime.utcnow().isoformat(),
            )
            with self._lock:
                self._baselines[user_id] = baseline

            # ML 路径:训练 IsolationForest
            if self._use_ml and len(window) >= 10:
                self._train_isolation_forest(user_id, window)
            return baseline
        except Exception as exc:
            logger.warning("[behavior] 训练基线失败: %s", exc)
            return BehaviorBaseline(
                user_id=user_id,
                trained_at=datetime.utcnow().isoformat(),
            )

    def analyze(self, features: BehaviorFeatures) -> AnomalyScore:
        """实时分析单次行为,返回异常评分。

        评分聚合:频次异常(0.3) + 时段异常(0.3) + 数据量异常(0.4)
        recommendation:
          - score < 0.5           → allow
          - 0.5 <= score < 0.8    → monitor
          - 0.8 <= score <= 0.95  → challenge_mfa
          - score > 0.95          → block
        """
        try:
            # 确保有基线(无基线时自动训练)
            baseline = self.get_baseline(features.user_id)
            if baseline is None:
                baseline = self.train_baseline(features.user_id)

            # 优先 ML 路径,降级到统计方法
            if self._use_ml and features.user_id in self._models:
                freq_score, time_score, data_score, reasons = self._ml_anomaly(
                    features, features.user_id
                )
            else:
                freq_score, time_score, data_score, reasons = self._statistical_anomaly(
                    features, baseline
                )

            # 聚合评分
            score = (
                freq_score * self.WEIGHT_FREQ
                + time_score * self.WEIGHT_TIME
                + data_score * self.WEIGHT_DATA
            )
            score = max(0.0, min(1.0, score))
            recommendation = self._recommend(score)

            result = AnomalyScore(
                user_id=features.user_id,
                score=score,
                reasons=reasons,
                recommendation=recommendation,
                features=features,
            )

            # 触发 MFA 或阻断时记录审计
            if recommendation in ("challenge_mfa", "block"):
                _audit_behavior_anomaly(features.user_id, score, recommendation, reasons)
                with self._lock:
                    self._anomalies.append(result)
                    # 防止内存无限增长
                    if len(self._anomalies) > 1000:
                        self._anomalies = self._anomalies[-1000:]
            return result
        except Exception as exc:
            # 异常时降级到 allow(可用性优先,但有日志)
            logger.warning("[behavior] 分析异常,降级 allow: %s", exc)
            return AnomalyScore(
                user_id=features.user_id,
                score=0.0,
                reasons=[f"分析异常: {type(exc).__name__}"],
                recommendation="allow",
                features=features,
            )

    def get_baseline(self, user_id: str) -> BehaviorBaseline | None:
        """获取用户基线(未训练返回 None)。"""
        with self._lock:
            return self._baselines.get(user_id)

    def list_anomalies(self, limit: int = 100) -> list[AnomalyScore]:
        """返回最近 N 条异常记录。"""
        with self._lock:
            return list(self._anomalies[-limit:])

    # -- 内部:特征向量化 -------------------------------------------------

    def _extract_feature_vector(self, f: BehaviorFeatures) -> list[float]:
        """将行为特征转为数值向量(供 IsolationForest 使用)。

        维度:[call_count_1h, call_count_24h, hour_of_day,
              tools_count, data_volume_kb]
        """
        return [
            float(f.call_count_1h),
            float(f.call_count_24h),
            float(f.hour_of_day),
            float(len(f.tools_used)),
            float(f.data_volume_kb),
        ]

    # -- 内部:统计方法 ---------------------------------------------------

    def _statistical_anomaly(
        self,
        f: BehaviorFeatures,
        baseline: BehaviorBaseline,
    ) -> tuple[float, float, float, list[str]]:
        """统计方法:均值 + 3σ,活跃时段检查。

        Returns:
            (freq_score, time_score, data_score, reasons)
            每个评分为 0.0-1.0
        """
        reasons: list[str] = []
        freq_score = 0.0
        time_score = 0.0
        data_score = 0.0

        # 1. 频次异常:超过均值 + 3σ
        if baseline.std_calls_1h > 0:
            deviation = f.call_count_1h - baseline.mean_calls_1h
            if deviation > self.SIGMA_MULTIPLIER * baseline.std_calls_1h:
                # 超出倍数越多评分越高(线性映射到 0.5-1.0)
                excess = deviation / (self.SIGMA_MULTIPLIER * baseline.std_calls_1h)
                freq_score = min(1.0, 0.5 + 0.5 * (excess - 1.0))
                reasons.append(
                    f"调用频次异常: {f.call_count_1h} > 均值 "
                    f"{baseline.mean_calls_1h:.1f} + "
                    f"{self.SIGMA_MULTIPLIER}σ"
                )
            elif f.call_count_1h > baseline.mean_calls_1h * 2:
                # 倍数异常(标准差为 0 但频次翻倍)
                freq_score = 0.5
                reasons.append(
                    f"调用频次翻倍: {f.call_count_1h} > 2×均值 {baseline.mean_calls_1h:.1f}"
                )
        elif baseline.mean_calls_1h > 0 and f.call_count_1h > baseline.mean_calls_1h * 2:
            freq_score = 0.5
            reasons.append(f"调用频次翻倍: {f.call_count_1h} > 2×均值 {baseline.mean_calls_1h:.1f}")

        # 2. 时段异常:凌晨 2-5 点 或 非活跃时段
        if f.hour_of_day in self.OFF_HOURS:
            time_score = 1.0
            reasons.append(f"非工作时段访问: 小时 {f.hour_of_day}")
        elif baseline.active_hours and f.hour_of_day not in baseline.active_hours:
            # 不在历史活跃时段(中等可疑)
            time_score = 0.6
            reasons.append(
                f"非活跃时段访问: 小时 {f.hour_of_day} 不在活跃时段 {baseline.active_hours}"
            )

        # 3. 数据量异常:超过均值 + 3σ
        if baseline.std_data_volume > 0:
            deviation = f.data_volume_kb - baseline.mean_data_volume
            if deviation > self.SIGMA_MULTIPLIER * baseline.std_data_volume:
                excess = deviation / (self.SIGMA_MULTIPLIER * baseline.std_data_volume)
                data_score = min(1.0, 0.5 + 0.5 * (excess - 1.0))
                reasons.append(
                    f"数据量异常: {f.data_volume_kb:.1f}KB > 均值 "
                    f"{baseline.mean_data_volume:.1f}KB + "
                    f"{self.SIGMA_MULTIPLIER}σ"
                )
        elif baseline.mean_data_volume > 0 and f.data_volume_kb > baseline.mean_data_volume * 2:
            data_score = 0.5
            reasons.append(
                f"数据量翻倍: {f.data_volume_kb:.1f}KB > 2×均值 {baseline.mean_data_volume:.1f}KB"
            )

        return freq_score, time_score, data_score, reasons

    # -- 内部:ML 方法 ----------------------------------------------------

    def _ml_anomaly(
        self,
        f: BehaviorFeatures,
        user_id: str,
    ) -> tuple[float, float, float, list[str]]:
        """ML 方法:IsolationForest 在线预测。

        Returns:
            (freq_score, time_score, data_score, reasons)
        """
        reasons: list[str] = []
        model = self._models.get(user_id)
        if model is None:
            return self._statistical_anomaly(
                f, self._baselines.get(user_id) or BehaviorBaseline(user_id=user_id)
            )

        try:
            vec = self._extract_feature_vector(f)
            # IsolationForest predict: 1=正常, -1=异常
            pred = model.predict([vec])[0]  # type: ignore[union-attr]
            # decision_function: 越小越异常(<0 视为异常)
            decision = float(
                model.decision_function([vec])[0]  # type: ignore[union-attr]
            )
        except Exception as exc:
            logger.warning("[behavior] ML 预测失败,降级统计: %s", exc)
            return self._statistical_anomaly(
                f, self._baselines.get(user_id) or BehaviorBaseline(user_id=user_id)
            )

        if pred == -1 and decision < 0:
            # 异常:decision 范围通常 [-0.5, 0],映射到评分
            # decision 越接近 -0.5 越异常
            anomaly_strength = min(1.0, abs(decision) / 0.5)
            # ML 无法区分具体维度,均匀分配(后续统计方法补充原因)
            freq_score = anomaly_strength
            time_score = anomaly_strength
            data_score = anomaly_strength
            reasons.append(f"IsolationForest 检测异常(decision={decision:.4f})")
            # 补充时段原因(可解释性)
            if f.hour_of_day in self.OFF_HOURS:
                reasons.append(f"非工作时段: 小时 {f.hour_of_day}")
            return freq_score, time_score, data_score, reasons

        # 正常:仍检查时段(可解释性增强)
        time_score = 0.0
        if f.hour_of_day in self.OFF_HOURS:
            time_score = 0.7
            reasons.append(f"非工作时段: 小时 {f.hour_of_day}")
        return 0.0, time_score, 0.0, reasons

    # -- 内部:IsolationForest 训练 ---------------------------------------

    def _train_isolation_forest(
        self,
        user_id: str,
        window: list[BehaviorFeatures],
    ) -> None:
        """训练用户的 IsolationForest 模型。"""
        if not _SKLEARN_AVAILABLE or IsolationForest is None:
            return
        try:
            X = [self._extract_feature_vector(f) for f in window]
            model = IsolationForest(  # type: ignore[misc]
                n_estimators=100,
                contamination=0.01,
                random_state=42,
            )
            model.fit(X)  # type: ignore[union-attr]
            with self._lock:
                self._models[user_id] = model
            logger.info(
                "[behavior] IsolationForest 训练完成(user=%s, 样本=%d)",
                user_id,
                len(X),
            )
        except Exception as exc:
            logger.warning("[behavior] IsolationForest 训练失败: %s", exc)

    # -- 内部:辅助 -------------------------------------------------------

    def _recommend(self, score: float) -> str:
        """根据评分给出处置建议。"""
        if score > self.BLOCK_THRESHOLD:
            return "block"
        if score >= self.ANOMALY_THRESHOLD:
            return "challenge_mfa"
        if score >= 0.5:
            return "monitor"
        return "allow"

    @staticmethod
    def _mean(values: list[float]) -> float:
        """计算均值(空列表返回 0)。"""
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _std(self, values: list[float], mean: float) -> float:
        """计算标准差(样本数 < 2 返回 0)。"""
        if len(values) < 2:
            return 0.0
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return math.sqrt(variance)

# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------

_analyzer_instance: BehaviorAnalyzer | None = None
_analyzer_lock = threading.Lock()

def get_behavior_analyzer() -> BehaviorAnalyzer:
    """获取全局 BehaviorAnalyzer 单例。"""
    global _analyzer_instance
    if _analyzer_instance is None:
        with _analyzer_lock:
            if _analyzer_instance is None:
                _analyzer_instance = BehaviorAnalyzer()
    return _analyzer_instance

def reset_behavior_analyzer() -> None:
    """重置单例(主要用于测试)。"""
    global _analyzer_instance
    with _analyzer_lock:
        _analyzer_instance = None
