"""块化消息(借鉴 AgentScope Msg + ContentBlock)。

本模块引入块化消息模型,替代现有 core/types.py 中的 Message(纯 str content)。
设计目标:
  1. content 为 list[Block],支持文本/思考/工具调用/工具结果/数据等多种块
  2. 携带路由字段(send_to/cause_by/sent_from),单 Agent 留空,P3 多 Agent 填写
  3. id 字段供 P0-1 Reducer 按id 去重合并,消除状态覆盖隐患

兼容方案:现有 Message 保留,新增 Msg;通过 to_legacy_dict() 兼容 to_llm_dict() 格式;
节点返回值可渐进迁移。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Union

# ---------------------------------------------------------------------------
# ContentBlock 基类 + 6 种 Block
# ---------------------------------------------------------------------------


@dataclass
class ContentBlock:
    """内容块基类。

    所有内容块共享 block_type 与 block_id 字段,
    block_id 用于跨消息去重与追踪。
    """

    block_type: str = "text"
    block_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class TextBlock(ContentBlock):
    """文本块(最常见,承载自然语言文本)。"""

    block_type: str = "text"
    text: str = ""


@dataclass
class ThinkingBlock(ContentBlock):
    """思考块(ReAct thought / GLM-4.5 思考模式)。

    与 TextBlock 分离,便于前端折叠展示思考过程,
    且不计入 LLM 上下文(避免思考链污染)。
    """

    block_type: str = "thinking"
    thought: str = ""


@dataclass
class HintBlock(ContentBlock):
    """提示块(系统/人工干预注入)。

    source 区分注入来源:
      - system: 系统提示(如安全约束)
      - human:  人工干预(如用户纠正)
      - tool:   工具反馈(如执行失败提示)
    """

    block_type: str = "hint"
    hint: str = ""
    source: str = "system"


@dataclass
class ToolCallBlock(ContentBlock):
    """工具调用块(LLM 决定调用工具时产出)。

    call_id 用于关联后续的 ToolResultBlock。
    """

    block_type: str = "tool_call"
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class ToolResultBlock(ContentBlock):
    """工具结果块(工具执行完成后产出)。

    通过 call_id 与 ToolCallBlock 关联。
    error 非 None 表示执行失败。
    """

    block_type: str = "tool_result"
    call_id: str = ""
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class DataBlock(ContentBlock):
    """通用数据块(图表/表格/文件引用等)。

    data_type 标识数据种类,payload 承载结构化数据。
    用于多模态结果返回(如生成的图表、文档引用)。
    """

    block_type: str = "data"
    data_type: str = ""  # chart / table / file / image
    payload: dict[str, Any] = field(default_factory=dict)


# Block 联合类型(用于类型注解)
Block = Union[
    TextBlock,
    ThinkingBlock,
    HintBlock,
    ToolCallBlock,
    ToolResultBlock,
    DataBlock,
]


# ---------------------------------------------------------------------------
# Msg 类(替代现有 Message)
# ---------------------------------------------------------------------------


@dataclass
class Msg:
    """块化消息(借鉴 AgentScope Msg)。

    与现有 core/types.py:Message 的区别:
      - content: list[Block] 而非 str(支持多模态)
      - 携带路由字段(send_to/cause_by/sent_from),单 Agent 留空,P3 填写
      - id 字段供 P0-1 Reducer 按id 去重合并

    路由字段语义(P3 多 Agent 阶段使用):
      - send_to:   目标 Agent 名(None 表示广播或当前 Agent)
      - cause_by:  触发此消息的 Action 名(用于 Watch 模式匹配)
      - sent_from: 发送方 Agent 名
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    role: str = "user"  # system / user / assistant / tool
    content: list[Block] = field(default_factory=list)
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int | None = None
    # 路由字段(单 Agent 留空,P3 多 Agent 填写)
    send_to: str | None = None
    cause_by: str | None = None
    sent_from: str | None = None

    @property
    def text_content(self) -> str:
        """提取全部 TextBlock 文本拼接。

        用于兼容现有以 str 处理 content 的代码路径。
        """
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    def get_blocks(self, block_type: str) -> list[Block]:
        """按 block_type 过滤返回块列表。

        Args:
            block_type: 块类型(如 "text" / "tool_call" / "tool_result" 等)

        Returns:
            匹配的块列表(空列表表示无匹配)

        Raises:
            TypeError: block_type 不是 str
            ValueError: block_type 为空字符串
        """
        if not isinstance(block_type, str):
            raise TypeError(f"block_type must be str, got {type(block_type).__name__}")
        if not block_type:
            raise ValueError("block_type must not be empty")
        return [b for b in self.content if b.block_type == block_type]

    def has_tool_call(self) -> bool:
        """是否包含工具调用块。"""
        return any(b.block_type == "tool_call" for b in self.content)

    def to_legacy_dict(self) -> dict[str, Any]:
        """兼容现有 Message.to_llm_dict() 格式。

        返回 {"role", "content", "name"} 三字段,
        供 LLM provider 的 chat 接口直接消费。
        """
        d: dict[str, Any] = {"role": self.role, "content": self.text_content}
        if self.name:
            d["name"] = self.name
        return d

    def to_dict(self) -> dict[str, Any]:
        """完整序列化(供持久化/日志)。"""
        return {
            "id": self.id,
            "role": self.role,
            "content": [_block_to_dict(b) for b in self.content],
            "name": self.name,
            "metadata": self.metadata,
            "token_count": self.token_count,
            "send_to": self.send_to,
            "cause_by": self.cause_by,
            "sent_from": self.sent_from,
        }


