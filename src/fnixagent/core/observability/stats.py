"""统一运行指标聚合器(P2-02)。

从各核心模块收集 get_stats() 返回的实时指标,
提供统一查询入口,便于 Prometheus 导出和运维监控。

设计原则:
  - 零侵入: 各模块已实现 get_stats(),此处仅聚合调用
  - 容错: 单模块异常不阻塞其他模块采集
  - 可扩展: 新增模块只需注册 stats provider
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StatsProvider:
    """统计提供者注册项。

    Attributes:
        name:     模块名称(用作 modules 字典的 key)
        provider: 统计获取函数,返回该模块的指标字典
        enabled:  是否启用(禁用的提供者在 collect 时不采集)
    """

    name: str
    provider: Callable[[], dict[str, Any]]
    enabled: bool = True


class StatsAggregator:
    """统一指标聚合器。

    注册各模块的 get_stats() 函数,聚合调用返回统一指标快照。

    线程安全:
      - register / unregister / enable / disable 使用 RLock 保护 _providers
      - collect 先快照提供者列表,再无锁采集(避免长时间持锁)

    用法:
        agg = get_stats_aggregator()
        agg.register("rate_limiter", lambda: get_limiter().get_stats())
        agg.register("guardrail", lambda: get_guardrail_registry().get_stats())
        ...
        # 获取全部指标
        snapshot = agg.collect()
    """

    def __init__(self) -> None:
        """初始化聚合器(无注册提供者)。"""
        self._providers: dict[str, StatsProvider] = {}
        # RLock 允许同线程嵌套(collect 内调用 collect_module 等)
        self._lock = threading.RLock()
        self._start_time: float = time.time()

    # ------------------------------------------------------------------
    # 注册管理
    # ------------------------------------------------------------------

    def register(self, name: str, provider: Callable[[], dict[str, Any]]) -> None:
        """注册一个统计提供者(同名覆盖)。

        Args:
            name:     模块名称
            provider: 统计获取函数,返回指标字典
        """
        with self._lock:
            self._providers[name] = StatsProvider(name=name, provider=provider)
        logger.debug("已注册统计提供者: %s", name)

    def unregister(self, name: str) -> bool:
        """注销一个统计提供者。

        Args:
            name: 模块名称

        Returns:
            True 表示存在并已移除;False 表示未注册
        """
        with self._lock:
            existed = name in self._providers
            self._providers.pop(name, None)
        if existed:
            logger.debug("已注销统计提供者: %s", name)
        return existed

    def enable(self, name: str) -> None:
        """启用指定提供者。"""
        with self._lock:
            p = self._providers.get(name)
            if p is not None:
                p.enabled = True

    def disable(self, name: str) -> None:
        """禁用指定提供者(采集时跳过)。"""
        with self._lock:
            p = self._providers.get(name)
            if p is not None:
                p.enabled = False

    # ------------------------------------------------------------------
    # 采集
    # ------------------------------------------------------------------

    def collect(self) -> dict[str, Any]:
        """采集所有已注册提供者的指标。

        单个提供者异常时记录到 errors 字典,不阻塞其他提供者。

        Returns:
            {
                "timestamp": 1234567890.123,
                "uptime_seconds": 3600.5,
                "modules": {
                    "rate_limiter": {...},
                    "guardrail": {...},
                    "autoscale_pool": {...},
                    ...
                },
                "errors": {
                    "module_name": "error message"
                }
            }
        """
        modules: dict[str, Any] = {}
        errors: dict[str, str] = {}

        # 快照提供者列表,避免采集期间长时间持锁
        with self._lock:
            providers = list(self._providers.values())

        for p in providers:
            if not p.enabled:
                continue
            try:
                modules[p.name] = p.provider()
            except Exception as e:
                errors[p.name] = f"{type(e).__name__}: {e}"
                logger.warning(
                    "采集模块 %s 指标失败: %s: %s",
                    p.name,
                    type(e).__name__,
                    e,
                )

        return {
            "timestamp": time.time(),
            "uptime_seconds": round(time.time() - self._start_time, 3),
            "modules": modules,
            "errors": errors,
        }

    def collect_module(self, name: str) -> dict[str, Any] | None:
        """采集单个模块指标。

        Args:
            name: 模块名称

        Returns:
            模块指标字典;提供者不存在 / 已禁用 / 采集异常时返回 None
        """
        with self._lock:
            p = self._providers.get(name)
        if p is None or not p.enabled:
            return None
        try:
            return p.provider()
        except Exception as e:
            logger.warning(
                "采集模块 %s 指标失败: %s: %s",
                name,
                type(e).__name__,
                e,
            )
            return None

    def list_providers(self) -> list[str]:
        """列出所有已注册的提供者名称。"""
        with self._lock:
            return list(self._providers.keys())

    def get_health(self) -> dict[str, str]:
        """返回各模块健康状态。

        通过尝试调用各提供者的 provider() 判断是否正常:
          - "healthy":  采集成功
          - "error":    采集抛异常
          - "disabled": 提供者已禁用

        Returns:
            {module_name: status_string}
        """
        health: dict[str, str] = {}
        with self._lock:
            providers = list(self._providers.values())
        for p in providers:
            if not p.enabled:
                health[p.name] = "disabled"
                continue
            try:
                p.provider()
                health[p.name] = "healthy"
            except Exception:
                health[p.name] = "error"
        return health


# ---------------------------------------------------------------------------
# 默认提供者注册
# ---------------------------------------------------------------------------


def register_default_providers() -> None:
    """注册默认的统计提供者。

    自动尝试注册以下模块(均用 try/except,不存在则跳过):
      - rate_limiter:   core.governance.limiter.get_limiter().get_stats()
      - guardrail:      core.guardrail.get_guardrail_registry().get_stats()
      - autoscale_pool: core.scheduler.get_autoscaled_pool().get_stats()
      - endpoint_pool:  core.adapters.get_endpoint_pool().get_stats()
      - deduplicator:   core.tools.deduplicator.get_deduplicator().get_stats()
      - priority_queue: core.scheduler.get_priority_queue().get_stats()
      - checkpoint:     core.checkpoint.get_checkpoint_manager().get_stats()
      - reflection:     core.reflection.get_reflection_manager().get_stats()
      - workflow:       core.workflow.get_workflow_engine().get_stats()
    """
    agg = get_stats_aggregator()

    # rate_limiter(治理层多层限流)
    try:
        from fnixagent.core.governance.limiter import get_limiter

        agg.register("rate_limiter", lambda: get_limiter().get_stats())
    except Exception as e:
        logger.debug("注册 rate_limiter 统计提供者失败: %s", e)

    # guardrail(三层护栏注册中心)
    try:
        from fnixagent.core.guardrail import get_guardrail_registry

        agg.register("guardrail", lambda: get_guardrail_registry().get_stats())
    except Exception as e:
        logger.debug("注册 guardrail 统计提供者失败: %s", e)

    # autoscale_pool(自适应并发池)
    try:
        from fnixagent.core.scheduler import get_autoscaled_pool

        agg.register("autoscale_pool", lambda: get_autoscaled_pool().get_stats())
    except Exception as e:
        logger.debug("注册 autoscale_pool 统计提供者失败: %s", e)

    # endpoint_pool(端点连接池)
    try:
        from fnixagent.core.adapters import get_endpoint_pool

        agg.register("endpoint_pool", lambda: get_endpoint_pool().get_stats())
    except Exception as e:
        logger.debug("注册 endpoint_pool 统计提供者失败: %s", e)

    # deduplicator(工具调用去重器)
    try:
        from fnixagent.core.tools.deduplicator import get_deduplicator

        agg.register("deduplicator", lambda: get_deduplicator().get_stats())
    except Exception as e:
        logger.debug("注册 deduplicator 统计提供者失败: %s", e)

    # priority_queue(优先级任务队列)
    try:
        from fnixagent.core.scheduler import get_priority_queue

        agg.register("priority_queue", lambda: get_priority_queue().get_stats())
    except Exception as e:
        logger.debug("注册 priority_queue 统计提供者失败: %s", e)

    # checkpoint(检查点管理器)
    try:
        from fnixagent.core.checkpoint import get_checkpoint_manager

        agg.register("checkpoint", lambda: get_checkpoint_manager().get_stats())
    except Exception as e:
        logger.debug("注册 checkpoint 统计提供者失败: %s", e)

    # reflection(反思管理器)
    try:
        from fnixagent.core.reflection import get_reflection_manager

        agg.register("reflection", lambda: get_reflection_manager().get_stats())
    except Exception as e:
        logger.debug("注册 reflection 统计提供者失败: %s", e)

    # workflow(工作流引擎)
    try:
        from fnixagent.core.workflow import get_workflow_engine

        agg.register("workflow", lambda: get_workflow_engine().get_stats())
    except Exception as e:
        logger.debug("注册 workflow 统计提供者失败: %s", e)


# ---------------------------------------------------------------------------
# 单例(双重检查锁定)
# ---------------------------------------------------------------------------

_singleton: StatsAggregator | None = None
_singleton_lock = threading.Lock()


def get_stats_aggregator() -> StatsAggregator:
    """获取全局统计聚合器单例(双重检查锁)。

    首次调用创建实例并注册默认提供者,后续调用返回同一实例。

    Returns:
        全局唯一的 StatsAggregator 实例
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        _singleton = StatsAggregator()
        # 此时 _singleton 已赋值,register_default_providers 内部调用
        # get_stats_aggregator() 会走快速路径返回同一实例,不会递归
        register_default_providers()
        return _singleton


def reset_stats_aggregator() -> None:
    """重置聚合器(测试用)。

    重置后,下次 get_stats_aggregator() 会重新创建实例并注册默认提供者。
    """
    global _singleton
    with _singleton_lock:
        _singleton = None


__all__ = [
    "StatsAggregator",
    "StatsProvider",
    "get_stats_aggregator",
    "register_default_providers",
    "reset_stats_aggregator",
]
