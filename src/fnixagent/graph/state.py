"""LangGraph 全局状态定义(显式 Reducer 版本)。

基于 TypedDict 的 State 定义,LangGraph 要求 State 必须是 TypedDict,
节点函数签名为 (State) -> State(部分字段更新)。

本版本引入显式 Reducer,
消除原 total=False 默认覆盖隐患:
  - messages/tool_calls/tool_results 等列表字段:追加而非覆盖
  - iteration:累加而非覆盖
  - skill_priorities:字典合并而非覆盖
  - trace:深合并(list 追加 + dict 合并)
  - goal/error/final_answer:覆盖(单值字段,符合预期)

State 承载飞轮 ① 感知-执行阶段的全部运行时状态:
    - messages:         对话历史(与 ShortTermMemory 同步)
    - current_goal:     当前任务目标(L1 候选)
    - concept_path:     命中的 L2 概念序列
    - topology_paths:   拓扑搜索返回的路径列表
    - selected_skills:  调度器选中的技能列表
    - tool_calls:       待执行/已执行的工具调用
    - tool_results:     工具返回结果
    - trace:            执行轨迹(累积 ThoughtStep)
    - iteration:        当前迭代轮次
    - should_continue:  是否继续循环(条件边判断)
    - final_answer:     最终答案
    - error:            错误信息
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from fnixagent.graph.reducers import (
    add_int,
    add_messages,
    append_list,
    append_unique,
    last_value,
    merge_dict,
    merge_trace,
)


class GraphState(TypedDict, total=False):
    """LangGraph 全局状态(飞轮 ① 感知-执行阶段,显式 Reducer 版本)。

    A-5 重命名:原 AgentState → GraphState,避免与 core/orchestrator/state.py
    的 AgentState(可持久化上下文)同名混淆。

    total=False 表示所有字段可选,允许部分更新。
    Annotated[T, reducer] 指定该字段的合并语义:
      - 多个节点返回同一字段时,LangGraph 调用 reducer 合并
      - 无 reducer 的字段默认覆盖(等价于 last_value)

    Reducer 语义对照:
      last_value:    覆盖(单值字段)
      add_int:       累加(计数)
      append_list:   追加(允许重复)
      append_unique: 去重追加
      add_messages:  消息去重(按 id 或 role+content)
      merge_dict:    字典合并(后者覆盖前者)
      merge_trace:   深合并(list 追加 + dict 合并)
    """

    # 对话与意图
    messages: Annotated[list[dict[str, Any]], add_messages]
    user_input: Annotated[str, last_value]
    current_goal: Annotated[str, last_value]
    intent_keywords: Annotated[list[str], append_unique]

    # 拓扑推理
    concept_path: Annotated[list[str], append_unique]
    topology_paths: Annotated[list[dict[str, Any]], append_list]

    # 技能调度
    selected_skills: Annotated[list[str], append_unique]
    skill_priorities: Annotated[dict[str, float], merge_dict]

    # 工具执行
    tool_calls: Annotated[list[dict[str, Any]], append_list]
    tool_results: Annotated[list[dict[str, Any]], append_list]

    # 执行轨迹(飞轮 ① 产出,飞轮 ② 消费)
    trace: Annotated[dict[str, Any], merge_trace]
    iteration: Annotated[int, add_int]

    # 控制流
    should_continue: Annotated[bool, last_value]
    final_answer: Annotated[str, last_value]
    error: Annotated[str | None, last_value]


def create_initial_state(user_input: str) -> GraphState:
    """创建初始状态。

    Args:
        user_input: 用户输入文本(允许空字符串, 用于测试场景)

    Returns:
        初始化的 GraphState(所有字段均为空/初始值)

    Raises:
        TypeError: user_input 不是 str
    """
    # 输入校验: user_input 必须为字符串(允许空串, 兼容测试场景)
    if not isinstance(user_input, str):
        raise TypeError(f"user_input 必须为 str, 收到 {type(user_input).__name__}")
    return GraphState(
        messages=[{"role": "user", "content": user_input}],
        user_input=user_input,
        current_goal="",
        intent_keywords=[],
        concept_path=[],
        topology_paths=[],
        selected_skills=[],
        skill_priorities={},
        tool_calls=[],
        tool_results=[],
        trace={},
        iteration=0,
        should_continue=True,
        final_answer="",
        error=None,
    )


# ---------------------------------------------------------------------------
# A-5 向后兼容别名
# ---------------------------------------------------------------------------
# 原 AgentState 已重命名为 GraphState(避免与 core/orchestrator/state.py 的
# AgentState 同名)。保留 AgentState = GraphState 别名,使现有 import 不破坏;
# 新代码应使用 GraphState。
AgentState = GraphState
