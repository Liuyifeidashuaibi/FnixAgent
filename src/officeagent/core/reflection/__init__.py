"""
反思纠错引擎 (Reflection Engine)。

功能:
  1. Validator: 结果完整性/逻辑校验(规则引擎 + LLM 校验)
  2. Replanner: 校验失败后自动重规划(生成改进建议 + 调整计划)
  3. P0-04: 多评估器反思质量系统(6 个加权评估器,并行执行)

参考 MiniMax Execute→Evaluate→Fix 闭环和 Self-Refine 思想。
P0-04 借鉴 kaoyan-ai-platform 的 reflection/manager.py 设计。

注意:
  本包导出的 ReflectionResult 为 P0-04 新版(含 sub_scores/issues/
  should_reflect/feedback_message),与 core.types.ReflectionResult
  (旧版 passed/score/reason)为不同类。如需旧版请显式从
  officeagent.core.types 导入。
"""
from officeagent.core.reflection.base import (
    ReflectionConfig,
    ReflectionIssue,
    ReflectionResult,
)
from officeagent.core.reflection.validator import (
    ResultValidator,
    ValidationResult,
)
from officeagent.core.reflection.replanner import (
    Replanner,
    ReplanResult,
)
from officeagent.core.reflection.manager import (
    ReflectionManager,
    get_reflection_manager,
    reset_reflection_manager,
)

__all__ = [
    # P0-04: 多评估器反思质量系统
    "ReflectionManager",
    "ReflectionConfig",
    "ReflectionResult",
    "ReflectionIssue",
    "get_reflection_manager",
    "reset_reflection_manager",
    # 旧版(向后兼容)
    "ResultValidator",
    "ValidationResult",
    "Replanner",
    "ReplanResult",
]
