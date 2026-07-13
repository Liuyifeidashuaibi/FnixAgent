"""插件生态(参考 unstructured 的 entry_points 机制)。

通过 Python entry_points 自动发现第三方插件:
  - converters: 实现 DocumentConverter 协议
  - experts:    实现 BaseExpert 接口
  - parsers:    实现解析扩展

插件只需在 pyproject.toml 中声明 entry_point 并实现对应 Protocol,
即可被 PluginManager 自动发现并注册到 ConverterRegistry。

设计参考:
  - unstructured 的 extras 插件化机制(entry_points group)
  - markitdown 的 converter 注册模式

线程安全:所有注册/发现操作加 threading.Lock。
异常隔离:单个插件加载失败不影响其他插件。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fnixagent.office.converter_protocol import (
    ConverterRegistry,
    create_default_registry,
)


# ---------------------------------------------------------------------------
# 插件元数据
# ---------------------------------------------------------------------------


@dataclass
class PluginMeta:
    """插件元数据。

    Attributes:
        name:        插件名(唯一)
        version:     版本号
        author:      作者
        description: 描述
        plugin_type: 类型("converter"/"expert"/"parser")
    """

    name: str
    version: str
    author: str = ""
    description: str = ""
    plugin_type: str = "converter"


@dataclass
class PluginEntry:
    """插件注册条目。

    Attributes:
        meta:    插件元数据
        factory: 工厂函数,调用返回实例(converter/expert/parser)
        enabled: 是否启用
    """

    meta: PluginMeta
    factory: Callable[[], Any]
    enabled: bool = True


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------


class PluginManager:
    """插件管理器:自动发现 + 手动注册 + 启用/禁用。

    用法:
        pm = PluginManager()
        pm.discover()                          # 从 entry_points 发现
        registry = pm.get_converter_registry() # 获取含插件的 Registry
    """

    # entry_point group(第三方插件在此 group 下注册)
    ENTRY_POINT_GROUP = "fnixagent.converters"

    def __init__(self) -> None:
        self._plugins: dict[str, PluginEntry] = {}
        self._lock = threading.Lock()
        self._discovered = False

    # ------------------------------------------------------------------
    # 发现(entry_points)
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginEntry]:
        """从 entry_points 发现第三方插件。

        逐个加载,单个插件失败不影响其他插件;
        重复调用不会重复注册(幂等)。

        Returns:
            本次新发现的 PluginEntry 列表(已注册的不含)
        """
        with self._lock:
            if self._discovered:
                return []
            self._discovered = True

        new_entries: list[PluginEntry] = []
        try:
            eps = self._iter_entry_points(self.ENTRY_POINT_GROUP)
        except Exception:
            return new_entries

        for ep in eps:
            try:
                factory = ep.load()
                if not callable(factory):
                    continue
                # 约定:factory() 返回 PluginEntry / dict / converter 实例
                spec = factory()
                entry = self._normalize_entry(spec, fallback_name=ep.name)
                if entry is None:
                    continue
                with self._lock:
                    if entry.meta.name not in self._plugins:
                        self._plugins[entry.meta.name] = entry
                        new_entries.append(entry)
            except Exception:
                # 单个插件加载失败,跳过,不影响其他插件
                continue
        return new_entries

    @staticmethod
    def _iter_entry_points(group: str):
        """兼容不同 Python 版本的 entry_points 迭代。

        - Python 3.12+: entry_points() 返回 SelectableGroups,用 .select(group=)
        - Python 3.9-3.11: entry_points(group=) 直接返回列表
        - Python 3.8: importlib_metadata backport
        """
        try:
            from importlib.metadata import entry_points
        except ImportError:
            try:
                from importlib_metadata import entry_points  # type: ignore
            except ImportError:
                return []
        try:
            eps = entry_points()
            if hasattr(eps, "select"):
                return list(eps.select(group=group))
        except TypeError:
            pass
        try:
            return list(entry_points(group=group))
        except TypeError:
            # 极旧版本:返回 dict-like
            try:
                return list(entry_points().get(group, []))
            except Exception:
                return []

    @staticmethod
    def _normalize_entry(
        spec: Any, fallback_name: str
    ) -> Optional[PluginEntry]:
        """把 factory() 的返回值统一为 PluginEntry。

        支持三种返回形式:
          1. PluginEntry(直接返回)
          2. dict({name/version/factory/...})
          3. converter 实例(有 accept/convert 方法)
        """
        if isinstance(spec, PluginEntry):
            return spec
        if isinstance(spec, dict):
            meta = PluginMeta(
                name=str(spec.get("name", fallback_name)),
                version=str(spec.get("version", "0.0.0")),
                author=str(spec.get("author", "")),
                description=str(spec.get("description", "")),
                plugin_type=str(spec.get("plugin_type", "converter")),
            )
            factory = spec.get("factory")
            if not callable(factory):
                return None
            return PluginEntry(
                meta=meta,
                factory=factory,
                enabled=bool(spec.get("enabled", True)),
            )
        # factory 直接返回 converter 实例:包装为 PluginEntry
        if hasattr(spec, "accept") and hasattr(spec, "convert"):
            inst = spec
            meta = PluginMeta(
                name=fallback_name,
                version="0.0.0",
                plugin_type="converter",
            )
            return PluginEntry(
                meta=meta,
                factory=(lambda _inst=inst: _inst),
                enabled=True,
            )
        return None

    # ------------------------------------------------------------------
    # 手动注册
    # ------------------------------------------------------------------

    def register(self, entry: PluginEntry) -> None:
        """手动注册插件(同名覆盖)。"""
        with self._lock:
            self._plugins[entry.meta.name] = entry

    def unregister(self, name: str) -> None:
        """注销插件。"""
        with self._lock:
            self._plugins.pop(name, None)

    def enable(self, name: str) -> bool:
        """启用插件;不存在返回 False。"""
        with self._lock:
            entry = self._plugins.get(name)
            if entry is None:
                return False
            entry.enabled = True
            return True

    def disable(self, name: str) -> bool:
        """禁用插件;不存在返回 False。"""
        with self._lock:
            entry = self._plugins.get(name)
            if entry is None:
                return False
            entry.enabled = False
            return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[PluginEntry]:
        """列出所有插件(含禁用的)。"""
        with self._lock:
            return list(self._plugins.values())

    def get_converter_registry(self) -> ConverterRegistry:
        """构建包含所有已启用 converter 插件的 Registry。

        内置 L1 转换器(Word/Excel/PPT/PDF)总是先注册,
        插件可覆盖同名条目(后注册覆盖先注册)。
        """
        registry = create_default_registry()
        with self._lock:
            plugins = list(self._plugins.values())
        for entry in plugins:
            if not entry.enabled:
                continue
            if entry.meta.plugin_type != "converter":
                continue
            try:
                converter = entry.factory()
                if converter is not None:
                    registry.register(converter, name=entry.meta.name)
            except Exception:
                # 插件工厂失败:跳过,不影响其他插件
                continue
        return registry
