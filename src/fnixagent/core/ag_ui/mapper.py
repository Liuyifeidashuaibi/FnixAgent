"""AG-UI 事件映射 — Python 层 Work/Code NDJSON → AG-UI SSE。

扩展版:对齐 AG-UI Protocol 17 事件类型。
https://docs.ag-ui.com/concepts/events

事件类型清单:
    1.  RUN_STARTED          — agent loop 启动
    2.  RUN_FINISHED         — agent loop 正常结束
    3.  RUN_ERROR            — agent loop 异常
    4.  TEXT_MESSAGE_START   — 流式文本消息开始
    5.  TEXT_MESSAGE_CONTENT — 流式文本消息增量
    6.  TEXT_MESSAGE_END     — 流式文本消息结束
    7.  THINKING_START       — 推理模型思考开始(前端折叠)
    8.  THINKING_CONTENT     — 思考内容增量
    9.  THINKING_END         — 思考结束
    10. TOOL_CALL_START      — 工具调用开始
    11. TOOL_CALL_ARGS       — 工具参数流式增量
    12. TOOL_CALL_END        — 工具调用结束(等待结果)
    13. TOOL_CALL_RESULT     — 工具结果返回
    14. STEP_STARTED         — 步骤开始
    15. STEP_FINISHED        — 步骤结束
    16. STATE_SNAPSHOT       — 全量状态快照(上下文预算等)
    17. STATE_DELTA          — 增量状态
    18. CUSTOM               — 自定义事件(evolution/KTG/STP/MFP/mission/widget/review/heal)
    19. HUMAN_APPROVAL       — 人工审批门(阻塞)
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

# ── AG-UI 标准事件类型 ─────────────────────────────────────────
AGUI_RUN_STARTED = "RUN_STARTED"
AGUI_RUN_FINISHED = "RUN_FINISHED"
AGUI_RUN_ERROR = "RUN_ERROR"
AGUI_TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
AGUI_TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
AGUI_TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
AGUI_THINKING_START = "THINKING_START"
AGUI_THINKING_CONTENT = "THINKING_CONTENT"
AGUI_THINKING_END = "THINKING_END"
AGUI_TOOL_CALL_START = "TOOL_CALL_START"
AGUI_TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
AGUI_TOOL_CALL_END = "TOOL_CALL_END"
AGUI_TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
AGUI_STEP_STARTED = "STEP_STARTED"
AGUI_STEP_FINISHED = "STEP_FINISHED"
AGUI_STATE_SNAPSHOT = "STATE_SNAPSHOT"
AGUI_STATE_DELTA = "STATE_DELTA"
AGUI_CUSTOM = "CUSTOM"
AGUI_HUMAN_APPROVAL = "HUMAN_APPROVAL"

# ── Fnix 内部 chunk → AG-UI 事件类型映射 ──────────────────────
CHUNK_MAP: dict[str, str] = {
    # 运行生命周期
    "run_start": AGUI_RUN_STARTED,
    "done": AGUI_RUN_FINISHED,
    "error": AGUI_RUN_ERROR,
    # 文本消息
    "text": AGUI_TEXT_MESSAGE_CONTENT,
    "message": AGUI_TEXT_MESSAGE_CONTENT,
    "text_start": AGUI_TEXT_MESSAGE_START,
    "text_end": AGUI_TEXT_MESSAGE_END,
    # 思考(推理模型)
    "thought": AGUI_THINKING_CONTENT,
    "thinking": AGUI_THINKING_CONTENT,
    "thinking_start": AGUI_THINKING_START,
    "thinking_end": AGUI_THINKING_END,
    # 工具调用
    "action": AGUI_TOOL_CALL_START,
    "tool_call": AGUI_TOOL_CALL_START,
    "tool_args": AGUI_TOOL_CALL_ARGS,
    "tool_end": AGUI_TOOL_CALL_END,
    "tool_result": AGUI_TOOL_CALL_RESULT,
    "observation": AGUI_TOOL_CALL_RESULT,
    # 步骤
    "plan": AGUI_STEP_STARTED,
    "step_start": AGUI_STEP_STARTED,
    "step_end": AGUI_STEP_FINISHED,
    "pipeline": AGUI_STEP_STARTED,
    # 状态
    "state": AGUI_STATE_SNAPSHOT,
    "state_delta": AGUI_STATE_DELTA,
    "context": AGUI_STATE_SNAPSHOT,
    # 自定义(保持 CUSTOM,前端按 name 区分)
    "mission": AGUI_CUSTOM,
    "evolution": AGUI_CUSTOM,
    "artifact": AGUI_CUSTOM,
    "widget": AGUI_CUSTOM,
    "review": AGUI_CUSTOM,
    "heal": AGUI_CUSTOM,
    "file_change": AGUI_CUSTOM,
    # 审批
    "approval": AGUI_HUMAN_APPROVAL,
    "needs_input": AGUI_HUMAN_APPROVAL,
}


def new_run_id() -> str:
    """生成新的 run id(16 字符 hex)。"""
    return uuid.uuid4().hex[:16]


def _now_ms() -> int:
    return int(time.time() * 1000)


def map_work_chunk(chunk_type: str, content: Any, run_id: str) -> dict[str, Any]:
    """Fnix Work NDJSON chunk → AG-UI event dict。

    Args:
        chunk_type: Fnix 内部 chunk 类型(如 "text"/"tool_call"/"done")
        content: chunk 内容(任意 JSON 可序列化对象)
        run_id: 当前 run 的 id

    Returns:
        AG-UI 事件字典,可直接 json.dumps 为 SSE
    """
    ag_type = CHUNK_MAP.get(chunk_type, AGUI_CUSTOM)
    event: dict[str, Any] = {
        "type": ag_type,
        "timestamp": _now_ms(),
        "runId": run_id,
    }

    if ag_type == AGUI_CUSTOM:
        event["name"] = chunk_type
        event["value"] = content

    elif ag_type == AGUI_TEXT_MESSAGE_CONTENT:
        event["messageId"] = run_id
        event["delta"] = str(content)

    elif ag_type == AGUI_TEXT_MESSAGE_START:
        event["messageId"] = run_id
        event["role"] = "assistant"

    elif ag_type == AGUI_TEXT_MESSAGE_END:
        event["messageId"] = run_id

    elif ag_type == AGUI_THINKING_CONTENT:
        event["messageId"] = f"{run_id}-thinking"
        event["delta"] = str(content)

    elif ag_type == AGUI_THINKING_START or ag_type == AGUI_THINKING_END:
        event["messageId"] = f"{run_id}-thinking"

    elif ag_type in (
        AGUI_TOOL_CALL_START,
        AGUI_TOOL_CALL_ARGS,
        AGUI_TOOL_CALL_END,
        AGUI_TOOL_CALL_RESULT,
    ):
        tool_call_id = f"{run_id}-{chunk_type}"
        event["toolCallId"] = tool_call_id
        event["toolCallName"] = (
            content.get("name", chunk_type) if isinstance(content, dict) else chunk_type
        )
        event["parentMessageId"] = run_id
        if ag_type == AGUI_TOOL_CALL_START:
            event["delta"] = (
                content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            )
        elif ag_type == AGUI_TOOL_CALL_ARGS:
            event["delta"] = (
                str(content)
                if not isinstance(content, dict)
                else json.dumps(content.get("args", content), ensure_ascii=False)
            )
        elif ag_type == AGUI_TOOL_CALL_RESULT:
            event["content"] = (
                content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            )

    elif ag_type == AGUI_STEP_STARTED or ag_type == AGUI_STEP_FINISHED:
        event["stepName"] = (
            content.get("step", chunk_type) if isinstance(content, dict) else str(content)
        )

    elif ag_type == AGUI_STATE_SNAPSHOT:
        event["snapshot"] = content

    elif ag_type == AGUI_STATE_DELTA:
        event["delta"] = (
            content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        )

    elif ag_type == AGUI_RUN_FINISHED:
        event["result"] = content

    elif ag_type == AGUI_RUN_ERROR:
        event["message"] = str(content)

    elif ag_type == AGUI_HUMAN_APPROVAL:
        event["messageId"] = run_id
        event["reason"] = (
            content.get("reason", str(content)) if isinstance(content, dict) else str(content)
        )

    else:
        event["payload"] = content

    return event


def encode_sse(event: dict[str, Any]) -> str:
    """将事件字典编码为 SSE 行(data: <json>\\n\\n)。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ── 便捷构造函数 ──────────────────────────────────────────────


