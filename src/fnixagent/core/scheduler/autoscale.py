"""自适应并发池 (Autoscaled Pool) — P0-05。

设计基础 zhua 项目的 AutoscaledPool(scheduler/kernel.py)。与固定大小的
ThreadPoolExecutor 不同,本池根据系统负载(CPU / 内存 / 平均响应延迟)动态
调整并发槽数,在过载时主动降级、空闲时逐步升级,实现"按压力伸缩"的并发治理。

核心机制:
  1. 信号量限流: 当前并发数 = Semaphore 的初始许可数。acquire() 阻塞获取,
     release() 释放。并发数变化时整体替换 Semaphore(渐进式调整,旧等待者
     仍按旧值释放,新等待者按新值获取)。
  2. 滚动延迟窗口: collections.deque(maxlen=N) 记录最近 N 次响应延迟,
     平均值 = sum(window)/len(window)。线程安全(读写均持锁)。
  3. 惰性调整: maybe_adjust() 由 acquire() 在 fast path 调用,先检查时间戳,
     冷却期内直接返回(O(1));超冷却期且有足够样本才执行指标采样与调整。
     不依赖后台线程,无定时器开销。
  4. psutil 可选: 缺失时仅依赖延迟指标(降级方案,保证零硬依赖)。

调整策略:
  - 任一指标超阈值 → 降并发 max(current * scale_down_factor, min),进入冷却期
  - 全部指标健康    → 升并发 min(current * scale_up_factor,   max),进入冷却期
  - 冷却期内不调整

线程安全: 所有状态变更(current_concurrency / last_adjust_time / latency_window /
semaphore 替换)均在 self._lock 内完成,避免 check-then-act 竞态。

依赖: 仅标准库(threading / logging / time / collections / dataclasses),
psutil 为可选依赖(缺失时跳过 CPU/内存检查)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import dataclasses
import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

# psutil 为可选依赖: 缺失时仅依赖延迟指标做自适应调整
try:
    import psutil  # type: ignore[import-not-found]

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

logger = logging.getLogger(__name__)

# ============================================================================
# 配置
# ============================================================================


@dataclass
class AutoscaledPoolConfig:
    """自适应并发池配置。

    Attributes:
        min_concurrency: 最小并发(降级下限)。
        max_concurrency: 最大并发(升级上限)。
        initial_concurrency: 初始并发。
        cpu_threshold: CPU 使用率阈值(0~1),超过则触发降级。
        memory_threshold: 内存使用率阈值(0~1),超过则触发降级。
        latency_threshold_ms: 平均响应延迟阈值(ms),超过则触发降级。
        scale_down_factor: 降级因子,新并发 = 当前并发 × 此因子(向下取整)。
        scale_up_factor: 升级因子,新并发 = 当前并发 × 此因子(向上取整)。
        cooldown_seconds: 调整冷却期(秒),冷却期内不重复调整。
        latency_window_size: 延迟滚动窗口大小(最近 N 次采样)。
        check_interval: 检查间隔(秒,实际为惰性检查的最小间隔)。
    """

    min_concurrency: int = 1  # 最小并发(降级下限)
    max_concurrency: int = 8  # 最大并发(升级上限)
    initial_concurrency: int = 4  # 初始并发
    # 系统负载阈值
    cpu_threshold: float = 0.80  # CPU 使用率阈值
    memory_threshold: float = 0.85  # 内存使用率阈值
    latency_threshold_ms: float = 5000.0  # 平均响应延迟阈值(ms)
    # 调整参数
    scale_down_factor: float = 0.5  # 降级: 当前并发 × 此因子
    scale_up_factor: float = 1.25  # 升级: 当前并发 × 此因子
    cooldown_seconds: float = 30.0  # 调整冷却期(秒)
    latency_window_size: int = 32  # 延迟滚动窗口大小
    check_interval: float = 10.0  # 检查间隔(秒,实际为惰性检查)

    def __post_init__(self) -> None:
        """参数合法性校验,防止构造出无法运行的配置。"""
        if self.min_concurrency < 1:
            raise ValueError(f"min_concurrency 必须 >= 1, got {self.min_concurrency}")
        if self.max_concurrency < self.min_concurrency:
            raise ValueError(
                f"max_concurrency({self.max_concurrency}) 不能小于 "
                f"min_concurrency({self.min_concurrency})"
            )
        if not (self.min_concurrency <= self.initial_concurrency <= self.max_concurrency):
            raise ValueError(
                f"initial_concurrency({self.initial_concurrency}) 必须落在 "
                f"[{self.min_concurrency}, {self.max_concurrency}] 区间"
            )
        if self.scale_down_factor <= 0 or self.scale_down_factor >= 1:
            raise ValueError(
                f"scale_down_factor 必须在 (0, 1) 开区间, got {self.scale_down_factor}"
            )
        if self.scale_up_factor <= 1:
            raise ValueError(f"scale_up_factor 必须 > 1, got {self.scale_up_factor}")
        if self.cooldown_seconds < 0:
            raise ValueError(f"cooldown_seconds 不能为负, got {self.cooldown_seconds}")
        if self.latency_window_size < 1:
            raise ValueError(f"latency_window_size 必须 >= 1, got {self.latency_window_size}")


# ============================================================================
# 自适应并发池
# ============================================================================


@dataclass
class _AdjustmentRecord:
    """单次调整记录(用于 get_stats 的调整历史)。"""

    timestamp: float  # monotonic 时间戳
    old_concurrency: int  # 调整前并发
    new_concurrency: int  # 调整后并发
    reason: str  # 调整原因


class AutoscaledPool:
    """自适应并发池 — 根据系统负载动态调整并发数。

    监控指标:
        1. CPU 使用率(psutil,可选)
        2. 内存使用率(psutil,可选)
        3. 平均响应延迟(滚动窗口,最近 ``latency_window_size`` 次)

    调整策略:
        - 任一指标超阈值 → 降并发 max(current * scale_down_factor, min), 进入冷却期
        - 全部指标健康    → 升并发 min(current * scale_up_factor,   max), 进入冷却期
        - 冷却期内不调整

    psutil 不可用时仅依赖延迟指标(降级方案)。

    用法::

        pool = AutoscaledPool(AutoscaledPoolConfig(max_concurrency=16))
        pool.acquire()              # 阻塞直到有可用槽位
        try:
            ...                     # 执行工具调用
            pool.record_latency(duration_ms)
        finally:
            pool.release()
            pool.maybe_adjust()     # 惰性调整(可选,acquire 内部已调用)
    """

    def __init__(self, config: AutoscaledPoolConfig | None = None) -> None:
        """初始化自适应并发池。

        Args:
            config: 配置对象;为 None 时使用默认配置。
        """
        self._config = config or AutoscaledPoolConfig()
        self._lock = threading.Lock()
        # 当前并发数(信号量许可数)
        self._current_concurrency: int = self._config.initial_concurrency
        # 信号量: 控制实际并发槽位。调整并发数时整体替换。
        self._semaphore: threading.Semaphore = threading.Semaphore(self._current_concurrency)
        # 滚动延迟窗口(线程安全: 读写均持 self._lock)
        self._latency_window: deque[float] = deque(maxlen=self._config.latency_window_size)
        # 上次调整时间戳(monotonic);初始化为 -cooldown 以允许首次立即调整
        self._last_adjust_time: float = time.monotonic() - self._config.cooldown_seconds
        # 上次指标检查时间戳(用于 check_interval 节流)
        self._last_check_time: float = 0.0
        # 调整历史(最多保留 64 条,避免无限增长)
        self._adjustment_history: deque[_AdjustmentRecord] = deque(maxlen=64)
        # 最新一次采样到的系统指标快照(供 get_stats 展示)
        self._last_cpu: float | None = None
        self._last_memory: float | None = None
        # 关闭标志
        self._shutdown: bool = False

    # -- 公共属性 ----------------------------------------------------------

    @property
    def current_concurrency(self) -> int:
        """当前并发数(信号量许可数)。"""
        with self._lock:
            return self._current_concurrency

    @property
    def config(self) -> AutoscaledPoolConfig:
        """返回配置对象(只读视图,修改请用 update_config)。"""
        return self._config

    def update_config(self, **kwargs: Any) -> AutoscaledPoolConfig:
        """线程安全更新配置(copy + modify + replace,P2-03 热更新)。

        用 dataclasses.replace 创建新配置实例(触发 __post_init__ 校验),
        若并发边界(min/max/initial)变化导致当前并发数越界,则钳位并重建
        信号量;其他字段(thresholds/factors/cooldown)直接替换即可。

        用法:
            pool.update_config(max_concurrency=16, cpu_threshold=0.90)

        Args:
            **kwargs: AutoscaledPoolConfig 字段名 = 新值

        Returns:
            更新后的 AutoscaledPoolConfig 实例

        Raises:
            ValueError: 新值不合法(__post_init__ 校验失败)
        """
        with self._lock:
            current = self._config
            valid_fields = {f.name for f in dataclasses.fields(current)}
            filtered = {k: v for k, v in kwargs.items() if k in valid_fields}
            if not filtered:
                return current
            new_config = dataclasses.replace(current, **filtered)
            self._config = new_config
            # 并发边界变化时钳位当前并发并重建信号量
            old_conc = self._current_concurrency
            clamped = max(
                new_config.min_concurrency,
                min(old_conc, new_config.max_concurrency),
            )
            if clamped != old_conc:
                self._current_concurrency = clamped
                self._semaphore = threading.Semaphore(clamped)
            logger.info(
                "AutoscaledPool 配置已更新: %s (current_concurrency=%d)",
                filtered,
                self._current_concurrency,
            )
            return new_config

    # -- 并发槽位获取/释放 -------------------------------------------------

    def acquire(self) -> threading.Semaphore:
        """获取信号量(阻塞直到有可用槽位)。

        在 fast path 内部调用 maybe_adjust() 完成惰性调整,无需调用方额外触发。
        冷却期内 maybe_adjust() 为 O(1) 直接返回,不影响吞吐。

        Returns:
            当前信号量对象(调用方通常无需使用返回值,
            直接配对调用 release() 即可;返回以便高级用法)。

        Raises:
            RuntimeError: 池已 shutdown。
        """
        if self._shutdown:
            raise RuntimeError("AutoscaledPool 已 shutdown, 无法 acquire")
        # 惰性调整: fast path, 冷却期内 O(1) 返回
        self.maybe_adjust()
        # 读取最新信号量(可能在 maybe_adjust 中被替换)
        with self._lock:
            sem = self._semaphore
        sem.acquire()
        return sem

    def release(self) -> None:
        """释放信号量(归还一个并发槽位)。

        向当前信号量释放许可。若并发数已被调整替换,旧信号量上的 release
        仍作用于旧对象——这是设计取舍(渐进式调整,避免许可泄漏)。
        """
        with self._lock:
            sem = self._semaphore
        sem.release()

    # -- 延迟采样 ----------------------------------------------------------

    def record_latency(self, latency_ms: float) -> None:
        """记录一次响应延迟(供滚动窗口计算)。

        Args:
            latency_ms: 本次响应延迟(毫秒),必须 >= 0。
        """
        if latency_ms < 0:
            return  # 非法采样忽略,不阻断主流程
        with self._lock:
            self._latency_window.append(float(latency_ms))

    # -- 惰性调整 ----------------------------------------------------------

    def maybe_adjust(self) -> int:
        """惰性检查并调整并发数(返回调整后的并发数)。

        检查条件:
            1. 距上次调整超过 cooldown_seconds(冷却期)
            2. 有足够的延迟样本(至少 4 次,避免噪声)

        满足条件后采样系统指标(CPU/内存,若 psutil 可用)与平均延迟,
        按策略升/降并发并进入新的冷却期。

        Returns:
            当前并发数(可能已调整)。
        """
        now = time.monotonic()
        cfg = self._config

        # fast path: 冷却期内直接返回(无锁竞争下的快速判定)
        # 用 _last_check_time 配合 check_interval 做更细粒度节流,
        # 避免每次 acquire 都尝试抢锁
        if now - self._last_check_time < cfg.check_interval:
            with self._lock:
                return self._current_concurrency
        # check_interval 已过,但仍可能在 cooldown 内
        if now - self._last_adjust_time < cfg.cooldown_seconds:
            with self._lock:
                self._last_check_time = now
                return self._current_concurrency

        with self._lock:
            # 双重检查: 拿到锁后再次确认冷却期(防止并发抢锁期间状态变化)
            if now - self._last_adjust_time < cfg.cooldown_seconds:
                self._last_check_time = now
                return self._current_concurrency

            # 延迟样本不足: 不调整(避免噪声驱动抖动)
            if len(self._latency_window) < 4:
                self._last_check_time = now
                return self._current_concurrency

            self._last_check_time = now

            # 采样系统指标
            cpu_usage: float | None = None
            memory_usage: float | None = None
            if _HAS_PSUTIL:
                try:
                    cpu_usage = psutil.cpu_percent(interval=None) / 100.0
                    memory_usage = psutil.virtual_memory().percent / 100.0
                except Exception:
                    # psutil 调用失败时静默降级到仅延迟模式
                    cpu_usage = None
                    memory_usage = None
            self._last_cpu = cpu_usage
            self._last_memory = memory_usage

            # 平均延迟
            avg_latency = sum(self._latency_window) / len(self._latency_window)

            # 判定是否需要降级: 任一可用指标超阈值
            overload_reasons: list[str] = []
            if cpu_usage is not None and cpu_usage >= cfg.cpu_threshold:
                overload_reasons.append(f"CPU={cpu_usage:.2f}>={cfg.cpu_threshold:.2f}")
            if memory_usage is not None and memory_usage >= cfg.memory_threshold:
                overload_reasons.append(f"MEM={memory_usage:.2f}>={cfg.memory_threshold:.2f}")
            if avg_latency >= cfg.latency_threshold_ms:
                overload_reasons.append(
                    f"latency={avg_latency:.0f}ms>={cfg.latency_threshold_ms:.0f}ms"
                )

            old_concurrency = self._current_concurrency

            if overload_reasons:
                # 降级: max(floor(current * scale_down_factor), min)
                new_concurrency = max(
                    int(old_concurrency * cfg.scale_down_factor),
                    cfg.min_concurrency,
                )
                reason = "降级: " + "; ".join(overload_reasons)
            else:
                # 升级: min(ceil(current * scale_up_factor), max)
                # 用 ceil 确保至少 +1(向上取整)
                new_concurrency = min(
                    math.ceil(old_concurrency * cfg.scale_up_factor),
                    cfg.max_concurrency,
                )
                reason = (
                    f"升级: 指标健康(cpu={cpu_usage}, mem={memory_usage}, "
                    f"latency={avg_latency:.0f}ms)"
                )

            # 无变化则不记录(已达边界值)
            if new_concurrency == old_concurrency:
                # 仍更新 last_adjust_time 以进入冷却期,避免高频采样
                self._last_adjust_time = now
                return self._current_concurrency

            # 执行调整: 替换信号量(渐进式,旧等待者按旧值释放)
            self._semaphore = threading.Semaphore(new_concurrency)
            self._current_concurrency = new_concurrency
            self._last_adjust_time = now
            self._adjustment_history.append(
                _AdjustmentRecord(
                    timestamp=now,
                    old_concurrency=old_concurrency,
                    new_concurrency=new_concurrency,
                    reason=reason,
                )
            )
            logger.info(
                "AutoscaledPool 调整并发: %d → %d (%s)",
                old_concurrency,
                new_concurrency,
                reason,
            )
            return self._current_concurrency

    # -- 统计与诊断 --------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """返回运行统计(当前并发 / CPU / 内存 / 平均延迟 / 调整历史)。

        Returns:
            包含以下键的字典:
                - current_concurrency: 当前并发数
                - min_concurrency / max_concurrency: 边界
                - cpu_usage / memory_usage: 最近一次采样值(psutil 不可用为 None)
                - avg_latency_ms: 平均延迟(无样本为 None)
                - latency_samples: 已采样延迟数
                - last_adjust_ago_seconds: 距上次调整的秒数(无则为 None)
                - psutil_available: psutil 是否可用
                - adjustments: 调整历史列表(每条含 timestamp/old/new/reason)
        """
        with self._lock:
            avg_latency: float | None = None
            if self._latency_window:
                avg_latency = sum(self._latency_window) / len(self._latency_window)
            now = time.monotonic()
            last_adjust_ago: float | None = None
            if self._adjustment_history:
                last_adjust_ago = now - self._adjustment_history[-1].timestamp
            elif self._last_adjust_time > 0:
                last_adjust_ago = now - self._last_adjust_time

            return {
                "current_concurrency": self._current_concurrency,
                "min_concurrency": self._config.min_concurrency,
                "max_concurrency": self._config.max_concurrency,
                "cpu_usage": self._last_cpu,
                "memory_usage": self._last_memory,
                "avg_latency_ms": avg_latency,
                "latency_samples": len(self._latency_window),
                "last_adjust_ago_seconds": last_adjust_ago,
                "psutil_available": _HAS_PSUTIL,
                "adjustments": [
                    {
                        "timestamp": rec.timestamp,
                        "old_concurrency": rec.old_concurrency,
                        "new_concurrency": rec.new_concurrency,
                        "reason": rec.reason,
                    }
                    for rec in self._adjustment_history
                ],
            }

    # -- 生命周期 ----------------------------------------------------------

    def reset(self) -> None:
        """重置到初始状态。

        清空延迟窗口、调整历史,并发数恢复为 initial_concurrency,
        重新创建信号量。不关闭池(可继续 acquire/release)。
        """
        with self._lock:
            self._current_concurrency = self._config.initial_concurrency
            self._semaphore = threading.Semaphore(self._current_concurrency)
            self._latency_window.clear()
            self._adjustment_history.clear()
            self._last_adjust_time = time.monotonic() - self._config.cooldown_seconds
            self._last_check_time = 0.0
            self._last_cpu = None
            self._last_memory = None
            self._shutdown = False

    def shutdown(self) -> None:
        """关闭线程池。

        标记池为已关闭,后续 acquire() 将抛 RuntimeError。
        本池不持有 ThreadPoolExecutor(信号量仅做限流,实际执行由外部
        ThreadPoolExecutor 完成),因此无需 shutdown 线程资源。
        """
        with self._lock:
            self._shutdown = True


# ============================================================================
# 模块级单例
# ============================================================================

_default_pool: AutoscaledPool | None = None
_default_lock = threading.Lock()


def get_autoscaled_pool(config: AutoscaledPoolConfig | None = None) -> AutoscaledPool:
    """获取全局默认自适应并发池(惰性单例,线程安全)。

    Args:
        config: 仅在首次创建时生效的配置;后续调用传入的 config 会被忽略
                (已存在单例时返回原实例)。为 None 时使用默认配置。

    Returns:
        全局默认 AutoscaledPool 实例。
    """
    global _default_pool
    if _default_pool is None:
        with _default_lock:
            if _default_pool is None:
                _default_pool = AutoscaledPool(config)
    return _default_pool


def reset_autoscaled_pool() -> None:
    """重置全局默认自适应并发池单例(释放引用,下次 get_autoscaled_pool 重建)。

    如需清空运行时状态而非重建实例,请对 ``get_autoscaled_pool()`` 调用
    ``reset()``。
    """
    global _default_pool
    with _default_lock:
        _default_pool = None
