"""内置护栏实现。

提供开箱即用的执行层与输出层护栏:
  - ToolPermissionGuardrail:    工具权限检查(按 permission_level + 用户确认)
  - ToolParameterGuardrail:     工具参数校验(必填/注入/长度)
  - HighRiskOperationGuardrail: 高危操作二次确认
  - OutputFormatGuardrail:      输出格式校验(长度/错误标记/占位符)
  - SensitiveOutputGuardrail:   输出敏感信息检测(复用 SensitiveDetector)

输入层护栏复用 core/security/guardrail.py 的现有实现
(InputInjectionGuardrail / InputSensitiveGuardrail / InputModerationGuardrail),
可通过适配包装为 InputGuardrailGate 注册到本中心。

设计说明:
  - 工具权限级别判定不直接依赖 ToolPermission 枚举,通过字符串比较兼容
    枚举值(str Enum)与纯字符串两种形式,避免与 core.types 强耦合。
"""

from __future__ import annotations

import re
from typing import Any

from fnixagent.core.guardrail.registry import (
    ExecutionGuardrailGate,
    GuardrailAction,
    GuardrailCheckResult,
    GuardrailContext,
    OutputGuardrailGate,
)

__all__ = [
    "HighRiskOperationGuardrail",
    "OutputFormatGuardrail",
    "SensitiveOutputGuardrail",
    "ToolParameterGuardrail",
    "ToolPermissionGuardrail",
]


# ---------------------------------------------------------------------------
# 执行层护栏
# ---------------------------------------------------------------------------


class ToolPermissionGuardrail(ExecutionGuardrailGate):
    """工具权限检查护栏。

    根据工具的 permission_level 和用户确认状态决定是否允许调用。
    HIGH 权限工具需要 ctx.metadata["confirmed"] == True,否则拦截。

    Args:
        tool_registry: 工具注册中心(需提供 get(name) 返回含 metadata
            的对象);为 None 时跳过权限级别检查
    """

    def __init__(self, tool_registry: Any = None) -> None:
        super().__init__(name="tool_permission", priority=10)
        self._tool_registry = tool_registry

    def check(self, ctx: GuardrailContext) -> GuardrailCheckResult:
        if not ctx.tool_name:
            return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)

        permission_level: Any = None
        if self._tool_registry is not None:
            try:
                tool = self._tool_registry.get(ctx.tool_name)
                permission_level = tool.metadata.permission_level
            except Exception:
                # 工具未注册或获取失败,无法判定权限级别,放行交由后续护栏
                return GuardrailCheckResult(
                    guardrail_name=self.name,
                    action=GuardrailAction.PASS,
                    message=f"工具 {ctx.tool_name} 未在注册中心找到,跳过权限检查",
                    details={"tool_name": ctx.tool_name},
                )

        if self._is_high_permission(permission_level):
            if ctx.metadata.get("confirmed") is not True:
                return GuardrailCheckResult(
                    guardrail_name=self.name,
                    action=GuardrailAction.BLOCK,
                    message=f"高危操作需要确认: 工具 {ctx.tool_name} 权限级别为 HIGH",
                    risk_score=0.9,
                    details={
                        "tool_name": ctx.tool_name,
                        "permission_level": "high",
                        "need_confirm": True,
                    },
                )

        return GuardrailCheckResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            details={
                "tool_name": ctx.tool_name,
                "permission_level": self._level_str(permission_level),
            },
        )

    @staticmethod
    def _level_str(level: Any) -> str:
        if level is None:
            return "unknown"
        if hasattr(level, "value"):
            return str(level.value).lower()
        return str(level).lower()

    @classmethod
    def _is_high_permission(cls, level: Any) -> bool:
        """判断是否为 HIGH 权限(兼容 str Enum 与纯字符串)。"""
        return cls._level_str(level) == "high"


