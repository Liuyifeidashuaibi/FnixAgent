"""内置 Skill → Work prompt 注入器（渐进式披露，Progressive Disclosure）。

对齐 Anthropic Agent Skills / Trae Work 的注入策略：
    1. 索引层：所有启用的内置技能以「一行名称+描述」注入（低 token 成本，
       让模型知道有哪些能力）
    2. 激活层：用户输入命中技能 triggers/tags/name 时，注入该技能的完整
       SKILL.md body（按匹配分排序，限额 max_full 个，防止 prompt 爆炸）

与 harness/skills_loader.format_skills_block 的区别：
    - harness 版处理 workspace/.fnix/skills（用户项目级技能）
    - 本模块处理 builtin/<name>/SKILL.md（产品内置技能）
    两者在 work_pipeline 中拼接共存。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
from collections.abc import Iterable

from fnixagent.core.skills.loader import BuiltinSkill
from fnixagent.core.skills.registry import get_builtin_registry

logger = logging.getLogger(__name__)

# 完整 body 注入的技能数上限（防止 prompt 过长）
_DEFAULT_MAX_FULL = 2
# 所有完整 body 合计字符预算
_DEFAULT_FULL_CHAR_BUDGET = 12_000
# 索引行描述截断长度
_INDEX_DESC_MAX = 90


def _match_score(skill: BuiltinSkill, text_lower: str) -> int:
    """技能与用户输入的匹配分：triggers 权重 3 / name 权重 2 / tags 权重 1。"""
    score = 0
    for trig in skill.triggers:
        t = trig.strip().lower()
        if t and t in text_lower:
            score += 3
    name_l = skill.name.lower()
    if name_l and name_l in text_lower:
        score += 2
    for tag in skill.tags:
        tg = tag.strip().lower()
        if tg and len(tg) >= 3 and tg in text_lower:
            score += 1
    return score


def select_activated_skills(
    user_input: str,
    skills: Iterable[BuiltinSkill],
    *,
    max_full: int = _DEFAULT_MAX_FULL,
) -> list[BuiltinSkill]:
    """按匹配分选出需要注入完整 body 的技能（分数 > 0，最多 max_full 个）。"""
    text_lower = (user_input or "").lower()
    if not text_lower:
        return []
    scored = [(s, _match_score(s, text_lower)) for s in skills]
    hits = [(s, sc) for s, sc in scored if sc > 0]
    hits.sort(key=lambda pair: pair[1], reverse=True)
    return [s for s, _ in hits[:max_full]]


def format_builtin_skills_block(
    user_input: str,
    *,
    disabled: set[str] | None = None,
    max_full: int = _DEFAULT_MAX_FULL,
    full_char_budget: int = _DEFAULT_FULL_CHAR_BUDGET,
) -> str:
    """生成注入 Work system prompt 的内置技能块。

    Args:
        user_input:       用户本轮输入（用于 trigger 匹配激活完整指南）
        disabled:         禁用技能名集合（来自前端技能开关）
        max_full:         完整注入 body 的技能数上限
        full_char_budget: 完整 body 合计字符预算

    Returns:
        prompt 追加块；无可用技能时返回空串。
    """
    try:
        all_skills = get_builtin_registry().list_all()
    except Exception as exc:
        logger.warning("builtin skills load failed: %s", exc)
        return ""

    disabled_set = {d.strip().lower() for d in (disabled or set()) if d}
    enabled = [s for s in all_skills if s.name.lower() not in disabled_set]
    if not enabled:
        return ""

    activated = select_activated_skills(user_input, enabled, max_full=max_full)

    lines: list[str] = ["\n\n## 内置技能（builtin skills）"]
    intro = "以下是产品内置能力索引。当任务匹配某技能时，遵循其描述执行。"
    if activated:
        intro += "标注了【完整指南】的技能已展开详细步骤，必须严格遵循。"
    lines.append(intro)
    for skill in enabled:
        desc = skill.description.replace("\n", " ")[:_INDEX_DESC_MAX]
        lines.append(f"- {skill.name}: {desc}")

    if activated:
        per_skill = max(full_char_budget // max(len(activated), 1), 1000)
        for skill in activated:
            body = (skill.body or "").strip()
            if not body:
                continue
            if len(body) > per_skill:
                body = body[:per_skill] + "\n…（指南过长已截断，核心规则如上）"
            lines.append(f"\n### 【完整指南】{skill.name}")
            lines.append(body)

    return "\n".join(lines)


__all__ = ["format_builtin_skills_block", "select_activated_skills"]
