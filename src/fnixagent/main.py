"""
FastAPI 主入口 - fnixagent 智能办公助手服务。

提供完整的 RESTful API 和流式对话接口。
"""
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings

from fnixagent.api.routers import admin, agentos, audit, auth, chat, chat_agent, coding, dashboard, documents, privacy, rbac, tasks, tools
from fnixagent.services import (
    build_graph,
    build_scheduler,
    get_scheduler,
    reset_graph,
    reset_scheduler,
)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """应用配置(从环境变量/.env 加载)。"""

    service_name: str = "fnixagent"
    service_env: str = "development"
    debug: bool = True

    # 数据库
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "fnixagent"
    postgres_user: str = "fnixagent"
    postgres_password: str = ""

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    # LLM
    glm_api_key: str = ""
    openai_api_key: str = ""
    qwen_api_key: str = ""

    # JWT
    jwt_secret_key: str = "fnixagent-dev-secret"
    jwt_algorithm: str = "HS256"

    class Settings:
        env_file = ".env"
        env_file_encoding = "utf-8"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def load_yaml_config() -> dict:
    """从 config/settings.yaml 加载配置(可选)。

    路径校验: 仅读取项目根目录下的 config/settings.yaml,
    不接受外部传入的路径, 避免路径遍历攻击。

    Returns:
        配置字典; 文件不存在或解析失败返回空 dict
    """
    # 固定路径计算(基于 __file__), 不接受外部输入, 防路径遍历
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "config",
        "settings.yaml",
    )
    if os.path.exists(config_path) and os.path.isfile(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as e:
            print(f"[main] 配置文件加载失败: {e}")
            return {}
    return {}


# ---------------------------------------------------------------------------
# 应用生命周期
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时构建调度器,关闭时清理。

    模式选择(通过环境变量 FNIXAGENT_MODE):
      - "legacy"  (默认): 仅初始化传统 AgentScheduler
      - "evolve"         : 仅初始化自进化 GraphComponents
      - "both"           : 两者皆初始化(开发/对比场景)
    """
    settings = Settings()
    mode = os.getenv("FNIXAGENT_MODE", "legacy").lower()
    print(f"[main] 启动 {settings.service_name} (env={settings.service_env}, mode={mode})")

    app.state.settings = settings
    app.state.start_time = datetime.utcnow()
    app.state.mode = mode

    # 传统模式: 构建 AgentScheduler
    if mode in ("legacy", "both"):
        scheduler = build_scheduler()
        app.state.scheduler = scheduler
        print(f"[main] 工具数: {scheduler.get_stats()['tools']['count']}")

    # 自进化模式: 构建 GraphComponents(KTG + STP + MFP + LangGraph)
    if mode in ("evolve", "both"):
        components = build_graph()
        app.state.graph_components = components
        print(f"[main] 自进化图节点数: {components.topology_graph.stats().get('node_count', 0)}")

    print("[main] fnixagent 启动完成 → http://0.0.0.0:8000/docs")

    yield

    # Shutdown
    print("[main] 正在关闭 fnixagent...")
    reset_scheduler()
    reset_graph()
    print("[main] 已关闭")


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------


app = FastAPI(
    title="fnixagent",
    description="智能办公助手 API - 论文检索/文档编辑/PDF生成/图表制作",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 2.10: Prometheus 指标(受 PROMETHEUS_ENABLED 环境变量控制,默认 true)
from fnixagent.core.observability import setup_metrics

setup_metrics(app)

# 注册路由
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(rbac.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(privacy.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(dashboard.stats_router, prefix="/api/v1")
app.include_router(agentos.router, prefix="/api/v1")
app.include_router(coding.router, prefix="/api/v1")
app.include_router(chat_agent.router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Phase 2.2: LDAP 定时同步调度器
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _start_ldap_sync_scheduler():
    """应用启动时启动 LDAP 同步调度器(后台守护线程)。"""
    from fnixagent.core.security.auth.ldap_sync import start_ldap_sync_scheduler
    start_ldap_sync_scheduler()


@app.on_event("shutdown")
async def _stop_ldap_sync_scheduler():
    """应用关闭时停止 LDAP 同步调度器。"""
    from fnixagent.core.security.auth.ldap_sync import stop_ldap_sync_scheduler
    stop_ldap_sync_scheduler()


# ---------------------------------------------------------------------------
# Phase 3.2: 账号注销清理调度器(每 6 小时硬删除已过保留期的账号)
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def _start_account_cleanup_scheduler():
    """应用启动时启动账号清理调度器。"""
    from fnixagent.services.account_cleanup import start_cleanup_scheduler
    start_cleanup_scheduler()


@app.on_event("shutdown")
async def _stop_account_cleanup_scheduler():
    """应用关闭时停止账号清理调度器。"""
    from fnixagent.services.account_cleanup import stop_cleanup_scheduler
    stop_cleanup_scheduler()


# ---------------------------------------------------------------------------
# 异常处理
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理。"""
    trace_id = str(uuid.uuid4())[:16]
    print(f"[error] trace_id={trace_id} {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": type(exc).__name__,
            "detail": str(exc),
            "trace_id": trace_id,
        },
    )


