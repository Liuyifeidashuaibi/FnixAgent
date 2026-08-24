"""Unified async RunEngine — one event dialect for Work + Code."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from fnixagent.core.run.checkpoint import RunCheckpointStore

SCHEMA_VERSION = 1


def _ev_data_to_dict(d: Any) -> dict[str, Any]:
    """Normalise RunEvent.data to a plain dict.

    Handles two cases:
      - plain dict / list / str (returned as-is)
      - CodingAgentEvent dataclass (fields extracted as camelCase for
        compatibility with the wire protocol expected by the frontend)
    """
    if isinstance(d, dict):
        return d
    if isinstance(d, list):
        return {"list": d}
    if d is None:
        return {}
    # CodingAgentEvent dataclass fields → wire-format camelCase keys
    if hasattr(d, "file_path"):
        return {
            "path": d.file_path or "",
            "action": d.file_action or "",
            "diff": d.diff or "",
            "content": d.content or "",
            "old_content": d.old_content or "",
        }
    if hasattr(d, "review_notes"):
        return {
            "review_passed": bool(d.review_passed) if d.review_passed is not None else None,
            "notes": d.review_notes or "",
        }
    if hasattr(d, "result"):
        # done event with TaskResult
        r = d.result
        if hasattr(r, "status"):
            return {"status": r.status, "review_passed": getattr(r, "review_passed", None)}
        return {"result": str(r)}
    return {"raw": str(d)}


@dataclass
class RunEvent:
    """Canonical stream event (AG-UI compatible envelope)."""

    type: str
    data: Any = None
    run_id: str = ""
    sequence: int = 0
    timestamp: int = 0
    channel: str = "work"
    schema_version: int = SCHEMA_VERSION

    def to_work_dict(self) -> dict[str, Any]:
        """Work pipeline / NDJSON shape: {type, data} + envelope fields."""
        return {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "channel": self.channel,
            "type": self.type,
            "data": self.data,
        }

    def to_code_ndjson(self) -> dict[str, Any]:
        """Legacy Code chat_agent NDJSON compatibility."""
        t = self.type
        d = self.data
        base = {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
        }
        if t == "thinking":
            return {**base, "type": "thinking", "content": str(d or "")}
        if t == "plan":
            return {**base, "type": "plan", "steps": d if isinstance(d, list) else []}
        if t == "step_start":
            return {**base, "type": "step_start", "step": d if isinstance(d, dict) else {}}
        if t == "step_end":
            return {**base, "type": "step_end", "step": d if isinstance(d, dict) else {}}
        if t == "file_change":
            payload = _ev_data_to_dict(d)
            return {**base, "type": "file_change", **payload}
        if t == "review":
            payload = _ev_data_to_dict(d)
            notes = str(payload.get("notes") or payload.get("review_notes") or "")
            out = (
                {**base, "type": "message", "content": notes}
                if notes
                else {**base, "type": "review", **payload}
            )
            return out
        if t == "heal":
            payload = _ev_data_to_dict(d)
            return {**base, "type": "heal", **payload}
        if t == "text" or t == "message":
            return {**base, "type": "message", "content": str(d or "")}
        if t == "done":
            payload = _ev_data_to_dict(d)
            return {**base, "type": "done", **payload}
        if t == "error":
            return {
                **base,
                "type": "done",
                "status": "failed",
                "changes": [],
                "error": str(d),
            }
        return {**base, "type": t, "data": d}


class StreamSource(Protocol):
    async def stream(self) -> AsyncIterator[dict[str, Any]]: ...


@dataclass
class RunEngine:
    """Thin façade: normalize Work/Code streams + optional SQLite sink."""

    store: RunCheckpointStore | None = None
    _seq: int = field(default=0, init=False)

    def new_run_id(self) -> str:
        return uuid.uuid4().hex[:16]

    async def run_stream(
        self,
        source: AsyncIterator[dict[str, Any]],
        *,
        channel: str = "work",
        run_id: str | None = None,
        session_id: str | None = None,
        persist: bool = True,
        meta: dict[str, Any] | None = None,
    ) -> AsyncIterator[RunEvent]:
        """Spec 4: 流式执行 + 自动 checkpoint（含 messages_so_far 完整 state）。

        对齐 LangGraph Checkpointer: 每个 node transition 后 commit state。
        上下文压缩机制: messages 超阈值时自动压缩（在 AgenticLoop 内）。

        checkpoint state 包含:
            messages_so_far: list[dict]  — 累积的 OpenAI chat 格式消息
            artifacts_so_far: list[dict] — 累积的产物路径
            completed_steps: int        — 完成的工具调用次数
            current_step: str           — 当前阶段 (security/memory/ktg/agent/done)
            last_type: str              — 最后一个事件类型
            channel: str                — work / code

        meta 参数会持久化到 runs.meta_json, resume 时用于恢复 LLM config / workspace / work_mode。
        """
        rid = run_id or self.new_run_id()
        self._seq = 0
        if persist and self.store is not None:
            self.store.start_run(rid, channel=channel, session_id=session_id, meta=meta)

        # Spec 4: 累积状态 — 让 resume 能从 checkpoint 直接恢复, 不必 replay 全部 events
        messages_acc: list[dict[str, Any]] = []
        artifacts_acc: list[dict[str, str]] = []
        completed_steps = 0
        current_step = "init"
        tool_call_id_counter = 0
        # 每 N 个事件 save 一次 checkpoint (避免每个事件都写盘)
        checkpoint_every = 5

        final_status = "completed"
        try:
            async for raw in source:
                event = self._normalize(raw, run_id=rid, channel=channel)
                # 累积 messages (Spec 4 核心改进)
                etype = event.type
                data = event.data
                if etype in ("tool_call", "action") and isinstance(data, dict):
                    tool_call_id_counter += 1
                    call_id = f"call_{tool_call_id_counter}"
                    name = str(data.get("name") or data.get("tool") or "")
                    args = data.get("args") or data.get("arguments") or {}
                    messages_acc.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(args, ensure_ascii=False),
                                    },
                                }
                            ],
                        }
                    )
                    completed_steps += 1
                    current_step = "agent"
                    # 工具调用里的产物路径也累积
                    if name in ("write_file", "edit_file") and isinstance(args, dict):
                        p = str(
                            args.get("path") or args.get("rel_path") or args.get("file_path") or ""
                        ).strip()
                        if p and not any(a.get("path") == p for a in artifacts_acc):
                            artifacts_acc.append({"path": p, "name": os.path.basename(p)})
                elif etype in ("tool_result", "observation"):
                    content = (
                        data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
                    )
                    # P0-2: 智能压缩替代硬截断 — 保留头尾 + 中间省略提示, 避免关键上下文丢失
                    # 4KB 以内完整保留; 超过则保留头 2KB + 尾 1.5KB + 中间省略标记
                    if len(content) <= 4000:
                        compressed = content
                    else:
                        head = content[:2000]
                        tail = content[-1500:]
                        omitted = len(content) - 3500
                        compressed = (
                            f"{head}\n\n... [已省略 {omitted} 字符, 保留头尾关键内容] ...\n\n{tail}"
                        )
                    messages_acc.append(
                        {
                            "role": "tool",
                            "content": compressed,
                            "tool_call_id": f"call_{tool_call_id_counter}",
                        }
                    )
                    current_step = "agent"
                elif etype == "text" and isinstance(data, str) and data.strip():
                    messages_acc.append({"role": "assistant", "content": data})
                    current_step = "agent"
                elif etype == "artifact" and isinstance(data, dict) and data.get("path"):
                    p = str(data["path"])
                    if not any(a.get("path") == p for a in artifacts_acc):
                        artifacts_acc.append({"path": p, "name": data.get("name", "")})
                elif etype == "plan":
                    current_step = "planning"
                elif etype == "thinking":
                    current_step = "thinking"

                if persist and self.store is not None:
                    self.store.append_event(
                        rid,
                        event.sequence,
                        event.type,
                        event.to_work_dict(),
                    )
                    # Spec 4: 定期 + 关键事件触发 save_checkpoint (完整 state)
                    should_save = (
                        etype in {"plan", "done", "error", "text"}
                        or event.sequence % checkpoint_every == 0
                    )
                    if should_save:
                        self.store.save_checkpoint(
                            rid,
                            event.sequence,
                            {
                                "messages_so_far": messages_acc,
                                "artifacts_so_far": artifacts_acc,
                                "completed_steps": completed_steps,
                                "current_step": current_step,
                                "last_type": etype,
                                "channel": channel,
                            },
                        )
                if event.type == "error":
                    final_status = "failed"
                elif event.type == "done":
                    data = event.data
                    if isinstance(data, dict) and data.get("status") == "failed":
                        final_status = "failed"
                yield event
        except Exception as exc:
            final_status = "failed"
            event = self._normalize(
                {"type": "error", "data": f"{type(exc).__name__}: {exc}"},
                run_id=rid,
                channel=channel,
            )
            if persist and self.store is not None:
                self.store.append_event(rid, event.sequence, event.type, event.to_work_dict())
                # 异常退出也保存 checkpoint, 让 resume 能恢复到崩溃前状态
                self.store.save_checkpoint(
                    rid,
                    event.sequence,
                    {
                        "messages_so_far": messages_acc,
                        "artifacts_so_far": artifacts_acc,
                        "completed_steps": completed_steps,
                        "current_step": current_step,
                        "last_type": "error",
                        "error": str(exc),
                        "channel": channel,
                    },
                )
            yield event
        finally:
            if persist and self.store is not None:
                # 最终 checkpoint (确保 done 时 messages 完整)
                self.store.save_checkpoint(
                    rid,
                    self._seq,
                    {
                        "messages_so_far": messages_acc,
                        "artifacts_so_far": artifacts_acc,
                        "completed_steps": completed_steps,
                        "current_step": "done" if final_status == "completed" else "failed",
                        "last_type": "done",
                        "channel": channel,
                    },
                )
                self.store.finish_run(rid, final_status)

    def _normalize(
        self,
        raw: dict[str, Any],
        *,
        run_id: str,
        channel: str,
    ) -> RunEvent:
        self._seq += 1
        etype = str(raw.get("type") or "custom")
        data = (
            raw["data"]
            if "data" in raw
            else {
                k: v
                for k, v in raw.items()
                if k not in {"type", "schemaVersion", "runId", "sequence", "timestamp", "channel"}
            }
        )
        # Flatten common Code legacy keys into data when present.
        if etype in {"thinking", "message"} and "content" in raw and "data" not in raw:
            data = raw.get("content")
        if etype == "plan" and "steps" in raw and "data" not in raw:
            data = raw.get("steps")
        if etype in {"step_start", "step_end"} and "step" in raw and "data" not in raw:
            data = raw.get("step")
        if etype == "file_change" and "data" not in raw:
            data = {k: v for k, v in raw.items() if k != "type"}
        if etype == "done" and "data" not in raw:
            data = {k: v for k, v in raw.items() if k != "type"}
        if etype == "heal" and "data" not in raw:
            data = {k: v for k, v in raw.items() if k != "type"}
        return RunEvent(
            type=etype,
            data=data,
            run_id=run_id,
            sequence=self._seq,
            timestamp=int(time.time() * 1000),
            channel=channel,
        )


async def work_loop_source(
    agent: Any,
    user_input: str,
    *,
    resume_from: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Adapter: AgenticLoop.run_stream → raw dicts.

    Spec 4: 透传 resume_from 到 AgenticLoop，支持长程任务从 checkpoint 恢复。
    P0-1: 透传 task_id 到 AgenticLoop，激活 CheckpointManager.append_messages
          持久化通道 。
    """
    async for event in agent.run_stream(user_input, resume_from=resume_from, task_id=task_id):
        if isinstance(event, dict):
            yield event
        else:
            yield {"type": "text", "data": str(event)}


