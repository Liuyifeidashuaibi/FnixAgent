"""SOP(标准作业流程)数据模型 —— P3-3。

借鉴:
  - MetaGPT:SOP 作为一等公民,Action 序列 + 依赖关系 + 期望输出校验
  - LangGraph:状态图节点 + 条件边
  - OpenAI Agents SDK:结构化输出校验

设计要点:
  1. SOP 由 Action 序列组成,每个 Action 调用一个工具
  2. Action.depends_on 声明依赖(其他 Action 的索引),支持 DAG
  3. ExpectedOutput 用 JSON Schema 校验工具输出
  4. ExecutionTrace 记录每个 Action 的执行结果(成功/失败/跳过/耗时)
  5. SOP 可被 SOPCompiler 编译为 LangGraph 子图(可选)

用例:
    sop = SOP(
        name="weekly-report",
        goal="生成本周工作周报",
        actions=[
            Action(name="collect", tool_name="excel_read",
                   arguments={"path": "week.xlsx"}),
            Action(name="summarize", tool_name="llm_summarize",
                   arguments={"template": "weekly"},
                   depends_on=[0]),
            Action(name="write", tool_name="word_create",
                   arguments={"template": "weekly.docx"},
                   depends_on=[1]),
        ],
    )
    trace = executor.execute(sop, ctx)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generator, Optional


# ---------------------------------------------------------------------------
# Action 状态
# ---------------------------------------------------------------------------


class ActionStatus(str, Enum):
    """Action 执行状态。"""

    PENDING = "pending"        # 待执行
    RUNNING = "running"        # 执行中
    SUCCESS = "success"        # 成功
    FAILED = "failed"          # 失败
    SKIPPED = "skipped"        # 跳过(依赖失败)
    BLOCKED = "blocked"        # 阻塞(等待依赖完成)


# ---------------------------------------------------------------------------
# ExpectedOutput(JSON Schema 校验)
# ---------------------------------------------------------------------------


@dataclass
class ExpectedOutput:
    """Action 的期望输出(JSON Schema 校验)。

    Attributes:
        schema:      JSON Schema dict,用于校验工具输出
        description: 期望输出的描述(供日志/调试)
        required:    是否必须校验(False 时跳过校验)
    """

    schema: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    required: bool = True

    def validate(self, output: Any) -> tuple[bool, str]:
        """校验 output 是否符合 schema。

        Args:
            output: 工具执行结果

        Returns:
            (is_valid, error_message)
            is_valid=True 时 error_message 为空
        """
        if not self.required:
            return True, ""
        if not self.schema:
            # 未定义 schema,跳过校验
            return True, ""
        try:
            import jsonschema  # type: ignore
        except ImportError:
            # jsonschema 未安装,降级为基本类型检查
            return self._basic_validate(output)
        try:
            jsonschema.validate(instance=output, schema=self.schema)
            return True, ""
        except jsonschema.ValidationError as e:
            return False, str(e.message)
        except Exception as e:
            return False, f"schema validation error: {e}"

    def _basic_validate(self, output: Any) -> tuple[bool, str]:
        """降级校验(jsonschema 未安装时)。"""
        expected_type = self.schema.get("type")
        if not expected_type:
            return True, ""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        py_type = type_map.get(expected_type)
        if py_type is None:
            return True, ""  # 未知类型,跳过
        if not isinstance(output, py_type):
            return False, f"expected {expected_type}, got {type(output).__name__}"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": dict(self.schema),
            "description": self.description,
            "required": self.required,
        }


# ---------------------------------------------------------------------------
# Action(SOP 中的一个步骤)
# ---------------------------------------------------------------------------


@dataclass
class Action:
    """SOP 中的一个 Action(调用一个工具)。

    Attributes:
        name:           Action 名(SOP 内唯一)
        tool_name:      调用的工具名(对应 ToolRegistry 中的工具)
        arguments:      工具参数(静态;动态参数通过 arguments_template 支持)
        expected_output: 期望输出(可选,用于校验)
        depends_on:     依赖的 Action 索引列表(本 Action 在这些 Action 完成后才能执行)
        retry_policy:   重试策略(可选;覆盖工具默认策略)
        timeout:        超时秒数(可选;None 表示不超时)
        description:    描述(供日志/调试)
    """

    name: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    expected_output: Optional[ExpectedOutput] = None
    depends_on: list[int] = field(default_factory=list)
    retry_policy: Optional[dict[str, Any]] = None
    timeout: Optional[float] = None
    description: str = ""

    def __post_init__(self) -> None:
        # 校验 Action 名非空
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Action name must be a non-empty string")
        if not self.tool_name or not isinstance(self.tool_name, str):
            raise ValueError(f"Action '{self.name}': tool_name must be non-empty")
        # 校验依赖索引非负
        for dep in self.depends_on:
            if dep < 0:
                raise ValueError(
                    f"Action '{self.name}': depends_on contains negative index {dep}"
                )
        # 参数消毒:拒绝 arguments 中含路径遍历/null 字节的字符串值
        # (防止恶意 SOP 通过参数注入攻击底层工具)
        self._sanitize_arguments(self.arguments)

    @staticmethod
    def _sanitize_arguments(arguments: dict[str, Any]) -> None:
        """递归消毒 arguments 中的字符串值(防止路径遍历/null 字节注入)。

        就地修改:若发现危险字符串,替换为空字符串。
        """
        dangerous = ("..", "\x00")
        for key, val in arguments.items():
            if isinstance(val, str):
                for pat in dangerous:
                    if pat in val:
                        arguments[key] = ""
                        break
            elif isinstance(val, dict):
                Action._sanitize_arguments(val)
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, str):
                        for pat in dangerous:
                            if pat in item:
                                val[i] = ""
                                break


# ---------------------------------------------------------------------------
# SOP(标准作业流程)
# ---------------------------------------------------------------------------


@dataclass
class SOP:
    """标准作业流程(SOP)。

    Attributes:
        name:    SOP 名(唯一标识)
        goal:    SOP 目标(供日志/调试)
        actions: Action 序列(按索引引用依赖)
        version: SOP 版本号(语义化版本)
        metadata: 扩展元数据(如创建者/标签/权限)
    """

    name: str
    goal: str = ""
    actions: list[Action] = field(default_factory=list)
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 校验依赖索引不越界
        n = len(self.actions)
        for i, action in enumerate(self.actions):
            for dep in action.depends_on:
                if dep >= n:
                    raise ValueError(
                        f"Action[{i}] '{action.name}': depends_on[{dep}] "
                        f"out of range (actions count={n})"
                    )
                if dep == i:
                    raise ValueError(
                        f"Action[{i}] '{action.name}': cannot depend on itself"
                    )

    def topological_order(self) -> list[list[int]]:
        """返回拓扑分层(Kahn 算法)。

        每一层是可并行执行的 Action 索引列表。
        例:[[0], [1, 2], [3]] 表示:
          - 第 0 层:Action[0]
          - 第 1 层:Action[1], Action[2](可并行)
          - 第 2 层:Action[3](依赖 1 和 2)

        Returns:
            分层列表,每层是 Action 索引列表

        Raises:
            ValueError: 检测到依赖环
        """
        # 复用生成器实现,收集成 list 返回(保持 API 兼容)
        return list(self.iter_topological_layers())

    def iter_topological_layers(self) -> Generator[list[int], None, None]:
        """拓扑分层生成器(Kahn 算法,内存优化版)。

        与 topological_order 等价,但逐层 yield,适用于大型 SOP:
          - 不一次性构建全部 layers 列表
          - 调用方可逐层处理,处理完即释放该层内存

        Yields:
            每一层的 Action 索引列表(已排序保证确定性)

        Raises:
            ValueError: 检测到依赖环
        """
        n = len(self.actions)
        if n == 0:
            return

        # 计算入度:in_degree[i] = Action[i] 的依赖数(未完成的)
        in_degree = [0] * n
        # dependents[dep] = 依赖 dep 的 Action 索引列表
        dependents: list[list[int]] = [[] for _ in range(n)]
        for i, action in enumerate(self.actions):
            for dep in action.depends_on:
                in_degree[i] += 1
                dependents[dep].append(i)

        # Kahn 算法:从入度为 0 的节点开始,逐层剥离
        current_layer = [i for i in range(n) if in_degree[i] == 0]
        processed = 0

        while current_layer:
            yield sorted(current_layer)  # 排序保证确定性
            next_layer: list[int] = []
            for idx in current_layer:
                # idx 完成,将其所有 dependents 的入度 -1
                for dependent in dependents[idx]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_layer.append(dependent)
                processed += 1
            current_layer = next_layer

        # 环检测:若处理的节点数 < 总节点数,说明存在环
        if processed != n:
            cyclic = [i for i in range(n) if in_degree[i] > 0]
            raise ValueError(
                f"SOP '{self.name}': dependency cycle detected at actions "
                f"{cyclic}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "goal": self.goal,
            "version": self.version,
            "actions": [
                {
                    "name": a.name,
                    "tool_name": a.tool_name,
                    "arguments": dict(a.arguments),
                    "depends_on": list(a.depends_on),
                    "description": a.description,
                    "expected_output": a.expected_output.to_dict() if a.expected_output else None,
                    "timeout": a.timeout,
                }
                for a in self.actions
            ],
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# ActionResult / ExecutionTrace(执行轨迹)
# ---------------------------------------------------------------------------


@dataclass
class ActionResult:
    """单个 Action 的执行结果。

    Attributes:
        action_name:  Action 名
        action_index: Action 在 SOP 中的索引
        status:       执行状态
        output:       工具输出(成功时)
        error:        错误信息(失败时)
        duration_ms:  执行耗时(毫秒)
        attempts:     实际尝试次数(含重试)
        validation_error: ExpectedOutput 校验失败信息(若有)
    """

    action_name: str = ""
    action_index: int = -1
    status: ActionStatus = ActionStatus.PENDING
    output: Any = None
    error: str = ""
    duration_ms: float = 0.0
    attempts: int = 0
    validation_error: str = ""

    @property
    def success(self) -> bool:
        """是否成功。"""
        return self.status == ActionStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "action_index": self.action_index,
            "status": self.status.value,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "validation_error": self.validation_error,
            "has_output": self.output is not None,
        }


@dataclass
class ExecutionTrace:
    """SOP 执行轨迹(全部 Action 的执行结果)。

    Attributes:
        sop_name:    SOP 名
        started_at:  开始时间戳
        ended_at:    结束时间戳
        results:     每个 Action 的执行结果(按 Action 索引排列)
        success:     整体是否成功(全部 Action 成功)
        error:       整体错误信息(失败时)
    """

    sop_name: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    results: list[ActionResult] = field(default_factory=list)
    success: bool = True
    error: str = ""

    @property
    def duration_ms(self) -> float:
        """总耗时(毫秒)。"""
        if self.started_at == 0 or self.ended_at == 0:
            return 0.0
        return (self.ended_at - self.started_at) * 1000

    def get_result(self, action_index: int) -> Optional[ActionResult]:
        """按 Action 索引获取执行结果。"""
        if 0 <= action_index < len(self.results):
            return self.results[action_index]
        return None

    def get_result_by_name(self, action_name: str) -> Optional[ActionResult]:
        """按 Action 名获取执行结果。"""
        for r in self.results:
            if r.action_name == action_name:
                return r
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sop_name": self.sop_name,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "results": [r.to_dict() for r in self.results],
        }


__all__ = [
    "ActionStatus",
    "ExpectedOutput",
    "Action",
    "SOP",
    "ActionResult",
    "ExecutionTrace",
]