# ---------------------------------------------------------------------------
# 基础路由
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    """根路由,返回服务基本信息与文档地址。"""
    return {
        "name": "fnixagent",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """健康检查,返回服务状态与运行时长。"""
    return {
        "status": "healthy",
        "service": "fnixagent",
        "uptime": str(datetime.utcnow() - app.state.start_time) if hasattr(app.state, "start_time") else "unknown",
    }


@app.get("/stats")
async def get_stats():
    """获取 Agent 运行统计。"""
    if hasattr(app.state, "scheduler"):
        return app.state.scheduler.get_stats()
    return {"error": "scheduler not initialized"}


# ---------------------------------------------------------------------------
# ASGI 网关闸门(最外层,鉴权 → 配额 → 审计)— P0-01
# ---------------------------------------------------------------------------
# 必须在所有路由注册之后包裹,确保覆盖全部 HTTP / WebSocket / 挂载子应用。
# 开发模式(debug=True)下 auth_required=False,无 Token 时匿名放行;
# 生产模式(debug=False)下 auth_required=True,未鉴权请求 fail-closed。
# uvicorn 引用 fnixagent.main:app,此处置换为包裹后的 ASGI 应用。
from fnixagent.core.gateway.middleware import GatewayMiddleware

_settings = Settings()
app = GatewayMiddleware(app, auth_required=not _settings.debug)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _run_serve(args) -> None:
    """启动 FastAPI 服务器 (fnixagent serve)。"""
    import uvicorn

    cfg = load_yaml_config()
    server_cfg = cfg.get("server", {}) or {}
    port = args.port or server_cfg.get("port", 8000)
    host = args.host or server_cfg.get("host", "0.0.0.0")

    if not isinstance(host, str) or not host:
        raise ValueError(f"server.host 必须为非空字符串, 收到 {host!r}")
    if not isinstance(port, int) or isinstance(port, bool):
        raise ValueError(f"server.port 必须为 int, 收到 {port!r}")
    if not (1 <= port <= 65535):
        raise ValueError(f"server.port 越界(1-65535), 收到 {port}")

    uvicorn.run(
        "fnixagent.main:app",
        host=host,
        port=port,
        reload=not args.no_reload,
        log_level=args.log_level or "info",
    )


def _run_chat(args) -> None:
    """启动交互式 REPL 对话 (fnixagent chat)。"""
    import asyncio

    async def _chat():
        from fnixagent.core.agent.shell import AgentShell, create_shell
        from fnixagent.core.agent.loop import AgenticLoop

        print("FnixAgent Chat — 交互式 AI 编程助手")
        print(f"工作区: {args.workspace or os.getcwd()}")
        print("输入消息开始对话，输入 /exit 退出，/help 查看帮助\n")

        # 创建 Shell
        shell = create_shell(in_memory=True, boot=True)
        workspace_root = args.workspace or os.getcwd()

        # 创建 AgenticLoop
        agent = _build_agent_loop(shell, workspace_root, max_steps=args.max_steps)

        while True:
            try:
                user_input = await asyncio.to_thread(input, ">>> ")
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input in ("/exit", "/quit"):
                print("再见！")
                break
            if user_input == "/help":
                print("命令:")
                print("  /exit, /quit  退出")
                print("  /help         帮助")
                print("  /reset        重置对话")
                print("  /stats        查看统计")
                print("  /workspace    查看工作区")
                continue
            if user_input == "/reset":
                agent.reset()
                print("对话已重置")
                continue
            if user_input == "/stats":
                print(f"步骤数: {len(agent.traces)}")
                continue
            if user_input == "/workspace":
                print(f"工作区: {agent.workspace_root}")
                continue

            print()
            result = await agent.run(user_input)
            if result.success:
                print(f"\n{result.response}\n")
            else:
                print(f"\n错误: {result.error}\n")

    asyncio.run(_chat())


def _run_execute(args) -> None:
    """单次执行 (fnixagent run)。"""
    import asyncio

    async def _execute():
        from fnixagent.core.agent.shell import create_shell

        workspace_root = args.workspace or os.getcwd()
        shell = create_shell(in_memory=True, boot=True)
        agent = _build_agent_loop(shell, workspace_root, max_steps=args.max_steps)

        print(f"执行中: {args.prompt}")
        result = await agent.run(args.prompt)
        if result.success:
            print(result.response)
        else:
            print(f"错误: {result.error}", file=sys.stderr)

    asyncio.run(_execute())


def _run_mcp(args) -> None:
    """启动 MCP Server (fnixagent mcp)。"""
    from fnixagent.core.mcp.server import MCPServer, StdioTransport, HTTPTransport

    workspace = args.workspace or os.getcwd()
    server = MCPServer(workspace)

    if args.transport == "http":
        transport = HTTPTransport(server)
        app = transport.get_app()
        import uvicorn
        uvicorn.run(app, host=args.host or "0.0.0.0", port=args.port or 8000)
    else:
        transport = StdioTransport(server)
        transport.run()


def _build_agent_loop(shell, workspace_root: str, max_steps: int = 30):
    """构建 AgenticLoop 实例。

    连接 shell/kernel 的 LLM 后端和工具注册表。
    优先使用 LLMAdapter (API Key 接入)，回退到 kernel 的 mock 后端。
    """
    from fnixagent.core.agent.loop import AgenticLoop
    from fnixagent.core.tools.workspace import register_workspace_tools
    from fnixagent.core.tools.registry import ToolRegistry
    from fnixagent.core.llm.adapter import LLMAdapter

    # 创建工具注册表并注册 workspace 工具
    registry = ToolRegistry()
    register_workspace_tools(registry, workspace_root)

    # 尝试使用 LLMAdapter (API Key 接入)
    adapter = LLMAdapter()
    if adapter.is_configured:
        print(f"[main] LLM 后端: {adapter.provider_name} (API Key)")
        llm_call = adapter.chat
    else:
        # 回退到 kernel 的 mock 后端
        print("[main] LLM 后端: Mock (未配置 API Key，返回模拟响应)")
        async def llm_call(messages, tools=None):
            kernel = shell.kernel
            if kernel._llm_backend:
                try:
                    return await kernel._llm_backend.chat(messages, tools=tools)
                except Exception:
                    pass
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "[LLM 未配置] 请在 .env 中设置 API Key:\n"
                                   "  OPENAI_API_KEY=sk-xxx\n"
                                   "  GLM_API_KEY=xxx\n"
                                   "  DEEPSEEK_API_KEY=xxx\n"
                                   "  CUSTOM_API_KEY=xxx",
                    }
                }]
            }

    return AgenticLoop(
        llm_call=llm_call,
        tool_executor=registry,
        workspace_root=workspace_root,
        max_steps=max_steps,
    )


