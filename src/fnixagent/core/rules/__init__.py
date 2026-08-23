"""
项目级 Rules 系统。

从项目根目录 .fnixrules 文件加载规则,支持:
- always: 始终包含在上下文
- manual: 按文件 glob 匹配触发
- agent_requestable: Agent 可按需请求
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.rules.engine import Rule, RuleParser, RulesEngine

__all__ = ["Rule", "RuleParser", "RulesEngine"]
