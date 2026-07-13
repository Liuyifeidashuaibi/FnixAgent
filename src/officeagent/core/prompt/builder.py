"""
分层 Prompt 构建器。

分层结构(从上到下):
  1. ROLE:       角色设定("你是办公智能助手...")
  2. CONSTRAINT:  业务约束(禁止/要求/输出规范)
  3. TOOLS:      可用工具列表(给 LLM function-calling)
  4. MEMORY:     长期记忆片段(向量检索召回的相关历史)
  5. HISTORY:    短期对话历史(滑动窗口裁剪后)
  6. FORMAT:     强制输出格式(JSON/Markdown)
  7. REFLECTION: 反思模板(校验/重规划引导)

Token 预算控制:
  组装后若总 token 超预算, 从最早的 HISTORY 消息开始裁剪,
  保留 ROLE + TOOLS + 最近对话 + FORMAT。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from officeagent.core.text import estimate_message_tokens, estimate_tokens
from officeagent.core.types import MemoryItem, Message, MessageRole


class PromptLayer(str, Enum):
    """Prompt 分层。"""
    ROLE = "role"
    CONSTRAINT = "constraint"
    TOOLS = "tools"
    MEMORY = "memory"
    HISTORY = "history"
    FORMAT = "format"
    REFLECTION = "reflection"


class PromptBuilder:
    """
    流式分层 Prompt 构建器。

    用法:
        builder = PromptBuilder(max_tokens=8000)
        builder.set_role("你是办公智能助手...")
        builder.set_constraints(["只能使用提供的工具", "输出必须为JSON"])
        builder.set_tools(tool_descriptions)
        builder.set_memory(memories)
        builder.set_history(messages)
        builder.set_format('{"result": "..."}')
        messages = builder.build()
    """

    # 模板变量正则: {{variable_name}}
    _VAR_RE = re.compile(r"\{\{(\w+)\}\}")

    def __init__(self, max_tokens: int = 8000):
        self._max_tokens = max_tokens
        self._layers: dict[PromptLayer, str] = {}
        self._tools: list[dict] = []
        self._memories: list[MemoryItem] = []
        self._history: list[Message] = []
        self._variables: dict[str, str] = {}

    # -- 分层设置 ----------------------------------------------------------

    def set_role(self, role_text: str) -> "PromptBuilder":
        """设置角色设定。"""
        self._layers[PromptLayer.ROLE] = role_text
        return self

    def set_constraints(self, constraints: list[str]) -> "PromptBuilder":
        """设置业务约束。"""
        text = "\n".join(f"- {c}" for c in constraints)
        self._layers[PromptLayer.CONSTRAINT] = text
        return self

    def set_tools(self, tools: list[dict]) -> "PromptBuilder":
        """设置工具列表(来自 ToolMetadata.to_llm_description())。"""
        self._tools = tools
        lines = ["## 可用工具"]
        for t in tools:
            func = t.get("function", t)
            name = func.get("name", "")
            desc = func.get("description", "")
            params = func.get("parameters", {})
            lines.append(f"- {name}: {desc}")
            if params.get("properties"):
                props = params["properties"]
                required = params.get("required", [])
                for pname, pschema in props.items():
                    req = "(必填)" if pname in required else ""
                    ptype = pschema.get("type", "any")
                    pdesc = pschema.get("description", "")
                    lines.append(f"  - {pname} ({ptype}){req}: {pdesc}")
        self._layers[PromptLayer.TOOLS] = "\n".join(lines)
        return self

    def set_memory(self, memories: list[MemoryItem]) -> "PromptBuilder":
        """注入长期记忆片段。"""
        self._memories = memories
        if not memories:
            return self
        lines = ["## 相关历史知识"]
        for m in memories:
            lines.append(f"[相似度={m.score:.2f}] {m.content}")
        self._layers[PromptLayer.MEMORY] = "\n".join(lines)
        return self

    def set_history(self, messages: list[Message]) -> "PromptBuilder":
        """设置短期对话历史(已裁剪)。"""
        self._history = messages
        return self

    def set_format(self, format_spec: str) -> "PromptBuilder":
        """设置强制输出格式。"""
        self._layers[PromptLayer.FORMAT] = f"## 输出格式\n{format_spec}"
        return self

    def set_reflection(self, template: str) -> "PromptBuilder":
        """设置反思模板。"""
        self._layers[PromptLayer.REFLECTION] = template
        return self

    def set_variable(self, name: str, value: str) -> "PromptBuilder":
        """设置模板变量(用于 {{name}} 替换)。"""
        self._variables[name] = value
        return self

    # -- 组装 --------------------------------------------------------------

    def _replace_vars(self, text: str) -> str:
        """替换 {{variable}} 占位符。"""
        def _replacer(m: re.Match) -> str:
            var = m.group(1)
            return self._variables.get(var, m.group(0))
        return self._VAR_RE.sub(_replacer, text)

    def _assemble_system(self) -> str:
        """拼接 system 消息(role+constraints+tools+memory+format+reflection)。"""
        parts: list[str] = []
        order = [
            PromptLayer.ROLE,
            PromptLayer.CONSTRAINT,
            PromptLayer.TOOLS,
            PromptLayer.MEMORY,
            PromptLayer.FORMAT,
            PromptLayer.REFLECTION,
        ]
        for layer in order:
            text = self._layers.get(layer)
            if text:
                parts.append(self._replace_vars(text))
        return "\n\n".join(parts)

    def build(self) -> list[Message]:
        """
        组装为 LLM 消息列表。
        返回 [system_message] + history。
        Token 超预算时从 history 最早消息开始裁剪。
        """
        system_text = self._assemble_system()
        system_msg = Message(role=MessageRole.SYSTEM, content=system_text)

        # Token 预算控制
        all_msgs = [system_msg] + list(self._history)
        total = estimate_message_tokens(all_msgs)

        if total <= self._max_tokens:
            return all_msgs

        # 超预算: 从 history 最早开始裁剪
        system_tokens = estimate_tokens(system_text) + 4
        budget_for_history = self._max_tokens - system_tokens
        if budget_for_history <= 0:
            # system 本身就超预算, 只返回 system
            return [system_msg]

        # 保留最近的 history 消息
        trimmed: list[Message] = []
        used = 0
        for msg in reversed(self._history):
            msg_tokens = estimate_tokens(msg.content) + 4
            if used + msg_tokens > budget_for_history:
                break
            trimmed.insert(0, msg)
            used += msg_tokens

        return [system_msg] + trimmed

    # -- 辅助 --------------------------------------------------------------

    def estimate_total_tokens(self) -> int:
        """估算当前组装后的总 token 数。"""
        msgs = self.build()
        return estimate_message_tokens(msgs)
