"""
FnixAgent Agentic Loop — 对标 Cursor/Trae 的核心执行循环

真正的 Agent 执行循环:
  Think → Act → Observe → Reflect → Respond

参照:
  - Cursor/Trae: 思考 → 工具调用 → 观察结果 → 继续思考 → 最终响应
  - ReAct 模式: Reasoning + Acting
  - Plan & Execute: 规划 → 执行 → 反馈
  - Reflection: 执行后反思

循环流程:
  1. 用户输入 → 构建系统提示词 (含工具列表 + 工作区上下文)
  2. LLM 思考 → 生成文本 或 工具调用
  3. 如果是工具调用 → 执行工具 → 观察结果 → 回到步骤 2
  4. 如果是文本响应 → 反思检查 → 输出给用户
  5. 记录执行轨迹 → 触发自进化飞轮
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Models sometimes emit fake XML / markdown instead of native tool_calls.
_PSEUDO_WRITE_RE = re.compile(
    r"<write_file>\s*"
    r"(?:<path>(.*?)</path>|<file_path>(.*?)</file_path>)\s*"
    r"<content>(.*?)</content>\s*"
    r"</write_file>",
    re.DOTALL | re.IGNORECASE,
)
_PSEUDO_EDIT_RE = re.compile(
    r"<edit_file>\s*"
    r"(?:<path>(.*?)</path>|<file_path>(.*?)</file_path>)\s*"
    r"(?:<old_string>(.*?)</old_string>)?\s*"
    r"(?:<new_string>(.*?)</new_string>)?\s*"
    r"</edit_file>",
    re.DOTALL | re.IGNORECASE,
)
_FENCE_PATH_RE = re.compile(
    r"```(?:html|css|js|javascript|ts|tsx|jsx|python|py|json)?\s+"
    r"(?:file(?:_path)?|path)\s*=\s*[\"']?([^\s\"'`]+)[\"']?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def extract_pseudo_tool_calls(text: str) -> list[dict[str, Any]]:
    """Recover write_file/edit_file calls when the model fakes tools as XML/markdown."""
    if not text or not text.strip():
        return []
    calls: list[dict[str, Any]] = []
    for i, m in enumerate(_PSEUDO_WRITE_RE.finditer(text)):
        path = (m.group(1) or m.group(2) or "").strip()
        content = m.group(3) if m.group(3) is not None else ""
        if not path:
            continue
        calls.append(
            {
                "id": f"pseudo_write_{i}",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": {
                        "file_path": path,
                        "content": content,
                    },
                },
            }
        )
    for i, m in enumerate(_PSEUDO_EDIT_RE.finditer(text)):
        path = (m.group(1) or m.group(2) or "").strip()
        if not path:
            continue
        calls.append(
            {
                "id": f"pseudo_edit_{i}",
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "arguments": {
                        "file_path": path,
                        "old_string": (m.group(3) or ""),
                        "new_string": (m.group(4) or ""),
                    },
                },
            }
        )
    if not calls:
        for i, m in enumerate(_FENCE_PATH_RE.finditer(text)):
            path = (m.group(1) or "").strip()
            content = m.group(2) or ""
            if not path or len(content.strip()) < 8:
                continue
            calls.append(
                {
                    "id": f"pseudo_fence_{i}",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": {
                            "file_path": path,
                            "content": content,
                        },
                    },
                }
            )
    # Truncated XML (model hit max_tokens mid-file): salvage last open <content>
    if not calls:
        partial = re.search(
            r"<write_file>\s*(?:<path>(.*?)</path>|<file_path>(.*?)</file_path>)\s*"
            r"<content>(.*)\Z",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if partial:
            path = (partial.group(1) or partial.group(2) or "").strip()
            content = (partial.group(3) or "").strip()
            if path and len(content) >= 15:
                calls.append(
                    {
                        "id": "pseudo_write_partial",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": {
                                "file_path": path,
                                "content": content,
                            },
                        },
                    }
                )
    return calls


def strip_pseudo_tool_markup(text: str) -> str:
    """Remove fake tool XML / path fences from assistant-facing text."""
    if not text:
        return text
    cleaned = _PSEUDO_WRITE_RE.sub("", text)
    cleaned = _PSEUDO_EDIT_RE.sub("", cleaned)
    cleaned = _FENCE_PATH_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _coerce_tool_arguments(raw: Any) -> dict[str, Any]:
    """Normalize tool arguments: providers may return dict or JSON string."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (list, tuple)):
        return {"items": list(raw)}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {"value": raw}


def _normalize_tool_call_for_api(tc: dict[str, Any]) -> dict[str, Any]:
    """Ensure OpenAI-compatible tool_call shape with stringified arguments."""
    fn_in = tc.get("function") if isinstance(tc.get("function"), dict) else None
    if fn_in is not None:
        name = fn_in.get("name", "") or ""
        args = _coerce_tool_arguments(fn_in.get("arguments"))
    else:
        name = tc.get("name", "") or ""
        args = _coerce_tool_arguments(tc.get("arguments"))
    return {
        "id": tc.get("id") or f"call_{abs(hash(name)) % 10_000_000}",
        "type": tc.get("type") or "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }


# ============================================================
# 消息类型
# ============================================================


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """对话消息"""

    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        msg = {"role": self.role.value, "content": self.content}
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg


# ============================================================
# 执行轨迹
# ============================================================


@dataclass
class StepTrace:
    """单步执行轨迹"""

    step_index: int
    thought: str = ""  # LLM 思考内容
    tool_name: str | None = None  # 被调用的工具名
    tool_input: dict | None = None  # 工具输入
    tool_output: str | None = None  # 工具输出
    tool_success: bool = True  # 工具是否成功
    duration_ms: float = 0.0  # 耗时
    tokens_used: int = 0  # token 消耗

    def to_summary(self) -> str:
        parts = [f"Step {self.step_index}"]
        if self.thought:
            parts.append(f"思考: {self.thought[:100]}...")
        if self.tool_name:
            status = "✓" if self.tool_success else "✗"
            parts.append(
                f"工具 {status} {self.tool_name}({json.dumps(self.tool_input or {}, ensure_ascii=False)[:50]})"
            )
        parts.append(f"耗时: {self.duration_ms:.0f}ms, tokens: {self.tokens_used}")
        return " | ".join(parts)


# ============================================================
# Agent 循环结果
# ============================================================


@dataclass
class AgentLoopResult:
    """Agent 循环执行结果"""

    success: bool
    response: str = ""  # 最终用户响应
    steps: list[StepTrace] = field(default_factory=list)
    total_tokens: int = 0
    total_duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "response": self.response,
            "steps": [s.to_summary() for s in self.steps],
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "error": self.error,
        }


# ============================================================
# Agentic Loop — 核心执行循环
# ============================================================


