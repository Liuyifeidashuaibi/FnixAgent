"""
Guardrail - 护栏 (Guardrails)
===============================
对标 Guardrails AI + Ragas 1.0 的输入/输出护栏系统。

设计要点:
  - 三层护栏: INPUT (LLM 调用前) / EXECUTION (工具调用前) / OUTPUT (返回前)
  - 四种动作: PASS / WARN / BLOCK / MODIFY
  - 上下文感知: 接收完整 syscall 上下文 (非仅字符串)
  - 优先级排序: 高优先级先评估
  - 可插拔: 注册自定义护栏函数

修复原版 bug:
  - 原版护栏签名 Callable[[str], tuple[bool, str]] 过于原始
  - 原版仅覆盖 LLM_COMPLETE/LLM_STREAM, 工具调用无护栏
  - 原版无 MODIFY 动作
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from officeagent.core.agentos.types import GuardrailAction, GuardrailLayer, utcnow_iso


@dataclass
class GuardrailContext:
    """护栏上下文 (对标 Guardrails AI Context)。

    提供完整 syscall 上下文, 而非仅字符串。

    Attributes:
        layer: 护栏层级 (INPUT/EXECUTION/OUTPUT)
        syscall: syscall 名称
        caller_pid: 调用方 PID
        content: 检查内容 (输入文本/工具参数/输出结果)
        args: syscall 参数
        metadata: 额外元数据 (trace_id 等)
    """
    layer: GuardrailLayer
    syscall: str = ""
    caller_pid: str = ""
    content: Any = None
    args: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer.value,
            "syscall": self.syscall,
            "caller_pid": self.caller_pid,
            "content": self.content,
            "args": dict(self.args),
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


@dataclass
class GuardrailResult:
    """护栏检查结果 (对标 Guardrails AI ValidationResult)。"""
    action: GuardrailAction = GuardrailAction.PASS
    message: str = ""
    modified_content: Any = None
    risk_score: float = 0.0  # 0.0-1.0
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def pass_(cls) -> GuardrailResult:
        return cls(action=GuardrailAction.PASS)

    @classmethod
    def warn(cls, message: str, risk_score: float = 0.0) -> GuardrailResult:
        return cls(action=GuardrailAction.WARN, message=message,
                   risk_score=risk_score)

    @classmethod
    def block(cls, message: str, risk_score: float = 1.0) -> GuardrailResult:
        return cls(action=GuardrailAction.BLOCK, message=message,
                   risk_score=risk_score)

    @classmethod
    def modify(cls, modified_content: Any, message: str = "") -> GuardrailResult:
        return cls(action=GuardrailAction.MODIFY, message=message,
                   modified_content=modified_content)

    @property
    def passed(self) -> bool:
        return self.action == GuardrailAction.PASS

    @property
    def blocked(self) -> bool:
        return self.action == GuardrailAction.BLOCK

    @property
    def modified(self) -> bool:
        return self.action == GuardrailAction.MODIFY

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "message": self.message,
            "modified_content": self.modified_content,
            "risk_score": self.risk_score,
            "details": dict(self.details),
        }


# 护栏函数签名: (context) -> result
GuardrailFunc = Callable[[GuardrailContext], GuardrailResult]


@dataclass
class GuardrailEntry:
    """护栏注册项。"""
    name: str
    func: GuardrailFunc
    layer: GuardrailLayer
    priority: int = 0
    enabled: bool = True
    description: str = ""


class GuardrailManager:
    """护栏管理器 (对标 Guardrails AI)。

    三层护栏:
      INPUT     - LLM 调用前检查输入
      EXECUTION - 工具调用前检查参数
      OUTPUT    - LLM/工具返回后检查输出

    四种动作:
      PASS    - 通过
      WARN    - 警告但放行
      BLOCK   - 阻止 (syscall 失败)
      MODIFY  - 修改后放行 (如 PII 脱敏)

    评估逻辑:
      1. 按优先级降序评估
      2. BLOCK 立即返回
      3. MODIFY 累积修改 (后续护栏基于修改后内容)
      4. WARN 累积警告
      5. 所有护栏评估完, 若有 MODIFY 则返回修改后内容
    """

    def __init__(self):
        self._guardrails: list[GuardrailEntry] = []

    def register(self, name: str, func: GuardrailFunc,
                 layer: GuardrailLayer, priority: int = 0,
                 description: str = "") -> None:
        """注册护栏。"""
        self._guardrails.append(GuardrailEntry(
            name=name, func=func, layer=layer, priority=priority,
            description=description,
        ))
        # 按优先级降序
        self._guardrails.sort(key=lambda g: -g.priority)

    def unregister(self, name: str) -> bool:
        """注销护栏。"""
        for i, g in enumerate(self._guardrails):
            if g.name == name:
                self._guardrails.pop(i)
                return True
        return False

    def enable(self, name: str) -> bool:
        """启用护栏。"""
        for g in self._guardrails:
            if g.name == name:
                g.enabled = True
                return True
        return False

    def disable(self, name: str) -> bool:
        """禁用护栏。"""
        for g in self._guardrails:
            if g.name == name:
                g.enabled = False
                return True
        return False

    def evaluate(self, context: GuardrailContext) -> GuardrailResult:
        """评估指定层的所有护栏。

        评估逻辑:
          1. 按 priority 降序评估同层护栏
          2. BLOCK 立即返回
          3. MODIFY 累积修改 (后续基于修改后内容)
          4. WARN 累积警告
          5. 全部 PASS 或有 MODIFY 则返回最终结果
        """
        current_content = context.content
        warnings: list[str] = []
        modified = False
        max_risk = 0.0

        for entry in self._guardrails:
            if not entry.enabled or entry.layer != context.layer:
                continue
            # 更新 context 为最新内容 (支持 MODIFY 链)
            ctx = GuardrailContext(
                layer=context.layer,
                syscall=context.syscall,
                caller_pid=context.caller_pid,
                content=current_content,
                args=context.args,
                metadata=context.metadata,
            )
            try:
                result = entry.func(ctx)
            except Exception as e:
                # 护栏异常不阻断, 降级为 WARN
                warnings.append(f"{entry.name} 异常: {e}")
                continue

            max_risk = max(max_risk, result.risk_score)

            if result.action == GuardrailAction.BLOCK:
                return GuardrailResult(
                    action=GuardrailAction.BLOCK,
                    message=f"[{entry.name}] {result.message}",
                    risk_score=result.risk_score,
                    details={"blocked_by": entry.name},
                )
            elif result.action == GuardrailAction.MODIFY:
                current_content = result.modified_content
                modified = True
            elif result.action == GuardrailAction.WARN:
                warnings.append(f"[{entry.name}] {result.message}")

        if modified:
            return GuardrailResult(
                action=GuardrailAction.MODIFY,
                modified_content=current_content,
                message="; ".join(warnings) if warnings else "",
                risk_score=max_risk,
            )
        if warnings:
            return GuardrailResult(
                action=GuardrailAction.WARN,
                message="; ".join(warnings),
                risk_score=max_risk,
            )
        return GuardrailResult.pass_()

    def list_guardrails(self, layer: GuardrailLayer | None = None) -> list[dict[str, Any]]:
        """列出护栏。"""
        entries = self._guardrails
        if layer:
            entries = [g for g in entries if g.layer == layer]
        return [
            {
                "name": g.name, "layer": g.layer.value,
                "priority": g.priority, "enabled": g.enabled,
                "description": g.description,
            }
            for g in entries
        ]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_guardrails": len(self._guardrails),
            "enabled": sum(1 for g in self._guardrails if g.enabled),
            "disabled": sum(1 for g in self._guardrails if not g.enabled),
            "by_layer": {
                layer.value: sum(1 for g in self._guardrails if g.layer == layer)
                for layer in GuardrailLayer
            },
        }


# --- 内置护栏 ---

def length_limit_guardrail(max_length: int = 100000,
                           layer: GuardrailLayer = GuardrailLayer.INPUT) -> GuardrailEntry:
    """内置护栏: 长度限制 (防止 context window 爆炸)。"""
    def func(ctx: GuardrailContext) -> GuardrailResult:
        content = str(ctx.content or "")
        if len(content) > max_length:
            return GuardrailResult.block(
                f"内容过长: {len(content)} > {max_length}",
                risk_score=0.8,
            )
        return GuardrailResult.pass_()
    return GuardrailEntry(
        name="length_limit", func=func, layer=layer,
        priority=10, description=f"限制内容长度 ≤ {max_length}",
    )


def sensitive_data_guardrail(patterns: list[str] | None = None) -> GuardrailEntry:
    """内置护栏: 敏感数据检测 (PII / 密钥)。"""
    import re
    default_patterns = [
        r"\b\d{15,18}[Xx]?\b",  # 身份证
        r"\b1[3-9]\d{9}\b",  # 手机号
        r"\b\d{16,19}\b",  # 银行卡号
        r"sk-[a-zA-Z0-9]{20,}",  # API key
        r"-----BEGIN [A-Z ]+-----",  # PEM 密钥
    ]
    all_patterns = patterns or default_patterns
    compiled = [re.compile(p) for p in all_patterns]

    def func(ctx: GuardrailContext) -> GuardrailResult:
        content = str(ctx.content or "")
        for pattern in compiled:
            if pattern.search(content):
                # MODIFY: 脱敏
                masked = pattern.sub("***REDACTED***", content)
                return GuardrailResult.modify(
                    masked, f"检测到敏感数据, 已脱敏 ({pattern.pattern[:30]})"
                )
        return GuardrailResult.pass_()
    return GuardrailEntry(
        name="sensitive_data", func=func,
        layer=GuardrailLayer.OUTPUT, priority=20,
        description="检测并脱敏 PII/密钥",
    )


__all__ = [
    "GuardrailManager", "GuardrailContext", "GuardrailResult", "GuardrailEntry",
    "GuardrailFunc",
    "length_limit_guardrail", "sensitive_data_guardrail",
]
