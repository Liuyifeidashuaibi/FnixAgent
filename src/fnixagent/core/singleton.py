"""单例双重检查锁工具(P2-05)。

统一各模块的单例实现模式,避免重复代码和竞态风险。

迁移模式(新模块推荐用法)::

    from fnixagent.core.singleton import SingletonHolder

    # 1. 定义工厂函数
    def _create_limiter() -> MultiLayerRateLimiter:
        return MultiLayerRateLimiter()

    # 2. 使用 SingletonHolder
    _holder = SingletonHolder(_create_limiter)

    # 3. 对外接口
    def get_limiter() -> MultiLayerRateLimiter:
        return _holder.get()

    def reset_limiter() -> None:
        _holder.reset()

注意: 现有 ``get_xxx()`` 单例(get_limiter / get_registry / get_router /
get_reflection_manager / get_autoscaled_pool / get_guardrail_registry /
get_endpoint_pool / get_deduplicator / get_priority_queue /
get_workflow_engine / get_checkpoint_manager / get_stats_aggregator /
get_config_manager 等)沿用各自实现,不做回溯性重构;本工具供新模块使用。

特性:
  - 双重检查锁: 先检查(无锁),再加锁检查,避免竞态
  - 类型安全: 泛型 T 约束工厂函数返回类型
  - 可重置: reset() 供测试使用
  - 线程安全: threading.Lock 保护
  - 零依赖: 仅标准库
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class SingletonHolder(Generic[T]):
    """泛型单例持有器(双重检查锁)。

    用法::

        _holder = SingletonHolder(lambda: MyService())

        # 获取单例(线程安全)
        service = _holder.get()

        # 重置(测试用)
        _holder.reset()

        # 检查是否已初始化
        if _holder.is_initialized:
            ...
    """

    def __init__(self, factory: Callable[[], T]) -> None:
        """初始化单例持有器。

        Args:
            factory: 创建单例实例的工厂函数(首次调用时执行)
        """
        self._factory = factory
        self._instance: Optional[T] = None
        self._lock = threading.Lock()

    @property
    def is_initialized(self) -> bool:
        """单例是否已初始化(无锁快速检查)。"""
        return self._instance is not None

    def get(self) -> T:
        """获取单例实例(双重检查锁)。

        快路径: 已初始化则直接返回(无锁)。
        慢路径: 加锁后再次检查,若未初始化则调用工厂函数。

        Returns:
            单例实例。
        """
        # 快路径: 无锁检查
        if self._instance is not None:
            return self._instance
        # 慢路径: 加锁
        with self._lock:
            if self._instance is not None:
                return self._instance
            self._instance = self._factory()
            return self._instance

    def reset(self) -> None:
        """重置单例(仅测试用)。

        清除已创建的实例,下次 get() 将重新调用工厂函数。

        注意: 不会调用旧实例的清理方法(shutdown/close 等),
        调用方应在 reset() 前手动清理。
        """
        with self._lock:
            self._instance = None

    def get_or_none(self) -> Optional[T]:
        """获取单例,未初始化返回 None(不触发创建)。"""
        return self._instance


# ---------------------------------------------------------------------------
# 便捷装饰器: 将类转换为单例
# ---------------------------------------------------------------------------

def singleton_class(cls: type[T]) -> type[T]:
    """类装饰器: 为类添加线程安全的单例访问。

    用法::

        @singleton_class
        class MyService:
            def __init__(self, config=None):
                ...

        # 获取单例
        service = MyService.get_instance()

        # 重置(测试用)
        MyService.reset_instance()

    注意:
        - 装饰后 __init__ 仍可正常调用(用于创建非单例实例)。
        - get_instance() 首次调用时执行 __init__(无参数)。
        - 如需传参初始化,请使用 SingletonHolder。
    """
    original_init = cls.__init__
    holder = SingletonHolder(lambda: cls.__new__(cls))

    @classmethod
    def get_instance(cls_inner: type[T]) -> T:
        instance = holder.get()
        if not getattr(instance, "_singleton_initialized", False):
            original_init(instance)
            instance._singleton_initialized = True  # type: ignore[attr-defined]
        return instance

    @classmethod
    def reset_instance(cls_inner: type[T]) -> None:
        holder.reset()

    cls.get_instance = get_instance  # type: ignore[attr-defined]
    cls.reset_instance = reset_instance  # type: ignore[attr-defined]
    return cls


# ---------------------------------------------------------------------------
# 全局单例注册表(调试/监控用)
# ---------------------------------------------------------------------------

class SingletonRegistry:
    """全局单例注册表。

    记录所有通过 SingletonHolder 创建的单例,用于:
    - 调试: 查看哪些单例已初始化
    - 监控: 统计单例数量
    - 测试: 批量重置所有单例
    """

    def __init__(self) -> None:
        self._holders: dict[str, "SingletonHolder[Any]"] = {}
        self._lock = threading.Lock()

    def register(self, name: str, holder: "SingletonHolder[Any]") -> None:
        """注册单例持有器。

        若 name 已存在则覆盖旧持有器并记录告警。

        Args:
            name: 单例名称(唯一标识)。
            holder: SingletonHolder 实例。
        """
        with self._lock:
            if name in self._holders:
                logger.warning("单例 '%s' 已注册,将覆盖旧持有器", name)
            self._holders[name] = holder

    def unregister(self, name: str) -> bool:
        """注销单例持有器。

        Args:
            name: 单例名称。

        Returns:
            bool: 是否成功注销(False 表示名称不存在)。
        """
        with self._lock:
            return self._holders.pop(name, None) is not None

    def list_singletons(self) -> list[str]:
        """列出所有已注册的单例名称。

        Returns:
            已注册单例名称列表(按字母序排序)。
        """
        with self._lock:
            return sorted(self._holders.keys())

    def list_initialized(self) -> list[str]:
        """列出已初始化的单例名称。

        Returns:
            已初始化(is_initialized 为 True)的单例名称列表(按字母序排序)。
        """
        with self._lock:
            return sorted(
                name
                for name, holder in self._holders.items()
                if holder.is_initialized
            )

    def reset_all(self) -> int:
        """重置所有已注册的单例(仅测试用)。

        遍历所有已注册的持有器并调用其 reset()。

        注意: 不会调用旧实例的清理方法(shutdown/close 等),
        调用方应在 reset 前手动清理。

        Returns:
            重置的单例数量。
        """
        with self._lock:
            holders = list(self._holders.values())
        count = 0
        for holder in holders:
            holder.reset()
            count += 1
        logger.info("已重置 %d 个单例", count)
        return count

    def get_stats(self) -> dict[str, Any]:
        """返回统计信息。

        Returns:
            含以下字段的字典:
            - total: 已注册单例总数
            - initialized: 已初始化单例数
            - names: 已注册单例名称列表(排序)
            - initialized_names: 已初始化单例名称列表(排序)
        """
        with self._lock:
            names = sorted(self._holders.keys())
            initialized_names = sorted(
                name
                for name, holder in self._holders.items()
                if holder.is_initialized
            )
        return {
            "total": len(names),
            "initialized": len(initialized_names),
            "names": names,
            "initialized_names": initialized_names,
        }


# 全局注册表单例
_registry = SingletonRegistry()


def get_singleton_registry() -> SingletonRegistry:
    """获取全局单例注册表。"""
    return _registry