class ToolParameterGuardrail(ExecutionGuardrailGate):
    """工具参数校验护栏。

    检查项:
      - 必填参数是否缺失(需 tool_registry 提供 input_schema)
      - 参数值是否包含注入模式(SQL / Shell 注入)
      - 参数长度是否超限

    Args:
        tool_registry: 工具注册中心(用于获取 input_schema 校验必填参数);
            为 None 时跳过必填检查
    """

    # SQL 注入特征(大小写不敏感)
    _SQL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"(?i)\b(OR|AND)\b\s+\d+\s*=\s*\d+\b"),  # OR 1=1
        re.compile(r"(?i)\bUNION\s+(ALL\s+)?SELECT\b"),  # UNION SELECT
        re.compile(r"(?i)\bDROP\s+TABLE\b"),  # DROP TABLE
        re.compile(r"(?i)\bINSERT\s+INTO\b"),  # INSERT INTO
        re.compile(r"(?i)\bDELETE\s+FROM\b"),  # DELETE FROM
        re.compile(r"(?i)\bUPDATE\s+\w+\s+SET\b"),  # UPDATE x SET
        re.compile(r"(?i)\bTRUNCATE\s+TABLE\b"),  # TRUNCATE TABLE
        re.compile(r"(?i);\s*(DROP|DELETE|UPDATE|INSERT|SELECT|TRUNCATE)\b"),
        re.compile(r"/\*.*?\*/"),  # /* 注释 */
        re.compile(r"(?i)\bEXEC(UTE)?\s*\("),  # EXEC(
        re.compile(r"(?i)\bxp_cmdshell\b"),  # xp_cmdshell
    ]

    # Shell 注入特征(命令替换 / 危险命令链接)
    _SHELL_INJECTION_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\$\([^)]*\)"),  # $(command)
        re.compile(r"`[^`]*`"),  # `command`
        re.compile(r"&&\s*\w"),  # && cmd
        re.compile(r"\|\|\s*\w"),  # || cmd
        re.compile(r"(?i);\s*(rm|del|format|shutdown|exec|eval|system|cmd|powershell)\b"),
        re.compile(r"(?i)\b(rm|del|format|shutdown)\s+-[rf]\b"),
    ]

    _MAX_PARAM_LENGTH = 10000

    def __init__(self, tool_registry: Any = None) -> None:
        super().__init__(name="tool_parameter", priority=20)
        self._tool_registry = tool_registry

    def check(self, ctx: GuardrailContext) -> GuardrailCheckResult:
        args = ctx.tool_arguments
        if not args:
            return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)

        issues: list[str] = []

        # 1. 必填参数检查(需工具注册中心提供 input_schema)
        if self._tool_registry is not None and ctx.tool_name:
            try:
                tool = self._tool_registry.get(ctx.tool_name)
                schema = tool.metadata.input_schema or {}
                required = schema.get("required", [])
                for field_name in required:
                    if field_name not in args or args[field_name] is None:
                        issues.append(f"缺少必填参数: {field_name}")
            except Exception:
                # 无法获取 schema,跳过必填检查
                pass

        # 2. 注入模式 + 长度检查(仅检查字符串值)
        for key, value in args.items():
            if not isinstance(value, str):
                continue
            if len(value) > self._MAX_PARAM_LENGTH:
                issues.append(f"参数 {key} 长度超限({len(value)} > {self._MAX_PARAM_LENGTH})")
            sql_hit = self._match_first(self._SQL_INJECTION_PATTERNS, value)
            if sql_hit is not None:
                issues.append(f"参数 {key} 疑似 SQL 注入: {sql_hit.pattern}")
            shell_hit = self._match_first(self._SHELL_INJECTION_PATTERNS, value)
            if shell_hit is not None:
                issues.append(f"参数 {key} 疑似 Shell 注入: {shell_hit.pattern}")

        if issues:
            return GuardrailCheckResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                message="; ".join(issues),
                risk_score=0.8,
                details={"issues": issues, "tool_name": ctx.tool_name or ""},
            )
        return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)

    @staticmethod
    def _match_first(patterns: list[re.Pattern[str]], text: str) -> re.Pattern[str] | None:
        for p in patterns:
            if p.search(text):
                return p
        return None


