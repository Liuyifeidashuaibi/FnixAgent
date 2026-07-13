"""
A2ABus - Agent 间通信 (Agent-to-Agent Communication)
=====================================================
对标 A2A Protocol v1.0 (Linux Foundation 2026-04 生产就绪)。

设计要点:
  - JSON-RPC 2.0 消息格式
  - AgentCard: Agent 能力声明 (capabilities/skills/endpoint)
  - 点对点消息 + 广播 + 请求-响应 + 任务委派
  - 订阅/发布模式
  - 可插拔传输: 内存队列 (默认) / NATS (生产)

修复原版 bug:
  - reply 双投递: 只走 subscription, 不再 send 到 mailbox
  - 缺失 JSON-RPC 格式: 已补全
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from fnixagent.core.agent.types import utcnow_iso


@dataclass
class AgentCard:
    """Agent 能力声明 (对标 A2A Protocol AgentCard)。

    每个 Agent 启动时向 A2ABus 注册 AgentCard,
    其他 Agent 可通过 discover() 发现具备特定能力的 Agent。

    Attributes:
        id: Agent ID (通常等于 PID)
        name: 人类可读名称
        description: 详细描述
        version: 版本号
        capabilities: 能力列表 (如 ["fs", "llm", "tool"])
        endpoint: A2A 端点 URL (如 "https://host/a2a/v1")
        skills: 技能列表 (如 ["doc.writer", "data.analyst"])
        protocol: 协议 (默认 "JSON-RPC 2.0")
        authentication: 认证信息 (如 {"type": "bearer", "token": "..."})
        metadata: 额外元数据
    """
    id: str
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: list[str] = field(default_factory=list)
    endpoint: str = ""
    skills: list[str] = field(default_factory=list)
    protocol: str = "JSON-RPC 2.0"
    authentication: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "endpoint": self.endpoint,
            "skills": list(self.skills),
            "protocol": self.protocol,
            "authentication": dict(self.authentication),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentCard:
        return cls(
            id=d["id"],
            name=d.get("name", ""),
            description=d.get("description", ""),
            version=d.get("version", "1.0.0"),
            capabilities=list(d.get("capabilities", [])),
            endpoint=d.get("endpoint", ""),
            skills=list(d.get("skills", [])),
            protocol=d.get("protocol", "JSON-RPC 2.0"),
            authentication=dict(d.get("authentication", {})),
            metadata=dict(d.get("metadata", {})),
        )


@dataclass
class A2AMessage:
    """A2A 消息 (JSON-RPC 2.0 格式)。

    Attributes:
        message_id: 消息 ID (UUID)
        source: 发送方 Agent ID
        target: 接收方 Agent ID ("*" 表示广播)
        message_type: 消息类型 (request/response/event/error)
        content: 消息内容 (Any)
        reply_to: 回复的消息 ID (None 表示非回复)
        timestamp: 时间戳 (ISO)
        metadata: 额外元数据 (trace_id 等)
        jsonrpc: JSON-RPC 版本 (固定 "2.0")
        method: JSON-RPC method (仅 request 有)
        params: JSON-RPC params (仅 request 有)
        result: JSON-RPC result (仅 response 有)
        error: JSON-RPC error (仅 error 有, {"code": int, "message": str})
    """
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""
    target: str = ""
    message_type: str = "request"  # request/response/event/error
    content: Any = None
    reply_to: str | None = None
    timestamp: str = field(default_factory=utcnow_iso)
    metadata: dict[str, Any] = field(default_factory=dict)
    # JSON-RPC 2.0 字段
    jsonrpc: str = "2.0"
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_jsonrpc(self) -> dict[str, Any]:
        """转换为 JSON-RPC 2.0 格式。"""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": self.message_id}
        if self.message_type == "request":
            msg["method"] = self.method or ""
            msg["params"] = self.params or {"content": self.content}
        elif self.message_type == "response":
            msg["result"] = self.result if self.result is not None else self.content
        elif self.message_type == "error":
            msg["error"] = self.error or {"code": -1, "message": "unknown"}
        # event 用 notification 风格 (无 id)
        if self.message_type == "event":
            msg.pop("id", None)
            msg["method"] = self.method or "event"
            msg["params"] = self.params or {"content": self.content}
        return msg

    @classmethod
    def from_jsonrpc(cls, msg: dict[str, Any], source: str = "",
                     target: str = "") -> A2AMessage:
        """从 JSON-RPC 2.0 格式构造。"""
        message_id = msg.get("id", str(uuid.uuid4()))
        if "error" in msg:
            return cls(
                message_id=message_id, source=source, target=target,
                message_type="error", error=msg["error"],
            )
        elif "result" in msg:
            return cls(
                message_id=message_id, source=source, target=target,
                message_type="response", result=msg["result"],
                content=msg["result"],
            )
        elif "method" in msg:
            mtype = "event" if "id" not in msg else "request"
            return cls(
                message_id=message_id, source=source, target=target,
                message_type=mtype, method=msg["method"],
                params=msg.get("params", {}),
                content=msg.get("params", {}).get("content"),
            )
        return cls(message_id=message_id, source=source, target=target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "source": self.source,
            "target": self.target,
            "message_type": self.message_type,
            "content": self.content,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
            "result": self.result,
            "error": self.error,
        }


class A2ABus:
    """Agent 间通信总线 (类比 IPC / Message Queue)。

    对标 A2A Protocol v1.0 (Linux Foundation 2026-04 生产就绪)。

    支持模式:
      - 点对点消息: send(target, message)
      - 广播: broadcast(message)
      - 请求-响应: request_response(target, content) → response
      - 任务委派: delegate_task(target, task) → result
      - 订阅/发布: subscribe(topic, callback) / publish(topic, message)

    传输后端:
      - memory: asyncio.Queue (默认, 测试用)
      - nats: NATS JetStream (生产, 可插拔)
    """

    def __init__(self, nats_url: str | None = None):
        self._nats_url = nats_url
        self._nats_client: Any = None  # 延迟初始化
        self._registry: dict[str, AgentCard] = {}
        self._mailboxes: dict[str, asyncio.Queue[A2AMessage]] = {}
        self._subscriptions: dict[str, list[Callable[[A2AMessage], None]]] = {}
        self._pending_requests: dict[str, asyncio.Future[A2AMessage]] = {}
        self._lock = asyncio.Lock()

    # --- Agent 注册 ---

    async def register(self, card: AgentCard) -> None:
        """注册 AgentCard (类比服务注册)。"""
        async with self._lock:
            self._registry[card.id] = card
            if card.id not in self._mailboxes:
                self._mailboxes[card.id] = asyncio.Queue()

    async def unregister(self, agent_id: str) -> None:
        """注销 Agent。"""
        async with self._lock:
            self._registry.pop(agent_id, None)
            self._mailboxes.pop(agent_id, None)

    async def discover(self, capability: str | None = None,
                       skill: str | None = None) -> list[AgentCard]:
        """发现 Agent (类比服务发现)。

        Args:
            capability: 按能力过滤 (None = 全部)
            skill: 按技能过滤 (None = 全部)

        Returns:
            匹配的 AgentCard 列表
        """
        async with self._lock:
            cards = list(self._registry.values())
        if capability:
            cards = [c for c in cards if capability in c.capabilities]
        if skill:
            cards = [c for c in cards if skill in c.skills]
        return cards

    def get_registry_info(self) -> list[dict[str, Any]]:
        """获取注册表信息。"""
        return [card.to_dict() for card in self._registry.values()]

    # --- 消息传递 ---

    async def send(self, target: str, message: A2AMessage) -> None:
        """发送点对点消息 (类比 msgsnd)。"""
        if target not in self._mailboxes:
            raise ValueError(f"Agent {target} 未注册")
        await self._mailboxes[target].put(message)

    async def receive(self, agent_id: str, timeout: float = 30.0) -> A2AMessage:
        """接收消息 (类比 msgrcv, 阻塞直到有消息或超时)。"""
        if agent_id not in self._mailboxes:
            raise ValueError(f"Agent {agent_id} 未注册")
        try:
            return await asyncio.wait_for(
                self._mailboxes[agent_id].get(), timeout=timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Agent {agent_id} 等待消息超时 ({timeout}s)")

    async def broadcast(self, message: A2AMessage, exclude: str | None = None) -> int:
        """广播消息 (类比 publish)。

        Args:
            message: 消息 (target 设为 "*")
            exclude: 排除的 Agent ID (通常是发送方)

        Returns:
            投递到的 Agent 数量
        """
        count = 0
        for agent_id, mailbox in self._mailboxes.items():
            if agent_id == exclude:
                continue
            await mailbox.put(message)
            count += 1
        return count

    async def request_response(
        self,
        target: str,
        content: Any,
        source: str,
        timeout: float = 30.0,
        method: str = "query",
    ) -> A2AMessage | None:
        """请求-响应模式 (类比 RPC)。

        发送 request, 等待 response (通过 subscription 机制)。
        """
        request = A2AMessage(
            source=source, target=target, message_type="request",
            content=content, method=method,
        )
        # 注册 future 等待回复
        future: asyncio.Future[A2AMessage] = asyncio.get_event_loop().create_future()
        self._pending_requests[request.message_id] = future
        # 订阅回复 (通过 subscription 机制, 避免 mailbox 双投递)
        await self.send(target, request)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_requests.pop(request.message_id, None)

    async def reply(self, original: A2AMessage, content: Any,
                    message_type: str = "response") -> None:
        """回复消息 (修复原版双投递 bug)。

        修复: 只通过 subscription (pending_requests) 投递, 不再 send 到 mailbox。
        """
        reply_msg = A2AMessage(
            source=original.target, target=original.source,
            message_type=message_type, content=content,
            reply_to=original.message_id,
            result=content if message_type == "response" else None,
        )
        # 仅通过 pending_requests 投递 (修复双投递 bug)
        future = self._pending_requests.get(original.message_id)
        if future and not future.done():
            future.set_result(reply_msg)
        # 不再 send 到 mailbox (避免双投递和内存泄漏)

    async def delegate_task(
        self,
        target: str,
        task: dict[str, Any],
        source: str,
        timeout: float = 300.0,
    ) -> dict[str, Any] | None:
        """任务委派 (类比 RPC 调用, 等待完整结果)。"""
        response = await self.request_response(
            target=target, content=task, source=source,
            timeout=timeout, method="delegate",
        )
        if response is None:
            return None
        return {
            "success": response.message_type == "response",
            "result": response.result if response.message_type == "response" else None,
            "error": response.error.get("message") if response.error else None,
            "from": response.source,
        }

    # --- 订阅/发布 ---

    def subscribe(self, topic: str,
                  callback: Callable[[A2AMessage], None]) -> None:
        """订阅主题 (类比 pub/sub)。"""
        self._subscriptions.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic: str,
                    callback: Callable[[A2AMessage], None]) -> None:
        """取消订阅。"""
        if topic in self._subscriptions:
            try:
                self._subscriptions[topic].remove(callback)
            except ValueError:
                pass

    async def publish(self, topic: str, message: A2AMessage) -> int:
        """发布消息到主题。"""
        count = 0
        for callback in self._subscriptions.get(topic, []):
            try:
                callback(message)
                count += 1
            except Exception:
                continue
        return count

    # --- 统计 ---

    def get_stats(self) -> dict[str, Any]:
        """总线统计。"""
        return {
            "registered_agents": len(self._registry),
            "total_mailboxes": len(self._mailboxes),
            "pending_requests": len(self._pending_requests),
            "total_subscriptions": sum(len(v) for v in self._subscriptions.values()),
            "topics": list(self._subscriptions.keys()),
            "has_nats": self._nats_client is not None,
        }


__all__ = ["A2ABus", "AgentCard", "A2AMessage"]
