"""ASGI 三道闸门中间件(鉴权 → 配额 → 审计)- P0-01。

设计目标:
    在 ASGI 层(而非 FastAPI Depends)对 **所有** 请求(HTTP + WebSocket +
    挂载子应用)统一执行三道闸门,弥补 Depends 无法覆盖 WebSocket / 子应用的缺陷。

三道闸门(顺序执行,任一失败即 fail-closed):
    Gate 1 鉴权(Auth):  Bearer Token / ?token= 校验 → 写入 scope["state"]["principal"]
    Gate 2 配额(Quota): 全局并发 + 每 Principal 并发 + 每 Principal QPS(滑动窗口)
    Gate 3 审计(Audit): 包装 send() 捕获响应状态码,finally 块记录访问日志

设计要点:
    - 纯 ASGI 中间件(任何 ASGI 框架可用,不绑定 FastAPI)
    - fail-closed:未鉴权请求在进入任何 handler 前即被拒绝
    - WebSocket 支持:连接时鉴权 + 配额,断开时审计
    - PUBLIC_PATHS 白名单:健康检查等端点跳过鉴权但仍审计
    - 配额基于 asyncio.Semaphore,acquire/release 严格配对(try/finally)

用法:
    from fnixagent.core.gateway.middleware import GatewayMiddleware
    app = GatewayMiddleware(app, auth_required=not settings.debug)
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qs

from loguru import logger

# ---------------------------------------------------------------------------
# 公共路径(跳过鉴权,但仍计入审计)
# ---------------------------------------------------------------------------

PUBLIC_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/stats",
    "/docs",
    "/redoc",
    "/openapi.json",
})


# ---------------------------------------------------------------------------
# Principal(鉴权通过后写入 scope["state"]["principal"])
# ---------------------------------------------------------------------------


@dataclass
class Principal:
    """鉴权主体。

    Attributes:
        sub:   用户标识(user_id 的字符串形式)
        scope: 权限范围列表(角色 / 自定义 scope)
        via:   鉴权来源 — "token"(JWT 校验通过) / "dev"(开发模式匿名)
               / "public"(公共路径)
    """

    sub: str
    scope: list[str] = field(default_factory=list)
    via: str = "public"

    @property
    def is_anonymous(self) -> bool:
        """是否匿名(非 token 鉴权)。"""
        return self.via != "token"


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------


@dataclass
class AuditEntry:
    """单次请求审计记录。"""

    principal: str
    path: str
    method: str
    status: int
    latency_ms: float
    via: str
    timestamp: str = ""


class AuditLogger:
    """网关审计日志器(基于 loguru)。

    在 finally 块中调用 log(),确保异常场景也能记录访问日志。
    """

    def __init__(self) -> None:
        self._logger = logger.bind(component="gateway.audit")

    def log(self, entry: AuditEntry) -> None:
        """记录一条审计日志(失败不影响主流程)。"""
        try:
            self._logger.info(
                "{via} {method} {path} -> {status} ({latency:.1f}ms) principal={principal}",
                via=entry.via,
                method=entry.method,
                path=entry.path,
                status=entry.status,
                latency=entry.latency_ms,
                principal=entry.principal,
            )
        except Exception:
            # 审计失败不应影响请求处理
            pass


# ---------------------------------------------------------------------------
# 配额管理器
# ---------------------------------------------------------------------------


class QuotaManager:
    """协程安全(单事件循环内)的配额管理器。

    三层限制:
        1. 全局并发(max_global_concurrent,默认 100)— 过载保护
        2. 每 Principal 并发(max_principal_concurrent,默认 10)
        3. 每 Principal QPS(max_principal_qps,默认 20 req/s,滑动窗口)

    并发控制基于 asyncio.Semaphore;QPS 基于 deque 滑动窗口(单事件循环,
    帧内无 await,无需加锁)。acquire/release 必须严格配对(中间件用 try/finally 保证)。
    """

    def __init__(
        self,
        max_global_concurrent: int = 100,
        max_principal_concurrent: int = 10,
        max_principal_qps: int = 20,
    ) -> None:
        self._global_sem = asyncio.Semaphore(max_global_concurrent)
        self._max_principal_concurrent = max_principal_concurrent
        self._max_principal_qps = max_principal_qps

        # 每 Principal 的并发信号量(惰性创建)
        self._principal_sems: dict[str, asyncio.Semaphore] = {}
        # 每 Principal 的 QPS 滑动窗口(时间戳队列)
        self._qps_windows: dict[str, deque[float]] = defaultdict(deque)
        # 保护字典惰性创建的锁
        self._lock = asyncio.Lock()

    async def _get_principal_sem(self, sub: str) -> asyncio.Semaphore:
        """获取(或惰性创建)指定 Principal 的并发信号量。

        先无锁读命中时直接返回,避免锁开销;未命中时加锁二次检查后创建
        (double-checked locking)。
        """
        sem = self._principal_sems.get(sub)
        if sem is not None:
            return sem
        async with self._lock:
            sem = self._principal_sems.get(sub)
            if sem is None:
                sem = asyncio.Semaphore(self._max_principal_concurrent)
                self._principal_sems[sub] = sem
            return sem

    def _check_qps(self, sub: str) -> bool:
        """滑动窗口 QPS 检查。

        单事件循环内调用,peek 与 append 之间无 await,无需加锁。
        被拒绝的请求也占用一个 QPS 槽位(防止重试风暴)。
        """
        now = time.monotonic()
        window = self._qps_windows[sub]
        # 清理 1 秒前的记录
        while window and now - window[0] >= 1.0:
            window.popleft()
        if len(window) >= self._max_principal_qps:
            return False
        window.append(now)
        return True

    @staticmethod
    def _sem_has_slot(sem: asyncio.Semaphore) -> bool:
        """非阻塞探查 asyncio.Semaphore 是否仍有槽位。

        asyncio.Semaphore 内部用 _value 记录剩余槽位(CPython 3.10+ 稳定)。
        peek 与后续 await acquire() 之间无 await,单事件循环下不会被打断,
        因此 await acquire() 必然立即成功,不存在 TOCTOU 竞态。
        """
        return getattr(sem, "_value", 0) > 0

    async def acquire(self, principal: Principal) -> tuple[bool, str]:
        """尝试获取配额(非阻塞,失败立即返回)。

        Returns:
            (ok, reason) — ok=False 时 reason 为 "qps" / "global" / "concurrent";
            ok=True 时 reason 为空串。ok=False 时 **不会** 持有任何信号量,无需 release。
        """
        # 1. QPS 检查(不消耗信号量,失败直接返回;通过则占用一个时间槽)
        if not self._check_qps(principal.sub):
            return False, "qps"

        # 2. 全局并发(非阻塞探查 → acquire)
        if not self._sem_has_slot(self._global_sem):
            return False, "global"
        await self._global_sem.acquire()

        # 3. 每 Principal 并发(非阻塞探查 → acquire;失败回滚全局)
        sem = await self._get_principal_sem(principal.sub)
        if not self._sem_has_slot(sem):
            self._global_sem.release()
            return False, "concurrent"
        await sem.acquire()
        return True, ""

    async def release(self, principal: Principal) -> None:
        """释放配额(与 acquire ok=True 严格配对)。

        QPS 槽位为时间窗自动过期,无需显式释放;仅释放并发信号量。
        """
        sem = self._principal_sems.get(principal.sub)
        if sem is not None:
            try:
                sem.release()
            except ValueError:
                # 信号量已平衡(防御性:理论上不应发生)
                pass
        try:
            self._global_sem.release()
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_quota_manager: Optional[QuotaManager] = None
_audit_logger: Optional[AuditLogger] = None


def get_quota_manager() -> QuotaManager:
    """获取配额管理器单例(惰性初始化)。"""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager


def get_audit_logger() -> AuditLogger:
    """获取审计日志器单例(惰性初始化)。"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# ---------------------------------------------------------------------------
