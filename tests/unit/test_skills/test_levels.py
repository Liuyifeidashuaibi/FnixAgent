"""
技能权限策略 (SkillPermissionPolicy) 单元测试。

测试模块: fnixagent.core.skills.levels.SkillPermissionPolicy
覆盖:
    - 常量校验: AUTO_INVOKE_LEVELS / CONFIRM_LEVELS / FORBIDDEN_LEVELS / KTG_WRITE_PERMISSION
    - can_auto_invoke / needs_confirmation / is_forbidden / can_write_ktg
    - check_invoke_permission: 三级权限判定 + 显式授权覆盖
    - check_ktg_write_permission: 允许/拒绝(抛异常)/授权覆盖
    - authorize / revoke / is_authorized
    - set_auto_invoke / set_confirm / set_forbidden
    - describe
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import pytest

from fnixagent.core.exceptions import SkillPermissionDeniedError
from fnixagent.core.skills.levels import (
    AUTO_INVOKE_LEVELS,
    CONFIRM_LEVELS,
    FORBIDDEN_LEVELS,
    KTG_WRITE_PERMISSION,
)
from fnixagent.core.types import SkillLevel

# ---------------------------------------------------------------------------
# 常量校验
# ---------------------------------------------------------------------------


class TestConstants:
    """测试权限策略固化常量。"""

    def test_auto_invoke_levels(self):
        """默认仅 BASIC 级别可自动调用。"""
        assert frozenset({SkillLevel.BASIC}) == AUTO_INVOKE_LEVELS

    def test_confirm_levels(self):
        """默认仅 REASONING 级别需确认。"""
        assert frozenset({SkillLevel.REASONING}) == CONFIRM_LEVELS

    def test_forbidden_levels(self):
        """默认仅 META 级别禁用。"""
        assert frozenset({SkillLevel.META}) == FORBIDDEN_LEVELS

    def test_ktg_write_permission(self):
        """仅 META 级技能可写入 KTG。"""
        assert KTG_WRITE_PERMISSION == {
            SkillLevel.BASIC: False,
            SkillLevel.REASONING: False,
            SkillLevel.META: True,
        }


# ---------------------------------------------------------------------------
# 级别判定
# ---------------------------------------------------------------------------


class TestLevelChecks:
    """测试 can_auto_invoke / needs_confirmation / is_forbidden / can_write_ktg。"""

    def test_can_auto_invoke(self, permission_policy):
        """BASIC 可自动调用,REASONING/META 不可。"""
        assert permission_policy.can_auto_invoke(SkillLevel.BASIC) is True
        assert permission_policy.can_auto_invoke(SkillLevel.REASONING) is False
        assert permission_policy.can_auto_invoke(SkillLevel.META) is False

    def test_needs_confirmation(self, permission_policy):
        """仅 REASONING 需确认。"""
        assert permission_policy.needs_confirmation(SkillLevel.BASIC) is False
        assert permission_policy.needs_confirmation(SkillLevel.REASONING) is True
        assert permission_policy.needs_confirmation(SkillLevel.META) is False

    def test_is_forbidden(self, permission_policy):
        """仅 META 禁用。"""
        assert permission_policy.is_forbidden(SkillLevel.BASIC) is False
        assert permission_policy.is_forbidden(SkillLevel.REASONING) is False
        assert permission_policy.is_forbidden(SkillLevel.META) is True

    def test_can_write_ktg(self, permission_policy):
        """仅 META 可写入 KTG。"""
        assert permission_policy.can_write_ktg(SkillLevel.BASIC) is False
        assert permission_policy.can_write_ktg(SkillLevel.REASONING) is False
        assert permission_policy.can_write_ktg(SkillLevel.META) is True


# ---------------------------------------------------------------------------
# check_invoke_permission
# ---------------------------------------------------------------------------


class TestCheckInvokePermission:
    """测试 check_invoke_permission() 方法。"""

    def test_basic_auto_invoke(self, permission_policy):
        """BASIC 级技能应返回 (True, "auto")。"""
        allowed, reason = permission_policy.check_invoke_permission(
            "search_skill", SkillLevel.BASIC
        )
        assert allowed is True
        assert reason == "auto"

    def test_reasoning_needs_confirmation(self, permission_policy):
        """REASONING 级技能应返回 (False, "needs_confirmation")。"""
        allowed, reason = permission_policy.check_invoke_permission(
            "convert_skill", SkillLevel.REASONING
        )
        assert allowed is False
        assert reason == "needs_confirmation"

    def test_meta_forbidden(self, permission_policy):
        """META 级技能应返回 (False, "forbidden")。"""
        allowed, reason = permission_policy.check_invoke_permission("meta_skill", SkillLevel.META)
        assert allowed is False
        assert reason == "forbidden"

    def test_authorized_overrides_forbidden(self, permission_policy):
        """显式授权的技能应返回 (True, "authorized"),即使原本禁用。"""
        permission_policy.authorize("meta_skill")
        allowed, reason = permission_policy.check_invoke_permission("meta_skill", SkillLevel.META)
        assert allowed is True
        assert reason == "authorized"

    def test_authorized_overrides_confirmation(self, permission_policy):
        """显式授权的技能应返回 (True, "authorized"),跳过确认。"""
        permission_policy.authorize("convert_skill")
        allowed, reason = permission_policy.check_invoke_permission(
            "convert_skill", SkillLevel.REASONING
        )
        assert allowed is True
        assert reason == "authorized"


# ---------------------------------------------------------------------------
# check_ktg_write_permission
# ---------------------------------------------------------------------------


class TestCheckKtgWritePermission:
    """测试 check_ktg_write_permission() 方法。"""

    def test_basic_denied(self, permission_policy):
        """BASIC 级技能无 KTG 写入权限,应抛 SkillPermissionDeniedError。"""
        with pytest.raises(SkillPermissionDeniedError, match="无 KTG 写入权限"):
            permission_policy.check_ktg_write_permission("search_skill", SkillLevel.BASIC)

    def test_reasoning_denied(self, permission_policy):
        """REASONING 级技能无 KTG 写入权限,应抛异常。"""
        with pytest.raises(SkillPermissionDeniedError):
            permission_policy.check_ktg_write_permission("convert_skill", SkillLevel.REASONING)

    def test_meta_allowed(self, permission_policy):
        """META 级技能有 KTG 写入权限,不应抛异常。"""
        # 不应抛异常
        permission_policy.check_ktg_write_permission("meta_skill", SkillLevel.META)

    def test_authorized_overrides_ktg_write(self, permission_policy):
        """显式授权的 BASIC 级技能也可写入 KTG。"""
        permission_policy.authorize("search_skill")
        # 不应抛异常
        permission_policy.check_ktg_write_permission("search_skill", SkillLevel.BASIC)


# ---------------------------------------------------------------------------
# 动态授权
# ---------------------------------------------------------------------------


class TestAuthorizeRevoke:
    """测试 authorize() / revoke() / is_authorized()。"""

    def test_authorize(self, permission_policy):
        """授权后技能应处于已授权状态。"""
        assert permission_policy.is_authorized("meta_skill") is False
        permission_policy.authorize("meta_skill")
        assert permission_policy.is_authorized("meta_skill") is True

    def test_revoke(self, permission_policy):
        """撤销后技能应处于未授权状态。"""
        permission_policy.authorize("meta_skill")
        permission_policy.revoke("meta_skill")
        assert permission_policy.is_authorized("meta_skill") is False

    def test_revoke_unauthorized_no_error(self, permission_policy):
        """撤销未授权的技能不应抛异常(幂等)。"""
        permission_policy.revoke("never_authorized_skill")

    def test_authorize_idempotent(self, permission_policy):
        """重复授权同一技能应为幂等操作。"""
        permission_policy.authorize("meta_skill")
        permission_policy.authorize("meta_skill")
        assert permission_policy.is_authorized("meta_skill") is True


# ---------------------------------------------------------------------------
# 策略配置
# ---------------------------------------------------------------------------


class TestPolicyConfig:
    """测试 set_auto_invoke / set_confirm / set_forbidden。"""

    def test_set_auto_invoke(self, permission_policy):
        """set_auto_invoke 应更新可自动调用的级别集合。"""
        permission_policy.set_auto_invoke({SkillLevel.REASONING})
        assert permission_policy.can_auto_invoke(SkillLevel.REASONING) is True
        assert permission_policy.can_auto_invoke(SkillLevel.BASIC) is False

    def test_set_confirm(self, permission_policy):
        """set_confirm 应更新需确认的级别集合。"""
        permission_policy.set_confirm({SkillLevel.BASIC})
        assert permission_policy.needs_confirmation(SkillLevel.BASIC) is True
        assert permission_policy.needs_confirmation(SkillLevel.REASONING) is False

    def test_set_forbidden(self, permission_policy):
        """set_forbidden 应更新禁用的级别集合。"""
        permission_policy.set_forbidden({SkillLevel.BASIC})
        assert permission_policy.is_forbidden(SkillLevel.BASIC) is True
        assert permission_policy.is_forbidden(SkillLevel.META) is False


# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------


class TestDescribe:
    """测试 describe() 方法。"""

    def test_describe_default(self, permission_policy):
        """默认策略描述应包含正确的级别映射。"""
        desc = permission_policy.describe()
        assert "auto_invoke" in desc
        assert "confirm" in desc
        assert "forbidden" in desc
        assert "authorized_skills" in desc
        assert "ktg_write" in desc
        assert desc["auto_invoke"] == ["basic"]
        assert desc["confirm"] == ["reasoning"]
        assert desc["forbidden"] == ["meta"]
        assert desc["authorized_skills"] == []
        assert desc["ktg_write"] == {"basic": False, "reasoning": False, "meta": True}

    def test_describe_with_authorization(self, permission_policy):
        """授权后描述应包含已授权技能名。"""
        permission_policy.authorize("meta_skill")
        desc = permission_policy.describe()
        assert "meta_skill" in desc["authorized_skills"]

    def test_describe_after_config_change(self, permission_policy):
        """修改策略配置后描述应反映变更。"""
        permission_policy.set_auto_invoke({SkillLevel.META})
        desc = permission_policy.describe()
        assert desc["auto_invoke"] == ["meta"]