class HighRiskOperationGuardrail(ExecutionGuardrailGate):
    """高危操作确认护栏。

    对高危工具调用要求二次确认(ctx.metadata["confirmed"] == True)。
    高危工具集合由 HIGH_RISK_TOOLS 定义,可在运行时增删。
    """

    HIGH_RISK_TOOLS: set[str] = {
        "delete_file",
        "batch_delete",
        "overwrite_file",
        "execute_code",
        "send_email",
    }

    def __init__(self) -> None:
        super().__init__(name="high_risk_operation", priority=5)

    def check(self, ctx: GuardrailContext) -> GuardrailCheckResult:
        if not ctx.tool_name:
            return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)
        if ctx.tool_name in self.HIGH_RISK_TOOLS:
            if ctx.metadata.get("confirmed") is not True:
                return GuardrailCheckResult(
                    guardrail_name=self.name,
                    action=GuardrailAction.BLOCK,
                    message=f"高危操作 {ctx.tool_name} 需要确认",
                    risk_score=0.95,
                    details={
                        "tool_name": ctx.tool_name,
                        "high_risk_tools": sorted(self.HIGH_RISK_TOOLS),
                    },
                )
        return GuardrailCheckResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            details={"tool_name": ctx.tool_name},
        )


# ---------------------------------------------------------------------------
# 输出层护栏
# ---------------------------------------------------------------------------


class OutputFormatGuardrail(OutputGuardrailGate):
    """输出格式校验护栏。

    检查项:
      - 输出长度(过短可能为错误,过长建议截断)
      - 是否包含错误标记(ERROR/FAILED/异常/Traceback 等)
      - 是否包含未处理的占位符({var})
    """

    _MIN_LENGTH = 1
    _MAX_LENGTH = 100_000
    _ERROR_MARKERS: tuple[str, ...] = (
        "ERROR",
        "FAILED",
        "Exception",
        "Traceback",
        "异常",
        "出错",
    )
    _PLACEHOLDER_PATTERN = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")

    def __init__(self) -> None:
        super().__init__(name="output_format", priority=10)

    def check(self, ctx: GuardrailContext) -> GuardrailCheckResult:
        content = ctx.content
        issues: list[str] = []

        if not content:
            issues.append("输出内容为空")
        else:
            if len(content) < self._MIN_LENGTH:
                issues.append(f"输出长度过短({len(content)} < {self._MIN_LENGTH})")
            elif len(content) > self._MAX_LENGTH:
                issues.append(f"输出长度超限({len(content)} > {self._MAX_LENGTH}),建议截断")
            for marker in self._ERROR_MARKERS:
                if marker in content:
                    issues.append(f"输出包含错误标记: {marker}")
                    break
            placeholders = self._PLACEHOLDER_PATTERN.findall(content)
            if placeholders:
                issues.append(f"输出包含未处理的占位符: {placeholders[:5]}")

        if issues:
            return GuardrailCheckResult(
                guardrail_name=self.name,
                action=GuardrailAction.WARN,
                message="; ".join(issues),
                risk_score=0.3,
                details={"issues": issues},
            )
        return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)


class SensitiveOutputGuardrail(OutputGuardrailGate):
    """输出敏感信息检测护栏。

    复用现有 SensitiveDetector 检测输出中的敏感词,
    命中返回 WARN(不阻塞,但记录)。

    Args:
        sensitive_detector: 敏感词检测器(需提供 detect(text) 方法);
            为 None 时跳过检测
    """

    def __init__(self, sensitive_detector: Any = None) -> None:
        super().__init__(name="sensitive_output", priority=20)
        self._detector = sensitive_detector

    def check(self, ctx: GuardrailContext) -> GuardrailCheckResult:
        if self._detector is None or not ctx.content:
            return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)
        try:
            hits = self._detector.detect(ctx.content)
        except Exception:
            return GuardrailCheckResult(
                guardrail_name=self.name,
                action=GuardrailAction.PASS,
                message="敏感词检测器调用失败,跳过",
            )
        if not hits:
            return GuardrailCheckResult(guardrail_name=self.name, action=GuardrailAction.PASS)
        words = [w for w, _, _ in hits]
        return GuardrailCheckResult(
            guardrail_name=self.name,
            action=GuardrailAction.WARN,
            message=f"输出命中敏感词: {words}",
            risk_score=0.6,
            details={"hits": words, "count": len(words)},
        )
