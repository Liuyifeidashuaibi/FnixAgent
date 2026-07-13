"""配置热更新管理器(P2-03)。

支持运行时动态更新:
  1. 限流规则: 添加/删除 EndpointRule
  2. 护栏规则: 启用/禁用/注册/注销 GuardrailGate
  3. 专家路由: 添加/修改路由关键词映射
  4. 并发配置: 调整 AutoscaledPoolConfig

设计原则:
  - 线程安全: copy + modify + 原子替换(避免半修改状态)
  - 审计留痕: 关键配置变更记录审计日志
  - 幂等: 相同配置重复设置不会产生副作用
  - 回滚: 保留配置变更历史,支持回滚

使用方式:
    mgr = get_config_manager()

    # 添加限流规则
    mgr.add_rate_limit_rule(EndpointRule(prefix="/api/v1/chat", qps=5.0))

    # 启用护栏
    mgr.enable_guardrail("tool_permission")

    # 添加专家路由关键词
    mgr.add_expert_keyword("search", ["新关键词1", "新关键词2"])

    # 回滚到上一个配置版本
    mgr.rollback()
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "ConfigChange",
    "ConfigHotReloadManager",
    "get_config_manager",
    "reset_config_manager",
]

_logger = logging.getLogger(__name__)


@dataclass
class ConfigChange:
    """配置变更记录。

    Attributes:
        timestamp: 变更发生的时间戳(time.time)。
        module: 变更所属模块(rate_limit / guardrail / expert_route / autoscale)。
        action: 变更动作(add / remove / enable / disable / update / register)。
        target: 变更目标名称(如规则 prefix / 护栏名 / 专家 key)。
        old_value: 变更前的旧值(用于回滚)。
        new_value: 变更后的新值(用于审计)。
        operator: 操作者(user_id 或 "system")。
    """

    timestamp: float
    module: str               # rate_limit / guardrail / expert_route / autoscale
    action: str               # add / remove / enable / disable / update
    target: str               # 变更目标名称
    old_value: Any = None
    new_value: Any = None
    operator: str = ""        # 操作者(user_id 或 "system")


class ConfigHotReloadManager:
    """配置热更新管理器。

    通过委托各模块的线程安全方法实现热更新:
    - 限流: MultiLayerRateLimiter.add_endpoint_rule() / remove_endpoint_rule()
    - 护栏: GuardrailRegistry.enable / disable / register / unregister
    - 路由: ExpertRouter.add_keyword() / remove_keyword()
    - 并发: AutoscaledPool.update_config()

    每次变更记录 ConfigChange,保留历史用于回滚。

    线程安全: 变更历史(self._history)通过 self._lock 保护;
    实际配置变更委托给各模块自身的线程安全方法。
    """

    def __init__(self, max_history: int = 100) -> None:
        """初始化配置热更新管理器。

        Args:
            max_history: 变更历史保留上限(超出后丢弃最旧记录)。
        """
        self._max_history = max_history
        self._history: list[ConfigChange] = []
        self._lock = threading.Lock()
        # 统计计数器(按 module 分组)
        self._stats: dict[str, int] = {
            "rate_limit": 0,
            "guardrail": 0,
            "expert_route": 0,
            "autoscale": 0,
        }

    # ------------------------------------------------------------------
    # 内部: 单例获取(延迟导入避免循环依赖)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_limiter():
        """获取多层限流器单例(延迟导入)。"""
        from officeagent.core.governance import get_limiter
        return get_limiter()

    @staticmethod
    def _get_guardrail_registry():
        """获取护栏注册中心单例(延迟导入)。"""
        from officeagent.core.guardrail import get_guardrail_registry
        return get_guardrail_registry()

    @staticmethod
    def _get_expert_router():
        """获取专家路由器单例(延迟导入)。"""
        from officeagent.core.multiagent import get_router
        return get_router()

    @staticmethod
    def _get_expert_registry():
        """获取专家注册表单例(延迟导入)。"""
        from officeagent.core.multiagent import get_registry
        return get_registry()

    @staticmethod
    def _get_autoscaled_pool():
        """获取自适应并发池单例(延迟导入)。"""
        from officeagent.core.scheduler.autoscale import get_autoscaled_pool
        return get_autoscaled_pool()

    # ------------------------------------------------------------------
    # 内部: 历史记录
    # ------------------------------------------------------------------

    def _record(self, change: ConfigChange) -> None:
        """记录一条变更(线程安全,超出上限丢弃最旧)。"""
        with self._lock:
            self._history.append(change)
            if len(self._history) > self._max_history:
                # 丢弃最旧的记录(保留最近 max_history 条)
                del self._history[: len(self._history) - self._max_history]
            self._stats[change.module] = self._stats.get(change.module, 0) + 1

    # ------------------------------------------------------------------
    # 限流规则
    # ------------------------------------------------------------------

    def add_rate_limit_rule(self, rule: Any, operator: str = "") -> bool:
        """添加限流规则(委托 MultiLayerRateLimiter.add_endpoint_rule)。

        Args:
            rule: EndpointRule 实例(需有 prefix 字段)
            operator: 操作者标识

        Returns:
            bool: 成功返回 True,异常返回 False
        """
        try:
            prefix = getattr(rule, "prefix", None)
            if not prefix:
                _logger.warning("添加限流规则失败: rule 缺少 prefix 字段")
                return False
            self._get_limiter().add_endpoint_rule(rule)
            self._record(ConfigChange(
                timestamp=time.time(),
                module="rate_limit",
                action="add",
                target=prefix,
                new_value={
                    "qps": getattr(rule, "qps", None),
                    "concurrency": getattr(rule, "concurrency", None),
                    "min_interval": getattr(rule, "min_interval", None),
                },
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("添加限流规则异常: %s", e, exc_info=True)
            return False

    def remove_rate_limit_rule(self, prefix: str, operator: str = "") -> bool:
        """移除限流规则(委托 MultiLayerRateLimiter.remove_endpoint_rule)。

        Args:
            prefix: 要移除的规则 prefix(精确匹配)
            operator: 操作者标识

        Returns:
            bool: 成功移除返回 True,规则不存在返回 False
        """
        try:
            removed = self._get_limiter().remove_endpoint_rule(prefix)
            if removed is None:
                _logger.warning("移除限流规则失败: prefix=%s 不存在", prefix)
                return False
            self._record(ConfigChange(
                timestamp=time.time(),
                module="rate_limit",
                action="remove",
                target=prefix,
                old_value={
                    "qps": removed.qps,
                    "concurrency": removed.concurrency,
                    "min_interval": removed.min_interval,
                },
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("移除限流规则异常: %s", e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 护栏
    # ------------------------------------------------------------------

    def enable_guardrail(self, name: str, operator: str = "") -> bool:
        """启用护栏(委托 GuardrailRegistry.enable)。

        Args:
            name: 护栏名称
            operator: 操作者标识

        Returns:
            bool: 成功启用返回 True,护栏不存在返回 False
        """
        try:
            registry = self._get_guardrail_registry()
            # 校验护栏是否存在(enable 不存在时静默忽略,无法区分)
            if name not in registry.list_guardrails():
                _logger.warning("启用护栏失败: %s 不存在", name)
                return False
            registry.enable(name)
            self._record(ConfigChange(
                timestamp=time.time(),
                module="guardrail",
                action="enable",
                target=name,
                old_value=False,
                new_value=True,
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("启用护栏异常: %s", e, exc_info=True)
            return False

    def disable_guardrail(self, name: str, operator: str = "") -> bool:
        """禁用护栏(委托 GuardrailRegistry.disable)。

        Args:
            name: 护栏名称
            operator: 操作者标识

        Returns:
            bool: 成功禁用返回 True,护栏不存在返回 False
        """
        try:
            registry = self._get_guardrail_registry()
            if name not in registry.list_guardrails():
                _logger.warning("禁用护栏失败: %s 不存在", name)
                return False
            registry.disable(name)
            self._record(ConfigChange(
                timestamp=time.time(),
                module="guardrail",
                action="disable",
                target=name,
                old_value=True,
                new_value=False,
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("禁用护栏异常: %s", e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 专家路由
    # ------------------------------------------------------------------

    def add_expert_keyword(
        self, expert_key: str, keywords: list[str], operator: str = ""
    ) -> bool:
        """添加专家路由关键词(委托 ExpertRouter.add_keyword)。

        Args:
            expert_key: 专家 key(如 "search")
            keywords: 要追加的关键词列表
            operator: 操作者标识

        Returns:
            bool: 成功返回 True,异常返回 False
        """
        try:
            if not expert_key or not keywords:
                _logger.warning("添加专家关键词失败: expert_key/keywords 为空")
                return False
            # 去重保序的快照(用于回滚)
            clean_keywords = [kw.strip() for kw in keywords if kw and kw.strip()]
            if not clean_keywords:
                _logger.warning("添加专家关键词失败: 清洗后为空")
                return False
            self._get_expert_router().add_keyword(expert_key, clean_keywords)
            self._record(ConfigChange(
                timestamp=time.time(),
                module="expert_route",
                action="add",
                target=expert_key,
                new_value=list(clean_keywords),
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("添加专家关键词异常: %s", e, exc_info=True)
            return False

    def register_expert(self, expert: Any, operator: str = "") -> bool:
        """注册新专家(委托 ExpertRegistry.register)。

        Args:
            expert: ExpertDefinition 实例(需有 expert_key 字段)
            operator: 操作者标识

        Returns:
            bool: 成功返回 True,异常返回 False

        Note:
            回滚为 best-effort: ExpertRegistry 若无 unregister 方法,
            回滚将记录警告并跳过。
        """
        try:
            expert_key = getattr(expert, "expert_key", None)
            if not expert_key:
                _logger.warning("注册专家失败: expert 缺少 expert_key 字段")
                return False
            registry = self._get_expert_registry()
            # 记录是否为新增(覆盖也算成功,但回滚时只能移除)
            was_new = expert_key not in registry
            registry.register(expert)
            self._record(ConfigChange(
                timestamp=time.time(),
                module="expert_route",
                action="register",
                target=expert_key,
                old_value=None if was_new else "overwritten",
                new_value={
                    "display_name": getattr(expert, "display_name", ""),
                    "description": getattr(expert, "description", ""),
                },
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("注册专家异常: %s", e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 并发配置
    # ------------------------------------------------------------------

    def update_autoscale_config(
        self, *, operator: str = "", **kwargs: Any
    ) -> bool:
        """更新自适应并发配置(委托 AutoscaledPool.update_config)。

        Args:
            operator: 操作者标识(仅关键字参数)
            **kwargs: AutoscaledPoolConfig 字段名 = 新值

        Returns:
            bool: 成功返回 True,异常返回 False
        """
        try:
            if not kwargs:
                _logger.warning("更新并发配置失败: 未提供任何字段")
                return False
            pool = self._get_autoscaled_pool()
            old_config = pool.config
            # 记录被更新字段的旧值(用于回滚)
            old_values: dict[str, Any] = {}
            for key in kwargs:
                if hasattr(old_config, key):
                    old_values[key] = getattr(old_config, key)
            pool.update_config(**kwargs)
            self._record(ConfigChange(
                timestamp=time.time(),
                module="autoscale",
                action="update",
                target="AutoscaledPoolConfig",
                old_value=old_values,
                new_value=dict(kwargs),
                operator=operator or "system",
            ))
            return True
        except Exception as e:
            _logger.error("更新并发配置异常: %s", e, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # 变更历史
    # ------------------------------------------------------------------

    def get_history(
        self, module: Optional[str] = None, limit: int = 20
    ) -> list[ConfigChange]:
        """获取配置变更历史。

        Args:
            module: 按模块筛选(rate_limit / guardrail / expert_route / autoscale);
                    None 表示全部
            limit: 返回最近 N 条(按时间倒序)

        Returns:
            ConfigChange 列表(最近的在前)
        """
        with self._lock:
            snapshot = list(self._history)
        if module is not None:
            snapshot = [c for c in snapshot if c.module == module]
        # 按时间倒序(最近在前),取前 limit 条
        snapshot.sort(key=lambda c: c.timestamp, reverse=True)
        if limit > 0:
            snapshot = snapshot[:limit]
        return snapshot

    def rollback(self, steps: int = 1) -> bool:
        """回滚到 N 步之前的配置(best-effort)。

        逆序取出最近 N 条变更,逐条执行反向操作:
          - add      → remove
          - remove   → add(用 old_value 重建)
          - enable   → disable
          - disable  → enable
          - update   → 用 old_value 恢复

        Args:
            steps: 回滚步数(默认 1)

        Returns:
            bool: 全部回滚成功返回 True,部分失败返回 False

        Note:
            回滚是 best-effort 的,某些操作(如 register 覆盖)可能无法完全回滚。
        """
        if steps <= 0:
            return True
        with self._lock:
            # 取最近 N 条(按时间正序回滚,即先回滚最新的)
            to_rollback = self._history[-steps:] if steps <= len(self._history) else list(self._history)
            # 从历史中移除这些记录(避免回滚后再回滚重复)
            if to_rollback:
                self._history = self._history[: -len(to_rollback)] if len(to_rollback) < len(self._history) else []
        if not to_rollback:
            _logger.warning("回滚失败: 历史为空")
            return False
        # 逆序回滚(最后发生的最先回滚)
        to_rollback.reverse()
        all_ok = True
        for change in to_rollback:
            ok = self._apply_rollback(change)
            if not ok:
                all_ok = False
                _logger.warning(
                    "回滚失败: module=%s action=%s target=%s",
                    change.module, change.action, change.target,
                )
        _logger.info(
            "回滚完成: steps=%d success=%s", len(to_rollback), all_ok
        )
        return all_ok

    def _apply_rollback(self, change: ConfigChange) -> bool:
        """对单条变更执行反向操作(best-effort)。"""
        try:
            if change.module == "rate_limit":
                if change.action == "add":
                    # add → remove
                    removed = self._get_limiter().remove_endpoint_rule(change.target)
                    return removed is not None
                elif change.action == "remove":
                    # remove → add(用 old_value 重建 EndpointRule)
                    from officeagent.core.governance import EndpointRule
                    old = change.old_value or {}
                    rule = EndpointRule(
                        prefix=change.target,
                        qps=old.get("qps"),
                        concurrency=old.get("concurrency"),
                        min_interval=old.get("min_interval"),
                    )
                    self._get_limiter().add_endpoint_rule(rule)
                    return True
            elif change.module == "guardrail":
                registry = self._get_guardrail_registry()
                if change.action == "enable":
                    # enable → disable
                    if change.target in registry.list_guardrails():
                        registry.disable(change.target)
                        return True
                    return False
                elif change.action == "disable":
                    # disable → enable
                    if change.target in registry.list_guardrails():
                        registry.enable(change.target)
                        return True
                    return False
            elif change.module == "expert_route":
                if change.action == "add":
                    # add → remove_keyword
                    self._get_expert_router().remove_keyword(
                        change.target, change.new_value or []
                    )
                    return True
                elif change.action == "register":
                    # register → unregister(best-effort,可能不支持)
                    registry = self._get_expert_registry()
                    unregister_fn = getattr(registry, "unregister", None)
                    if unregister_fn is not None:
                        return bool(unregister_fn(change.target))
                    _logger.warning(
                        "回滚 register 专家失败: ExpertRegistry 无 unregister 方法 (%s)",
                        change.target,
                    )
                    return False
            elif change.module == "autoscale":
                if change.action == "update":
                    # update → 用 old_value 恢复
                    old_values = change.old_value or {}
                    if old_values:
                        self._get_autoscaled_pool().update_config(**old_values)
                        return True
                    return False
            _logger.warning(
                "回滚: 未知的 module/action: %s/%s", change.module, change.action
            )
            return False
        except Exception as e:
            _logger.error(
                "回滚异常: module=%s target=%s error=%s",
                change.module, change.target, e, exc_info=True,
            )
            return False

    def get_stats(self) -> dict[str, Any]:
        """返回统计信息。

        Returns:
            含 total_changes / by_module / history_size 的字典
        """
        with self._lock:
            return {
                "total_changes": sum(self._stats.values()),
                "by_module": dict(self._stats),
                "history_size": len(self._history),
                "max_history": self._max_history,
            }

    def clear_history(self) -> int:
        """清空变更历史。

        Returns:
            清空前的历史记录数
        """
        with self._lock:
            count = len(self._history)
            self._history.clear()
            for k in self._stats:
                self._stats[k] = 0
            return count


# ---------------------------------------------------------------------------
# 模块级单例(双重检查锁)
# ---------------------------------------------------------------------------

_singleton: Optional[ConfigHotReloadManager] = None
_singleton_lock = threading.Lock()


def get_config_manager() -> ConfigHotReloadManager:
    """获取全局配置管理器单例(双重检查锁)。

    Returns:
        全局唯一的 ConfigHotReloadManager 实例
    """
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = ConfigHotReloadManager()
    return _singleton


def reset_config_manager() -> None:
    """重置配置管理器单例(测试用)。

    清空单例引用,下次调用 get_config_manager() 将创建新实例。
    """
    global _singleton
    with _singleton_lock:
        _singleton = None