async def code_agent_source(agent: Any, task: Any) -> AsyncIterator[dict[str, Any]]:
    """Adapter: CodingAgent.streaming_execute → Work-shaped dicts."""
    async for ev in agent.streaming_execute(task):
        et = getattr(ev, "type", "") or ""
        if et == "status":
            # Map agent status to a lightweight "status" event (not "thinking").
            # Previously this was "thinking" which caused the frontend to
            # concatenate status words (planning+executing → "planningexecuting")
            # in ThinkingBlock's content via appendBlock's thinking-merge rule.
            yield {"type": "status", "data": str(getattr(ev, "status", "") or "")}
        elif et == "thinking":
            # Agent emits thinking events with a human-readable content string
            # (e.g. "正在分析任务需求，制定执行计划...").
            # Extract the content field — without this, the else branch dumps
            # the entire dataclass __dict__ as the "data" payload, which
            # to_code_ndjson then str()-ifies into an ugly repr.
            yield {"type": "thinking", "data": str(getattr(ev, "content", "") or "")}
        elif et == "plan":
            yield {"type": "plan", "data": list(getattr(ev, "steps", None) or [])}
        elif et == "step":
            step = getattr(ev, "step", None) or {}
            status = str(step.get("status") or "")
            if status in {"", "pending", "running"}:
                yield {"type": "step_start", "data": step}
            else:
                yield {"type": "step_end", "data": step}
        elif et == "file_change":
            yield {
                "type": "file_change",
                "data": {
                    "path": getattr(ev, "file_path", None),
                    "action": getattr(ev, "file_action", None),
                    "diff": getattr(ev, "diff", None),
                    "content": getattr(ev, "content", None),
                    "old_content": getattr(ev, "old_content", None),
                },
            }
        elif et == "review":
            yield {
                "type": "review",
                "data": {
                    "passed": getattr(ev, "review_passed", None),
                    "notes": getattr(ev, "review_notes", None),
                },
            }
        elif et == "heal":
            yield {
                "type": "heal",
                "data": {
                    "notes": getattr(ev, "review_notes", None),
                    "status": getattr(ev, "status", None),
                },
            }
        elif et == "message":
            # Agent emits message events with a human-readable content string
            # (e.g. task completion summary). Extract content to avoid dumping
            # the entire dataclass __dict__ as the data payload.
            yield {"type": "message", "data": str(getattr(ev, "content", "") or "")}
        elif et == "done":
            result = getattr(ev, "result", None)
            status = getattr(result, "status", None)
            status_val = status.value if hasattr(status, "value") else str(status or "completed")
            yield {
                "type": "done",
                "data": {
                    "status": "completed" if status_val == "completed" else "failed",
                    "changes": [],
                    "error": getattr(result, "error", None) if result else None,
                    "review_passed": getattr(result, "review_passed", None) if result else None,
                    "review_notes": getattr(result, "review_notes", None) if result else None,
                },
            }
        else:
            yield {"type": et or "custom", "data": getattr(ev, "__dict__", str(ev))}
