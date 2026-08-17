"""
FnixAgent MCP Server — 让 FnixAgent 可被 行业编码工具 等 IDE 作为 MCP 工具调用

MCP (Model Context Protocol) Server 实现:
  - 标准 MCP JSON-RPC 协议
  - stdio 传输 (用于 IDE 集成)
  - HTTP/SSE 传输 (用于远程调用)
  - 暴露所有 FnixAgent 工具和能力

行业编码工具 配置示例:
  {
    "mcpServers": {
      "fnixagent": {
        "command": "python",
        "args": ["-m", "fnixagent.core.mcp.server"],
        "cwd": "/path/to/workspace"
      }
    }
  }
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# ============================================================
# MCP 协议常量
# ============================================================

JSONRPC_VERSION = "2.0"
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "fnixagent"
SERVER_VERSION = "1.0.0"


# ============================================================
# MCP Server 核心
# ============================================================


class MCPServerError(Exception):
    """MCP Server 基类异常"""

    pass


class MCPServerAlreadyRunningError(MCPServerError):
    """MCP Server 已在运行"""

    pass


class MCPToolNotExposedError(MCPServerError):
    """MCP 工具未暴露"""

    pass


class MCPServer:
    """
    MCP Server — 标准 MCP JSON-RPC 协议实现

    支持:
    - initialize: 握手
    - tools/list: 列出所有可用工具
    - tools/call: 调用工具
    - resources/list: 列出资源
    - prompts/list: 列出提示词
    """

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = str(Path(workspace_root).resolve())
        self._tools: dict[str, dict] = {}
        self._initialized = False
        self._register_tools()

    # ============================================================
    # 工具注册
    # ============================================================

    def _register_tools(self):
        """注册所有内置工具"""
        self._tools = {
            "read_file": {
                "name": "read_file",
                "description": "读取文件内容，支持行号范围",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径（绝对路径或相对于 workspace 的路径）",
                        },
                        "offset": {"type": "integer", "description": "起始行号（1-based，默认 1）"},
                        "limit": {"type": "integer", "description": "最大读取行数"},
                    },
                    "required": ["file_path"],
                },
            },
            "write_file": {
                "name": "write_file",
                "description": "写入文件（覆盖模式），会自动创建父目录",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "文件内容"},
                    },
                    "required": ["file_path", "content"],
                },
            },
            "edit_file": {
                "name": "edit_file",
                "description": "精确字符串替换编辑文件。如果 old_string 不唯一，需要设置 replace_all=True",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "old_string": {"type": "string", "description": "要替换的字符串"},
                        "new_string": {"type": "string", "description": "替换后的字符串"},
                        "replace_all": {
                            "type": "boolean",
                            "description": "是否替换所有匹配项（默认 false）",
                            "default": False,
                        },
                    },
                    "required": ["file_path", "old_string", "new_string"],
                },
            },
            "glob": {
                "name": "glob",
                "description": "文件名模式匹配搜索，如 '*.py', 'src/**/*.ts'",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "glob 模式"},
                        "path": {
                            "type": "string",
                            "description": "搜索起始目录",
                            "default": ".",
                        },
                    },
                    "required": ["pattern"],
                },
            },
            "grep": {
                "name": "grep",
                "description": "文件内容正则搜索",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "正则表达式"},
                        "path": {
                            "type": "string",
                            "description": "搜索目录",
                            "default": ".",
                        },
                        "glob": {
                            "type": "string",
                            "description": "文件名过滤 glob",
                            "default": "*",
                        },
                        "output_mode": {
                            "type": "string",
                            "description": "输出模式: content | files_with_matches | count",
                            "default": "content",
                        },
                    },
                    "required": ["pattern"],
                },
            },
            "ls": {
                "name": "ls",
                "description": "列出目录内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "目录路径",
                            "default": ".",
                        },
                    },
                },
            },
            "run_command": {
                "name": "run_command",
                "description": "执行 Shell 命令（Windows 使用 PowerShell）",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的命令"},
                        "cwd": {"type": "string", "description": "工作目录"},
                        "timeout": {
                            "type": "integer",
                            "description": "超时秒数",
                            "default": 60,
                        },
                    },
                    "required": ["command"],
                },
            },
            "web_search": {
                "name": "web_search",
                "description": "网络搜索",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "num": {
                            "type": "integer",
                            "description": "结果数量",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            "web_fetch": {
                "name": "web_fetch",
                "description": "获取网页内容",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "网页 URL"},
                    },
                    "required": ["url"],
                },
            },
            "ask_agent": {
                "name": "ask_agent",
                "description": "向 FnixAgent 提问，Agent 会使用工具来完成任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "任务描述"},
                    },
                    "required": ["prompt"],
                },
            },
        }

    # ============================================================
    # JSON-RPC 处理
    # ============================================================

    def handle_request(self, request: dict) -> dict:
        """处理 JSON-RPC 请求"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        try:
            if method == "initialize":
                result = self._handle_initialize(params)
            elif method == "notifications/initialized":
                self._initialized = True
                return {}  # 通知不需要响应
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = self._handle_resources_list()
            elif method == "prompts/list":
                result = self._handle_prompts_list()
            elif method == "ping":
                result = {}
            else:
                return self._error_response(req_id, -32601, f"方法未找到: {method}")

            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": req_id,
                "result": result,
            }
        except Exception as e:
            return self._error_response(req_id, -32603, str(e))

    # ============================================================
    # 方法处理器
    # ============================================================

    def _handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {},
            },
        }

    def _handle_tools_list(self) -> dict:
        return {
            "tools": list(self._tools.values()),
        }

    def _handle_tools_call(self, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return self._error_content(f"未知工具: {tool_name}")

        result = self._execute_tool(tool_name, arguments)

        return {
            "content": [
                {
                    "type": "text",
                    "text": result,
                }
            ]
        }

    def _handle_resources_list(self) -> dict:
        return {"resources": []}

    def _handle_prompts_list(self) -> dict:
        return {"prompts": []}

    # ============================================================
    # 工具执行
    # ============================================================

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具调用"""
        from fnixagent.core.tools.workspace import WorkspaceTools

        tools = WorkspaceTools(self.workspace_root)

        if tool_name == "read_file":
            result = tools.read_file(
                args.get("file_path", ""),
                args.get("offset", 1),
                args.get("limit"),
            )
        elif tool_name == "write_file":
            result = tools.write_file(
                args.get("file_path", ""),
                args.get("content", ""),
            )
        elif tool_name == "edit_file":
            result = tools.edit_file(
                args.get("file_path", ""),
                args.get("old_string", ""),
                args.get("new_string", ""),
                args.get("replace_all", False),
            )
        elif tool_name == "glob":
            result = tools.glob(
                args.get("pattern", "*"),
                args.get("path", "."),
            )
        elif tool_name == "grep":
            result = tools.grep(
                args.get("pattern", ""),
                args.get("path", "."),
                args.get("glob", "*"),
                args.get("output_mode", "content"),
            )
        elif tool_name == "ls":
            result = tools.ls(args.get("path", "."))
        elif tool_name == "run_command":
            result = asyncio.run(
                tools.run_command(
                    args.get("command", ""),
                    args.get("cwd"),
                    args.get("timeout", 60),
                )
            )
        elif tool_name == "web_search":
            result = asyncio.run(
                tools.web_search(
                    args.get("query", ""),
                    args.get("num", 5),
                )
            )
        elif tool_name == "web_fetch":
            result = asyncio.run(tools.web_fetch(args.get("url", "")))
        elif tool_name == "ask_agent":
            result = self._handle_ask_agent(args.get("prompt", ""))
        else:
            return f"错误: 未知工具 {tool_name}"

        if hasattr(result, "to_llm_context"):
            return result.to_llm_context()
        elif hasattr(result, "content"):
            return result.content if result.success else f"错误: {result.error}"
        return str(result)

    def _handle_ask_agent(self, prompt: str) -> str:
        """通过 Agent 处理复杂任务"""
        try:
            from fnixagent.core.agent.kernel import get_kernel
            from fnixagent.core.agent.loop import create_agent_from_kernel

            kernel = get_kernel()
            agent = create_agent_from_kernel(kernel, self.workspace_root)

            result = asyncio.run(agent.run(prompt))
            return result.response
        except Exception as e:
            return f"Agent 执行失败: {e}"

    # ============================================================
    # 辅助
    # ============================================================

    def _error_response(self, req_id, code: int, message: str) -> dict:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }

    def _error_content(self, message: str) -> dict:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"错误: {message}",
                }
            ],
            "isError": True,
        }


# ============================================================
# stdio 传输
# ============================================================


class StdioTransport:
    """MCP stdio 传输 — 通过 stdin/stdout 通信"""

    def __init__(self, server: MCPServer):
        self.server = server

    def run(self):
        """运行 stdio 传输循环"""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                request = json.loads(line)
                response = self.server.handle_request(request)

                if response:  # 通知不需要响应
                    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                    sys.stdout.flush()

            except json.JSONDecodeError:
                sys.stderr.write(f"JSON 解析错误: {line}\n")
                sys.stderr.flush()
            except EOFError:
                break
            except Exception as e:
                sys.stderr.write(f"MCP Server 错误: {e}\n")
                sys.stderr.flush()


# ============================================================
# HTTP/SSE 传输
# ============================================================


class HTTPTransport:
    """MCP HTTP 传输 — 通过 HTTP/SSE 提供远程调用"""

    def __init__(self, server: MCPServer):
        self.server = server

    def get_app(self):
        """获取 FastAPI/Starlette 应用"""
        try:
            from starlette.applications import Starlette
            from starlette.responses import JSONResponse
            from starlette.routing import Route

            async def handle_mcp(request):
                body = await request.json()
                response = self.server.handle_request(body)
                return JSONResponse(response)

            routes = [
                Route("/mcp", handle_mcp, methods=["POST"]),
            ]

            # 健康检查
            async def health(request):
                return JSONResponse({"status": "ok", "server": SERVER_NAME})

            routes.append(Route("/health", health))

            return Starlette(routes=routes)

        except ImportError:
            raise ImportError("HTTP 传输需要安装 starlette: pip install starlette uvicorn")


# ============================================================
# 入口
# ============================================================


def main():
    """MCP Server 入口 (命令行启动)"""
    import argparse

    parser = argparse.ArgumentParser(description="FnixAgent MCP Server")
    parser.add_argument("--workspace", "-w", default=".", help="工作区路径")
    parser.add_argument(
        "--transport", "-t", choices=["stdio", "http"], default="stdio", help="传输方式"
    )
    parser.add_argument("--port", "-p", type=int, default=8000, help="HTTP 端口")
    args = parser.parse_args()

    server = MCPServer(args.workspace)

    if args.transport == "http":
        transport = HTTPTransport(server)
        app = transport.get_app()
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        transport = StdioTransport(server)
        transport.run()


if __name__ == "__main__":
    main()
