"""
MCPToolRegistry 适配器 (MCPToolRegistry Adapter)
=================================================
将 core/mcp/registry.py 的 MCPToolRegistry 适配为 ToolBackend 协议。

适配要点:
  - list_tools: ToolMetadata → dict 序列化
  - invoke: 使用 call_async (异步), 捕获 MCP 异常
  - 工具名: 使用全局名 (server_id.tool_name)

使用方式:
    from fnixagent.core.mcp.registry import MCPToolRegistry
    from fnixagent.core.agent.backends.mcp_registry import MCPToolRegistryAdapter

    mcp = MCPToolRegistry()
    backend = MCPToolRegistryAdapter(mcp)
    kernel = AgentKernel(tool_backend=backend)
"""
from __future__ import annotations

from typing import Any

from fnixagent.core.agent.types import ToolBackend


class MCPToolRegistryAdapter:
    """MCPToolRegistry → ToolBackend 适配器。

    将 core/mcp/registry.py 的 MCPToolRegistry 适配为 async ToolBackend。

    Args:
        registry: MCPToolRegistry 实例
        timeout_ms: 默认调用超时 (毫秒)
    """

    def __init__(self, registry: Any, timeout_ms: int = 30000):
        self._registry = registry
        self._timeout_ms = timeout_ms

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出所有可用工具 (ToolMetadata → dict)。"""
        try:
            tools = self._registry.list_all_tools_metadata()
        except AttributeError:
            # 降级: 尝试 list_all_tools
            try:
                tools = self._registry.list_all_tools()
            except AttributeError:
                return []
        result: list[dict[str, Any]] = []
        for tool in tools:
            # ToolMetadata → dict
            if hasattr(tool, "__dict__"):
                result.append(dict(tool.__dict__))
            elif hasattr(tool, "to_dict"):
                result.append(tool.to_dict())
            else:
                result.append({"name": str(tool)})
        return result

    async def invoke(self, tool_name: str,
                     arguments: dict[str, Any]) -> Any:
        """调用工具 (使用 call_async, 捕获 MCP 异常)。"""
        try:
            # 优先使用 call_async
            if hasattr(self._registry, "call_async"):
                result = await self._registry.call_async(
                    tool_name, arguments, timeout_ms=self._timeout_ms
                )
                return result
            # 降级: 使用同步 call (用 asyncio.to_thread 包装)
            elif hasattr(self._registry, "call"):
                import asyncio
                result = await asyncio.to_thread(
                    self._registry.call,
                    tool_name, arguments,
                    timeout_ms=self._timeout_ms,
                )
                return result
            else:
                return {"error": f"registry 不支持 call/call_async"}
        except Exception as e:
            # 捕获 MCP 异常, 返回错误 dict
            return {
                "error": f"工具调用失败: {type(e).__name__}: {e}",
                "tool": tool_name,
                "arguments": arguments,
            }


__all__ = ["MCPToolRegistryAdapter"]
