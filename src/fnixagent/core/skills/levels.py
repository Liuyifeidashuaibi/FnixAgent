"""
技能-拓扑突触协议 (STP) 三级权限体系。

基于 SkillLevel 枚举的权限校验与调度策略:
    - BASIC:     纯计算/检索,无副作用 → 自动调用
    - REASONING: 调用外部 API/读写文件 → 需用户确认
    - META:      修改自身(技能/拓扑)  → 默认禁用,需显式授权

权限校验规则:
    1. 只有 META 级技能可写入 KTG(新增节点/边/修改权重)
    2. BASIC/REASONING 级技能只读 KTG
    3. 调度时按权限级别决定是否需要用户确认
"""

from __future__ import annotations

from typing import Any

from fnixagent.core.exceptions import SkillPermissionDeniedError
from fnixagent.core.types import SkillLevel

# 权限级别是否可自动调用(无需用户确认)
AUTO_INVOKE_LEVELS: frozenset[SkillLevel] = frozenset({SkillLevel.BASIC})

# 需用户确认的权限级别
CONFIRM_LEVELS: frozenset[SkillLevel] = frozenset({SkillLevel.REASONING})

# 默认禁用的权限级别
FORBIDDEN_LEVELS: frozenset[SkillLevel] = frozenset({SkillLevel.META})

# 权限级别 → 是否可写入 KTG
KTG_WRITE_PERMISSION: dict[SkillLevel, bool] = {
    SkillLevel.BASIC: False,
    SkillLevel.REASONING: False,
    SkillLevel.META: True,
}


class SkillPermissionPolicy:
    """技能权限策略管理器。

    管理哪些技能级别允许自动调用、需确认、或禁用。
    支持动态授权(如用户显式授权 META 级技能)。
    """

    def __init__(self) -> None:
        """初始化权限策略(使用默认配置)。"""
        self._auto_invoke: set[SkillLevel] = set(AUTO_INVOKE_LEVELS)
        self._confirm: set[SkillLevel] = set(CONFIRM_LEVELS)
        self._forbidden: set[SkillLevel] = set(FORBIDDEN_LEVELS)
        # 显式授权的技能名集合(META 级技能需显式授权)
        self._authorized_skills: set[str] = set()

    # -----------------------------------------------------------------------
    # 权限判定
    # -----------------------------------------------------------------------

    def can_auto_invoke(self, skill_level: SkillLevel) -> bool:
        """判断该级别技能是否可自动调用。"""
        return skill_level in self._auto_invoke

    def needs_confirmation(self, skill_level: SkillLevel) -> bool:
        """判断该级别技能是否需要用户确认。"""
        return skill_level in self._confirm

    def is_forbidden(self, skill_level: SkillLevel) -> bool:
        """判断该级别技能是否默认禁用。"""
        return skill_level in self._forbidden

    def can_write_ktg(self, skill_level: SkillLevel) -> bool:
        """判断该级别技能是否可写入 KTG。"""
        return KTG_WRITE_PERMISSION.get(skill_level, False)

    def check_invoke_permission(
        self,
        skill_name: str,
        skill_level: SkillLevel,
    ) -> tuple[bool, str]:
        """检查技能调用权限。

        Returns:
            (是否允许调用, 原因说明)
            - (True, "auto"): 自动调用
            - (True, "authorized"): 已显式授权
            - (False, "needs_confirmation"): 需用户确认
            - (False, "forbidden"): 禁用
        """
        # 显式授权优先
        if skill_name in self._authorized_skills:
            return True, "authorized"
        # BASIC 自动调用
        if self.can_auto_invoke(skill_level):
            return True, "auto"
        # REASONING 需确认
        if self.needs_confirmation(skill_level):
            return False, "needs_confirmation"
        # META 禁用
        if self.is_forbidden(skill_level):
            return False, "forbidden"
        return False, "unknown_level"

    def check_ktg_write_permission(
        self,
        skill_name: str,
        skill_level: SkillLevel,
    ) -> None:
        """检查 KTG 写入权限(不允许则抛异常)。"""
        if skill_name not in self._authorized_skills:
            if not self.can_write_ktg(skill_level):
                raise SkillPermissionDeniedError(
                    f"技能 {skill_name}({skill_level.value}) 无 KTG 写入权限,"
                    f"仅 META 级技能且经显式授权后可写入"
                )

    # -----------------------------------------------------------------------
    # 动态授权
    # -----------------------------------------------------------------------

    def authorize(self, skill_name: str) -> None:
        """显式授权技能(用于 META 级技能)。

        Args:
            skill_name: 技能名(非空)

        Raises:
            ValueError: skill_name 为空
        """
        if not skill_name:
            raise ValueError("skill_name must be non-empty")
        self._authorized_skills.add(skill_name)

    def revoke(self, skill_name: str) -> None:
        """撤销授权。

        Args:
            skill_name: 技能名
        """
        if not skill_name:
            return  # 幂等:空名直接返回
        self._authorized_skills.discard(skill_name)

    def is_authorized(self, skill_name: str) -> bool:
        """判断技能是否已显式授权。"""
        return skill_name in self._authorized_skills

    # -----------------------------------------------------------------------
    # 策略配置(运行期可调整,但默认值固化)
    # -----------------------------------------------------------------------

    def set_auto_invoke(self, levels: set[SkillLevel]) -> None:
        """设置可自动调用的级别集合。"""
        self._auto_invoke = set(levels)

    def set_confirm(self, levels: set[SkillLevel]) -> None:
        """设置需确认的级别集合。"""
        self._confirm = set(levels)

    def set_forbidden(self, levels: set[SkillLevel]) -> None:
        """设置禁用的级别集合。"""
        self._forbidden = set(levels)

    # -----------------------------------------------------------------------
    # 策略信息
    # -----------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """返回当前策略描述(调试用)。"""
        return {
            "auto_invoke": [lv.value for lv in self._auto_invoke],
            "confirm": [lv.value for lv in self._confirm],
            "forbidden": [lv.value for lv in self._forbidden],
            "authorized_skills": list(self._authorized_skills),
            "ktg_write": {lv.value: KTG_WRITE_PERMISSION[lv] for lv in SkillLevel},
        }
