"""LangGraph 状态 Reducer 函数集合(借鉴 LangGraph Annotated[T, reducer])。

Reducer 定义状态字段的合并语义:当多个节点返回同一字段的更新时,
LangGraph 调用对应 reducer 合并,而非默认覆盖。

7 个 reducer 覆盖 fnixagent 全部状态字段:
  - last_value:    覆盖(默认语义,用于 goal/error 等单值字段)
  - add_int:       累加(用于 iteration 计数)
  - append_list:   追加(用于 tool_calls/tool_results,允许重复)
  - append_unique: 去重追加(用于 intent_keywords/selected_skills,去重)
  - add_messages:  消息去重(按 id 或 role+content 去重)
  - merge_dict:    字典合并(用于 skill_priorities,后者覆盖前者)
  - merge_trace:   深合并(用于 trace,list 追加+dict 合并)

设计原则:reducer 为纯函数,不修改入参,返回新对象。
"""

from __future__ import annotations

from typing import Any


def last_value(left: Any, right: Any) -> Any:
    """覆盖语义:返回右值(最后写入胜出)。

    用于单值字段:goal / error / final_answer / should_continue / user_input 等。
    与 LangGraph 默认行为一致,显式声明可读性更好。
    """
    return right


def add_int(left: int | None, right: int) -> int:
    """累加语义:左值 + 右值。

    用于 iteration 计数字段,每次节点返回 1 表示递增一轮。
    """
    return (left or 0) + right


def append_list(left: list | None, right: list) -> list:
    """追加语义:左列表 + 右列表(允许重复)。

    用于 tool_calls / tool_results / topology_paths 等,
    这些字段允许重复(同一工具可能被多次调用)。
    """
    return (left or []) + list(right)


def append_unique(left: list | None, right: list) -> list:
    """去重追加语义:合并去重(按值相等判断)。

    用于 intent_keywords / concept_path / selected_skills 等,
    这些字段不应有重复元素。
    """
    merged = list(left or [])
    for item in right:
        if item not in merged:
            merged.append(item)
    return merged


def add_messages(left: list[dict] | None, right: list[dict]) -> list[dict]:
    """消息去重追加:按 id 或 role+content 去重。

    用于 messages 字段。
    去重策略(解决消息合并冲突):
      1. 优先按 msg["id"] 去重(块化 Msg 的 id 字段)
      2. 无 id 时按 role+content 拼接去重(兼容旧格式)

    与 core/types_msg.py:add_msgs 语义一致,但此处处理 dict 格式
    (LangGraph 状态要求可序列化,Msg 对象需先 to_dict)。

    Args:
        left:  累积消息列表(可为 None 表示首次)
        right: 新增消息列表

    Returns:
        去重合并后的消息列表(新对象, 不修改入参)
    """
    merged: list[dict] = []
    seen: set[str] = set()
    for msg in (left or []) + right:
        # 防御性: 跳过非 dict 元素(避免脏数据导致 KeyError)
        if not isinstance(msg, dict):
            continue
        # 去重 key: 优先用 id, 无 id 用 role:content
        key = msg.get("id") or f"{msg.get('role', '')}:{msg.get('content', '')}"
        if key not in seen:
            seen.add(key)
            merged.append(msg)
    return merged


def merge_dict(left: dict | None, right: dict) -> dict:
    """字典合并语义:后者覆盖前者。

    用于 skill_priorities 等字典字段,
    同 key 时右值覆盖左值,新 key 直接加入。
    """
    merged = dict(left or {})
    merged.update(right)
    return merged


def merge_trace(left: dict | None, right: dict) -> dict:
    """trace 字段深合并:list 追加,dict 递归合并,其他覆盖。

    用于 trace 字段(执行轨迹,含 steps/tool_calls/reflections 等)。
    合并规则:
      - 同 key 且双方都是 list:追加
      - 同 key 且双方都是 dict:递归合并(本函数)
      - 其他:右值覆盖左值
    """
    merged = dict(left or {})
    for k, v in right.items():
        if k in merged and isinstance(merged[k], list) and isinstance(v, list):
            merged[k] = merged[k] + v
        elif k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = merge_trace(merged[k], v)
        else:
            merged[k] = v
    return merged