def main():
    """FnixAgent CLI 主入口。

    子命令:
      fnixagent serve   启动 FastAPI 服务器
      fnixagent chat    启动交互式 REPL 对话
      fnixagent run     单次执行任务
      fnixagent mcp     启动 MCP Server (stdio/http)
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="FnixAgent — 智能 AI 编程助手 & 自进化 Agent 框架",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ---- serve ----
    serve_parser = subparsers.add_parser("serve", help="启动 FastAPI 服务器")
    serve_parser.add_argument("--host", default=None, help="绑定地址 (默认 0.0.0.0)")
    serve_parser.add_argument("--port", "-p", type=int, default=None, help="端口 (默认 8000)")
    serve_parser.add_argument("--no-reload", action="store_true", help="禁用热重载")
    serve_parser.add_argument("--log-level", default=None, help="日志级别")

    # ---- chat ----
    chat_parser = subparsers.add_parser("chat", help="交互式 REPL 对话")
    chat_parser.add_argument("--workspace", "-w", default=None, help="工作区路径")
    chat_parser.add_argument("--max-steps", type=int, default=30, help="最大执行步数")

    # ---- run ----
    run_parser = subparsers.add_parser("run", help="单次执行任务")
    run_parser.add_argument("prompt", help="任务描述")
    run_parser.add_argument("--workspace", "-w", default=None, help="工作区路径")
    run_parser.add_argument("--max-steps", type=int, default=30, help="最大执行步数")

    # ---- mcp ----
    mcp_parser = subparsers.add_parser("mcp", help="启动 MCP Server")
    mcp_parser.add_argument("--workspace", "-w", default=None, help="工作区路径")
    mcp_parser.add_argument("--transport", "-t", choices=["stdio", "http"], default="stdio",
                            help="传输方式 (默认 stdio)")
    mcp_parser.add_argument("--host", default=None, help="HTTP 绑定地址")
    mcp_parser.add_argument("--port", "-p", type=int, default=None, help="HTTP 端口")

    args = parser.parse_args()

    if args.command == "serve":
        _run_serve(args)
    elif args.command == "chat":
        _run_chat(args)
    elif args.command == "run":
        _run_execute(args)
    elif args.command == "mcp":
        _run_mcp(args)
    else:
        # 默认: 启动服务器 (向后兼容)
        parser.print_help()
        print("\n未指定子命令，默认启动 serve 模式...")
        _run_serve(argparse.Namespace(host=None, port=None, no_reload=False, log_level=None))


if __name__ == "__main__":
    main()
