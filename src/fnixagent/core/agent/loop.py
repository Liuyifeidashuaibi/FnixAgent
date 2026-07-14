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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

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
    thought: str = ""               # LLM 思考内容
    tool_name: str | None = None    # 被调用的工具名
    tool_input: dict | None = None  # 工具输入
    tool_output: str | None = None  # 工具输出
    tool_success: bool = True       # 工具是否成功
    duration_ms: float = 0.0        # 耗时
    tokens_used: int = 0            # token 消耗

    def to_summary(self) -> str:
        parts = [f"Step {self.step_index}"]
        if self.thought:
            parts.append(f"思考: {self.thought[:100]}...")
        if self.tool_name:
            status = "✓" if self.tool_success else "✗"
            parts.append(f"工具 {status} {self.tool_name}({json.dumps(self.tool_input or {}, ensure_ascii=False)[:50]})")
        parts.append(f"耗时: {self.duration_ms:.0f}ms, tokens: {self.tokens_used}")
        return " | ".join(parts)


# ============================================================
# Agent 循环结果
# ============================================================

@dataclass
class AgentLoopResult:
    """Agent 循环执行结果"""
    success: bool
    response: str = ""              # 最终用户响应
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
        """
        self._llm = llm_call
        self._tools = tool_executor
        self.workspace_root = str(Path(workspace_root).resolve())
        self.max_steps = max_steps
        self.enable_reflection = enable_reflection
        self.enable_evolution = enable_evolution
        self.evolution_interval = evolution_interval
        self._session_store = session_store

        # 对话历史
        self.messages: list[Message] = []
        self.traces: list[StepTrace] = []

        # 自进化计数器
        self._execution_count: int = 0
        self._all_trajectories: list[dict] = []

        # 回调
        self.on_step: Optional[Callable[[StepTrace], None]] = None
        self.on_thinking: Optional[Callable[[str], None]] = None
        self.on_tool_call: Optional[Callable[[str, dict], None]] = None
        self.on_response: Optional[Callable[[str], None]] = None
        self.on_evolution: Optional[Callable[[dict], None]] = None

    # ============================================================
    # 初始化
    # ============================================================

    def reset(self):
        """重置对话状态"""
        self.messages = []
        self.traces = []

    def _get_system_prompt(self) -> str:
        """构建系统提示词"""
        # 获取工作区概览
        workspace = Path(self.workspace_root)
        tree = f"工作区: {workspace.name}"

        # 获取工具列表
        tools_desc = self._tools.get_tools_description() if hasattr(self._tools, 'get_tools_description') else ""

        prompt = self.SYSTEM_PROMPT.format(workspace_root=self.workspace_root)
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
                        error="LLM 调用失败",
                        steps=self.traces,
                        total_tokens=total_tokens,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )

                # 解析 LLM 响应
                text_content, tool_calls = self._parse_llm_response(llm_result)
                total_tokens += llm_result.get("usage", {}).get("total_tokens", 0)

                # Step 2: 如果是最终文本响应
                if text_content and not tool_calls:
                    trace = StepTrace(
                        step_index=step_idx,
                        thought=text_content[:200],
                        duration_ms=(time.time() - step_start) * 1000,
                        tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                    )
                    self.traces.append(trace)

                    if self.on_response:
                        self.on_response(text_content)

                    result = AgentLoopResult(
                        success=True,
                        response=text_content,
                        steps=self.traces,
                        total_tokens=total_tokens,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )
                    # 触发自进化飞轮
                    if self.enable_evolution:
                        self._trigger_evolution_hook(result)
                    return result

                # Step 3: Act — 执行工具调用
                if tool_calls:
                    # 添加 assistant 消息
                    assistant_msg = {
                        "role": "assistant",
                        "content": text_content or "",
                    }
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls

                    messages_for_llm.append(assistant_msg)
                    self.messages.append(Message(
                        role=MessageRole.ASSISTANT,
                        content=text_content or "",
                        tool_calls=tool_calls,
                    ))

                    # 执行每个工具调用
                    for tc in tool_calls:
                        tool_name = tc.get("function", {}).get("name", "")
                        tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))

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
                        messages_for_llm.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": tool_result,
                        })
                        self.messages.append(Message(
                            role=MessageRole.TOOL,
                            content=tool_result,
                            tool_call_id=tc.get("id", ""),
                        ))

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

    async def run_stream(self, user_input: str):
        """
        流式执行 Agent 循环 (Generator)

        Yields:
            dict: {"type": "thinking"|"tool_call"|"tool_result"|"text"|"done", "data": ...}
        """
        self.reset()
        start_time = time.time()

        system_prompt = self._get_system_prompt()
        messages_for_llm = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        self.messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt[:200]))
        self.messages.append(Message(role=MessageRole.USER, content=user_input))

        try:
            for step_idx in range(self.max_steps):
                step_start = time.time()

                yield {"type": "thinking", "data": f"Step {step_idx + 1}: 思考中..."}

                llm_result = await self._call_llm(messages_for_llm)
                if llm_result is None:
                    yield {"type": "error", "data": "LLM 调用失败"}
                    return

                text_content, tool_calls = self._parse_llm_response(llm_result)

                # 最终响应
                if text_content and not tool_calls:
                    yield {"type": "text", "data": text_content}
                    yield {"type": "done", "data": {
                        "steps": len(self.traces),
                        "duration_ms": (time.time() - start_time) * 1000,
                    }}
                    return

                # 工具调用
                if tool_calls:
                    assistant_msg = {"role": "assistant", "content": text_content or ""}
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    messages_for_llm.append(assistant_msg)

                    for tc in tool_calls:
                        tool_name = tc.get("function", {}).get("name", "")
                        tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))

                        yield {"type": "tool_call", "data": {"name": tool_name, "args": tool_args}}

                        tool_result = await self._execute_tool(tool_name, tool_args)

                        yield {"type": "tool_result", "data": tool_result[:500]}

                        messages_for_llm.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": tool_result,
                        })

            yield {"type": "error", "data": f"超过最大步数 ({self.max_steps})"}

        except Exception as e:
            yield {"type": "error", "data": str(e)}

    # ============================================================
    # 内部方法
    # ============================================================

    async def _call_llm(self, messages: list[dict]) -> dict | None:
        """调用 LLM"""
        try:
            # 获取工具定义
            tools = self._tools.get_tool_definitions() if hasattr(self._tools, 'get_tool_definitions') else None

            if asyncio.iscoroutinefunction(self._llm):
                result = await self._llm(messages, tools)
            else:
                result = self._llm(messages, tools)

            return result
        except Exception as e:
            # 如果 LLM 不支持 tools 参数，重试不带 tools
            try:
                if asyncio.iscoroutinefunction(self._llm):
                    return await self._llm(messages)
                return self._llm(messages)
            except Exception:
                return None

    def _parse_llm_response(self, llm_result: dict) -> tuple[str, list[dict] | None]:
        """解析 LLM 响应，提取文本和工具调用"""
        text_content = ""
        tool_calls = []

        if isinstance(llm_result, dict):
            choices = llm_result.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                text_content = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls", []) or []

        elif isinstance(llm_result, str):
            text_content = llm_result

        return text_content, tool_calls if tool_calls else None

    async def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具调用"""
        try:
            if hasattr(self._tools, 'execute'):
                result = self._tools.execute(tool_name, args)
            elif hasattr(self._tools, 'call'):
                result = self._tools.call(tool_name, **args)
            else:
                return f"[失败] 工具执行器不支持 execute/call 方法"

            if asyncio.iscoroutine(result):
                result = await result

            # 转换为字符串
            if hasattr(result, 'to_llm_context'):
                return result.to_llm_context()
            elif hasattr(result, 'content'):
                if result.success:
                    return f"[成功] {result.content}"
                return f"[失败] {result.error}"
            elif isinstance(result, str):
                return result
            else:
                return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return f"[失败] 工具执行异常: {e}"

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": result.success,
            "response": result.response[:500],
            "steps": len(result.steps),
            "total_tokens": result.total_tokens,
            "total_duration_ms": result.total_duration_ms,
            "tool_calls": [
                {"name": s.tool_name, "success": s.tool_success}
                for s in result.steps if s.tool_name
            ],
        }
        self._all_trajectories.append(trajectory)

        # 持久化到 session store
        if self._session_store:
            try:
                self._session_store.save_session(
                    session_id=getattr(self, "_session_id", "default"),
                    messages=[m.to_dict() if hasattr(m, 'to_dict') else m for m in self.messages],
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
        """运行一次自进化周期。

        收集最近的执行轨迹，调用 EvolutionMaster 进行:
          1. 感知采集 (Layer 0)
          2. 循环工程 (Layer 1)
          3. 遗传进化 (Layer 2)
          4. 安全检查 (Layer 3)
          5. 知识合成 (Layer 4)
          6. 记忆存储 (Layer 5)
          7. 自我审判 (Layer 7)
        """
        try:
            from fnixagent.core.intelligence.evolution_master import EvolutionMaster

            # 提取最近的轨迹作为输入
            recent_trajectories = self._all_trajectories[-self.evolution_interval:]
            insights = self._extract_insights_from_trajectories(recent_trajectories)

            if not insights:
                return

            # 启动进化周期
            master = EvolutionMaster(workspace_root=self.workspace_root)
            master.run_full_evolution_cycle(
                external_insights=insights,
                trajectories=recent_trajectories,
            )

            # 清理旧轨迹 (保留最近 100 条)
            if len(self._all_trajectories) > 100:
                self._all_trajectories = self._all_trajectories[-100:]

        except ImportError:
            pass  # 自进化模块未安装
        except Exception as e:
            # 自进化失败不应影响主流程
            print(f"[AgenticLoop] 进化周期异常: {e}")

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
                insights.append({
                    "content": f"执行失败: {t.get('response', '')[:200]}",
                    "source": "execution_trace",
                    "upgrade_priority": "high",
                })
            elif t["total_tokens"] > 5000:
                insights.append({
                    "content": f"高 token 消耗 ({t['total_tokens']} tokens): 考虑优化提示词或工具调用策略",
                    "source": "execution_trace",
                    "upgrade_priority": "medium",
                })
            elif t["total_duration_ms"] > 30000:
                insights.append({
                    "content": f"执行耗时过长 ({t['total_duration_ms']:.0f}ms): 考虑并行化或缓存",
                    "source": "execution_trace",
                    "upgrade_priority": "medium",
                })
        return insights


# ============================================================
# Agent 工厂
# ============================================================

def create_agent_from_kernel(
    kernel,       # AgentKernel 实例
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
    from fnixagent.core.tools.workspace import WorkspaceTools, register_workspace_tools
    from fnixagent.core.tools.registry import ToolRegistry

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