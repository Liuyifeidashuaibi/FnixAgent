"""
项目级 Rules 系统 (类似 .cursorrules / .traerules)。

从项目根目录 .fnixrules 文件加载规则,支持:
- always: 始终包含在上下文
- manual: 按文件 glob 匹配触发
- agent_requestable: Agent 可按需请求
"""

from officeagent.core.rules.engine import Rule, RuleParser, RulesEngine

__all__ = ["Rule", "RuleParser", "RulesEngine"]