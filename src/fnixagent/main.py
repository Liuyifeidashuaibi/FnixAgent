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

    模式选择(通过环境变量 fnixagent_MODE):
      - "legacy"  (默认): 仅初始化传统 AgentScheduler
      - "evolve"         : 仅初始化自进化 GraphComponents
      - "both"           : 两者皆初始化(开发/对比场景)
    """
    settings = Settings()
    mode = os.getenv("fnixagent_MODE", "legacy").lower()
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
# 启动
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    cfg = load_yaml_config()
    server_cfg = cfg.get("server", {}) or {}
    port = server_cfg.get("port", 8000)
    host = server_cfg.get("host", "0.0.0.0")

    # CLI 参数校验
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
        reload=True,
        log_level="info",
    )
