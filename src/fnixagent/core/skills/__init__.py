"""FnixAgent Skills 子包 — HERA 持续演进层（Spec 6）。

公共 API:
    - BuiltinSkill / BuiltinSkillLoader / BuiltinSkillRegistry
    - list_builtin_skills() / get_builtin_skill(name)
    - format_builtin_skills_block() — Work prompt 注入（渐进式披露）
    - CapturedSkill / SkillLibrary (HERA 自动捕获)

顶级架构升级组件:
    - SkillEvaluator: 9 维评估器
    - SkillEvolver: 技能进化器（棘轮机制）
    - HumanInTheLoop: 三层守关机制
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.skills.injector import format_builtin_skills_block
from fnixagent.core.skills.library import CapturedSkill, SkillLibrary
from fnixagent.core.skills.loader import (
    BuiltinSkill,
    BuiltinSkillLoader,
    BuiltinSkillLoadError,
)
from fnixagent.core.skills.registry import (
    BUILTIN_SOURCE,
    BuiltinSkillRegistry,
    get_builtin_registry,
    reset_builtin_registry,
)

# 顶级架构升级组件
from fnixagent.core.skills.evaluator import (
    SkillEvaluator,
    SkillScore,
    DimensionScore,
    Dimension,
)
from fnixagent.core.skills.evolver import (
    SkillEvolver,
    EvolutionResult,
    EvolutionRecord,
    HumanInTheLoop,
)

__all__ = [
    # HERA 自动捕获（已有）
    "CapturedSkill",
    "SkillLibrary",
    # 内置 Skill 加载与注册（新增）
    "BuiltinSkill",
    "BuiltinSkillLoadError",
    "BuiltinSkillLoader",
    "BuiltinSkillRegistry",
    "BUILTIN_SOURCE",
    "get_builtin_registry",
    "reset_builtin_registry",
    # 便捷函数
    "list_builtin_skills",
    "get_builtin_skill",
    "format_builtin_skills_block",
    # 顶级架构升级组件
    "SkillEvaluator",
    "SkillScore",
    "DimensionScore",
    "Dimension",
    "SkillEvolver",
    "EvolutionResult",
    "EvolutionRecord",
    "HumanInTheLoop",
]


def list_builtin_skills() -> list[BuiltinSkill]:
    """列出全部内置 skill（按 name 字母序）。

    Returns:
        BuiltinSkill 列表（首次调用时扫描磁盘，后续走缓存）
    """
    return get_builtin_registry().list_all()


def get_builtin_skill(name: str) -> BuiltinSkill | None:
    """按 name 获取内置 skill。

    Args:
        name: skill 名（小写字母/数字/连字符）

    Returns:
        BuiltinSkill 或 None（不存在时）
    """
    return get_builtin_registry().get_skill(name)
