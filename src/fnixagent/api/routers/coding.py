"""API 路由 - 编码智能体接口 (IDEServer HTTP 包装)。

将 IDEServer 的 10 个 CLI 命令 + 7 个 MCP 工具包装为 HTTP 接口。

CLI 包装 (POST, body 传参):
    index / search / read / write / edit / git / test / task
    map / help (GET)

MCP 工具 (统一端点):
    GET  /coding/mcp/tools  - 列出 MCP 工具 schema
    POST /coding/mcp/call   - 调用 MCP 工具

鉴权: 复用 verify_jwt_token (当前用户 JWT 校验)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import contextlib
import io
import os
import threading
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from fnixagent.api.routers.auth import verify_jwt_token
from fnixagent.core.code.server import IDEServer
from fnixagent.harness.paths import default_workspace

router = APIRouter(prefix="/coding", tags=["coding"])


# ===========================================================================
# IDEServer 单例管理
# TODO: 此处 get_server 与 chat_agent.py 中的实现重复，两模块各自维护独立
# 全局变量。若后续需共享同一单例，可从 chat_agent 导入 get_server（签名兼容），
# 但需注意两模块鉴权依赖不同（verify_jwt_token vs verify_jwt_token_optional）。
# ===========================================================================

_server: IDEServer | None = None
_server_workspace: str | None = None
_server_lock = threading.Lock()


def get_server(workspace: str | None = None) -> IDEServer:
    """懒加载 IDEServer 单例。

    首次调用, 或请求的 workspace 与当前实例不一致时创建新实例;
    其余调用直接复用单例。

    Args:
        workspace: 工作区路径, 缺省取默认工作区(~/.fnix/workspaces/default)。

    Returns:
        IDEServer 实例。
    """
    global _server, _server_workspace
    ws = workspace or str(default_workspace())
    with _server_lock:
        if _server is None or _server_workspace != ws:
            _server = IDEServer(project_root=ws)
            _server_workspace = ws
    return _server


# ===========================================================================
# 统一响应模型
# ===========================================================================


class CodingResponse(BaseModel):
    """编码接口统一响应。

    Attributes:
        success: 是否成功。
        result: 结果数据 (CLI 包装下为 stdout 文本, MCP 下为工具返回值)。
        error: 错误信息 (成功时为 None)。
    """

    success: bool
    result: Any = None
    error: str | None = None


# ===========================================================================
# 请求模型
# ===========================================================================


class IndexRequest(BaseModel):
    workspace: str | None = None
    path: str | None = None
    no_incremental: bool = False


class SearchRequest(BaseModel):
    workspace: str | None = None
    query: str
    top_k: int = 10


class ReadRequest(BaseModel):
    workspace: str | None = None
    file: str
    start: int = 0
    end: int = 0


class WriteRequest(BaseModel):
    workspace: str | None = None
    file: str
    content: str


class EditRequest(BaseModel):
    workspace: str | None = None
    file: str
    old: str
    new: str


class GitRequest(BaseModel):
    workspace: str | None = None
    args: list[str] = Field(default_factory=list)


class TestRequest(BaseModel):
    workspace: str | None = None
    args: list[str] = Field(default_factory=list)


class TaskRequest(BaseModel):
    workspace: str | None = None
    description: str
    files: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class McpCallRequest(BaseModel):
    workspace: str | None = None
    tool: str
    arguments: dict = Field(default_factory=dict)


# ===========================================================================
# CLI 包装辅助
# ===========================================================================


async def _run_cli(server: IDEServer, argv: list[str]) -> tuple[int, str]:
    """执行 CLI 命令并捕获 stdout 输出。

    IDEServer.run_cli 通过 print 输出结果并返回退出码;
    本辅助函数用 redirect_stdout 捕获输出文本。

    Args:
        server: IDEServer 实例。
        argv: 命令行参数 (不含程序名)。

    Returns:
        (exit_code, captured_output)。
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exit_code = await server.run_cli(argv)
    return exit_code, buf.getvalue()


def _ok(output: Any) -> CodingResponse:
    """构造成功响应。"""
    return CodingResponse(success=True, result=output, error=None)


def _fail(output: Any, exit_code: int) -> CodingResponse:
    """构造失败响应 (CLI 退出码非 0)。"""
    return CodingResponse(success=False, result=output, error=f"CLI 退出码 {exit_code}")


# ===========================================================================
# CLI 命令路由 (10 个)
# ===========================================================================


