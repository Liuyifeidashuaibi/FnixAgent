"""
FastAPI 主入口 - fnixagent 智能办公助手服务。

提供完整的 RESTful API 和流式对话接口。
"""

import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from fnixagent.core.profile import apply_profile_defaults, profile_info

# Standalone 默认 profile（GitHub 克隆零 Docker 起步）
apply_profile_defaults()

from fnixagent.api.routers import (
    admin,
    agentos,
    audit,
    auth,
    benchmark,
    chat,
    chat_agent,
    coding,
    dashboard,
    documents,
    harness,
    memory,
    privacy,
    rbac,
    skills,
    tasks,
    work,
)
from fnixagent.services import (
    build_graph,
    build_scheduler,
    reset_graph,
    reset_scheduler,
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """应用配置(从环境变量/.env 加载)。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "fnixagent"
    service_env: str = "development"
    debug: bool = Field(
        default=True,
        validation_alias=AliasChoices("SERVICE_DEBUG", "DEBUG", "debug"),
    )

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

    # LLM (OpenAI-compatible providers)
    glm_api_key: str = ""
    openai_api_key: str = ""
    qwen_api_key: str = ""
    deepseek_api_key: str = ""
    dashscope_api_key: str = ""
    custom_api_key: str = ""
    custom_base_url: str = ""
    embedding_api_key: str = ""

    # Optional LLM knobs commonly present in local .env
    llm_provider: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    model_timeout_seconds: int = 120

    # JWT
    jwt_secret_key: str = "fnixagent-dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24


def load_yaml_config() -> dict:
    """从 config/settings.yaml 加载配置(可选)。

    路径校验: 仅读取项目根目录下的 config/settings.yaml,
    不接受外部传入的路径, 避免路径遍历攻击。

    Returns:
        配置字典; 文件不存在或解析失败返回空 dict
    """
    # __file__ = .../src/fnixagent/main.py → 上溯 3 层到项目根
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config_path = os.path.join(project_root, "config", "settings.yaml")
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
    # 确保 .env 进入 os.environ，供 LLMAdapter / 业务工具读取 DASHSCOPE_API_KEY 等
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except Exception:
        pass
    # 自进化内核(KTG+STP+MFP)是产品护城河，默认与办公调度器一并启动
    # legacy=仅调度器; evolve=仅图; both=双模(默认，保证 Work 主路径可用进化)
    mode = os.getenv("FNIXAGENT_MODE", "both").lower()
    pinfo = profile_info()
    print(
        f"[main] 启动 {settings.service_name} "
        f"(env={settings.service_env}, mode={mode}, profile={pinfo['profile']})"
    )
    if os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY"):
        print("[main] LLM: DashScope/Qwen API Key 已加载")
    elif os.getenv("OPENAI_API_KEY") or os.getenv("GLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY"):
        print("[main] LLM: 已检测到 API Key")
    else:
        print("[main] WARNING: 未检测到 LLM API Key（DASHSCOPE/QWEN/OPENAI/GLM/DEEPSEEK）")

    # Production guardrails: refuse known-insecure defaults
    if settings.service_env.lower() in ("production", "prod"):
        weak_secrets = {
            "",
            "fnixagent-dev-secret",
            "fnixagent-dev-secret-change-me",
            "your_jwt_secret_key_here",
        }
        secret = os.getenv("JWT_SECRET_KEY", settings.jwt_secret_key)
        if secret in weak_secrets:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set to a strong secret when SERVICE_ENV=production"
            )
        if settings.debug:
            print("[main] WARNING: SERVICE_DEBUG=true in production — gateway auth is open")

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
        print(f"[main] 自进化图节点数: {components.topology_graph.stats().get('active_nodes', 0)}")

    # Work 流水线共享引擎（记忆 / 安全 / 推理选择）— README 能力矩阵必开
    try:
        from fnixagent.core.config import get_config
        from fnixagent.core.memory.manager import MemoryManager
        from fnixagent.core.reasoning.selector import ReasoningSelector
        from fnixagent.core.security.engine import SecurityEngine

        cfg = get_config()
        app.state.memory_manager = MemoryManager(config=cfg.memory)
        app.state.security_engine = SecurityEngine(config=cfg.security)
        app.state.reasoning_selector = ReasoningSelector(config=cfg.reasoning)
        print("[main] Work 流水线引擎已就绪: memory + security + reasoning")
    except Exception as e:
        print(f"[main] Work 流水线引擎初始化失败: {e}")

    try:
        from fnixagent.harness.gateway import init_harness

        init_harness()
        print("[main] Harness 本地门面已就绪 (~/.fnix)")
    except Exception as e:
        print(f"[main] Harness 初始化失败: {e}")

    print("[main] fnixagent 启动完成 → http://127.0.0.1:8003/docs (default local port)")
    print(f"[main] 部署形态: {pinfo['label']} · 存储: {pinfo['storage']}")

    # Standalone 测试版：跳过后台 LDAP / 账号清理调度（无企业 SSO 依赖）
    if pinfo["profile"] != "standalone":
        from fnixagent.core.security.auth.ldap_sync import start_ldap_sync_scheduler

        start_ldap_sync_scheduler()
        from fnixagent.services.account_cleanup import start_cleanup_scheduler

        start_cleanup_scheduler()
    else:
        print("[main] Standalone：已跳过 LDAP / 账号清理后台任务")

    try:
        from fnixagent.harness.work_jobs import start_work_job_worker_async

        await start_work_job_worker_async()
        print("[main] Work 后台任务 worker 已启动")
    except Exception as e:
        print(f"[main] Work 后台 worker 启动失败: {e}")

    yield

    # Shutdown
    print("[main] 正在关闭 fnixagent...")
    try:
        from fnixagent.harness.work_jobs import stop_work_job_worker_async

        await stop_work_job_worker_async()
    except Exception:
        pass
    if profile_info()["profile"] != "standalone":
        from fnixagent.core.security.auth.ldap_sync import stop_ldap_sync_scheduler

        stop_ldap_sync_scheduler()
        from fnixagent.services.account_cleanup import stop_cleanup_scheduler

        stop_cleanup_scheduler()
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


def _cors_allow_origins() -> list[str]:
    """Standalone/desktop: only local UI origins. Cloud may override via env."""
    raw = (os.getenv("FNIX_CORS_ORIGINS") or "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    # Local-first desktop / Vite workbench. Never use wildcard + credentials.
    return [
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost",
        "https://localhost",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
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
app.include_router(work.router, prefix="/api/v1")
app.include_router(harness.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(rbac.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(privacy.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(dashboard.stats_router, prefix="/api/v1")
app.include_router(agentos.router, prefix="/api/v1")
app.include_router(coding.router, prefix="/api/v1")
app.include_router(chat_agent.router, prefix="/api/v1")
app.include_router(benchmark.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(memory.router, prefix="/api/v1")


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
        "version": "1.1.0-beta",
        "status": "running",
        "docs": "/docs",
        "deploy": profile_info(),
    }


@app.get("/health")
async def health_check():
    """健康检查,返回服务状态与运行时长。"""
    # 注意：模块末尾会用 GatewayMiddleware 包裹 FastAPI，
    # 运行时 `app` / `request.app` 可能指向中间件，不能再读 `.state`。
    return {
        "status": "healthy",
        "service": "fnixagent",
        "version": "1.1.0-beta",
        **profile_info(),
    }


@app.get("/stats")
async def get_stats(request: Request):
    """获取 Agent 运行统计。"""
    inner = request.scope.get("app")
    # 若 ASGI scope 指向中间件，尝试取到内层 FastAPI
    state = getattr(inner, "state", None) or getattr(getattr(inner, "app", None), "state", None)
    scheduler = getattr(state, "scheduler", None) if state is not None else None
    if scheduler is not None:
        return scheduler.get_stats()
    return {"error": "scheduler not initialized"}


# ---------------------------------------------------------------------------
# ASGI 网关闸门(最外层,鉴权 → 配额 → 审计)— P0-01
# ---------------------------------------------------------------------------
# 必须在所有路由注册之后包裹,确保覆盖全部 HTTP / WebSocket / 挂载子应用。
# 开发模式(debug=True)或 standalone 开源形态下 auth_required=False;
# cloud 生产模式 auth_required=True,未鉴权请求 fail-closed。
# uvicorn 引用 fnixagent.main:app,此处置换为包裹后的 ASGI 应用。
from fnixagent.core.gateway.capability import CapabilityMiddleware
from fnixagent.core.gateway.middleware import GatewayMiddleware
from fnixagent.core.profile import is_standalone

_settings = Settings()
# Standalone / debug：本机开源模式无需 JWT（对标 Hermes 自托管）
app = GatewayMiddleware(
    app,
    auth_required=not (_settings.debug or is_standalone()),
)
# Desktop-managed runs set FNIX_CAPABILITY_TOKEN; reject anonymous localhost control.
app = CapabilityMiddleware(app)


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _run_serve(args) -> None:
    """启动 FastAPI 服务器 (fnixagent serve)。"""
    import uvicorn

    from fnixagent.core.profile import is_standalone

    cfg = load_yaml_config()
    server_cfg = cfg.get("server", {}) or {}
    port = args.port or server_cfg.get("port", 8003)
    # 安全默认:standalone(桌面)形态强制 127.0.0.1,避免本机服务对外暴露
    # 仅 cloud/local-stack 形态允许显式配置 0.0.0.0 或其它外部地址
    default_host = "127.0.0.1" if is_standalone() else "0.0.0.0"
    host = args.host or server_cfg.get("host", default_host)

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
        from fnixagent.core.agent.shell import create_shell

        print("FnixAgent Chat — 交互式 AI 编程助手")
        print(f"工作区: {args.workspace or os.getcwd()}")
        print("输入消息开始对话，输入 /exit 退出，/help 查看帮助\n")

        # 创建 Shell
        loop = asyncio.get_running_loop()
        shell = create_shell(in_memory=True, boot=True, _loop=loop)
        await shell.kernel.boot()  # 在已有事件循环中手动启动
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
        loop = asyncio.get_running_loop()
        shell = create_shell(in_memory=True, boot=True, _loop=loop)
        await shell.kernel.boot()  # 在已有事件循环中手动启动
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
    from fnixagent.core.mcp.server import HTTPTransport, MCPServer, StdioTransport

    workspace = args.workspace or os.getcwd()
    server = MCPServer(workspace)

    if args.transport == "http":
        transport = HTTPTransport(server)
        app = transport.get_app()
        import uvicorn

        uvicorn.run(app, host=args.host or "0.0.0.0", port=args.port or 8003)
    else:
        transport = StdioTransport(server)
        transport.run()


def _build_agent_loop(shell, workspace_root: str, max_steps: int = 30):
    """构建 AgenticLoop 实例。

    连接 shell/kernel 的 LLM 后端和工具注册表。
    优先使用 LLMAdapter (API Key 接入)，回退到 kernel 的 mock 后端。
    """
    from fnixagent.core.agent.loop import AgenticLoop
    from fnixagent.core.llm.adapter import LLMAdapter
    from fnixagent.core.tools.registry import ToolRegistry
    from fnixagent.core.tools.workspace import register_workspace_tools

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
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "[LLM 未配置] 请在 .env 中设置 API Key:\n"
                            "  OPENAI_API_KEY=sk-xxx\n"
                            "  GLM_API_KEY=xxx\n"
                            "  DEEPSEEK_API_KEY=xxx\n"
                            "  CUSTOM_API_KEY=xxx",
                        }
                    }
                ]
            }

    return AgenticLoop(
        llm_call=llm_call,
        tool_executor=registry,
        workspace_root=workspace_root,
        max_steps=max_steps,
    )


def _run_local(args) -> None:
    """启动 fnix-local sidecar (fnixagent local)。"""
    if args.host:
        os.environ["FNIX_LOCAL_HOST"] = args.host
    if args.port:
        os.environ["FNIX_LOCAL_PORT"] = str(args.port)
    from fnixagent.local.sidecar_app import main

    main()


def main():
    """FnixAgent CLI 主入口（对标 Hermes CLI）。

    子命令:
      fnixagent setup / doctor / dashboard / model
      fnixagent serve / chat / run / mcp / local
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Fnix Harness — 本地优先 AI 工作台（无账号 · BYOK · Work/Code）",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ---- setup / doctor / dashboard / model（Hermes 对标）----
    setup_parser = subparsers.add_parser("setup", help="交互配置 API Key / 模型")
    setup_parser.add_argument("--non-interactive", action="store_true")
    setup_parser.add_argument("--provider", default=None)
    setup_parser.add_argument("--model", default=None)
    setup_parser.add_argument("--api-key", default=None)
    setup_parser.add_argument("--base-url", default=None)

    subparsers.add_parser("doctor", help="环境诊断")

    dash_parser = subparsers.add_parser("dashboard", help="本机 Web 管理台 (:9119)")
    dash_parser.add_argument("--host", default="127.0.0.1")
    dash_parser.add_argument("--port", "-p", type=int, default=9119)
    dash_parser.add_argument("--no-open", action="store_true")

    model_parser = subparsers.add_parser("model", help="查看/切换默认模型")
    model_parser.add_argument("--provider", default=None)
    model_parser.add_argument("--model", default=None)
    model_parser.add_argument("--base-url", default=None)

    # ---- serve ----
    serve_parser = subparsers.add_parser("serve", help="启动 FastAPI 服务器")
    serve_parser.add_argument("--host", default=None, help="绑定地址 (默认 0.0.0.0)")
    serve_parser.add_argument("--port", "-p", type=int, default=None, help="端口 (默认 8003)")
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
    mcp_parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "http"],
        default="stdio",
        help="传输方式 (默认 stdio)",
    )
    mcp_parser.add_argument("--host", default=None, help="HTTP 绑定地址")
    mcp_parser.add_argument("--port", "-p", type=int, default=None, help="HTTP 端口")

    # ---- local (fnix-local sidecar) ----
    local_parser = subparsers.add_parser("local", help="启动 fnix-local sidecar")
    local_parser.add_argument("--host", default=None, help="绑定地址 (默认 127.0.0.1)")
    local_parser.add_argument("--port", "-p", type=int, default=None, help="端口 (默认 8710)")

    args = parser.parse_args()

    if args.command == "setup":
        from fnixagent.cli.setup import run_setup

        raise SystemExit(
            run_setup(
                non_interactive=args.non_interactive,
                provider=args.provider,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
            )
        )
    if args.command == "doctor":
        from fnixagent.cli.doctor import run_doctor

        raise SystemExit(run_doctor())
    if args.command == "dashboard":
        from fnixagent.cli.dashboard import run_dashboard

        run_dashboard(host=args.host, port=args.port, open_browser=not args.no_open)
        return
    if args.command == "model":
        from fnixagent.cli.model_cmd import run_model

        raise SystemExit(
            run_model(provider=args.provider, model=args.model, base_url=args.base_url)
        )
    if args.command == "serve":
        _run_serve(args)
    elif args.command == "chat":
        _run_chat(args)
    elif args.command == "run":
        _run_execute(args)
    elif args.command == "mcp":
        _run_mcp(args)
    elif args.command == "local":
        _run_local(args)
    else:
        parser.print_help()
        print("\n快速开始（对标 Hermes）:")
        print("  fnixagent setup")
        print("  fnixagent doctor")
        print("  fnixagent dashboard")
        print("  fnixagent chat")
        print("\n未指定子命令，默认启动 serve…")
        _run_serve(argparse.Namespace(host=None, port=None, no_reload=False, log_level=None))


if __name__ == "__main__":
    main()
