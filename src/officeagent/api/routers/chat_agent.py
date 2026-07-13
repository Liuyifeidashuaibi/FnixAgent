"""API 路由 - Agent 流式聊天端点。

提供基于 NDJSON 的流式编码 Agent 聊天接口,
支持实时反馈 Agent 的思考、计划、执行和审查过程。

设计要点:
  - 流式响应: 使用 StreamingResponse 返回 NDJSON (每行一个 JSON 对象)
  - 事件类型: thinking / plan / step_start / step_end / file_change / message / done
  - 智能体复用: 通过 IDEServer 懒加载 CodingAgent 单例
  - 鉴权: 复用 verify_jwt_token 依赖
  - router 前缀: /chat (由主流程在 main.py 注册时挂到 /api/v1 下)
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from officeagent.api.routers.auth import verify_jwt_token
from officeagent.core.coding.coding_agent import (
    CodingAgent,
    CodingTask,
    TaskStep,
)
from officeagent.core.coding.ide_server import IDEServer

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================================
# IDEServer 单例管理
# ============================================================================

_server: IDEServer | None = None
_server_workspace: str | None = None


def get_server(workspace: Optional[str] = None) -> IDEServer:
    """懒加载 IDEServer 单例。

    首次调用, 或请求的 workspace 与当前实例不一致时创建新实例;
    其余调用直接复用单例。

    Args:
        workspace: 工作区路径, 缺省取 os.getcwd()。

    Returns:
        IDEServer 实例。
    """
    global _server, _server_workspace
    ws = workspace or os.getcwd()
    if _server is None or _server_workspace != ws:
        _server = IDEServer(project_root=ws)
        _server_workspace = ws
    return _server


# ============================================================================
# 请求模型
# ============================================================================

class ChatMessage(BaseModel):
    """聊天消息。"""
    role: str   # "user" 或 "assistant"
    content: str


class ChatAgentRequest(BaseModel):
    """Agent 聊天请求。

    Attributes:
        messages: 对话消息列表, 每条消息包含 role 和 content。
        workspace: 可选的工作区路径, 指定 Agent 操作的代码项目根目录。
    """
    messages: list[ChatMessage]
    workspace: Optional[str] = None


# ============================================================================
# 流式响应辅助
# ============================================================================

def _ndjson_line(data: dict[str, Any]) -> str:
    """将字典序列化为一行 NDJSON 字符串。

    Args:
        data: 待序列化的字典。

    Returns:
        单行 JSON 字符串 (末尾带换行符)。
    """
    return json.dumps(data, ensure_ascii=False, default=str) + "\n"


# ============================================================================
# 流式 Agent 聊天端点
# ============================================================================

@router.post("/agent")
async def chat_agent(
    req: ChatAgentRequest,
    _payload: dict = Depends(verify_jwt_token),
):
    """Agent 流式聊天端点。

    接收自然语言编码任务, 以 NDJSON 流式返回 Agent 的思考、计划、
    执行步骤和最终结果。

    请求体:
        messages: 对话消息列表 ([{"role": "user"|"assistant", "content": "..."}])
        workspace: 可选的工作区路径

    流式响应 (NDJSON, 每行一个 JSON 对象):
        {"type": "thinking", "content": "..."}  - Agent 思考过程
        {"type": "plan", "steps": [...]}        - 执行计划
        {"type": "step_start", "step": {...}}   - 步骤开始
        {"type": "step_end", "step": {...}}     - 步骤完成
        {"type": "file_change", "path": "...", "action": "...", "diff": "..."}  - 文件变更
        {"type": "message", "content": "..."}   - 文本消息
        {"type": "done", "status": "completed"|"failed", "changes": [...]}  - 最终结果
    """
    return StreamingResponse(
        _stream_agent_response(req),
        media_type="application/x-ndjson",
    )


async def _stream_agent_response(
    req: ChatAgentRequest,
) -> AsyncGenerator[str, None]:
    """流式生成 Agent 响应事件。

    复制 CodingAgent.execute_task 的 Plan → Execute → Review 流程,
    在每个阶段之间产出 NDJSON 事件, 实现实时流式反馈。

    Args:
        req: 聊天请求。

    Yields:
        NDJSON 格式的事件行。
    """
    # 获取 IDEServer 并确保初始化
    server = get_server(req.workspace)
    server._ensure_initialized()  # noqa: SLF001
    agent: CodingAgent = server._agent  # type: ignore[assignment]  # noqa: SLF001

    # 提取用户最后一条消息作为任务描述
    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        yield _ndjson_line({
            "type": "done",
            "status": "failed",
            "changes": [],
            "error": "未提供用户消息",
        })
        return

    task_description = user_messages[-1].content
    task = CodingTask(description=task_description)

    # 注册到活跃任务表 (供 _review 中的 _collect_diff 使用)
    agent._active_tasks[task.id] = task  # noqa: SLF001
    agent._task_changesets[task.id] = []  # noqa: SLF001

    changes: list[dict[str, Any]] = []

    try:
        # ================================================================
        # 阶段 1: PLAN - 生成执行计划
        # ================================================================
        yield _ndjson_line({
            "type": "thinking",
            "content": "正在分析任务, 生成执行计划...",
        })

        plan: list[TaskStep] = await agent._plan(task)  # noqa: SLF001

        # 输出计划
        plan_steps = [
            {
                "description": s.description,
                "action": s.action,
                "target": s.target,
            }
            for s in plan
        ]
        yield _ndjson_line({
            "type": "plan",
            "steps": plan_steps,
        })

        # ================================================================
        # 阶段 2: EXECUTE - 按计划执行步骤
        # ================================================================
        yield _ndjson_line({
            "type": "thinking",
            "content": "开始执行计划...",
        })

        # 记录执行前的 DiffEngine 历史长度, 用于事后收集变更集
        hist_before = len(agent._tools._diff.get_history())  # noqa: SLF001

        for step in plan:
            # 步骤开始
            step_data = {
                "id": step.id,
                "description": step.description,
                "action": step.action,
                "target": step.target,
            }
            yield _ndjson_line({
                "type": "step_start",
                "step": step_data,
            })

            try:
                await agent._execute_step(step)  # noqa: SLF001
                if step.status != "skipped":
                    step.status = "done"

                # 如果是写操作, 产出 file_change 事件
                action = step.action.strip().lower()
                if action in ("write", "edit"):
                    change_info = {
                        "path": step.target,
                        "action": "modify",
                        "diff": step.result or "",
                    }
                    changes.append(change_info)
                    yield _ndjson_line({
                        "type": "file_change",
                        **change_info,
                    })

            except Exception as exc:  # noqa: BLE001
                step.status = "failed"
                step.error = str(exc)
                # 步骤失败事件
                step_data["status"] = "failed"
                step_data["error"] = str(exc)
                yield _ndjson_line({
                    "type": "step_end",
                    "step": step_data,
                })
                yield _ndjson_line({
                    "type": "message",
                    "content": f"步骤执行失败: {step.description[:80]} - {exc}",
                })
                yield _ndjson_line({
                    "type": "done",
                    "status": "failed",
                    "changes": changes,
                    "error": str(exc),
                })
                return

            # 步骤完成
            step_data["status"] = step.status
            step_data["result"] = step.result
            yield _ndjson_line({
                "type": "step_end",
                "step": step_data,
            })

        # 收集本次执行产生的变更集 ID (供 _review 中的 _collect_diff 使用)
        history = agent._tools._diff.get_history()  # noqa: SLF001
        new_ids = [cs.id for cs, _ in history[hist_before:]]
        agent._task_changesets[task.id] = new_ids  # noqa: SLF001

        # ================================================================
        # 阶段 3: REVIEW - 审查变更
        # ================================================================
        yield _ndjson_line({
            "type": "thinking",
            "content": "正在审查变更...",
        })

        review_passed, review_notes = await agent._review(task, plan)  # noqa: SLF001

        if review_notes:
            yield _ndjson_line({
                "type": "message",
                "content": review_notes,
            })

        if review_passed:
            yield _ndjson_line({
                "type": "done",
                "status": "completed",
                "changes": changes,
            })
        else:
            yield _ndjson_line({
                "type": "done",
                "status": "failed",
                "changes": changes,
                "error": review_notes or "审查未通过",
            })

    except Exception as exc:  # noqa: BLE001
        yield _ndjson_line({
            "type": "message",
            "content": f"Agent 执行异常: {type(exc).__name__}: {exc}",
        })
        yield _ndjson_line({
            "type": "done",
            "status": "failed",
            "changes": changes,
            "error": str(exc),
        })

    finally:
        # 清理活跃任务
        agent._active_tasks.pop(task.id, None)  # noqa: SLF001
        agent._task_changesets.pop(task.id, None)  # noqa: SLF001