# ASGI 三道闸门中间件
# ---------------------------------------------------------------------------


class GatewayMiddleware:
    """ASGI 三道闸门中间件(鉴权 → 配额 → 审计)。

    作为最外层包裹整个 ASGI 应用,确保所有请求(HTTP / WebSocket / 挂载子应用)
    都经过统一的三道闸门。

    Args:
        app:            被包裹的 ASGI 应用
        auth_required:  是否强制鉴权(True=生产模式,无 Token 拒绝;
                        False=开发模式,无 Token 匿名放行)
    """

    # WebSocket 鉴权 / 配额失败关闭码(应用层自定义,4xxx)
    WS_CLOSE_AUTH_FAIL: int = 4401
    WS_CLOSE_QUOTA_EXCEEDED: int = 4401

    def __init__(self, app: Any, auth_required: bool = True) -> None:
        self.app = app
        self.auth_required = auth_required
        self._quota = get_quota_manager()
        self._audit = get_audit_logger()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        """ASGI 入口:对 http / websocket 执行三道闸门,其余直接透传。"""
        # 非 http/websocket(如 lifespan)直接透传
        if scope.get("type") not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        is_ws: bool = scope["type"] == "websocket"
        method: str = scope.get("method", "WS")
        start = time.monotonic()

        # ── Gate 1: 鉴权 ──────────────────────────────────────────────
        principal = self._authenticate(scope, path)
        if principal is None:
            # 鉴权失败:fail-closed(在进入任何 handler 前拒绝)
            status = self.WS_CLOSE_AUTH_FAIL if is_ws else 401
            if is_ws:
                await send({
                    "type": "websocket.close",
                    "code": self.WS_CLOSE_AUTH_FAIL,
                    "reason": "Unauthorized",
                })
            else:
                await self._send_json(send, 401, {"detail": "Unauthorized"})
            self._audit_log(
                principal="(denied)", path=path, method=method,
                status=status, start=start, via="denied",
            )
            return

        # 写入 scope["state"]["principal"] 供下游 handler 使用
        # (本中间件为最外层,scope["state"] 尚未存在,这里初始化为 dict)
        scope.setdefault("state", {})["principal"] = principal

        # ── Gate 2: 配额 ──────────────────────────────────────────────
        ok, reason = await self._quota.acquire(principal)
        if not ok:
            status = self.WS_CLOSE_QUOTA_EXCEEDED if is_ws else 429
            if is_ws:
                await send({
                    "type": "websocket.close",
                    "code": self.WS_CLOSE_QUOTA_EXCEEDED,
                    "reason": f"Quota exceeded: {reason}",
                })
            else:
                await self._send_json(
                    send, 429, {"detail": f"Quota exceeded: {reason}"},
                    extra_headers=[(b"retry-after", b"1")],
                )
            # acquire 返回 False 时未持有信号量,无需 release
            self._audit_log(
                principal=principal.sub, path=path, method=method,
                status=status, start=start, via=principal.via,
            )
            return

        # ── Gate 3: 审计(包装 send 捕获响应状态码) ───────────────────
        status_holder = {"status": 0}

        async def send_wrapper(message: dict) -> None:
            """包装 send 以捕获响应状态码(HTTP) / 关闭码(WebSocket)。"""
            mtype = message.get("type")
            if mtype == "http.response.start":
                status_holder["status"] = message.get("status", 0)
            elif mtype == "websocket.accept":
                status_holder["status"] = 200
            elif mtype == "websocket.close":
                status_holder["status"] = message.get("code", 1005)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # 确保配额释放 + 审计记录(异常场景也执行)
            try:
                await self._quota.release(principal)
            except Exception:
                pass
            self._audit_log(
                principal=principal.sub, path=path, method=method,
                status=status_holder["status"], start=start, via=principal.via,
            )

    # ------------------------------------------------------------------
    # Gate 1: 鉴权实现
    # ------------------------------------------------------------------

    def _authenticate(self, scope: dict, path: str) -> Optional[Principal]:
        """Gate 1: 鉴权。返回 Principal 或 None(失败)。

        优先级:
            1. 公共路径 → Principal(via="public")
            2. 提取 Token 并校验 → Principal(via="token")
            3. 无 Token:
               - 开发模式(auth_required=False)→ Principal(via="dev")
               - 生产模式 → None(fail-closed)
            4. Token 校验失败:
               - 开发模式 → Principal(via="dev")
               - 生产模式 → None(fail-closed)
        """
        # 1. 公共路径:跳过鉴权但仍审计
        if path in PUBLIC_PATHS:
            return Principal(sub="anonymous", scope=[], via="public")

        # 2. 提取 Token
        token = self._extract_token(scope)

        if token is None:
            # 3. 无 Token
            if not self.auth_required:
                return Principal(sub="anonymous", scope=[], via="dev")
            return None

        # 4. 有 Token:校验
        try:
            payload = self._verify_token(token)
        except Exception:
            # Token 校验失败
            if not self.auth_required:
                # 开发模式:Token 无效也放行(匿名)
                return Principal(sub="anonymous", scope=[], via="dev")
            return None

        return self._build_principal(payload)

    @staticmethod
    def _verify_token(token: str) -> dict:
        """复用项目既有 JWT 校验(fnixagent.core.security.auth.token)。

        校验项:签名(HMAC-SHA256,使用 jwt_secret_key) + 过期 + token_type=access。
        失败抛 ValueError,由调用方捕获。
        """
        # 延迟导入避免循环依赖
        from fnixagent.core.security.auth.token import verify_token

        return verify_token(token, expected_type="access")

    @staticmethod
    def _build_principal(payload: dict) -> Principal:
        """从 JWT payload 构建 Principal。"""
        user_id = payload.get("user_id")
        role = payload.get("role", "user")
        sub = str(user_id) if user_id is not None else "unknown"

        # scope 优先取 payload.scope,其次用 role 兜底
        scope_claim = payload.get("scope", [])
        if isinstance(scope_claim, str):
            scopes = [s for s in scope_claim.split() if s]
        elif isinstance(scope_claim, list):
            scopes = [str(s) for s in scope_claim]
        else:
            scopes = []
        if not scopes:
            scopes = [role]

        return Principal(sub=sub, scope=scopes, via="token")

    @staticmethod
    def _extract_token(scope: dict) -> Optional[str]:
        """从 ASGI scope 提取 Token。

        HTTP:      Authorization: Bearer <token>
        WebSocket: ?token=<token>(query string)
        """
        if scope["type"] == "websocket":
            query_string = scope.get("query_string", b"")
            if isinstance(query_string, bytes):
                query_string = query_string.decode("utf-8", errors="ignore")
            params = parse_qs(query_string)
            tokens = params.get("token")
            return tokens[0] if tokens else None

        # HTTP: 从 headers 提取 Authorization
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                auth = value.decode("utf-8", errors="ignore")
                if auth.lower().startswith("bearer "):
                    return auth[7:].strip()
                return auth.strip()  # 兼容裸 token
        return None

    # ------------------------------------------------------------------
    # Gate 3: 审计辅助
    # ------------------------------------------------------------------

    def _audit_log(
        self,
        principal: str,
        path: str,
        method: str,
        status: int,
        start: float,
        via: str,
    ) -> None:
        """记录一条审计日志(latency 由 start 计算)。"""
        latency_ms = (time.monotonic() - start) * 1000.0
        self._audit.log(AuditEntry(
            principal=principal,
            path=path,
            method=method,
            status=status,
            latency_ms=latency_ms,
            via=via,
        ))

    # ------------------------------------------------------------------
    # HTTP 响应辅助
    # ------------------------------------------------------------------

    @staticmethod
    async def _send_json(
        send: Any,
        status: int,
        payload: dict,
        extra_headers: Optional[list] = None,
    ) -> None:
        """直接发送 JSON HTTP 响应(用于闸门拒绝场景,不进入下游 handler)。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers: list = [(b"content-type", b"application/json")]
        if extra_headers:
            headers.extend(extra_headers)
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        })
        await send({"type": "http.response.body", "body": body})
