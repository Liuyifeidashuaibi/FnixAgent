"""
统一工具协议 (Tool Protocol)。

定义工具的元数据结构、执行函数签名和入参校验逻辑。
所有业务工具(论文检索/Word编辑/PDF生成等)均按此协议注册,
引擎层只认 ToolMetadata + func,不感知具体业务实现。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from fnixagent.core.types import ToolCallState, ToolPermission

if TYPE_CHECKING:
    from fnixagent.core.tools.retry import RetryPolicy

# 工具执行函数的统一签名: 接收 dict 参数,返回任意结果
ToolFunc = Callable[[dict[str, Any]], Any]

# JSON Schema 类型 → Python 类型映射(模块级预定义,避免每次校验重建)
_JSON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ---------------------------------------------------------------------------
# P2-4: 工具两层架构(L1 Office 专家 + L2 办公生态 + INFRA 基础设施)
# ---------------------------------------------------------------------------


class ToolLayer(str, Enum):
    """工具层级。

    L1_OFFICE:     L1 Office 专家层(Word/Excel/PPT/PDF 等顶级 office 能力,护城河)
    L2_ECOSYSTEM:  L2 办公生态层(邮件/日程/会议/IM 等办公生态连接器,适度覆盖)
    INFRA:         基础设施层(检索/嵌入/向量化等内部能力,不直接暴露给 LLM)

    检索时 L1 默认加权(l1_boost),让 LLM 优先选择 Office 专家能力。
    """

    L1_OFFICE = "L1_OFFICE"
    L2_ECOSYSTEM = "L2_ECOSYSTEM"
    INFRA = "INFRA"


@dataclass
class ToolMetadata:
    """
    工具元数据(标准化描述)。

    给 LLM 看的描述和给引擎看的权限/超时/限流都在这里。
    STP 扩展字段(skill_level/topology_binding/priority)用于技能-拓扑绑定。
    P2-4 扩展字段(layer/source/cost_score/description_embedding)用于两层架构 + 检索。
    """

    name: str  # 工具唯一名(如 "search_paper")
    description: str  # 功能描述(给 LLM 看)
    category: str = "general"  # 分类(search/word/pdf/chart/...)
    input_schema: dict = field(default_factory=dict)  # JSON Schema 入参
    output_schema: dict = field(default_factory=dict)  # JSON Schema 输出
    permission_level: ToolPermission = ToolPermission.LOW
    timeout_ms: int = 30000  # 超时毫秒
    rate_limit: int | None = None  # 每分钟调用上限
    enabled: bool = True
    version: str = "1.0.0"
    # -- STP 扩展:技能-拓扑突触协议 -----------------------------------------
    skill_level: str = "basic"  # 技能级别: basic/reasoning/meta
    topology_binding: str | None = None  # 绑定的 L2 概念节点 ID
    priority: float = 0.5  # 调度优先级(由拓扑权重动态换算)
    # -- P0-4 扩展:重试策略 + 并发安全 + 初始状态 ----------------------------
    retry_policy: RetryPolicy | None = None  # 重试策略(None 表示用默认)
    is_concurrency_safe: bool = True  # 是否线程安全(决定并行/串行执行)
    initial_state: ToolCallState = ToolCallState.CREATED  # 工具调用初始状态
    # -- P2-4 扩展:两层架构 + 检索 ------------------------------------------
    layer: ToolLayer | None = None  # 工具层级(L1_OFFICE/L2_ECOSYSTEM/INFRA)
    source: str = "builtin"  # 来源:builtin(内置)/mcp(外部 MCP)/market(技能市场)
    cost_score: float = 0.5  # 成本评分(0.0-1.0,越低越便宜;影响 LLM 工具选择)
    description_embedding: list[float] | None = None  # 描述向量(由 ToolRetriever.build_index 计算)

    def __post_init__(self) -> None:
        """构造后校验:工具名非空、超时为正、成本评分合法。"""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ToolMetadata.name 必须为非空字符串")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("ToolMetadata.description 必须为非空字符串")
        if not isinstance(self.timeout_ms, int) or self.timeout_ms <= 0:
            raise ValueError("ToolMetadata.timeout_ms 必须为正整数")
        if not (0.0 <= self.cost_score <= 1.0):
            raise ValueError("ToolMetadata.cost_score 必须在 [0.0, 1.0] 范围内")

    def to_llm_description(self) -> dict:
        """
        生成给 LLM function-calling 的工具描述。
        格式兼容 OpenAI tools API。
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
                or {
                    "type": "object",
                    "properties": {},
                },
            },
        }


@dataclass
class RegisteredTool:
    """已注册的工具: 元数据 + 执行函数。"""

    metadata: ToolMetadata
    func: ToolFunc


# ---------------------------------------------------------------------------
# 入参校验
# ---------------------------------------------------------------------------


def validate_arguments(metadata: ToolMetadata, arguments: dict[str, Any]) -> tuple[bool, list[str]]:
    """基于 input_schema 做轻量入参校验。

    检查项:
      - 必填字段是否存在
      - 字段类型是否与 JSON Schema 声明匹配(bool 与 int 严格区分)

    Args:
        metadata: 工具元数据(含 input_schema)
        arguments: 待校验的参数字典

    Returns:
        (是否通过, 错误信息列表);通过时错误列表为空

    Raises:
        TypeError: arguments 不是 dict
    """
    if not isinstance(arguments, dict):
        raise TypeError(f"arguments 必须为 dict, 实为 {type(arguments).__name__}")
    if not metadata.input_schema:
        return True, []

    errors: list[str] = []
    schema = metadata.input_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # 必填检查
    for field_name in required:
        if field_name not in arguments:
            errors.append(f"缺少必填参数: '{field_name}'")

    # 类型检查(使用模块级 _JSON_TYPE_MAP,避免每次重建)
    for field_name, value in arguments.items():
        if field_name not in properties:
            # 未知字段: 允许但可告警
            continue
        expected_type = properties[field_name].get("type")
        if expected_type and expected_type in _JSON_TYPE_MAP:
            py_type = _JSON_TYPE_MAP[expected_type]
            # bool 是 int 的子类,需特殊处理
            if expected_type == "boolean" and isinstance(value, bool):
                continue
            if expected_type == "integer" and isinstance(value, bool):
                errors.append(f"参数 '{field_name}' 应为整数,实为布尔值")
                continue
            if not isinstance(value, py_type):
                errors.append(
                    f"参数 '{field_name}' 应为 {expected_type},实为 {type(value).__name__}"
                )

    return len(errors) == 0, errors
