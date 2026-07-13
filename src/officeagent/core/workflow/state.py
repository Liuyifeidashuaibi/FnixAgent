"""工作流状态定义(借鉴 kaoyan routing.py 的 state dict + 条件路由)。

工作流节点:
  analyze → plan → think → execute_tools → reflect → end

条件路由:
  - analyze → plan (始终)
  - plan → think (始终)
  - think → execute_tools (有 tool_calls 且未达上限)
  - think → reflect (无 tool_calls 或已达 max_total_steps)
  - execute_tools → think (继续循环)
  - execute_tools → reflect (达 max_tool_rounds)
  - reflect → end (始终)

设计要点:
  1. WorkflowState 用 str+Enum,序列化时取 .value 字符串
  2. WorkflowContext 为 dataclass,所有字段为纯数据(可 pickle/JSON)
  3. to_dict / from_dict 支持 Checkpoint 持久化与恢复
  4. max_total_steps / max_tool_rounds 双重上限保护(借鉴 kaoyan)
  5. extra 字段容纳扩展状态(如 expert_key / reflection_score)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowState(str, Enum):
    """工作流节点状态。

    继承 str+Enum,可直接与字符串比较,序列化时取 .value。
    """

    ANALYZE = "analyze"               # 任务分析
    PLAN = "plan"                     # 规划
    THINK = "think"                   # LLM 推理
    EXECUTE_TOOLS = "execute_tools"   # 工具执行
    REFLECT = "reflect"               # 反思
    END = "end"                       # 结束


@dataclass
class WorkflowContext:
    """工作流上下文(在节点间传递的状态)。

    所有字段均为纯数据(无引擎引用),可安全:
      - pickle / JSON 序列化
      - 写入 Checkpoint(BaseCheckpointer)
      - 跨节点传递(每个节点收到同一份 ctx 并可修改)

    字段说明:
      - task_id / user_id / session_id: 请求标识(多租户/审计/追踪)
      - goal:                           当前任务目标
      - current_node:                   当前工作流节点(驱动路由)
      - round_idx:                      当前 think 循环轮次
      - tool_round_idx:                 工具执行轮次(execute_tools 累计)
      - max_total_steps:                think 循环上限(防无限循环)
      - max_tool_rounds:                工具执行轮次上限(防工具调用失控)
      - analyze_text / plan_text / think_text / reflect_text: 各节点输出文本
      - tool_calls:                     LLM 决定的工具调用列表
      - tool_results:                   工具执行结果列表
      - final_answer:                   最终答案
      - status:                         running / success / failed
      - error:                          失败时的错误信息
      - extra:                          扩展字段(如 expert_key / reflection_score)
    """

    # 基本信息
    task_id: str = ""
    user_id: str = ""
    session_id: str = ""
    goal: str = ""

    # 工作流状态
    current_node: WorkflowState = WorkflowState.ANALYZE
    round_idx: int = 0                # 当前 think 循环轮次
    tool_round_idx: int = 0           # 工具执行轮次
    max_total_steps: int = 15         # think 循环上限
    max_tool_rounds: int = 10         # 工具执行轮次上限

    # 数据(各节点输出)
    analyze_text: str = ""            # analyze 节点输出
    plan_text: str = ""               # plan 节点输出
    think_text: str = ""              # think 节点输出
    tool_calls: list[dict] = field(default_factory=list)     # LLM 决定的工具调用
    tool_results: list[dict] = field(default_factory=list)   # 工具执行结果
    reflect_text: str = ""            # reflect 节点输出
    final_answer: str = ""            # 最终答案

    # 状态标志
    status: str = "running"           # running / success / failed
    error: str = ""

    # 扩展字段(供节点存放自定义状态,如 expert_key / reflection_score)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典(供 Checkpoint 持久化)。

        将所有字段转为 JSON 友好的纯数据:
          - WorkflowState → str(.value)
          - list/dict → 拷贝副本(避免外部修改污染 ctx)
        """
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "current_node": self.current_node.value,
            "round_idx": self.round_idx,
            "tool_round_idx": self.tool_round_idx,
            "max_total_steps": self.max_total_steps,
            "max_tool_rounds": self.max_tool_rounds,
            "analyze_text": self.analyze_text,
            "plan_text": self.plan_text,
            "think_text": self.think_text,
            "tool_calls": list(self.tool_calls),
            "tool_results": list(self.tool_results),
            "reflect_text": self.reflect_text,
            "final_answer": self.final_answer,
            "status": self.status,
            "error": self.error,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowContext":
        """从字典反序列化(与 to_dict 互逆)。

        Args:
            data: to_dict 产出的字典(允许缺失部分字段,用默认值填充)

        Returns:
            重建的 WorkflowContext 实例

        Raises:
            TypeError: data 不是 dict
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"data must be dict, got {type(data).__name__}"
            )

        # current_node: 字符串 → 枚举(非法值降级为 ANALYZE)
        raw_node = data.get("current_node", WorkflowState.ANALYZE.value)
        if isinstance(raw_node, WorkflowState):
            current_node = raw_node
        else:
            try:
                current_node = WorkflowState(str(raw_node))
            except ValueError:
                current_node = WorkflowState.ANALYZE

        # 数值字段安全转换(容忍字符串形式的整数)
        def _int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        return cls(
            task_id=data.get("task_id", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            goal=data.get("goal", ""),
            current_node=current_node,
            round_idx=_int(data.get("round_idx", 0), 0),
            tool_round_idx=_int(data.get("tool_round_idx", 0), 0),
            max_total_steps=_int(data.get("max_total_steps", 15), 15),
            max_tool_rounds=_int(data.get("max_tool_rounds", 10), 10),
            analyze_text=data.get("analyze_text", ""),
            plan_text=data.get("plan_text", ""),
            think_text=data.get("think_text", ""),
            tool_calls=list(data.get("tool_calls", [])),
            tool_results=list(data.get("tool_results", [])),
            reflect_text=data.get("reflect_text", ""),
            final_answer=data.get("final_answer", ""),
            status=data.get("status", "running"),
            error=data.get("error", ""),
            extra=dict(data.get("extra", {})),
        )


__all__ = ["WorkflowState", "WorkflowContext"]
