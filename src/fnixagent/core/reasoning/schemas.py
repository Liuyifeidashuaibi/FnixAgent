"""LLM 输出结构化 Schema(借鉴 PydanticAI output_type)。

为 LLM 关键输出定义 Pydantic Model,在 _call_llm 后强制校验,
失败触发重试/降级而非静默继续。

4 个 Schema 覆盖推理引擎全部输出场景:
  - ToolCallDecision: ReAct 单步决策(思考 + 工具调用 / 最终答案)
  - PlanStepOutput:   Plan&Execute 单步规划
  - PlanOutput:       Plan&Execute 完整计划
  - FinalAnswer:      最终答案(含置信度/引用/摘要)

设计要点:
  - 全部继承 pydantic.BaseModel,自动校验类型
  - 字段含 description,便于 LLM 理解期望格式
  - 可选字段用 Optional,避免 LLM 漏字段时校验失败
  - 与 core/types.py 的 dataclass 保持字段名一致,便于互转
  - action_type 用 Literal 限定取值,避免 LLM 输出非法值后静默继续
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


# ---------------------------------------------------------------------------
# ReAct 单步决策
# ---------------------------------------------------------------------------

class ToolCallDecision(BaseModel):
    """ReAct 单步决策(LLM 输出 JSON,校验后转为 ToolCall 或最终答案)。

    LLM Prompt 要求返回此结构的 JSON:
    ```json
    {
      "thought": "我需要搜索论文...",
      "action_type": "tool_call",
      "tool_name": "arxiv_search",
      "tool_arguments": {"query": "GPT-4", "max_results": 10}
    }
    ```
    或:
    ```json
    {
      "thought": "已收集足够信息",
      "action_type": "final_answer",
      "final_answer": "根据检索结果..."
    }
    ```
    """

    thought: str = Field(description="推理思考过程")
    action_type: Literal["tool_call", "final_answer"] = Field(
        description="动作类型: tool_call(调用工具) 或 final_answer(给出最终答案)"
    )
    tool_name: Optional[str] = Field(
        default=None, description="工具名(action_type=tool_call 时必填)"
    )
    tool_arguments: dict[str, Any] = Field(
        default_factory=dict, description="工具参数(action_type=tool_call 时必填)"
    )
    final_answer: Optional[str] = Field(
        default=None, description="最终答案(action_type=final_answer 时必填)"
    )

    @field_validator("tool_name", "tool_arguments")
    @classmethod
    def _validate_tool_call_fields(
        cls, v: Any, info: Any
    ) -> Any:
        """action_type=tool_call 时,tool_name 不能为空字符串。"""
        # info.context 在 pydantic v2 中不直接含其他字段,这里只做空串保护
        if isinstance(v, str) and v.strip() == "":
            raise ValueError("tool_name 不能为空字符串")
        return v

    def is_tool_call(self) -> bool:
        """是否为工具调用决策。"""
        return self.action_type == "tool_call"

    def is_final_answer(self) -> bool:
        """是否为最终答案决策。"""
        return self.action_type == "final_answer"


# ---------------------------------------------------------------------------
# Plan&Execute 规划
# ---------------------------------------------------------------------------

class PlanStepOutput(BaseModel):
    """Plan&Execute 单步规划输出。

    描述一个执行步骤,含步骤号/描述/工具/参数/依赖。
    """
    step_no: int = Field(description="步骤序号(从 1 开始)", ge=1)
    description: str = Field(description="步骤描述")
    tool_name: Optional[str] = Field(
        default=None, description="工具名(无工具则为纯推理步骤)"
    )
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    depends_on: list[int] = Field(
        default_factory=list, description="依赖的前置步骤号列表"
    )


class PlanOutput(BaseModel):
    """Plan&Execute 完整计划输出。

    LLM Prompt 要求返回此结构:
    ```json
    {
      "goal": "撰写 GPT-4 论文综述",
      "steps": [
        {"step_no": 1, "description": "检索论文", "tool_name": "arxiv_search", ...},
        {"step_no": 2, "description": "整理要点", "depends_on": [1]}
      ],
      "reasoning": "先检索再整理..."
    }
    ```
    """
    goal: str = Field(description="计划目标")
    steps: list[PlanStepOutput] = Field(description="步骤列表")
    reasoning: str = Field(default="", description="规划推理过程")


# ---------------------------------------------------------------------------
# 最终答案
# ---------------------------------------------------------------------------

class FinalAnswer(BaseModel):
    """最终答案输出(含置信度/引用/摘要)。

    用于 Self-Reflect 模式反思后的结构化输出,
    或 ReAct 模式 action_type=final_answer 时的扩展校验。
    """
    answer: str = Field(description="最终答案正文")
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="置信度 0~1"
    )
    citations: list[str] = Field(
        default_factory=list, description="引用来源列表(如论文 DOI/URL)"
    )
    summary: str = Field(default="", description="答案摘要(一句话总结)")


# ---------------------------------------------------------------------------
# 便捷校验函数
# ---------------------------------------------------------------------------

def validate_tool_call_decision(text: str) -> Optional[ToolCallDecision]:
    """尝试从 LLM 输出文本解析并校验 ToolCallDecision。

    Args:
        text: LLM 输出文本(应为 JSON)

    Returns:
        校验成功的 ToolCallDecision,失败返回 None
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return ToolCallDecision.model_validate(data)
    except ValidationError:
        return None


def validate_plan_output(text: str) -> Optional[PlanOutput]:
    """尝试从 LLM 输出文本解析并校验 PlanOutput。

    Args:
        text: LLM 输出文本(应为 JSON)

    Returns:
        校验成功的 PlanOutput,失败返回 None
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return PlanOutput.model_validate(data)
    except ValidationError:
        return None


def validate_final_answer(text: str) -> Optional[FinalAnswer]:
    """尝试从 LLM 输出文本解析并校验 FinalAnswer。

    Args:
        text: LLM 输出文本(应为 JSON)

    Returns:
        校验成功的 FinalAnswer,失败返回 None
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        return FinalAnswer.model_validate(data)
    except ValidationError:
        return None
