"""任务 DSL 与数据模型(Phase 5.2)。

定义 fnixagent 任务引擎的核心数据结构,是 Agent 调度层的"语言":
  - TaskType:    任务类型枚举(题库/格式统一/文档编辑/...)
  - Intent:      用户意图枚举(填答案/修复乱码/统一格式/...)
  - TaskRequest: 任务请求(自然语言描述 + 文件 + 参数)
  - TaskResult:  任务执行结果(产物文件 + 待确认项 + 统计)
  - TaskStep:    任务步骤(一个任务可拆多步,带依赖关系)

设计原则:
  - 纯数据结构,不含业务逻辑(逻辑在 router.py)
  - dataclass + 类型注解,TaskResult 提供 to_dict() 支持序列化
  - 与 office.base.ExpertResult 解耦:TaskResult 是任务级聚合结果,
    ExpertResult 是单步原子操作结果;多个 ExpertResult 聚合成一个 TaskResult

数据流:
  TaskRequest --classify--> TaskRouter --route--> list[TaskStep]
  TaskStep 逐步执行产出 ExpertResult,最终聚合为 TaskResult
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# 任务类型与意图枚举
# ---------------------------------------------------------------------------


class TaskType(Enum):
    """任务类型枚举。

    每种类型对应一组固定的执行步骤模板(见 router.TaskRouter.route)。
    UNKNOWN 用于未能识别的任务,路由到最小步骤。
    """

    QUESTION_BANK = "question_bank"  # 题库处理(填答案/统一格式/删题号)
    FORMAT_NORMALIZE = "format_normalize"  # 格式统一
    DOCUMENT_EDIT = "document_edit"  # 文档编辑
    TABLE_EXTRACT = "table_extract"  # 表格抽取
    DOCUMENT_CONVERT = "document_convert"  # 格式转换
    BATCH_PROCESS = "batch_process"  # 批量处理
    DOCUMENT_REVIEW = "document_review"  # 文档审查
    DATA_ANALYSIS = "data_analysis"  # 数据分析
    REPORT_GENERATE = "report_generate"  # 报告生成
    UNKNOWN = "unknown"  # 未知/未能识别


class Intent(Enum):
    """用户意图枚举(从自然语言描述中识别)。

    一个任务可命中多个意图(如"填答案并统一格式" → FILL_ANSWER + UNIFY_FORMAT)。
    """

    FILL_ANSWER = "fill_answer"  # 填答案
    FIX_GARBLED = "fix_garbled"  # 修复乱码
    UNIFY_FORMAT = "unify_format"  # 统一格式
    DELETE_NUMBER = "delete_number"  # 删除题号
    EXTRACT_CONTENT = "extract_content"  # 提取内容
    CONVERT_FORMAT = "convert_format"  # 转换格式
    MERGE_FILES = "merge_files"  # 合并文件
    SPLIT_FILE = "split_file"  # 拆分文件


# ---------------------------------------------------------------------------
# 任务请求 / 结果 / 步骤
# ---------------------------------------------------------------------------


@dataclass
class TaskRequest:
    """任务请求。

    Attributes:
        task_id: 唯一任务 ID(默认 uuid4)
        description: 自然语言任务描述
        file_paths: 输入文件路径列表
        output_path: 输出路径(可选,None 表示原地或临时输出)
        task_type: 任务类型(classify 后填充,默认 UNKNOWN)
        intents: 识别到的用户意图列表(classify 后填充)
        params: 额外参数(字体/字号/答案表 等)
        created_at: 创建时间
        priority: 优先级(0 普通, 1 高, 2 紧急)
        requires_confirmation: 是否需要人工确认(高风险任务由 classify 置 True)
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    file_paths: list[str] = field(default_factory=list)
    output_path: str | None = None
    task_type: TaskType = TaskType.UNKNOWN
    intents: list[Intent] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    priority: int = 0
    requires_confirmation: bool = False


@dataclass
class TaskResult:
    """任务执行结果(任务级聚合)。

    Attributes:
        task_id: 对应的 TaskRequest.task_id
        success: 是否整体成功
        output_files: 产物文件路径列表
        pending_items: 待人工确认项(高风险操作的确认清单)
        stats: 统计信息(处理文件数/步骤数/各步耗时 等)
        error: 失败时的错误描述
        duration_ms: 整体耗时(毫秒)
    """

    task_id: str
    success: bool = True
    output_files: list[str] = field(default_factory=list)
    pending_items: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典(供 JSON 输出/日志/Agent 工具结果)。"""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output_files": list(self.output_files),
            "pending_items": list(self.pending_items),
            "stats": dict(self.stats),
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TaskStep:
    """任务步骤(一个任务可拆分为多个步骤)。

    Attributes:
        step_id: 步骤唯一 ID(如 "s1"/"s2")
        name: 步骤名称(人类可读,如 "解析文档")
        handler: 处理器名(如 "parser"/"format_normalizer"/"run_editor")
        params: 步骤参数(文件路径/选项 等)
        depends_on: 依赖的前置步骤 step_id 列表(空表示可立即执行)
    """

    step_id: str
    name: str
    handler: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