def run_started(run_id: str) -> str:
    """构造 RUN_STARTED SSE。"""
    return encode_sse(
        {
            "type": AGUI_RUN_STARTED,
            "timestamp": _now_ms(),
            "runId": run_id,
        }
    )


def run_finished(run_id: str, result: Any = None) -> str:
    """构造 RUN_FINISHED SSE。"""
    return encode_sse(
        {
            "type": AGUI_RUN_FINISHED,
            "timestamp": _now_ms(),
            "runId": run_id,
            "result": result,
        }
    )


def run_error(run_id: str, message: str) -> str:
    """构造 RUN_ERROR SSE。"""
    return encode_sse(
        {
            "type": AGUI_RUN_ERROR,
            "timestamp": _now_ms(),
            "runId": run_id,
            "message": message,
        }
    )


def text_message_start(run_id: str) -> str:
    """构造 TEXT_MESSAGE_START SSE。"""
    return encode_sse(
        {
            "type": AGUI_TEXT_MESSAGE_START,
            "timestamp": _now_ms(),
            "runId": run_id,
            "messageId": run_id,
            "role": "assistant",
        }
    )


def text_message_content(run_id: str, delta: str) -> str:
    """构造 TEXT_MESSAGE_CONTENT SSE。"""
    return encode_sse(
        {
            "type": AGUI_TEXT_MESSAGE_CONTENT,
            "timestamp": _now_ms(),
            "runId": run_id,
            "messageId": run_id,
            "delta": delta,
        }
    )


