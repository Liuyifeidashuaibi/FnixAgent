"""
内存后端实现 (In-Memory Backend Implementations)
==================================================
零外部依赖的 Protocol 实现, 用于测试/开发/无外部服务场景。

特点:
  - 全部纯 Python + asyncio, 无需任何外部服务
  - 内存数据结构, 重启丢失 (生产用 postgres/redis 适配器)
  - 完整实现 6 个 Protocol 接口
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict, deque
from typing import Any, AsyncIterator

from officeagent.core.agentos.types import (
    AuditBackend, LLMBackend, MemoryBackend, MemoryLayer,
    PolicyBackend, StorageBackend, ToolBackend, utcnow_iso,
)


# ============================================================================
# InMemoryLLMBackend
# ============================================================================

class InMemoryLLMBackend:
    """内存 LLM 后端 (Mock 实现, 用于测试)。

    特点:
      - complete: 返回固定模板响应
      - stream: 逐字符异步迭代
      - embed: 简单哈希向量
      - count_tokens: 简单空格分词计数
    """

    def __init__(self, response_template: str = "[LLM] {prompt}",
                 embed_dim: int = 128):
        self._template = response_template
        self._embed_dim = embed_dim
        self._call_count = 0
        self._total_tokens = 0

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        self._call_count += 1
        # 提取最后一条用户消息
        last_msg = messages[-1] if messages else {}
        prompt = str(last_msg.get("content", ""))
        self._total_tokens += len(prompt.split())
        return self._template.format(prompt=prompt[:100])

    async def stream(self, messages: list[dict[str, Any]],
                     **kwargs: Any) -> AsyncIterator[str]:
        self._call_count += 1
        last_msg = messages[-1] if messages else {}
        prompt = str(last_msg.get("content", ""))
        response = self._template.format(prompt=prompt[:100])
        # 逐字符流式
        for ch in response:
            yield ch
            await asyncio.sleep(0)  # 让出控制权

    async def embed(self, text: str) -> list[float]:
        self._call_count += 1
        # 简单哈希向量 (确定性, 测试用)
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 扩展到 embed_dim
        result = []
        for i in range(self._embed_dim):
            result.append((h[i % 32] / 255.0) * 2 - 1)  # [-1, 1]
        return result

    async def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            total += len(content.split())
        return total

    def get_stats(self) -> dict[str, Any]:
        return {
            "call_count": self._call_count,
            "total_tokens": self._total_tokens,
        }


# ============================================================================
# InMemoryMemoryBackend
# ============================================================================

class InMemoryMemoryBackend:
    """内存记忆后端 (Mock 实现)。

    支持按 layer 分层存储 (episodic/semantic 独立)。
    """

    def __init__(self):
        self._stores: dict[MemoryLayer, list[dict]] = {
            MemoryLayer.EPISODIC: [],
            MemoryLayer.SEMANTIC: [],
        }
        self._id_map: dict[str, dict] = {}
        self._counter = 0

    async def recall(self, query: str, top_k: int = 5,
                     layer: MemoryLayer | None = None) -> list[dict]:
        layers = [layer] if layer else list(self._stores.keys())
        results: list[dict] = []
        query_lower = query.lower()
        for ly in layers:
            for item in self._stores.get(ly, []):
                content = str(item.get("content", "")).lower()
                if query_lower in content or any(
                    w in content for w in query_lower.split()
                ):
                    item_copy = dict(item)
                    item_copy["score"] = 0.9  # 简单评分
                    results.append(item_copy)
        return results[:top_k]

    async def store(self, content: str, metadata: dict[str, Any],
                    layer: MemoryLayer = MemoryLayer.EPISODIC) -> str:
        self._counter += 1
        memory_id = f"mem-{self._counter}"
        item = {
            "id": memory_id,
            "content": content,
            "metadata": dict(metadata),
            "layer": layer.value,
            "stored_at": utcnow_iso(),
        }
        self._stores.setdefault(layer, []).append(item)
        self._id_map[memory_id] = item
        return memory_id

    async def search(self, query: str, top_k: int = 5,
                     layer: MemoryLayer | None = None) -> list[dict]:
        return await self.recall(query, top_k=top_k, layer=layer)

    async def forget(self, memory_id: str) -> bool:
        item = self._id_map.pop(memory_id, None)
        if item is None:
            return False
        layer = MemoryLayer(item.get("layer", MemoryLayer.EPISODIC.value))
        try:
            self._stores[layer].remove(item)
        except (ValueError, KeyError):
            pass
        return True

    def get_stats(self) -> dict[str, Any]:
        return {
            "episodic_count": len(self._stores.get(MemoryLayer.EPISODIC, [])),
            "semantic_count": len(self._stores.get(MemoryLayer.SEMANTIC, [])),
            "total_count": len(self._id_map),
        }


# ============================================================================
# InMemoryToolBackend
# ============================================================================

class InMemoryToolBackend:
    """内存工具后端 (Mock 实现)。

    内置 echo/add 工具, 支持注册自定义工具。
    """

    def __init__(self):
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Any] = {}
        # 内置工具
        self.register("echo", {"description": "回显输入"},
                      lambda args: {"echo": args.get("text", "")})
        self.register("add", {"description": "加法"},
                      lambda args: {"sum": args.get("a", 0) + args.get("b", 0)})

    def register(self, name: str, metadata: dict[str, Any],
                 handler: Any) -> None:
        """注册工具。"""
        self._tools[name] = metadata
        self._handlers[name] = handler

    async def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": k, **v} for k, v in self._tools.items()]

    async def invoke(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name not in self._handlers:
            raise ValueError(f"工具 {tool_name} 不存在")
        handler = self._handlers[tool_name]
        # 支持 sync 和 async handler
        if asyncio.iscoroutinefunction(handler):
            return await handler(arguments)
        return handler(arguments)


# ============================================================================
# InMemoryStorageBackend
# ============================================================================

class InMemoryStorageBackend:
    """内存存储后端 (Mock 实现)。

    支持 TTL 过期 (类比 Redis)。
    """

    def __init__(self):
        self._data: dict[str, tuple[str, float | None]] = {}  # key → (value, expire_at)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if expire_at and time.time() > expire_at:
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        async with self._lock:
            expire_at = time.time() + ttl if ttl else None
            self._data[key] = (value, expire_at)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            return self._data.pop(key, None) is not None

    async def list_prefix(self, prefix: str) -> list[str]:
        async with self._lock:
            now = time.time()
            keys = []
            for k, (_, expire_at) in self._data.items():
                if k.startswith(prefix):
                    if expire_at and now > expire_at:
                        continue
                    keys.append(k)
            return sorted(keys)

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_keys": len(self._data),
            "expired_keys": sum(
                1 for _, exp in self._data.values()
                if exp and time.time() > exp
            ),
        }


# ============================================================================
# InMemoryPolicyBackend
# ============================================================================

class InMemoryPolicyBackend:
    """内存策略后端 (Mock 实现)。

    支持注册 (action, resource, subject) → allow/deny 规则。
    """

    def __init__(self, default_allow: bool = True):
        """内存策略后端。

        default_allow 默认 True: 无规则匹配时不阻止 (让 PolicyEngine 自身
        的 mode 决定默认策略)。如需后端独立默认拒绝, 显式传入 False。
        """
        self._rules: list[tuple[str, str, str, bool]] = []
        self._default_allow = default_allow

    def add_rule(self, action_pattern: str, resource_pattern: str,
                 subject_pattern: str, allow: bool) -> None:
        """添加策略规则。"""
        self._rules.append((action_pattern, resource_pattern,
                            subject_pattern, allow))

    @staticmethod
    def _match(pattern: str, value: str) -> bool:
        import fnmatch
        if pattern == "*":
            return True
        return fnmatch.fnmatch(value, pattern)

    async def evaluate(self, action: str, resource: str, subject: str,
                       context: dict[str, Any]) -> tuple[bool, str]:
        for ap, rp, sp, allow in self._rules:
            if (self._match(ap, action) and
                self._match(rp, resource or "*") and
                    self._match(sp, subject)):
                if allow:
                    return True, ""
                return False, f"策略拒绝: {ap}/{rp}/{sp}"
        if self._default_allow:
            return True, ""
        return False, "默认拒绝 (无匹配规则)"


# ============================================================================
# InMemoryAuditBackend
# ============================================================================

class InMemoryAuditBackend:
    """内存审计后端 (带简单哈希链)。

    哈希链: 每条日志包含前一条的 hash, 防篡改。
    """

    def __init__(self, max_entries: int = 10000):
        self._entries: deque[dict] = deque(maxlen=max_entries)
        self._last_hash: str = "0" * 64  # 创世哈希

    async def log(self, action: str, subject: str | None = None,
                  detail: dict[str, Any] | None = None,
                  trace_id: str | None = None) -> None:
        entry = {
            "action": action,
            "subject": subject,
            "detail": detail or {},
            "trace_id": trace_id,
            "timestamp": utcnow_iso(),
            "prev_hash": self._last_hash,
        }
        # 计算当前条目哈希
        content = f"{action}|{subject}|{detail}|{trace_id}|{self._last_hash}"
        entry["hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self._last_hash = entry["hash"]
        self._entries.append(entry)

    async def query(self, limit: int = 100, offset: int = 0,
                    action: str | None = None,
                    subject: str | None = None) -> list[dict]:
        entries = list(self._entries)
        if action:
            entries = [e for e in entries if e.get("action") == action]
        if subject:
            entries = [e for e in entries if e.get("subject") == subject]
        return entries[offset:offset + limit]

    def verify_chain(self) -> tuple[bool, int | None]:
        """验证哈希链完整性。"""
        prev_hash = "0" * 64
        for i, entry in enumerate(self._entries):
            if entry.get("prev_hash") != prev_hash:
                return False, i
            prev_hash = entry.get("hash", "")
        return True, None

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "last_hash": self._last_hash[:16] + "...",
        }


__all__ = [
    "InMemoryLLMBackend", "InMemoryMemoryBackend", "InMemoryToolBackend",
    "InMemoryStorageBackend", "InMemoryPolicyBackend", "InMemoryAuditBackend",
]