@router.post("/index", response_model=CodingResponse)
async def coding_index(
    req: IndexRequest,
    _: dict = Depends(verify_jwt_token),
):
    """索引项目代码。"""
    server = get_server(req.workspace)
    argv: list[str] = ["index"]
    if req.path:
        argv.append(req.path)
    if req.no_incremental:
        argv.append("--no-incremental")
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/search", response_model=CodingResponse)
async def coding_search(
    req: SearchRequest,
    _: dict = Depends(verify_jwt_token),
):
    """语义搜索代码。"""
    server = get_server(req.workspace)
    argv = ["search", req.query, "--top_k", str(req.top_k)]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/read", response_model=CodingResponse)
async def coding_read(
    req: ReadRequest,
    _: dict = Depends(verify_jwt_token),
):
    """读取文件 (支持行范围)。"""
    server = get_server(req.workspace)
    argv = ["read", req.file, "--start", str(req.start), "--end", str(req.end)]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/write", response_model=CodingResponse)
async def coding_write(
    req: WriteRequest,
    _: dict = Depends(verify_jwt_token),
):
    """写入文件 (创建或覆盖)。"""
    server = get_server(req.workspace)
    argv = ["write", req.file, "--content", req.content]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/edit", response_model=CodingResponse)
async def coding_edit(
    req: EditRequest,
    _: dict = Depends(verify_jwt_token),
):
    """精确替换文件内容 (old 须唯一匹配)。"""
    server = get_server(req.workspace)
    argv = ["edit", req.file, "--old", req.old, "--new", req.new]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/git", response_model=CodingResponse)
async def coding_git(
    req: GitRequest,
    _: dict = Depends(verify_jwt_token),
):
    """执行 Git 命令 (沙箱白名单)。"""
    server = get_server(req.workspace)
    argv = ["git"] + list(req.args)
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/test", response_model=CodingResponse)
async def coding_test(
    req: TestRequest,
    _: dict = Depends(verify_jwt_token),
):
    """运行测试 (pytest)。"""
    server = get_server(req.workspace)
    argv = ["test"] + list(req.args)
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.post("/task", response_model=CodingResponse)
async def coding_task(
    req: TaskRequest,
    _: dict = Depends(verify_jwt_token),
):
    """执行编码任务 (Plan → Execute → Review)。

    注意: CLI task 命令仅消费 description; files / constraints 字段
    供 MCP coding.task 工具使用, 在 CLI 包装下忽略。
    """
    server = get_server(req.workspace)
    argv = ["task", req.description]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.get("/map", response_model=CodingResponse)
async def coding_map(
    max_tokens: int = Query(4096, ge=1, description="仓库地图 token 上限"),
    workspace: str | None = Query(None, description="工作区路径"),
    _: dict = Depends(verify_jwt_token),
):
    """输出仓库地图 (RepoMap)。"""
    server = get_server(workspace)
    argv = ["map", "--max-tokens", str(max_tokens)]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


@router.get("/help", response_model=CodingResponse)
async def coding_help(
    workspace: str | None = Query(None, description="工作区路径"),
    _: dict = Depends(verify_jwt_token),
):
    """显示 CLI 帮助。"""
    server = get_server(workspace)
    argv = ["help"]
    code, out = await _run_cli(server, argv)
    return _ok(out) if code == 0 else _fail(out, code)


# ===========================================================================
# MCP 工具路由 (7 个工具, 统一端点)
# ===========================================================================


@router.get("/mcp/tools", response_model=CodingResponse)
async def mcp_tools(
    workspace: str | None = Query(None, description="工作区路径"),
    _: dict = Depends(verify_jwt_token),
):
    """列出 MCP 工具 schema (tools/list)。

    返回 7 个工具: code.read / code.write / code.edit / code.search /
    code.git / code.test / coding.task。
    """
    server = get_server(workspace)
    tools = server.mcp_list_tools()
    return _ok(tools)


@router.post("/mcp/call", response_model=CodingResponse)
async def mcp_call(
    req: McpCallRequest,
    _: dict = Depends(verify_jwt_token),
):
    """调用 MCP 工具 (tools/call)。

    body:
        tool: 工具名 (如 "code.read")。
        arguments: 工具参数 (如 {"file_path": "src/main.py"})。
    """
    server = get_server(req.workspace)
    result = await server.mcp_call(req.tool, req.arguments)
    # mcp_call 已返回 {success, result, error} 统一格式, 直接透传
    return CodingResponse(
        success=bool(result.get("success", False)),
        result=result.get("result"),
        error=result.get("error"),
    )