def text_message_end(run_id: str) -> str:
    """构造 TEXT_MESSAGE_END SSE。"""
    return encode_sse(
        {
            "type": AGUI_TEXT_MESSAGE_END,
            "timestamp": _now_ms(),
            "runId": run_id,
            "messageId": run_id,
        }
    )


def tool_call_start(run_id: str, tool_name: str, tool_call_id: str | None = None) -> str:
    """构造 TOOL_CALL_START SSE。"""
    return encode_sse(
        {
            "type": AGUI_TOOL_CALL_START,
            "timestamp": _now_ms(),
            "runId": run_id,
            "toolCallId": tool_call_id or f"{run_id}-{tool_name}",
            "toolCallName": tool_name,
            "parentMessageId": run_id,
        }
    )


def tool_call_result(
    run_id: str, tool_name: str, content: Any, tool_call_id: str | None = None
) -> str:
    """构造 TOOL_CALL_RESULT SSE。"""
    return encode_sse(
        {
            "type": AGUI_TOOL_CALL_RESULT,
            "timestamp": _now_ms(),
            "runId": run_id,
            "toolCallId": tool_call_id or f"{run_id}-{tool_name}",
            "toolCallName": tool_name,
            "parentMessageId": run_id,
            "content": content
            if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False),
        }
    )


def step_started(run_id: str, step_name: str) -> str:
    """构造 STEP_STARTED SSE。"""
    return encode_sse(
        {
            "type": AGUI_STEP_STARTED,
            "timestamp": _now_ms(),
            "runId": run_id,
            "stepName": step_name,
        }
    )


def step_finished(run_id: str, step_name: str) -> str:
    """构造 STEP_FINISHED SSE。"""
    return encode_sse(
        {
            "type": AGUI_STEP_FINISHED,
            "timestamp": _now_ms(),
            "runId": run_id,
            "stepName": step_name,
        }
    )


def human_approval(run_id: str, reason: str) -> str:
    """构造 HUMAN_APPROVAL SSE(阻塞,等待前端响应)。"""
    return encode_sse(
        {
            "type": AGUI_HUMAN_APPROVAL,
            "timestamp": _now_ms(),
            "runId": run_id,
            "messageId": run_id,
            "reason": reason,
        }
    )


def custom_event(run_id: str, name: str, value: Any) -> str:
    """构造 CUSTOM SSE(evolution/KTG/STP/MFP/mission/widget/review/heal)。"""
    return encode_sse(
        {
            "type": AGUI_CUSTOM,
            "timestamp": _now_ms(),
            "runId": run_id,
            "name": name,
            "value": value,
        }
    )


def state_snapshot(run_id: str, snapshot: Any) -> str:
    """构造 STATE_SNAPSHOT SSE(上下文预算等全量状态)。"""
    return encode_sse(
        {
            "type": AGUI_STATE_SNAPSHOT,
            "timestamp": _now_ms(),
            "runId": run_id,
            "snapshot": snapshot,
        }
    )


def state_delta(run_id: str, delta: Any) -> str:
    """构造 STATE_DELTA SSE(增量状态)。"""
    return encode_sse(
        {
            "type": AGUI_STATE_DELTA,
            "timestamp": _now_ms(),
            "runId": run_id,
            "delta": delta if isinstance(delta, str) else json.dumps(delta, ensure_ascii=False),
        }
    )


def map_pipeline_events(
    chunk_type: str,
    content: Any,
    run_id: str,
) -> Iterator[str]:
    """Yield SSE lines for one pipeline chunk.

    兼容旧接口:保留 map_pipeline_events 函数签名。
    """
    if chunk_type == "done":
        yield encode_sse(map_work_chunk("done", content, run_id))
        return
    if chunk_type == "error":
        yield encode_sse(map_work_chunk("error", content, run_id))
        return
    yield encode_sse(map_work_chunk(chunk_type, content, run_id))


# ── 事件类型清单(供前端对齐) ──────────────────────────────────
ALL_EVENT_TYPES: tuple[str, ...] = (
    AGUI_RUN_STARTED,
    AGUI_RUN_FINISHED,
    AGUI_RUN_ERROR,
    AGUI_TEXT_MESSAGE_START,
    AGUI_TEXT_MESSAGE_CONTENT,
    AGUI_TEXT_MESSAGE_END,
    AGUI_THINKING_START,
    AGUI_THINKING_CONTENT,
    AGUI_THINKING_END,
    AGUI_TOOL_CALL_START,
    AGUI_TOOL_CALL_ARGS,
    AGUI_TOOL_CALL_END,
    AGUI_TOOL_CALL_RESULT,
    AGUI_STEP_STARTED,
    AGUI_STEP_FINISHED,
    AGUI_STATE_SNAPSHOT,
    AGUI_STATE_DELTA,
    AGUI_CUSTOM,
    AGUI_HUMAN_APPROVAL,
)

# 17 + 2 (CUSTOM + HUMAN_APPROVAL 扩展) = 19 种事件类型
