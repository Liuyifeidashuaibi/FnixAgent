"""MCP(Model Context Protocol)模块(P2-3)。

让 fnixagent 既能消费外部 MCP server(Feishu/WeChat Work/DingTalk 等办公生态),
也能把自身工具暴露为 MCP server(供 Claude Desktop / 其他 agent 调用)。

子模块:
  - types:    数据模型(MCPToolDef/MCPRequest/MCPResponse/MCPServerInfo)
  - client:   MCP 客户端(连接外部 MCP server,STDIO/SSE 传输)
  - registry: MCP 工具注册表(管理多 server,统一暴露为本地工具)
  - server:   MCP 服务器(把本地工具暴露给外部 MCP client)

设计原则:
  - 无第三方依赖(不依赖官方 mcp SDK;STDIO 用 asyncio,SSE 用 urllib)
  - 协议兼容 Anthropic MCP(2024-11-05)
  - 异步优先(client 内部 async,提供同步包装)
  - 白名单模式(server 默认不暴露任何工具)
"""
from fnixagent.core.mcp.types import (
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPErrorCode,
    MCPRequest,
    MCPResponse,
    MCPServerInfo,
    MCPServerStatus,
    MCPToolDef,
    MCPTransport,
)
from fnixagent.core.mcp.client import (
    MCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPTimeoutError,
    MCPToolExecutionError,
)
from fnixagent.core.mcp.registry import (
    MCPServerAlreadyExistsError,
    MCPServerNotFoundError,
    MCPRegistryError,
    MCPToolNotFoundError,
    MCPToolRegistry,
)
from fnixagent.core.mcp.server import (
    MCPServer,
    MCPServerAlreadyRunningError,
    MCPServerError,
    MCPToolNotExposedError,
)

__all__ = [
    # types
    "MCPTransport",
    "MCPServerStatus",
    "MCPToolDef",
    "MCPRequest",
    "MCPResponse",
    "MCPServerInfo",
    "MCPErrorCode",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "JSONRPCError",
    # client
    "MCPClient",
    "MCPClientError",
    "MCPConnectionError",
    "MCPTimeoutError",
    "MCPToolExecutionError",
    # registry
    "MCPToolRegistry",
    "MCPRegistryError",
    "MCPServerNotFoundError",
    "MCPServerAlreadyExistsError",
    "MCPToolNotFoundError",
    # server
    "MCPServer",
    "MCPServerError",
    "MCPServerAlreadyRunningError",
    "MCPToolNotExposedError",
]