class AgenticLoop:
    """
    Agentic Loop — 真正的 Agent 执行循环

    用法:
        loop = AgenticLoop(
            llm_call=my_llm_function,
            tool_executor=my_tool_executor,
            workspace_root="/path/to/project",
        )
        result = await loop.run("帮我修复 bug.py 中的错误")
        print(result.response)
    """

    # 系统提示词
    SYSTEM_PROMPT = """你是一个 AI 编程助手，运行在 FnixAgent 框架中。

你有以下能力:
- 读取和编辑文件
- 搜索代码库
- 执行 Shell 命令
- 搜索网络

请遵循以下规则:
1. 先理解问题，再制定计划
2. 使用工具来获取信息（读取文件、搜索代码）
3. 做出改动前先确认理解现有代码
4. 每次只做被要求的改动，不过度设计
5. 如果工具调用失败，分析原因并尝试其他方法
6. 回复保持简洁，直接给出答案

你当前的工作目录是: {workspace_root}
"""

    def __init__(
        self,
        llm_call: Callable[..., Any],
        tool_executor: Any,
        workspace_root: str = ".",
        max_steps: int = 30,
        enable_reflection: bool = True,
        enable_evolution: bool = True,
        evolution_interval: int = 10,
        session_store: Any = None,
        system_prompt: str | None = None,
        force_tool_delivery: bool = False,
        max_reflect_rounds: int = 3,
    ):
        """
        Args:
            llm_call: LLM 调用函数 (messages, tools) -> response
            tool_executor: 工具执行器 (tool_name, args) -> ToolResult
            workspace_root: 工作区根目录
            max_steps: 最大执行步数 (防止无限循环)
            enable_reflection: 是否启用反思
            enable_evolution: 是否启用自进化飞轮
            evolution_interval: 每 N 次执行后触发一次进化周期
            session_store: 会话持久化存储 (SessionStore 实例)
            system_prompt: 自定义系统提示（含 {workspace_root} 占位）；默认编码助手提示
            force_tool_delivery: Craft/建站时若模型只聊天，强制再催一轮工具调用
            max_reflect_rounds: Spec 6 VMAO — Reflexion 自反思重试最大轮数
                (借鉴 noahshinn/reflexion 的 self_reflection → 重生成 → 验证模式)
                当连续工具失败 ≥2 次时，触发一次自反思并注入到下轮上下文。
        """
        self._llm = llm_call
        self._tools = tool_executor
        self.workspace_root = str(Path(workspace_root).resolve())
        self.max_steps = max_steps
        self.enable_reflection = enable_reflection
        self.enable_evolution = enable_evolution
        self.evolution_interval = evolution_interval
        self._session_store = session_store
        self._system_prompt_template = system_prompt
        self.force_tool_delivery = force_tool_delivery
        self.max_reflect_rounds = max_reflect_rounds
        self._tool_nudge_used = False
        self._pseudo_recoveries = 0
        self._last_round_was_pseudo = False

        # 对话历史
        self.messages: list[Message] = []
        self.traces: list[StepTrace] = []

        # Spec 6 VMAO: Reflexion 自反思重试状态
        self._consecutive_failures: int = 0
        self._reflect_rounds_used: int = 0
        self._recent_failures: list[dict] = []
        self._round_had_failure: bool = False

        # 自进化计数器
        self._execution_count: int = 0
        self._all_trajectories: list[dict] = []

        # 回调
        self.on_step: Callable[[StepTrace], None] | None = None
        self.on_thinking: Callable[[str], None] | None = None
        self.on_tool_call: Callable[[str, dict], None] | None = None
        self.on_response: Callable[[str], None] | None = None
        self.on_evolution: Callable[[dict], None] | None = None

    # ============================================================
    # 初始化
    # ============================================================

    def reset(self):
        """重置对话状态"""
        self.messages = []
        self.traces = []
        self._tool_nudge_used = False
        self._pseudo_recoveries = 0
        self._last_round_was_pseudo = False
        # Spec 6 VMAO: 重置 Reflexion 状态
        self._consecutive_failures = 0
        self._reflect_rounds_used = 0
        self._recent_failures = []
        self._round_had_failure = False

    def _wrote_files(self) -> bool:
        return any(
            t.tool_name in ("write_file", "edit_file") and t.tool_success for t in self.traces
        )

    def _get_system_prompt(self) -> str:
        """构建系统提示词。

        只用显式替换 ``{workspace_root}``，不用 ``str.format``——
        memory / skills / rules 注入里常含 ``{workspace}/.fnix/...`` 等花括号，
        全量 format 会触发 KeyError（Work 流失败根因）。
        """
        workspace = Path(self.workspace_root)
        tree = f"工作区: {workspace.name}"
        tools_desc = (
            self._tools.get_tools_description()
            if hasattr(self._tools, "get_tools_description")
            else ""
        )

        template = self._system_prompt_template or self.SYSTEM_PROMPT
        prompt = template.replace("{workspace_root}", str(self.workspace_root))
        if tools_desc:
            prompt += f"\n\n可用工具:\n{tools_desc}"
        if tree:
            prompt += f"\n\n{tree}"

        return prompt

    # ============================================================
    # 主循环
    # ============================================================

    async def run(self, user_input: str) -> AgentLoopResult:
        """
        运行 Agent 执行循环

        Args:
            user_input: 用户输入

        Returns:
            AgentLoopResult 包含最终响应和执行轨迹
        """
        self.reset()
        start_time = time.time()
        total_tokens = 0

        # 系统提示词
        system_prompt = self._get_system_prompt()

        # 构建初始消息
        messages_for_llm = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        self.messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt[:200]))
        self.messages.append(Message(role=MessageRole.USER, content=user_input))

        try:
            for step_idx in range(self.max_steps):
                step_start = time.time()

                # Step 1: Think — LLM 思考
                if self.on_thinking:
                    self.on_thinking(f"Step {step_idx + 1}: 思考中...")

                llm_result = await self._call_llm(messages_for_llm)

                if llm_result is None:
                    return AgentLoopResult(
                        success=False,
                        error=getattr(self, "_last_llm_error", None) or "LLM 调用失败",
                        steps=self.traces,
                        total_tokens=total_tokens,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )

                # 解析 LLM 响应（含伪 XML 工具恢复）
                text_content, tool_calls, _reasoning = self._parse_llm_response(llm_result)
                total_tokens += llm_result.get("usage", {}).get("total_tokens", 0)

                # Step 2: 如果是最终文本响应
                if text_content and not tool_calls:
                    if self._wrote_files():
                        display = (
                            strip_pseudo_tool_markup(text_content)
                            or "已将源码写入 `.fnix/artifacts/`，可直接打开 index.html 验收。"
                        )
                    elif self._should_nudge_for_tools(text_content, step_idx):
                        messages_for_llm.append({"role": "assistant", "content": text_content})
                        messages_for_llm.append(
                            {
                                "role": "user",
                                "content": (
                                    "你没有调用 tools API。请立刻使用 write_file 工具写入完整源码；"
                                    "禁止用 <write_file> XML 或只描述计划。每个文件一次 write_file。"
                                ),
                            }
                        )
                        self._tool_nudge_used = True
                        continue
                    else:
                        display = strip_pseudo_tool_markup(text_content) or text_content

                    if (
                        not self._should_nudge_for_tools(text_content, step_idx)
                        or self._wrote_files()
                    ):
                        trace = StepTrace(
                            step_index=step_idx,
                            thought=display[:200],
                            duration_ms=(time.time() - step_start) * 1000,
                            tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                        )
                        self.traces.append(trace)

                        if self.on_response:
                            self.on_response(display)

                        result = AgentLoopResult(
                            success=True,
                            response=display,
                            steps=self.traces,
                            total_tokens=total_tokens,
                            total_duration_ms=(time.time() - start_time) * 1000,
                        )
                        if self.enable_evolution:
                            self._trigger_evolution_hook(result)
                        return result

                # Step 3: Act — 执行工具调用
                if tool_calls:
                    normalized_calls = [_normalize_tool_call_for_api(tc) for tc in tool_calls]
                    # 添加 assistant 消息（arguments 必须是 JSON 字符串，供下一轮 API）
                    assistant_msg = {
                        "role": "assistant",
                        "content": text_content or "",
                        "tool_calls": normalized_calls,
                    }

                    messages_for_llm.append(assistant_msg)
                    self.messages.append(
                        Message(
                            role=MessageRole.ASSISTANT,
                            content=text_content or "",
                            tool_calls=normalized_calls,
                        )
                    )

                    for tc_api in normalized_calls:
                        tool_name = tc_api["function"]["name"]
                        tool_args = _coerce_tool_arguments(tc_api["function"]["arguments"])

                        if self.on_tool_call:
                            self.on_tool_call(tool_name, tool_args)

                        # 执行工具
                        tool_result = await self._execute_tool(tool_name, tool_args)

                        trace = StepTrace(
                            step_index=step_idx,
                            thought=text_content[:200] if text_content else "",
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=tool_result,
                            tool_success=not tool_result.startswith("[失败]"),
                            duration_ms=(time.time() - step_start) * 1000,
                            tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                        )
                        self.traces.append(trace)

                        if self.on_step:
                            self.on_step(trace)

                        # 添加 tool 结果消息
                        messages_for_llm.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_api.get("id", ""),
                                "content": tool_result,
                            }
                        )
                        self.messages.append(
                            Message(
                                role=MessageRole.TOOL,
                                content=tool_result,
                                tool_call_id=tc_api.get("id", ""),
                            )
                        )

                    if (
                        self.force_tool_delivery
                        and self._last_round_was_pseudo
                        and self._wrote_files()
                    ):
                        display = "已将源码写入 `.fnix/artifacts/`，可直接打开 index.html 验收。"
                        if self.on_response:
                            self.on_response(display)
                        result = AgentLoopResult(
                            success=True,
                            response=display,
                            steps=self.traces,
                            total_tokens=total_tokens,
                            total_duration_ms=(time.time() - start_time) * 1000,
                        )
                        if self.enable_evolution:
                            self._trigger_evolution_hook(result)
                        return result

            # 达到最大步数
            return AgentLoopResult(
                success=False,
                error=f"超过最大步数 ({self.max_steps})",
                steps=self.traces,
                total_tokens=total_tokens,
                total_duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            return AgentLoopResult(
                success=False,
                error=str(e),
                steps=self.traces,
                total_tokens=total_tokens,
                total_duration_ms=(time.time() - start_time) * 1000,
            )

    # ============================================================
    # 流式执行
    # ============================================================

    async def run_stream(
        self, user_input: str, *, resume_from: dict | None = None, task_id: str | None = None
    ):
        """
        流式执行 Agent 循环 (Generator)

        Args:
            user_input: 用户输入
            resume_from: Spec 4 长程任务恢复上下文，结构:
                {
                    "messages": [{"role": "system"|"user"|"assistant"|"tool", "content": "..."}],
                    "completed_steps": int,
                    "artifacts": [{"path": "...", "name": "..."}],
                }
                提供时将跳过用户输入初始化，从历史消息继续执行。
            task_id: P0-1 集成 CheckpointManager.append_messages 的任务 ID。
                提供时，AgenticLoop 会以"每个 turn 边界批量写"的方式
                (借鉴 OpenAI Agents SDK Session.add_items)将 system/user/
                assistant/tool_call/tool_result/reflection 消息持久化到
                CheckpointManager 三层存储(内存+Redis+JSONL)。崩溃后可
                通过 resume_from 恢复完整对话上下文。

        Yields:
            dict: {"type": "thinking"|"tool_call"|"tool_result"|"text"|"done", "data": ...}
        """
        self.reset()
        start_time = time.time()

        system_prompt = self._get_system_prompt()

        # P0-1: CheckpointManager 句柄 (task_id 为空时降级为 no-op)
        _ckpt = None
        if task_id:
            try:
                from fnixagent.core.checkpoint.manager import get_checkpoint_manager

                _ckpt = get_checkpoint_manager()
            except Exception:
                _ckpt = None
        # 已写入 checkpoint 的 messages_for_llm 偏移量
        # 用偏移而非维护 pending 列表: 不修改任何 messages_for_llm.append 调用
        _ckpt_offset = 0

        # P3: 软/硬阈值异步 compactor (借鉴 LCM Equation 1)
        # τsoft=50K 异步压缩, τhard=80K 阻塞压缩
        _bg_compactor = None
        try:
            from fnixagent.core.agent.compaction import BackgroundCompactor

            async def _bg_llm(msgs, _tools=None):
                return await self._llm(msgs)

            _bg_compactor = BackgroundCompactor(
                _bg_llm,
                tau_soft=50000,
                tau_hard=80000,
                keep_recent=6,
                keep_first_n=2,
            )
        except Exception:
            _bg_compactor = None

        async def _aflush_step() -> None:
            """flush messages_for_llm 自上次偏移以来的新消息到 CheckpointManager (单次 fsync, async)。

            设计要点 (借鉴 OpenAI Agents SDK Session.add_items 每 turn 边界批量写):
              - step 末尾/return 前/error 退出前调用
              - 用 slice 一次性 aappend_messages, 单次 fsync
              - compaction 重赋 messages_for_llm 后偏移自动失效, 不重复写
              - P1-1: 用 async 接口避免 event loop 阻塞 (16ms → ~0ms)
            """
            nonlocal _ckpt_offset
            if not _ckpt or not task_id:
                _ckpt_offset = len(messages_for_llm)
                return
            if _ckpt_offset >= len(messages_for_llm):
                if _ckpt_offset > len(messages_for_llm):
                    _ckpt_offset = len(messages_for_llm)
                return
            new_msgs = messages_for_llm[_ckpt_offset:]
            try:
                await _ckpt.aappend_messages(task_id, [dict(m) for m in new_msgs])
            except Exception as _flush_err:
                logger.warning("aappend_messages flush 失败: %s", _flush_err)
            _ckpt_offset = len(messages_for_llm)

        if resume_from and resume_from.get("messages"):
            # Spec 4: 从 checkpoint 恢复 — 重建 LLM 上下文，跳过用户输入初始化
            messages_for_llm = list(resume_from["messages"])
            # 重建 self.messages (用于 reflection / 持久化)
            # P0-1 修复: MessageRole 值为小写 (system/user/assistant/tool),
            # 原 .upper() 会触发 ValueError — 改用 .lower() 容错大小写
            self.messages = [
                Message(
                    role=MessageRole(str(msg.get("role", "user")).lower()),
                    content=str(msg.get("content", "")),
                )
                for msg in resume_from["messages"]
            ]
            # 透传已完成的 artifacts，避免重复生成
            self._resumed_artifacts = list(resume_from.get("artifacts") or [])
            # P0-1: resume 场景 messages 偏移处理
            # 调用方可通过 _ckpt_offset 字段指定哪些 messages 已在 checkpoint 中
            # (默认: 全部已在 checkpoint, 不重复写; P0-2 Reflexion 修复场景: 显式传偏移
            # 让新增的 repair_prompt user message 被 flush)
            _ckpt_offset = resume_from.get("_ckpt_offset", len(messages_for_llm))
            yield {
                "type": "thinking",
                "data": f"Spec 4: 从 checkpoint 恢复，已完成 {resume_from.get('completed_steps', 0)} 步，继续执行...",
            }
        else:
            messages_for_llm = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ]

            self.messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt[:200]))
            self.messages.append(Message(role=MessageRole.USER, content=user_input))

            # P0-1 D1: 初始化阶段批量写 [system, user] (单次 fsync, async)
            if _ckpt:
                try:
                    await _ckpt.aappend_messages(
                        task_id,
                        [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_input},
                        ],
                    )
                    _ckpt_offset = len(messages_for_llm)
                except Exception as _init_err:
                    logger.warning("aappend_messages 初始化失败: %s", _init_err)

        try:
            for step_idx in range(self.max_steps):
                step_start = time.time()

                # AG-UI StepStarted 事件 — 让前端 ProgressStrip 显示 "Step N/M"
                # 调研：AG-UI 协议 16 种标准事件类型 + PatternFly "Step 1 of 6" 进度模式
                yield {
                    "type": "step_start",
                    "data": {
                        "step": step_idx + 1,
                        "total": self.max_steps,
                        "description": f"Step {step_idx + 1}/{self.max_steps}",
                    },
                }

                # P3: 每个 turn 开始时检查后台异步压缩任务是否完成, 完成则原子 swap
                # (借鉴 LCM Equation 1: turn 边界 swap, 避免在 LLM 调用中改 messages)
                # 第一个 step 时 _bg_result 必为 None, maybe_swap 返回 None, 无副作用
                if _bg_compactor is not None:
                    swapped = _bg_compactor.maybe_swap(messages_for_llm)
                    if swapped is not None:
                        old_len = len(messages_for_llm)
                        messages_for_llm = swapped
                        _ckpt_offset = len(messages_for_llm)
                        logger.info(
                            "P3 Swap: %d → %d msgs (后台异步压缩完成)",
                            old_len,
                            len(messages_for_llm),
                        )
                        if _ckpt and task_id:
                            try:
                                await _ckpt.areplace_messages(
                                    task_id,
                                    [dict(m) for m in messages_for_llm],
                                    compaction_info={
                                        "compacted": True,
                                        "level": "bg_swap",
                                        "before_tokens": old_len,
                                        "after_tokens": len(messages_for_llm),
                                        "compacted_messages_count": old_len - len(messages_for_llm),
                                        "summary": "background async swap",
                                        "error": None,
                                    },
                                )
                            except Exception:
                                pass

                # Spec 2: 思考链可见 — 真实 step 标记（具体内容由 LLM 返回后补发）
                yield {"type": "thinking", "data": f"Step {step_idx + 1}: 思考中..."}

                # P0-1 流式心跳: LLM 非流式调用期间定期 yield 心跳, 避免前端 60s idle timeout 误切断
                # 用 asyncio.Queue 把心跳从后台 task 传到主 async generator
                _hb_queue: asyncio.Queue = asyncio.Queue()
                _hb_stop = asyncio.Event()

                async def _heartbeat():
                    while not _hb_stop.is_set():
                        try:
                            await asyncio.wait_for(asyncio.shield(_hb_stop.wait()), timeout=15.0)
                        except TimeoutError:
                            await _hb_queue.put(
                                ("thinking", f"仍在思考中... (Step {step_idx + 1})")
                            )

                _hb_task = asyncio.create_task(_heartbeat())

                llm_result = None
                try:
                    # 把 _call_llm 与心跳消费合并: 任意一方完成都唤醒
                    # 注意: llm_task 本身已是 Task, 直接放入 asyncio.wait 等待集合即可
                    # (asyncio.wait 在 FIRST_COMPLETED 下不会取消未完成的 task)。
                    # 不能用 asyncio.create_task(asyncio.shield(llm_task)) —— shield 返回
                    # Future 而非 coroutine, create_task 会抛 "a coroutine was expected"。
                    llm_task = asyncio.create_task(self._call_llm(messages_for_llm))
                    while True:
                        hb_task = asyncio.create_task(_hb_queue.get())
                        try:
                            await asyncio.wait(
                                {llm_task, hb_task},
                                return_when=asyncio.FIRST_COMPLETED,
                            )
                        except Exception:
                            if not hb_task.done():
                                hb_task.cancel()
                            break
                        if llm_task.done():
                            llm_result = llm_task.result()
                            if not hb_task.done():
                                hb_task.cancel()
                            break
                        if hb_task.done():
                            try:
                                _ev_type, _ev_data = hb_task.result()
                                yield {"type": _ev_type, "data": _ev_data}
                            except Exception:
                                pass
                finally:
                    _hb_stop.set()
                    _hb_task.cancel()
                    try:
                        await _hb_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    if "llm_task" in locals() and not llm_task.done():
                        llm_task.cancel()

                # P0-3: LLM 工具被拒降级时明确告警 (而非静默退化)
                _tools_degraded = getattr(self, "_tools_degraded_this_step", False)
                if _tools_degraded:
                    yield {
                        "type": "warning",
                        "data": {
                            "code": "tools_degraded",
                            "message": "LLM 暂不支持工具调用, 已降级为纯对话模式。编码任务可能无法完成, 建议切换支持 function calling 的模型。",
                        },
                    }
                    self._tools_degraded_this_step = False

                if llm_result is None:
                    detail = getattr(self, "_last_llm_error", None) or "LLM 调用失败"
                    # P0-1: error 退出前 flush 已收集的 messages, 保留现场供 resume
                    await _aflush_step()
                    # AG-UI StepFinished — 让前端 ProgressStrip 标记完成（即使出错）
                    yield {
                        "type": "step_end",
                        "data": {
                            "step": step_idx + 1,
                            "total": self.max_steps,
                            "description": f"Step {step_idx + 1}/{self.max_steps} (error)",
                        },
                    }
                    yield {"type": "error", "data": detail}
                    return

                # P4.2: 监控 prompt cache 命中率 (qwen-plus 隐式 / GLM / DeepSeek)
                # 命中率 = cached_tokens / prompt_tokens, 0 表示无 cache 命中
                # cache-safe forking (P4.1) 后, compaction LLM 调用应看到命中率提升
                try:
                    _usage = (llm_result or {}).get("usage", {}) or {}
                    _cached = int(_usage.get("cached_tokens", 0) or 0)
                    _prompt = int(_usage.get("prompt_tokens", 0) or 0)
                    if _prompt > 0 and _cached > 0:
                        _hit_rate = _cached / _prompt * 100
                        logger.info(
                            "P4.2 Cache hit: %d/%d tokens (%.1f%%) — cache-safe=%s",
                            _cached,
                            _prompt,
                            _hit_rate,
                            "on" if _bg_compactor is not None else "off",
                        )
                except Exception:
                    pass

                text_content, tool_calls, reasoning_content = self._parse_llm_response(llm_result)

                # Spec 2: 真实思考链可见 — thought chunk 严格区分 3 种场景：
                #   1) reasoning_content 非空（Qwen3/o1/DeepSeek-R1/GLM-4.5 thinking）：
                #      发 reasoning_content 作为 thought（这才是模型"在想什么"）
                #   2) text_content 非空 + 有 tool_calls（ReAct 决策独白）：
                #      发 text_content 作为 thought（"我决定调用 xxx 工具因为…"）
                #   3) text_content 非空 + 无 tool_calls（最终答复）：
                #      不发 thought chunk（避免与后面的 text chunk 内容重复）
                # 这样前端 ProcessTimeline 的"展开思考"才有真实价值，对标 Cursor/Codex reasoning 可见性。
                thought_data = ""
                if reasoning_content and reasoning_content.strip():
                    thought_data = reasoning_content[:2000]
                elif text_content and tool_calls:
                    # ReAct 决策独白：LLM 在调用工具前给出的"我要做什么"说明
                    thought_data = strip_pseudo_tool_markup(text_content)[:500] or ""

                if thought_data:
                    yield {"type": "thought", "data": thought_data}

                # 最终响应
                if text_content and not tool_calls:
                    # P0-1 D3: 持久化 final assistant message (借鉴 OpenAI SDK
                    # Session "After each run: assistant responses stored")
                    messages_for_llm.append({"role": "assistant", "content": text_content})

                    if self._wrote_files():
                        display = (
                            strip_pseudo_tool_markup(text_content)
                            or "已将源码写入 `.fnix/artifacts/`，可直接打开 index.html 验收。"
                        )
                        await _aflush_step()
                        yield {"type": "text", "data": display}
                        # AG-UI StepFinished — 标记当前步骤完成，ProgressStrip 显示 ✓
                        yield {
                            "type": "step_end",
                            "data": {
                                "step": step_idx + 1,
                                "total": self.max_steps,
                                "description": f"Step {step_idx + 1}/{self.max_steps} (done)",
                            },
                        }
                        yield {
                            "type": "done",
                            "data": {
                                "steps": len(self.traces),
                                "duration_ms": (time.time() - start_time) * 1000,
                            },
                        }
                        return
                    if self._should_nudge_for_tools(text_content, step_idx):
                        messages_for_llm.append(
                            {
                                "role": "user",
                                "content": (
                                    "你没有调用 tools API。请立刻使用 write_file 工具写入完整源码；"
                                    "禁止用 <write_file> XML 或只描述计划。每个文件一次 write_file。"
                                ),
                            }
                        )
                        self._tool_nudge_used = True
                        # P0-1: nudge 场景 continue 前 flush, 保留 assistant + nudge user
                        await _aflush_step()
                        continue

                    display = strip_pseudo_tool_markup(text_content) or text_content
                    await _aflush_step()
                    yield {"type": "text", "data": display}
                    # AG-UI StepFinished — 标记当前步骤完成，ProgressStrip 显示 ✓
                    yield {
                        "type": "step_end",
                        "data": {
                            "step": step_idx + 1,
                            "total": self.max_steps,
                            "description": f"Step {step_idx + 1}/{self.max_steps} (done)",
                        },
                    }
                    yield {
                        "type": "done",
                        "data": {
                            "steps": len(self.traces),
                            "duration_ms": (time.time() - start_time) * 1000,
                        },
                    }
                    return

                # 工具调用
                if tool_calls:
                    normalized_calls = [_normalize_tool_call_for_api(tc) for tc in tool_calls]
                    assistant_msg = {
                        "role": "assistant",
                        "content": text_content or "",
                        "tool_calls": normalized_calls,
                    }
                    messages_for_llm.append(assistant_msg)

                    round_failures: list[dict] = []
                    for tc_api in normalized_calls:
                        tool_name = tc_api["function"]["name"]
                        tool_args = _coerce_tool_arguments(tc_api["function"]["arguments"])

                        # Spec 2: action chunk — 工具调用前置事件（对标 AG-UI ToolCallStart）
                        # 前端 fnixRuntime 已有 case 'action' → 显示 "Running xxx…"
                        yield {
                            "type": "action",
                            "data": {
                                "name": tool_name,
                                "args": tool_args,
                                "step": step_idx + 1,
                            },
                        }
                        # 保留 tool_call 向后兼容（AG-UI mapper 映射为 TOOL_CALL_START）
                        yield {"type": "tool_call", "data": {"name": tool_name, "args": tool_args}}

                        tool_result = await self._execute_tool(tool_name, tool_args)
                        result_text = (
                            tool_result if isinstance(tool_result, str) else str(tool_result)
                        )
                        ok = not result_text.startswith("[失败]")
                        self.traces.append(
                            StepTrace(
                                step_index=step_idx,
                                thought=text_content[:200] if text_content else "",
                                tool_name=tool_name,
                                tool_input=tool_args,
                                tool_output=result_text,
                                tool_success=ok,
                                duration_ms=(time.time() - step_start) * 1000,
                            )
                        )

                        # Spec 2: observation chunk — 工具结果事件（对标 AG-UI ToolCallResult）
                        # 截断到 500 字符避免长输出刷屏，前端 activity 卡片显示摘要
                        yield {
                            "type": "observation",
                            "data": {
                                "name": tool_name,
                                "success": ok,
                                "summary": result_text[:500],
                                "duration_ms": (time.time() - step_start) * 1000,
                            },
                        }
                        # 保留 tool_result 向后兼容
                        yield {"type": "tool_result", "data": result_text[:2000]}

                        # AG-UI file_change 事件 — 让前端 DiffBlock 显示三态 diff 审查
                        # 调研：Cursor 论坛 "per-change Apply + inline diff review" +
                        #   Claude Code Issue #31395 per-hunk accept/discard
                        # 当工具是文件编辑操作时，emit file_change 让前端 DiffBlock 渲染
                        if tool_name in (
                            "write_file",
                            "edit_file",
                            "writeFile",
                            "editFile",
                            "apply_diff",
                            "create_file",
                        ):
                            file_path = ""
                            if isinstance(tool_args, dict):
                                file_path = str(
                                    tool_args.get("file_path")
                                    or tool_args.get("path")
                                    or tool_args.get("file")
                                    or ""
                                )
                            yield {
                                "type": "file_change",
                                "data": {
                                    "path": file_path,
                                    "action": tool_name,
                                    "diff": result_text[:4000] if ok else "",
                                    "preview": True,
                                },
                            }

                        # Spec: inline widget 事件 — AI 调用 show_widget 时透传 code 到前端
                        # 对标 Trae dynamic-ui PureShowWidget + Claude Inline Visualizations
                        # 前端 WidgetBlock.tsx 用 iframe sandbox + CSP + DOMPurify 安全渲染
                        if tool_name == "show_widget" and ok and isinstance(tool_args, dict):
                            widget_code = str(tool_args.get("widget_code", ""))
                            widget_mode = str(tool_args.get("mode", "inline"))
                            widget_type = str(tool_args.get("widget_type", "custom"))
                            widget_id = f"widget_{step_idx + 1}_{int(time.time() * 1000) % 100000}"
                            if widget_code:
                                yield {
                                    "type": "widget",
                                    "data": {
                                        "widgetId": widget_id,
                                        "widgetType": widget_type,
                                        "code": widget_code,
                                        "mode": widget_mode,
                                        "step": step_idx + 1,
                                    },
                                }

                        messages_for_llm.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_api.get("id", ""),
                                "content": result_text,
                            }
                        )

                        # P2 + P3: 三级 Escalation Compaction + 软/硬阈值异步
                        # 对标 LCM Algorithm 3 (3-level escalation) + LCM Equation 1 (3-regime overhead)
                        # τsoft=50K: 异步压缩 (后台跑, turn 间 swap, 用户无感)
                        # τhard=80K: 阻塞压缩 (必须等待, 避免 context overflow)
                        try:
                            from fnixagent.core.agent.compaction import estimate_tokens

                            if _bg_compactor is not None:
                                action = _bg_compactor.check(messages_for_llm)
                                if action == "async":
                                    # 软阈值: 启动后台异步压缩, 当前 turn 继续 (不阻塞)
                                    _bg_compactor.start_async(messages_for_llm)
                                    yield {
                                        "type": "thinking",
                                        "data": "P3: 软阈值触发, 后台异步压缩已启动 (不阻塞当前 turn)",
                                    }
                                elif action == "blocking":
                                    # 硬阈值: 阻塞等待压缩完成
                                    yield {
                                        "type": "thinking",
                                        "data": "P3: 硬阈值触发, 阻塞压缩中...",
                                    }
                                    compacted, info = await _bg_compactor.await_compaction(
                                        messages_for_llm
                                    )
                                    if info and info.get("compacted"):
                                        messages_for_llm = compacted
                                        if _ckpt and task_id:
                                            try:
                                                await _ckpt.areplace_messages(
                                                    task_id,
                                                    compacted,
                                                    compaction_info=info,
                                                )
                                                _ckpt_offset = len(compacted)
                                            except Exception as _replace_err:
                                                logger.warning(
                                                    "areplace_messages (P3) 失败: %s", _replace_err
                                                )
                                        level = info.get("level", "?")
                                        yield {
                                            "type": "thinking",
                                            "data": (
                                                f"P3 Compaction L{level} (blocking): "
                                                f"{info['before_tokens']} → {info['after_tokens']} tokens "
                                                f"(节省 {int((1 - info['after_tokens'] / info['before_tokens']) * 100)}%)"
                                            ),
                                        }
                            else:
                                # Fallback: 无 BackgroundCompactor, 用同步 compact_with_escalation
                                if estimate_tokens(messages_for_llm) > 60000:
                                    from fnixagent.core.agent.compaction import (
                                        compact_with_escalation,
                                    )

                                    async def _summary_llm(msgs, _tools=None):
                                        return await self._llm(msgs)

                                    compacted, info = await compact_with_escalation(
                                        _summary_llm,
                                        messages_for_llm,
                                        threshold_tokens=60000,
                                        keep_recent=6,
                                    )
                                    if info and info.get("compacted"):
                                        messages_for_llm = compacted
                                        if _ckpt and task_id:
                                            try:
                                                await _ckpt.areplace_messages(
                                                    task_id,
                                                    compacted,
                                                    compaction_info=info,
                                                )
                                                _ckpt_offset = len(compacted)
                                            except Exception as _replace_err:
                                                logger.warning(
                                                    "areplace_messages 失败: %s", _replace_err
                                                )
                                        level = info.get("level", "?")
                                        yield {
                                            "type": "thinking",
                                            "data": f"P2 Compaction L{level}: {info['before_tokens']} → {info['after_tokens']} tokens",
                                        }
                        except Exception as _compact_err:
                            logger.warning("P3 Compaction exception: %s", _compact_err)

                        # Spec 6 VMAO: 收集本轮失败信息用于 Reflexion
                        if not ok:
                            round_failures.append(
                                {
                                    "name": tool_name,
                                    "error": result_text[:500],
                                    "step": step_idx + 1,
                                    "args_summary": json.dumps(tool_args, ensure_ascii=False)[:200],
                                }
                            )

                    # Spec 6 VMAO: Reflexion 自反思重试闭环
                    # 借鉴 noahshinn/reflexion 的 self_reflection → 注入 → 重生成模式
                    # 触发条件: 本轮有失败 + 累计连续失败 ≥2 + 反思轮数未超限
                    if round_failures:
                        self._consecutive_failures += 1
                        self._recent_failures.extend(round_failures[-5:])
                        if (
                            self._consecutive_failures >= 2
                            and self._reflect_rounds_used < self.max_reflect_rounds
                        ):
                            reflection = await self._generate_reflection(
                                user_input=user_input,
                                recent_failures=self._recent_failures[-3:],
                            )
                            if reflection:
                                self._reflect_rounds_used += 1
                                # 注入反思到下一轮 LLM 上下文（不重置 _consecutive_failures，
                                # 让模型有机会连续修正；下轮成功才重置）
                                reflection_msg = (
                                    f"[VMAO REFLECTION · round {self._reflect_rounds_used}] "
                                    f"近期工具调用连续失败 {self._consecutive_failures} 次。\n"
                                    f"反思: {reflection}\n\n"
                                    f"请基于反思调整策略，尝试不同的工具或参数。"
                                )
                                messages_for_llm.append(
                                    {
                                        "role": "user",
                                        "content": reflection_msg,
                                    }
                                )
                                yield {
                                    "type": "reflection",
                                    "data": {
                                        "round": self._reflect_rounds_used,
                                        "reason": f"连续 {self._consecutive_failures} 轮工具失败",
                                        "reflection": reflection,
                                        "previous_failures": round_failures[-3:],
                                    },
                                }
                    else:
                        # 本轮全部成功 → 重置连续失败计数
                        self._consecutive_failures = 0

                    # P0-1 D2: 工具调用 + 反思注入完成后, step 末尾批量 flush
                    # (单次 fsync 写入 assistant + tool_calls + tool_results + reflection)
                    await _aflush_step()

                    # Pseudo-XML recovery already wrote files — do not re-enter LLM
                    # (models often re-emit the same XML for dozens of steps).
                    if (
                        self.force_tool_delivery
                        and self._last_round_was_pseudo
                        and self._wrote_files()
                    ):
                        yield {
                            "type": "text",
                            "data": "已将源码写入 `.fnix/artifacts/`，可直接打开 index.html 验收。",
                        }
                        yield {
                            "type": "done",
                            "data": {
                                "steps": len(self.traces),
                                "duration_ms": (time.time() - start_time) * 1000,
                            },
                        }
                        return

            # Spec 6 VMAO: 达到最大步数前最后一次反思机会
            if (
                self._reflect_rounds_used < self.max_reflect_rounds
                and self._recent_failures
                and not self._wrote_files()
            ):
                reflection = await self._generate_reflection(
                    user_input=user_input,
                    recent_failures=self._recent_failures[-3:],
                )
                if reflection:
                    self._reflect_rounds_used += 1
                    yield {
                        "type": "reflection",
                        "data": {
                            "round": self._reflect_rounds_used,
                            "reason": "达到最大步数前的最终反思",
                            "reflection": reflection,
                            "previous_failures": self._recent_failures[-3:],
                        },
                    }
            # P0-1: 超过最大步数 error 退出前 flush, 保留完整轨迹供 resume
            await _aflush_step()
            yield {"type": "error", "data": f"超过最大步数 ({self.max_steps})"}

        except Exception as e:
            # P0-1: 异常退出前 best-effort flush, 保留崩溃现场
            try:
                await _aflush_step()
            except Exception:
                pass
            yield {"type": "error", "data": str(e)}

    # ============================================================
    # 内部方法
    # ============================================================

    def _should_nudge_for_tools(self, text_content: str, step_idx: int) -> bool:
        if not self.force_tool_delivery or self._tool_nudge_used:
            return False
        if step_idx >= self.max_steps - 1:
            return False
        # Already recovered via pseudo tools elsewhere; only nudge pure chat.
        if extract_pseudo_tool_calls(text_content):
            return False
        return True

    async def _call_llm(self, messages: list[dict]) -> dict | None:
        """调用 LLM"""
        self._last_llm_error = None
        self._tools_degraded_this_step = False
        try:
            # 获取工具定义
            tools = (
                self._tools.get_tool_definitions()
                if hasattr(self._tools, "get_tool_definitions")
                else None
            )

            if asyncio.iscoroutinefunction(self._llm):
                result = await self._llm(messages, tools)
            else:
                result = self._llm(messages, tools)

            return result
        except Exception as e:
            err = str(e)
            # Only drop tools when the provider clearly rejects the tools payload.
            tools_rejected = any(
                token in err.lower()
                for token in ("tool", "function calling", "function_call", "tool_choice")
            )
            if tools_rejected:
                logger.warning("LLM rejected tools payload; retrying without tools: %s", err[:400])
                # P0-3: 标记工具降级, 让主循环 yield 告警事件
                self._tools_degraded_this_step = True
                try:
                    if asyncio.iscoroutinefunction(self._llm):
                        return await self._llm(messages)
                    return self._llm(messages)
                except Exception as e2:
                    detail = str(e2) or err or "unknown error"
                    if len(err) > len(detail):
                        detail = err
                    self._last_llm_error = f"LLM 调用失败: {detail}"[:1200]
                    return None
            self._last_llm_error = f"LLM 调用失败: {err}"[:1200]
            return None

    def _parse_llm_response(self, llm_result: dict) -> tuple[str, list[dict] | None, str]:
        """解析 LLM 响应，提取文本、工具调用（含伪 XML 恢复）与 reasoning_content。

        Spec 2 升级：返回三元组 ``(text_content, tool_calls, reasoning_content)``。

        - ``text_content``: 助手可见的文本回复 (普通模型) 或 决策独白 (ReAct 模式有 tool_calls 时)
        - ``tool_calls``: 标准 OpenAI function calling 工具调用列表
        - ``reasoning_content``: reasoning model 的思考链内容
          (Qwen3 ``reasoning_content`` / OpenAI o1 ``reasoning`` / DeepSeek-R1 / GLM-4.5 thinking)
          普通模型此字段为空字符串。

        前端 thought chunk 优先取 reasoning_content，其次在有 tool_calls 时取 text_content 作为决策独白，
        最终纯文本答复场景不发 thought chunk（避免与 text chunk 重复）。
        """
        text_content = ""
        tool_calls: list[dict] = []
        reasoning_content = ""

        if isinstance(llm_result, dict):
            choices = llm_result.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                text_content = msg.get("content", "") or ""
                # Spec 2: 提取 reasoning_content (LLMAdapter 已透传 provider 的 reasoning_content)
                reasoning_content = (
                    msg.get("reasoning_content")
                    or msg.get("reasoning")
                    or msg.get("thinking")
                    or ""
                )
                if not isinstance(reasoning_content, str):
                    reasoning_content = str(reasoning_content or "")
                raw_calls = msg.get("tool_calls", []) or []
                tool_calls = [
                    _normalize_tool_call_for_api(tc) for tc in raw_calls if isinstance(tc, dict)
                ]

        elif isinstance(llm_result, str):
            text_content = llm_result

        self._last_round_was_pseudo = False
        if not tool_calls and text_content and self._pseudo_recoveries < 2:
            pseudo = extract_pseudo_tool_calls(text_content)
            if pseudo:
                logger.info("Recovered %d pseudo tool call(s) from assistant text", len(pseudo))
                self._pseudo_recoveries += 1
                self._last_round_was_pseudo = True
                tool_calls = [_normalize_tool_call_for_api(tc) for tc in pseudo]
                text_content = strip_pseudo_tool_markup(text_content)

        return text_content, tool_calls if tool_calls else None, reasoning_content

    async def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具调用"""
        try:
            if hasattr(self._tools, "execute"):
                result = self._tools.execute(tool_name, args)
            elif hasattr(self._tools, "call"):
                result = self._tools.call(tool_name, **args)
            else:
                return "[失败] 工具执行器不支持 execute/call 方法"

            if asyncio.iscoroutine(result):
                result = await result

            # 转换为字符串
            if hasattr(result, "to_llm_context"):
                return result.to_llm_context()
            elif hasattr(result, "content"):
                if result.success:
                    return f"[成功] {result.content}"
                return f"[失败] {result.error}"
            elif isinstance(result, str):
                return result
            elif isinstance(result, dict):
                # P1 修复: dict 结果 (office/search 工具) 需正确标记成功/失败
                # 原来直接 json.dumps 导致 loop.py L987 的 startswith("[失败]") 失效,
                # 工具失败时被误判为成功, Reflexion 不触发, trace 计数错误
                ok = bool(result.get("success", True))
                # 移除 success 字段避免重复, 保留其他字段供 LLM 参考
                payload = {k: v for k, v in result.items() if k != "success"}
                body = json.dumps(payload, ensure_ascii=False, default=str)
                return f"[成功] {body}" if ok else f"[失败] {body}"
            else:
                return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return f"[失败] 工具执行异常: {e}"

    async def _generate_reflection(
        self,
        *,
        user_input: str,
        recent_failures: list[dict],
    ) -> str:
        """Spec 6 VMAO — 生成自反思（Reflexion pattern, noahshinn/reflexion 借鉴）。

        借鉴 reflexion/programming_runs/reflexion.py 的 self_reflection 步骤:
        - 给 LLM 看「最近失败的工具调用 + 用户原始目标」
        - 让 LLM 输出"为什么失败 + 下一步该尝试什么策略"
        - 不带 tools（防止反思本身又触发工具调用）

        Returns:
            反思文本（截断到 800 字符）；失败时返回空串。
        """
        if not recent_failures:
            return ""
        failure_lines: list[str] = []
        for i, f in enumerate(recent_failures[-3:], 1):
            failure_lines.append(
                f"  {i}. Step {f.get('step', '?')} · `{f.get('name', 'tool')}` 失败: "
                f"{str(f.get('error', ''))[:200]}"
            )
        failures_text = "\n".join(failure_lines)
        goal_text = (user_input or "")[:200]

        reflection_messages = [
            {
                "role": "system",
                "content": (
                    "你是 VMAO 反思代理（Verification Monitoring Adaptive Optimization）。"
                    "分析近期工具调用失败，给出**简洁可执行**的策略调整建议。"
                    "输出格式: 1) 失败根因 (1句) 2) 建议的下一步动作 (1-2句)。"
                    "禁止调用工具。最多 200 字。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户目标: {goal_text}\n\n"
                    f"近期失败的工具调用:\n{failures_text}\n\n"
                    f"请反思: 为什么当前策略不奏效？下一步应该尝试什么不同的方法？"
                ),
            },
        ]
        try:
            # 反思调用不带 tools（防止又触发工具调用）
            if asyncio.iscoroutinefunction(self._llm):
                result = await self._llm(reflection_messages)
            else:
                result = self._llm(reflection_messages)
            if result is None:
                return ""
            text, _tool_calls, _reasoning = self._parse_llm_response(result)
            return (text or "").strip()[:800]
        except Exception as e:
            logger.warning("VMAO reflection LLM call failed: %s", str(e)[:200])
            return ""

    # ============================================================
    # 自进化集成
    # ============================================================

    def _trigger_evolution_hook(self, result: AgentLoopResult) -> None:
        """执行后触发自进化钩子。

        收集执行轨迹，周期性触发进化周期。
        """
        self._execution_count += 1

        # 保存轨迹到内存
        trajectory = {
            "timestamp": datetime.now(UTC).isoformat(),
            "success": result.success,
            "response": result.response[:500],
            "steps": len(result.steps),
            "total_tokens": result.total_tokens,
            "total_duration_ms": result.total_duration_ms,
            "tool_calls": [
                {"name": s.tool_name, "success": s.tool_success}
                for s in result.steps
                if s.tool_name
            ],
        }
        self._all_trajectories.append(trajectory)

        # 持久化到 session store
        if self._session_store:
            try:
                self._session_store.save_session(
                    session_id=getattr(self, "_session_id", "default"),
                    messages=[m.to_dict() if hasattr(m, "to_dict") else m for m in self.messages],
                    traces=[t.to_summary() for t in self.traces],
                )
            except Exception:
                pass

        # 每 N 次执行触发一次进化
        if self._execution_count % self.evolution_interval == 0:
            self._run_evolution_cycle()

        # 回调
        if self.on_evolution:
            self.on_evolution(trajectory)

    def _run_evolution_cycle(self) -> None:
        """运行一次自进化周期（MFP 主路径）。

        - MFP（KTG 固化 / 元反思 / 爬山）每次任务后必跑 — README 护城河，主路径
        - 长期进化逻辑已下线，由 MFP 覆盖
        - MFP 失败只记日志，不影响主流程
        """
        # ---- 主路径：MFP（每次任务后短期固化）----
        components = getattr(self, "_graph_components", None)
        if components is not None:
            try:
                from fnixagent.services.work_agent import run_mfp_after_task

                recent = self._all_trajectories[-1] if self._all_trajectories else {}
                tool_calls = recent.get("tool_calls") or []
                run_mfp_after_task(
                    components,
                    user_input=getattr(self, "_work_user_input", "") or recent.get("response", ""),
                    success=bool(recent.get("success", True)),
                    tool_calls=tool_calls,
                    duration_ms=float(recent.get("total_duration_ms") or 0),
                    concept_path=list(getattr(self, "_ktg_concept_path", []) or []),
                    workspace=getattr(self, "_workspace", "") or "",
                )
                if len(self._all_trajectories) > 100:
                    self._all_trajectories = self._all_trajectories[-100:]
            except Exception as e:
                print(f"[AgenticLoop] MFP 进化异常: {e}")

    def _extract_insights_from_trajectories(self, trajectories: list[dict]) -> list[dict]:
        """从执行轨迹中提取洞察。

        Returns:
            洞察列表，每个洞察包含:
              - content: 洞察内容
              - source: 来源
              - upgrade_priority: 升级优先级
        """
        insights = []
        for t in trajectories:
            if not t["success"]:
                insights.append(
                    {
                        "content": f"执行失败: {t.get('response', '')[:200]}",
                        "source": "execution_trace",
                        "upgrade_priority": "high",
                    }
                )
            elif t["total_tokens"] > 5000:
                insights.append(
                    {
                        "content": f"高 token 消耗 ({t['total_tokens']} tokens): 考虑优化提示词或工具调用策略",
                        "source": "execution_trace",
                        "upgrade_priority": "medium",
                    }
                )
            elif t["total_duration_ms"] > 30000:
                insights.append(
                    {
                        "content": f"执行耗时过长 ({t['total_duration_ms']:.0f}ms): 考虑并行化或缓存",
                        "source": "execution_trace",
                        "upgrade_priority": "medium",
                    }
                )
        return insights


# ============================================================
# Agent 工厂
# ============================================================


def create_agent_from_kernel(
    kernel,  # AgentKernel 实例
    workspace_root: str = ".",
    max_steps: int = 30,
) -> AgenticLoop:
    """从 AgentKernel 创建 AgenticLoop

    Args:
        kernel: AgentKernel 实例
        workspace_root: 工作区
        max_steps: 最大步数

    Returns:
        AgenticLoop 实例
    """
    from fnixagent.core.tools.registry import ToolRegistry
    from fnixagent.core.tools.workspace import register_workspace_tools

    # 创建工具注册表
    registry = ToolRegistry()

    # 注册 workspace 工具
    register_workspace_tools(registry, workspace_root)

    # 创建 LLM 调用函数
    async def llm_call(messages, tools=None):
        """通过 kernel 调用 LLM"""
        from fnixagent.core.llm.base import LLMService

        service = LLMService()
        return await service.chat(messages, tools=tools)

    return AgenticLoop(
        llm_call=llm_call,
        tool_executor=registry,
        workspace_root=workspace_root,
        max_steps=max_steps,
    )
