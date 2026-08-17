"""
Prompt 管理引擎。

分层组装 + 版本管理 + Token 预算控制:
  - PromptBuilder: 流式组装 system(history+memory+tools+format) → messages
  - PromptManager: 模板注册/版本管理/变量替换
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.prompt.builder import PromptBuilder, PromptLayer
from fnixagent.core.prompt.manager import (
    DEFAULT_PLAN_TEMPLATE,
    DEFAULT_REACT_TEMPLATE,
    DEFAULT_REFLECTION_TEMPLATE,
    DEFAULT_SYSTEM_ROLE,
    PromptManager,
    PromptTemplate,
)

__all__ = [
    "DEFAULT_PLAN_TEMPLATE",
    "DEFAULT_REACT_TEMPLATE",
    "DEFAULT_REFLECTION_TEMPLATE",
    "DEFAULT_SYSTEM_ROLE",
    "PromptBuilder",
    "PromptLayer",
    "PromptManager",
    "PromptTemplate",
]