def _block_to_dict(block: Block) -> dict[str, Any]:
    """将 Block 序列化为 dict(用于持久化/日志)。

    Args:
        block: 任意 Block 子类实例

    Returns:
        dataclasses.asdict 产出的纯数据字典
    """
    return asdict(block)


# ---------------------------------------------------------------------------
# 工厂函数(便捷构造)
# ---------------------------------------------------------------------------


def user_msg(text: str, **kwargs: Any) -> Msg:
    """构造用户文本消息。

    Args:
        text: 用户输入文本
        **kwargs: 透传给 Msg 构造函数(如 name / metadata / send_to 等)

    Returns:
        role="user" 的 Msg

    Raises:
        TypeError: text 不是 str
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    return Msg(role="user", content=[TextBlock(text=text)], **kwargs)


def assistant_msg(text: str = "", blocks: list[Block] | None = None, **kwargs: Any) -> Msg:
    """构造助手消息(可传 blocks 或 text)。

    Args:
        text:   助手文本(当 blocks 为 None 时使用)
        blocks: 内容块列表(优先于 text)
        **kwargs: 透传给 Msg 构造函数

    Returns:
        role="assistant" 的 Msg

    Raises:
        TypeError: text 不是 str 或 blocks 不是 list
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if blocks is not None and not isinstance(blocks, list):
        raise TypeError(f"blocks must be list or None, got {type(blocks).__name__}")
    if blocks is not None:
        content = blocks
    elif text:
        content = [TextBlock(text=text)]
    else:
        content = []
    return Msg(role="assistant", content=content, **kwargs)


def system_msg(text: str, **kwargs: Any) -> Msg:
    """构造系统提示消息。

    Args:
        text: 系统提示文本
        **kwargs: 透传给 Msg 构造函数

    Returns:
        role="system" 的 Msg

    Raises:
        TypeError: text 不是 str
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    return Msg(role="system", content=[TextBlock(text=text)], **kwargs)


def tool_msg(call_id: str, output: Any, error: str | None = None, **kwargs: Any) -> Msg:
    """构造工具结果消息(role=tool)。

    Args:
        call_id: 工具调用 ID(用于关联 ToolCallBlock)
        output:  工具输出
        error:   错误信息(None 表示成功)
        **kwargs: 透传给 Msg 构造函数

    Returns:
        role="tool" 的 Msg

    Raises:
        TypeError:  call_id 不是 str
        ValueError: call_id 为空字符串
    """
    if not isinstance(call_id, str):
        raise TypeError(f"call_id must be str, got {type(call_id).__name__}")
    if not call_id:
        raise ValueError("call_id must not be empty")
    return Msg(
        role="tool",
        content=[ToolResultBlock(call_id=call_id, output=output, error=error)],
        **kwargs,
    )


def thinking_msg(thought: str, **kwargs: Any) -> Msg:
    """构造思考消息(ReAct thought,角色 assistant)。

    Args:
        thought: 思考内容文本
        **kwargs: 透传给 Msg 构造函数

    Returns:
        含 ThinkingBlock 的 Msg

    Raises:
        TypeError: thought 不是 str
    """
    if not isinstance(thought, str):
        raise TypeError(f"thought must be str, got {type(thought).__name__}")
    return Msg(role="assistant", content=[ThinkingBlock(thought=thought)], **kwargs)


# ---------------------------------------------------------------------------
# Reducer 语义(供 P0-1 AgentState.messages 字段使用)
# ---------------------------------------------------------------------------


def add_msgs(left: list[Msg] | None, right: list[Msg]) -> list[Msg]:
    """Msg 列表 Reducer:按 id 去重追加。

    LangGraph 的 Annotated[list[Msg], add_msgs] 会调用此函数合并状态更新。
    语义:同 id 的 Msg 视为已存在,不再追加(避免重复)。

    Args:
        left:  当前状态中的 Msg 列表(可能为 None)
        right: 本次节点返回的新增 Msg 列表

    Returns:
        合并后的 Msg 列表(新对象,不修改入参)

    Raises:
        TypeError: right 不是 list
    """
    if right is None:
        # 容错:LangGraph 偶尔会传入 None,等价于无新增
        return list(left or [])
    if not isinstance(right, list):
        raise TypeError(f"right must be list[Msg], got {type(right).__name__}")
    merged = list(left or [])
    seen_ids = {m.id for m in merged}
    for msg in right:
        if msg.id not in seen_ids:
            merged.append(msg)
            seen_ids.add(msg.id)
    return merged


def add_dicts_by_key(left: list[dict] | None, right: list[dict], key: str = "id") -> list[dict]:
    """dict 列表 Reducer:按指定 key 去重追加。

    供 tool_calls/tool_results 等 dict 列表字段使用。

    Args:
        left:  当前状态中的 dict 列表(可能为 None)
        right: 本次新增的 dict 列表
        key:   用于去重的字段名(默认 "id")

    Returns:
        合并后的 dict 列表(新对象,不修改入参)

    Raises:
        TypeError: right 不是 list 或 key 不是 str
    """
    if right is None:
        return list(left or [])
    if not isinstance(right, list):
        raise TypeError(f"right must be list[dict], got {type(right).__name__}")
    if not isinstance(key, str):
        raise TypeError(f"key must be str, got {type(key).__name__}")
    merged = list(left or [])
    seen = {d.get(key) for d in merged if d.get(key) is not None}
    for d in right:
        k = d.get(key)
        if k is None or k not in seen:
            merged.append(d)
            if k is not None:
                seen.add(k)
    return merged
