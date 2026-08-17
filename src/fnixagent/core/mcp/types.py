"""MCP(Model Context Protocol)类型定义(P2-3)。

定义 MCP 工具/请求/响应/服务器信息的标准数据模型。
所有 MCP 客户端/服务器/注册表共享这些类型。

参考:
  - Anthropic MCP 规范:https://modelcontextprotocol.io
  - JSON-RPC 2.0:https://www.jsonrpc.org/specification

设计原则:
  - 与 LLM 工具描述兼容(input_schema 用 JSON Schema)
  - 与本地 ToolMetadata 可互转(由 registry.to_tool_metadata 完成)
  - 异步友好(所有 IO 字段为纯数据,无 IO 资源)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# URL 合法 scheme(MCP SSE/WebSocket 传输)
_URL_SCHEME_PATTERN = re.compile(
    r"^(https?|wss?)://[A-Za-z0-9.\-_:]+(?:/[^\s]*)?$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 传输层
# ---------------------------------------------------------------------------


class MCPTransport(str, Enum):
    """MCP 传输协议。"""

    STDIO = "stdio"  # 子进程 stdin/stdout(JSON-RPC over stdio)
    SSE = "sse"  # Server-Sent Events(HTTP + SSE 长连接)
    WEBSOCKET = "websocket"  # WebSocket(未来扩展)


class MCPServerStatus(str, Enum):
    """MCP 服务器连接状态。"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


# ---------------------------------------------------------------------------
# 工具定义
# ---------------------------------------------------------------------------


class MCPToolDef(BaseModel):
    """MCP 工具定义(从 MCP server 的 tools/list 返回解析得到)。

    与本地 ToolMetadata 字段对齐,可由 MCPToolRegistry.to_tool_metadata 转换。
    """

    name: str = Field(..., description="工具名(全 server 内唯一)")
    description: str = Field("", description="工具描述(给 LLM 看)")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="入参 JSON Schema(MCP 协议规定)",
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="出参 JSON Schema(可选)",
    )
    server_id: str = Field(..., description="所属 MCP server ID")
    annotations: dict[str, Any] = Field(
        default_factory=dict,
        description="MCP 工具注解(如 readOnlyHint/destructiveHint)",
    )
    # 本地补充字段(由 registry 注入)
    source: str = "mcp"
    cost_score: float = 0.5
    layer: str = "L2_ECOSYSTEM"  # 默认归入 L2 办公生态

    def to_llm_description(self) -> dict:
        """生成给 LLM function-calling 的工具描述(OpenAI tools 格式)。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
                or {
                    "type": "object",
                    "properties": {},
                },
            },
        }


# ---------------------------------------------------------------------------
# 请求/响应
# ---------------------------------------------------------------------------


class MCPRequest(BaseModel):
    """MCP 工具调用请求。"""

    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    tool_name: str = Field(..., description="工具名")
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(30000, description="超时毫秒")
    server_id: str = Field("", description="目标 server ID(可空,由 registry 路由)")
    # 元数据(供 tracing/审计)
    trace_id: str = ""
    user_id: str = ""
    tenant_id: str = ""


class MCPResponse(BaseModel):
    """MCP 工具调用响应。"""

    request_id: str = Field(..., description="对应 MCPRequest.request_id")
    success: bool = Field(..., description="调用是否成功")
    result: Any = Field(None, description="成功时的返回结果")
    error: str | None = Field(None, description="失败时的错误信息")
    error_code: int | None = Field(None, description="错误码(JSON-RPC)")
    latency_ms: float = Field(0.0, description="调用耗时毫秒")
    server_id: str = Field("")
    tool_name: str = ""


# ---------------------------------------------------------------------------
# 服务器信息
# ---------------------------------------------------------------------------


class MCPServerInfo(BaseModel):
    """MCP 服务器元信息(从 initialize 握手得到)。"""

    server_id: str = Field(..., description="本地唯一 ID(由 registry 分配)")
    name: str = Field(..., description="server 自报名(initialize 返回)")
    version: str = Field("0.0.0", description="server 自报版本")
    protocol_version: str = Field("2024-11-05", description="MCP 协议版本")
    capabilities: dict[str, Any] = Field(
        default_factory=dict,
        description="server 能力声明(tools/resources/prompts/logging)",
    )
    description: str = ""
    transport: MCPTransport = MCPTransport.STDIO
    # 连接配置(用于 reconnect)
    command: str | None = None  # STDIO:启动命令
    args: list[str] = Field(default_factory=list)  # STDIO:命令参数
    env: dict[str, str] = Field(default_factory=dict)  # STDIO:环境变量
    url: str | None = None  # SSE/WebSocket:服务器 URL
    headers: dict[str, str] = Field(default_factory=dict)  # SSE:HTTP 头
    # 身份认证(SSE 模式下携带 Bearer Token,由 client 注入到请求头)
    auth_token: str | None = None
    # 运行时状态
    status: MCPServerStatus = MCPServerStatus.DISCONNECTED
    last_connected_at: datetime | None = None
    last_error: str = ""

    def validate_url(self) -> None:
        """校验 URL 格式(SSE/WebSocket 传输必须提供合法 URL)。

        Raises:
            ValueError: URL 为空或格式非法
        """
        if self.transport == MCPTransport.STDIO:
            return  # STDIO 不需要 URL
        if not self.url:
            raise ValueError(f"MCP transport '{self.transport.value}' requires 'url'")
        if not _URL_SCHEME_PATTERN.match(self.url):
            raise ValueError(
                f"Invalid MCP server URL '{self.url}': must be http(s):// or ws(s):// scheme"
            )


# ---------------------------------------------------------------------------
# 错误码(JSON-RPC 2.0 + MCP 扩展)
# ---------------------------------------------------------------------------


class MCPErrorCode(int, Enum):
    """MCP 错误码。"""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    # MCP 扩展
    TOOL_NOT_FOUND = -32001
    TOOL_EXECUTION_FAILED = -32002
    SERVER_NOT_CONNECTED = -32003
    TIMEOUT = -32004
    RATE_LIMITED = -32005


# ---------------------------------------------------------------------------
# JSON-RPC 消息(用于底层传输)
# ---------------------------------------------------------------------------


class JSONRPCRequest(BaseModel):
    """JSON-RPC 2.0 请求。

    id 字段为请求唯一标识,由 client 生成,server 在响应中回填相同 id。
    为避免冲突,id 默认使用 uuid4 前 16 位(碰撞概率极低);
    多线程并发场景下应配合 client 内部的 _id_counter 保证唯一性。
    """

    jsonrpc: str = "2.0"
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    method: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class JSONRPCResponse(BaseModel):
    """JSON-RPC 2.0 响应。

    id 必须与对应 JSONRPCRequest.id 一样,client 据此匹配请求-响应。
    """

    jsonrpc: str = "2.0"
    id: str = ""
    result: Any = None
    error: dict[str, Any] | None = None


class JSONRPCError(BaseModel):
    """JSON-RPC 2.0 错误对象。"""

    code: int
    message: str
    data: Any = None
