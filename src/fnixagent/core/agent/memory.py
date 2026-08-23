"""
MemoryManager - 四层记忆架构 (Four-Layer Memory Architecture)
===============================================================
2026 行业统一共识: 感知/工作/情节/语义 四层分层。

层级:
  SENSORY  - 感知记忆: LLM 当前处理的 token 流 (GPU KV Cache)
             介质: vLLM PagedAttention, 最快, 容量最小
  WORKING  - 工作记忆: 当前对话上下文 (LLM Context Window)
             介质: LLM 本身, 快, 容量有限, 超限自动卸载到情节记忆
  EPISODIC - 情节记忆: 历史对话事件
             介质: 记忆服务层 (记忆服务 23K star) + Postgres, 自动摘要
  SEMANTIC - 语义记忆: 知识图谱 / 向量库
             介质: Milvus + cognee + GraphRAG, 多跳推理

设计修复:
  - 修复原版 EPISODIC/SEMANTIC 调用同一后端 bug: 支持 EPISODIC_BACKEND/SEMANTIC_BACKEND
  - 修复原版无后端时 working 记忆无法检索 bug
  - 完整的 store/recall/search/forget 四层路由
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import uuid
from collections import defaultdict, deque
from typing import Any

from fnixagent.core.agent.types import MemoryBackend, MemoryLayer, utcnow_iso


class MemoryManager:
    """记忆管理器 (类比 OS 内存管理)。

    四层分层:
      感知记忆 → GPU KV Cache (vLLM PagedAttention), 最快, 容量最小
      工作记忆 → Context Window (LLM 本身), 快, 容量有限
      情节记忆 → 记忆服务层 + Postgres (自动摘要 / 卸载), 中速, 大容量
      语义记忆 → Milvus + GraphRAG (向量 + 多跳推理), 慢, 海量

    冷热分层:
      - 热数据: 感知 + 工作记忆 (内存)
      - 温数据: 情节记忆 (Postgres + 摘要)
      - 冷数据: 语义记忆 (Milvus + 知识图谱)

    可插拔后端:
      - episodic_backend: 情节记忆后端 (记忆服务层 / Postgres)
      - semantic_backend: 语义记忆后端 (Milvus / cognee)
      - 若两者使用同一 MemoryBackend, 则通过 layer 参数区分
    """

    def __init__(
        self,
        episodic_backend: MemoryBackend | None = None,
        semantic_backend: MemoryBackend | None = None,
        max_working_items: int = 100,
        max_sensory_items: int = 50,
    ):
        self._episodic_backend = episodic_backend
        self._semantic_backend = semantic_backend or episodic_backend
        # 内存缓存 (感知 + 工作记忆)
        self._sensory: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=max_sensory_items))
        self._working: dict[str, list[dict]] = defaultdict(list)
        self._max_working_items = max_working_items
        self._max_sensory_items = max_sensory_items

    # --- 感知记忆 (SENSORY) ---

    def append_sensory(
        self, caller_pid: str, token_chunk: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """追加感知记忆 (LLM 流式 token, 类比 GPU KV Cache 写入)。"""
        memory_id = str(uuid.uuid4())
        self._sensory[caller_pid].append(
            {
                "id": memory_id,
                "content": token_chunk,
                "metadata": {**(metadata or {}), "timestamp": utcnow_iso()},
                "layer": MemoryLayer.SENSORY.value,
            }
        )
        return memory_id

    def get_sensory(self, caller_pid: str, last_n: int = 50) -> list[dict]:
        """获取最近的感知记忆 (类比 KV Cache 读取)。"""
        items = list(self._sensory.get(caller_pid, []))
        return items[-last_n:] if last_n < len(items) else items

    # --- 工作记忆 (WORKING) ---

    async def store_working(
        self, caller_pid: str, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """存储工作记忆 (类比 context window 写入)。

        超限时自动卸载最旧条目到情节记忆 (eviction)。
        """
        memory_id = str(uuid.uuid4())
        item = {
            "id": memory_id,
            "content": content,
            "metadata": {**(metadata or {}), "caller_pid": caller_pid, "timestamp": utcnow_iso()},
            "layer": MemoryLayer.WORKING.value,
        }
        self._working[caller_pid].append(item)
        # 容量管理: 超限时卸载到情节记忆
        if len(self._working[caller_pid]) > self._max_working_items:
            evicted = self._working[caller_pid].pop(0)
            if self._episodic_backend:
                await self._episodic_backend.store(
                    evicted["content"],
                    {**evicted["metadata"], "evicted": True},
                    layer=MemoryLayer.EPISODIC,
                )
        return memory_id

    def get_working(self, caller_pid: str, last_n: int = 100) -> list[dict]:
        """获取工作记忆 (当前上下文)。"""
        items = self._working.get(caller_pid, [])
        return items[-last_n:] if last_n < len(items) else list(items)

    def clear_working(self, caller_pid: str) -> int:
        """清空工作记忆 (类比 context window reset)。"""
        count = len(self._working.get(caller_pid, []))
        self._working[caller_pid] = []
        return count

    # --- 统一接口 ---

    async def recall(
        self,
        query: str,
        layers: list[MemoryLayer],
        caller_pid: str,
        top_k: int = 5,
    ) -> list[dict]:
        """召回记忆 (类比内存读取)。

        分层召回:
          1. 感知记忆: 返回最近 token 流 (无检索)
          2. 工作记忆: 返回当前上下文片段 (无检索)
          3. 情节记忆: 通过 episodic_backend 检索
          4. 语义记忆: 通过 semantic_backend 检索

        修复原版 EPISODIC/SEMANTIC 返回相同数据 bug: 分别路由到不同后端。
        """
        results: list[dict] = []
        for layer in layers:
            if layer == MemoryLayer.WORKING:
                items = self._working.get(caller_pid, [])
                results.extend(items[-top_k:])
            elif layer == MemoryLayer.SENSORY:
                items = list(self._sensory.get(caller_pid, []))
                results.extend(items[-top_k:])
            elif layer == MemoryLayer.EPISODIC and self._episodic_backend:
                backend_results = await self._episodic_backend.recall(
                    query, top_k=top_k, layer=MemoryLayer.EPISODIC
                )
                for item in backend_results:
                    item["layer"] = MemoryLayer.EPISODIC.value
                    results.append(item)
            elif layer == MemoryLayer.SEMANTIC and self._semantic_backend:
                backend_results = await self._semantic_backend.recall(
                    query, top_k=top_k, layer=MemoryLayer.SEMANTIC
                )
                for item in backend_results:
                    item["layer"] = MemoryLayer.SEMANTIC.value
                    results.append(item)
        return results

    async def store(
        self,
        content: str,
        layer: MemoryLayer,
        metadata: dict[str, Any] | None,
        caller_pid: str,
    ) -> str:
        """存储记忆 (类比内存写入)。

        分层存储:
          感知记忆 → 内存 deque (append_sensory)
          工作记忆 → 内存 list (超限卸载到情节记忆)
          情节记忆 → episodic_backend 持久化
          语义记忆 → semantic_backend 持久化
        """
        metadata = metadata or {}
        metadata["caller_pid"] = caller_pid
        metadata["timestamp"] = utcnow_iso()

        if layer == MemoryLayer.SENSORY:
            return self.append_sensory(caller_pid, content, metadata)
        elif layer == MemoryLayer.WORKING:
            return await self.store_working(caller_pid, content, metadata)
        elif layer == MemoryLayer.EPISODIC and self._episodic_backend:
            return await self._episodic_backend.store(content, metadata, layer=MemoryLayer.EPISODIC)
        elif layer == MemoryLayer.SEMANTIC and self._semantic_backend:
            return await self._semantic_backend.store(content, metadata, layer=MemoryLayer.SEMANTIC)
        # 无后端时, 降级到工作记忆
        return await self.store_working(caller_pid, content, metadata)

    async def search(
        self,
        query: str,
        layer: MemoryLayer,
        caller_pid: str,
        top_k: int = 5,
    ) -> list[dict]:
        """语义搜索 (类比内存检索)。

        内存层: 简单词频匹配
        后端层: 向量检索 (由后端实现)
        """
        if layer == MemoryLayer.SENSORY:
            items = list(self._sensory.get(caller_pid, []))
            return self._text_match(items, query, top_k)
        elif layer == MemoryLayer.WORKING:
            items = list(self._working.get(caller_pid, []))
            return self._text_match(items, query, top_k)
        elif layer == MemoryLayer.EPISODIC and self._episodic_backend:
            return await self._episodic_backend.search(
                query, top_k=top_k, layer=MemoryLayer.EPISODIC
            )
        elif layer == MemoryLayer.SEMANTIC and self._semantic_backend:
            return await self._semantic_backend.search(
                query, top_k=top_k, layer=MemoryLayer.SEMANTIC
            )
        return []

    async def forget(self, memory_id: str, caller_pid: str) -> bool:
        """遗忘记忆 (类比 free / munmap)。"""
        # 尝试从工作记忆删除
        items = self._working.get(caller_pid, [])
        for i, item in enumerate(items):
            if item.get("id") == memory_id:
                items.pop(i)
                return True
        # 尝试从感知记忆删除
        sensory = self._sensory.get(caller_pid, [])
        for i, item in enumerate(sensory):
            if item.get("id") == memory_id:
                sensory.remove(item)
                return True
        # 尝试从后端删除 (先 episodic 再 semantic)
        if self._episodic_backend:
            if await self._episodic_backend.forget(memory_id):
                return True
        if self._semantic_backend and self._semantic_backend is not self._episodic_backend:
            if await self._semantic_backend.forget(memory_id):
                return True
        return False

    @staticmethod
    def _text_match(items: list[dict], query: str, top_k: int) -> list[dict]:
        """简单词频匹配 (无后端时的降级检索)。"""
        query_lower = query.lower()
        query_words = query_lower.split()
        scored = [
            (item, sum(1 for w in query_words if w in item.get("content", "").lower()))
            for item in items
        ]
        scored.sort(key=lambda x: -x[1])
        return [item for item, score in scored[:top_k] if score > 0]

    def get_stats(self, caller_pid: str) -> dict[str, Any]:
        """记忆统计 (类比 /proc/meminfo)。"""
        return {
            "sensory_count": len(self._sensory.get(caller_pid, [])),
            "working_count": len(self._working.get(caller_pid, [])),
            "max_working": self._max_working_items,
            "max_sensory": self._max_sensory_items,
            "has_episodic_backend": self._episodic_backend is not None,
            "has_semantic_backend": self._semantic_backend is not None,
            "backends_unified": self._semantic_backend is self._episodic_backend,
        }

    def clear_all(self, caller_pid: str) -> dict[str, int]:
        """清空指定 PID 的所有内存层记忆 (不含后端)。"""
        sensory_count = len(self._sensory.pop(caller_pid, deque()))
        working_count = len(self._working.pop(caller_pid, []))
        return {"sensory_cleared": sensory_count, "working_cleared": working_count}


__all__ = ["MemoryManager"]
