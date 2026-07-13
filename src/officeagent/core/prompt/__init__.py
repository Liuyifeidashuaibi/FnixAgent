"""
Prompt 管理引擎。

分层组装 + 版本管理 + Token 预算控制:
  - PromptBuilder: 流式组装 system(history+memory+tools+format) → messages
  - PromptManager: 模板注册/版本管理/变量替换
"""
from officeagent.core.prompt.builder import PromptBuilder, PromptLayer
from officeagent.core.prompt.manager import (
    PromptManager,
    PromptTemplate,
    DEFAULT_SYSTEM_ROLE,
    DEFAULT_REACT_TEMPLATE,
    DEFAULT_PLAN_TEMPLATE,
    DEFAULT_REFLECTION_TEMPLATE,
)

__all__ = [
    "PromptBuilder",
    "PromptLayer",
    "PromptManager",
    "PromptTemplate",
    "DEFAULT_SYSTEM_ROLE",
    "DEFAULT_REACT_TEMPLATE",
    "DEFAULT_PLAN_TEMPLATE",
    "DEFAULT_REFLECTION_TEMPLATE",
]
