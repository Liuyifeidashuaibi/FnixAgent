"""SOP(标准作业流程)模块 —— P3-3。

借鉴 MetaGPT 的 SOP 一等公民设计,提供:
  - SOP 数据模型(Action 序列 + 依赖关系 + 期望输出校验)
  - SOPExecutor(拓扑排序分层执行 + 并行 + 重试 + 校验)
  - SOPCompiler(SOP → LangGraph 子图,可选)

模块导出:
  - ActionStatus:     Action 执行状态枚举
  - ExpectedOutput:   期望输出(JSON Schema 校验)
  - Action:           SOP 中的一个步骤
  - SOP:              标准作业流程
  - ActionResult:     单个 Action 执行结果
  - ExecutionTrace:   SOP 执行轨迹
  - SOPExecutor:      SOP 执行器
  - FailurePolicy:    失败策略常量
  - SOPCompiler:      SOP → LangGraph 子图编译器
"""
from fnixagent.core.sop.executor import FailurePolicy, SOPExecutor
from fnixagent.core.sop.models import (
    Action,
    ActionStatus,
    ActionResult,
    ExecutionTrace,
    ExpectedOutput,
    SOP,
)
from fnixagent.core.sop.compiler import SOPCompiler

__all__ = [
    "Action",
    "ActionStatus",
    "ActionResult",
    "ExecutionTrace",
    "ExpectedOutput",
    "SOP",
    "SOPExecutor",
    "FailurePolicy",
    "SOPCompiler",
]
