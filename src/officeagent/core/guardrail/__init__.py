"""三层护栏注册中心 (Guardrail Registry) 包。

导出三层护栏注册中心及相关基类、上下文、动作枚举与单例访问函数。

三层护栏:
  1. 输入护栏 (Input):      用户输入进入 Agent 前
  2. 执行护栏 (Execution):  工具调用执行前
  3. 输出护栏 (Output):     Agent 输出返回用户前

用法:
    from officeagent.core.guardrail import (
        get_guardrail_registry,
        GuardrailContext,
        GuardrailAction,
        HighRiskOperationGuardrail,
    )

    registry = get_guardrail_registry()
    registry.register(HighRiskOperationGuardrail())

    ctx = GuardrailContext(tool_name="delete_file", tool_arguments={...})
    results = registry.run_execution(ctx)
"""
from __future__ import annotations

from officeagent.core.guardrail.registry import (
    BaseGuardrailGate,
    ExecutionGuardrail,
    ExecutionGuardrailGate,
    GuardrailAction,
    GuardrailCheckResult,
    GuardrailContext,
    GuardrailRegistry,
    InputGuardrailGate,
    OutputGuardrailGate,
    get_guardrail_registry,
    reset_guardrail_registry,
)
from officeagent.core.guardrail.builtin import (
    HighRiskOperationGuardrail,
    OutputFormatGuardrail,
    SensitiveOutputGuardrail,
    ToolParameterGuardrail,
    ToolPermissionGuardrail,
)

__all__ = [
    # 注册中心与单例
    "GuardrailRegistry",
    "get_guardrail_registry",
    "reset_guardrail_registry",
    # 上下文与结果
    "GuardrailContext",
    "GuardrailCheckResult",
    "GuardrailAction",
    # 基类
    "BaseGuardrailGate",
    "InputGuardrailGate",
    "ExecutionGuardrail",
    "ExecutionGuardrailGate",
    "OutputGuardrailGate",
    # 内置护栏
    "ToolPermissionGuardrail",
    "ToolParameterGuardrail",
    "HighRiskOperationGuardrail",
    "OutputFormatGuardrail",
    "SensitiveOutputGuardrail",
]
