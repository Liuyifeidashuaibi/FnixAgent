"""内置 Skill 注册表 — 单例,启动时加载所有内置 skill。

与 `market.py` 的关系:
    - market.py 管「组织市场」(draft → review → published → deprecated)
    - 本模块管「产品内置」(随产品分发,只读,不可卸载)
    - 内置 skill 标记 source="builtin",market 中的 skill 标记 source="market"

设计要点:
    1. 单例: 用 SingletonHolder 模式 (与项目其他模块对齐)
    2. 懒加载: 首次访问时调用 BuiltinSkillLoader 扫描磁盘
    3. 不可写: 内置 skill 只读,不允许 unregister / disable
    4. 与 market 协作: 提供 is_builtin() 供 market 判断是否允许卸载
"""

from __future__ import annotations

import threading

from fnixagent.core.singleton import SingletonHolder
from fnixagent.core.skills.loader import BuiltinSkill, BuiltinSkillLoader

# 内置 skill 来源标记(对齐 market.py 的 source 字段约定)
BUILTIN_SOURCE: str = "builtin"


class BuiltinSkillRegistry:
    """内置 Skill 注册表 (单例)。

    用法::

        from fnixagent.core.skills.registry import get_builtin_registry

        registry = get_builtin_registry()
        all_skills = registry.list_all()                # 全部内置 skill
        pdf = registry.get_skill("pdf")                 # 按名获取
        if registry.is_builtin("pdf"):                  # 判断是否内置
            ...
    """

    def __init__(self) -> None:
        """初始化注册表 (懒加载,首次访问时扫描磁盘)。"""
        self._loader = BuiltinSkillLoader()
        self._skills: list[BuiltinSkill] | None = None
        self._index: dict[str, BuiltinSkill] | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def list_all(self, *, refresh: bool = False) -> list[BuiltinSkill]:
        """列出全部内置 skill (按 name 字母序)。

        Args:
            refresh: True 强制重新扫描磁盘 (默认走缓存)

        Returns:
            BuiltinSkill 列表
        """
        with self._lock:
            if self._skills is None or refresh:
                self._reload()
            assert self._skills is not None
            return list(self._skills)

    def get_skill(self, name: str) -> BuiltinSkill | None:
        """按 name 获取内置 skill。

        Args:
            name: skill 名 (小写字母/数字/连字符)

        Returns:
            BuiltinSkill 或 None (不存在时)
        """
        if not name:
            return None
        with self._lock:
            if self._index is None:
                self._reload()
            assert self._index is not None
            return self._index.get(name)

    def is_builtin(self, name: str) -> bool:
        """判断给定 skill 名是否为内置 skill。

        与 market.py 协作: 内置 skill 不可卸载,market 调用 uninstall 前需检查。

        Args:
            name: skill 名

        Returns:
            True 表示该 skill 是内置 skill
        """
        return self.get_skill(name) is not None

    def list_names(self) -> list[str]:
        """列出全部内置 skill 名 (按字母序)。"""
        return [s.name for s in self.list_all()]

    def stats(self) -> dict[str, object]:
        """返回注册表统计 (总数 / 按级别分组 / 按输出格式分组)。"""
        skills = self.list_all()
        by_level: dict[str, int] = {}
        by_format: dict[str, int] = {}
        for s in skills:
            level_key = s.level.value
            by_level[level_key] = by_level.get(level_key, 0) + 1
            fmt_key = s.output_format or "none"
            by_format[fmt_key] = by_format.get(fmt_key, 0) + 1
        return {
            "total": len(skills),
            "source": BUILTIN_SOURCE,
            "by_level": by_level,
            "by_output_format": by_format,
        }

    def refresh(self) -> None:
        """清除缓存,下次访问时重新扫描磁盘。"""
        with self._lock:
            self._skills = None
            self._index = None
            self._loader.refresh()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _reload(self) -> None:
        """(重新)加载全部内置 skill 到内存索引。"""
        skills = self._loader.list_skills(refresh=True)
        index: dict[str, BuiltinSkill] = {}
        for s in skills:
            index[s.name] = s
        self._skills = skills
        self._index = index


# ---------------------------------------------------------------------------
# 单例 (用 SingletonHolder,与项目其他模块对齐)
# ---------------------------------------------------------------------------

_registry_holder: SingletonHolder[BuiltinSkillRegistry] = SingletonHolder(BuiltinSkillRegistry)


def get_builtin_registry() -> BuiltinSkillRegistry:
    """获取内置 skill 注册表单例 (线程安全,首次调用时加载磁盘)。"""
    return _registry_holder.get()


def reset_builtin_registry() -> None:
    """重置注册表单例 (仅测试用)。

    清除已创建的实例,下次 get_builtin_registry() 将重新创建。
    """
    _registry_holder.reset()
