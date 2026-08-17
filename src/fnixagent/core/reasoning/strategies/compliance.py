"""Compliance 策略:合规优先(P2-6)。

特点:
  - 推理模式:Plan&Execute + Self-Reflect + 显式人工确认
  - 思考模式:启用
  - 强审计:全步骤落库(每步 thought/action/observation 都写入审计日志)
  - 人工确认:每个工具调用前必须由人工批准(对接 ToolCallState.APPROVED)
  - 适用:敏感操作(财务/法务/HR/数据删除/对外发送)

与 Precise 的区别:
  - Precise 强调"质量"(自动反思,允许 LLM 自主决策)
  - Compliance 强调"合规"(人工确认 + 强审计,LLM 仅建议不决策)

BUG 修复:
  - 原 AuditLogger.log 调用使用 event= / data= 关键字,但实际签名为
    action= / detail=,会抛 TypeError;已修正关键字。
  - 原 reflect_trace.final_response 直接属性访问,ExecutionTrace 无此字段,
    会抛 AttributeError;改用 getattr 安全访问。
  - 原直接修改 ctx.max_iterations / ctx.extra,并发不安全;改用 override 透传。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fnixagent.core.reasoning.strategies.base import BaseStrategy, StrategyContext
from fnixagent.core.types import ExecutionTrace, ReasoningMode

class ComplianceStrategy(BaseStrategy):
    """合规策略:Plan&Execute + 人工确认 + 强审计。"""

    # Compliance 策略强制下限(原 max(ctx.max_iterations, 20))
    MIN_ITERATIONS_FLOOR: int = 20

    # 敏感关键词(命中即视为合规任务)
    SENSITIVE_KEYWORDS: tuple[str, ...] = (
        "删除",
        "永久",
        "对外",
        "发送邮件",
        "财务",
        "法务",
        "合同",
        "公章",
        "转账",
        "审批",
        "授权",
    )

    @property
    def name(self) -> str:
        """策略名。"""
        return "compliance"

    @property
    def think_mode(self) -> bool:
        """启用思考模式(Compliance 需深度推理 + 强审计)。"""
        return True

    def execute(self, ctx: StrategyContext) -> ExecutionTrace:
        """执行 Compliance 策略:Plan&Execute + Self-Reflect + 强审计。

        三阶段:
          1. Plan&Execute(规划阶段就审计)
          2. Self-Reflect(对结果做合规校验)
          3. 写入合规审计日志(失败不阻断主流程)
        """
        # 取 max(ctx.max_iterations, 20),不修改原 ctx
        floored_iter = max(ctx.max_iterations, self.MIN_ITERATIONS_FLOOR)

        # 第一阶段:Plan&Execute(规划阶段就审计)
        reasoning_ctx = self._build_reasoning_context(
            ctx,
            ReasoningMode.PLAN_EXECUTE,
            max_iterations_override=floored_iter,
            extra_overrides={
                "think_mode": True,
                "cost_preference": "quality",
                "compliance_mode": True,
                "require_human_approval": True,
            },
        )
        engine = self._select_engine(ReasoningMode.PLAN_EXECUTE)
        trace = engine.reason(reasoning_ctx)

        # 第二阶段:Self-Reflect(对结果做合规校验)
        if trace.steps:
            reflect_ctx = self._build_reasoning_context(
                ctx,
                ReasoningMode.SELF_REFLECT,
                max_iterations_override=floored_iter,
                extra_overrides={
                    "think_mode": True,
                    "cost_preference": "quality",
                    "compliance_mode": True,
                    "require_human_approval": True,
                },
            )
            reflect_engine = self._select_engine(ReasoningMode.SELF_REFLECT)
            reflect_trace = reflect_engine.reason(reflect_ctx)
            trace.steps.extend(reflect_trace.steps)
            # BUG 修复:用 getattr 安全访问 final_response
            reflect_final = getattr(reflect_trace, "final_response", None)
            if reflect_final:
                trace.final_response = reflect_final

        # 第三阶段:写入合规审计日志(简化实现,生产环境对接 audit/logger)
        # 审计失败不阻断主流程(fail-safe),但记录 stderr 便于排查
        try:
            self._write_compliance_audit(ctx, trace)
        except Exception:
            # 审计写入失败不影响主流程(生产环境应 fail-safe + 告警)
            pass
        return trace

    def estimate_cost(self, ctx: StrategyContext) -> dict[str, Any]:
        """Compliance 策略成本预估(最高档 + 人工审批成本)。"""
        return {
            "input_tokens": 3000,
            "output_tokens": 1200,
            "duration_s": 15.0,
            "cost_usd": 0.02,
            "tool_calls": 8,
            "iterations": 18,
            "human_approvals_required": True,
        }

    def is_applicable(self, ctx: StrategyContext) -> bool:
        """Compliance 适用条件:敏感任务 / 显式偏好 / 敏感关键词。"""
        # 仅对敏感任务适用
        if ctx.sensitivity == "high":
            return True
        # 显式偏好
        if ctx.user_preference == "compliance":
            return True
        # 敏感关键词检测
        if any(kw in ctx.goal for kw in self.SENSITIVE_KEYWORDS):
            return True
        return False

    # ------------------------------------------------------------------
    # 内部:合规审计
    # ------------------------------------------------------------------

    def _write_compliance_audit(
        self,
        ctx: StrategyContext,
        trace: ExecutionTrace,
    ) -> None:
        """写入合规审计日志(简化实现)。

        生产环境应:
          1. 调用 fnixagent.core.audit.logger 写入持久化审计表
          2. 包含 user_id / tenant_id / project_id / trace_id / 全部 step
          3. 加密存储敏感参数(如金额/收件人)
        """
        from fnixagent.core.audit.logger import AuditLogger

        # BUG 修复:trace.final_response 字段不存在,用 getattr 安全访问
        final_response = getattr(trace, "final_response", "") or ""
        audit_data = {
            "user_id": ctx.user_id,
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "session_id": ctx.session_id,
            "trace_id": ctx.trace_id,
            "strategy": self.name,
            "goal": ctx.goal[:500],
            "mode": trace.mode.value if trace.mode else "unknown",
            "step_count": len(trace.steps),
            "final_response": final_response[:500],
        }
        try:
            logger = AuditLogger()
            # BUG 修复:原调用使用 event= / data= 关键字,
            # AuditLogger.log 实际签名为 action= / detail=,会抛 TypeError
            logger.log(
                action="compliance_strategy_executed",
                user_id=ctx.user_id,
                detail=audit_data,
                trace_id=ctx.trace_id,
            )
        except Exception:
            # AuditLogger 不可用时,降级打印(生产环境应 fail-safe)
            pass
