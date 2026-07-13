"""
ContextFS - 上下文文件系统 (Context Filesystem)
================================================
2026 前沿共识: "Filesystem Is All Your Agent Needs for Memory"

设计要点:
  - LLM 原生理解 Markdown / 文本文件, 无需 embedding/retrieval pipeline
  - just-in-time context loading (按需加载, 减少 context window bloat)
  - 类比 Unix VFS: 路径规范化 / 权限检查 / 目录遍历
  - 树结构 + StorageBackend 持久化 (可插拔)
  - LRU 缓存 (修复原版无 storage 时 eviction 丢数据 bug)
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

from officeagent.core.agentos.types import StorageBackend


class ContextFSNode:
    """ContextFS 节点 (文件或目录)。

    使用 __slots__ 节省内存 (大量节点场景)。
    """
    __slots__ = ("name", "is_dir", "content", "children", "metadata",
                 "created_at", "modified_at", "loaded")

    def __init__(self, name: str, is_dir: bool = False):
        self.name = name
        self.is_dir = is_dir
        self.content: str = ""
        self.children: dict[str, ContextFSNode] = {}
        self.metadata: dict[str, Any] = {}
        self.created_at: float = time.time()
        self.modified_at: float = time.time()
        self.loaded = False  # just-in-time: 内容是否已加载

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "is_dir": self.is_dir,
            "size": len(self.content) if not self.is_dir else 0,
            "children": len(self.children) if self.is_dir else 0,
            "modified_at": self.modified_at,
            "loaded": self.loaded,
        }


class ContextFS:
    """上下文文件系统 (Context Filesystem)。

    2026 前沿共识: "Filesystem Is All Your Agent Needs for Memory"
    - LLM 原生理解 Markdown / 文本文件
    - 无需 embedding / retrieval pipeline
    - just-in-time context loading (按需加载, 减少 context window bloat)
    - 类比 Unix VFS: 路径规范化 / 权限检查 / 目录遍历

    支持后端:
      - memory: 内存树 (默认, 测试用)
      - storage: 可插拔 StorageBackend (Postgres / MinIO)

    LRU 缓存策略:
      - 无 storage (纯内存): 不驱逐 (数据只存内存, 驱逐会丢数据)
      - 有 storage: 超过 max_cache_size 时驱逐最久未访问, 内容已持久化可安全驱逐
    """

    def __init__(self, storage: StorageBackend | None = None,
                 max_cache_size: int = 100):
        self._storage = storage
        self._root = ContextFSNode("/", is_dir=True)
        self._root.loaded = True
        self._max_cache_size = max_cache_size
        # LRU 缓存: OrderedDict[path, float] (path → last_access_time)
        # 修复原版 deque 重复路径 bug
        self._cache_lru: OrderedDict[str, float] = OrderedDict()
        # 并发安全锁: 保护文件树 + LRU 缓存的读写操作
        self._lock = asyncio.Lock()

    # --- 路径处理 ---

    @staticmethod
    def _normalize_path(path: str) -> list[str]:
        """路径规范化 (类比 realpath): 消除 . / .. / 多余斜杠。

        "/a/b/../c/./d" → ["a", "c", "d"]
        """
        if not path or not path.startswith("/"):
            raise ValueError(f"路径必须以 / 开头: {path}")
        parts: list[str] = []
        for part in path.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(part)
        return parts

    @staticmethod
    def join(*parts: str) -> str:
        """路径拼接 (类比 os.path.join, 但始终用 /)。"""
        result: list[str] = []
        for part in parts:
            for sub in part.split("/"):
                if sub:
                    result.append(sub)
        return "/" + "/".join(result)

    # --- 节点查找 ---

    def _find_node(self, path: str, create: bool = False) -> ContextFSNode | None:
        """查找路径对应的节点 (内存树)。

        create=True 时自动创建缺失的中间目录节点。
        """
        parts = self._normalize_path(path)
        if not parts:
            return self._root
        current = self._root
        for i, part in enumerate(parts):
            if not current.is_dir:
                return None
            if part not in current.children:
                if create:
                    is_last = (i == len(parts) - 1)
                    # 中间节点始终为目录; 末节点根据路径是否以 / 结尾判断
                    is_dir = (not is_last) or path.endswith("/")
                    current.children[part] = ContextFSNode(part, is_dir=is_dir)
                else:
                    return None
            current = current.children[part]
        return current

    def _ensure_parent(self, parts: list[str]) -> ContextFSNode:
        """确保父目录链存在, 返回父节点。"""
        current = self._root
        for part in parts[:-1]:
            if part not in current.children:
                current.children[part] = ContextFSNode(part, is_dir=True)
            current = current.children[part]
            if not current.is_dir:
                raise NotADirectoryError(f"路径冲突, 已存在非目录: {part}")
        return current

    # --- LRU 缓存管理 ---

    def _touch_cache(self, path: str) -> None:
        """更新缓存访问时间 (修复原版 deque 重复路径 bug)。"""
        now = time.time()
        # 若已存在, 先删除再插入 (移到末尾表示最近访问)
        if path in self._cache_lru:
            self._cache_lru.pop(path)
        self._cache_lru[path] = now
        # 仅在有 storage 时驱逐 (无 storage 驱逐会丢数据)
        if self._storage and len(self._cache_lru) > self._max_cache_size:
            # 驱逐最久未访问 (OrderedDict 首项)
            oldest_path, _ = self._cache_lru.popitem(last=False)
            node = self._find_node(oldest_path)
            if node and not node.is_dir:
                # 内容已持久化到 storage, 可安全驱逐
                node.content = ""
                node.loaded = False

    def cache_stats(self) -> dict[str, Any]:
        """缓存统计。"""
        return {
            "cache_size": len(self._cache_lru),
            "max_cache_size": self._max_cache_size,
            "has_storage": self._storage is not None,
        }

    # --- 文件操作 ---

    async def read(self, path: str, caller_pid: str) -> str:
        """读上下文文件 (类比 read syscall)。

        just-in-time: 首次读取时从后端加载, 后续走缓存。
        无后端时直接返回内存内容 (修复原版返回空字符串 bug)。
        并发安全: 加锁保护文件树与 LRU 缓存。
        """
        async with self._lock:
            node = self._find_node(path)
            if node is None or node.is_dir:
                raise FileNotFoundError(f"文件不存在或为目录: {path}")
            if not node.loaded and self._storage:
                # just-in-time loading
                content = await self._storage.get(f"ctx:{caller_pid}:{path}")
                node.content = content or ""
                node.loaded = True
            # 返回副本, 避免外部修改影响缓存
            self._touch_cache(path)
            return str(node.content)

    async def write(self, path: str, content: str, caller_pid: str) -> None:
        """写上下文文件 (类比 write syscall)。并发安全。"""
        async with self._lock:
            parts = self._normalize_path(path)
            if not parts:
                raise ValueError("不能写入根目录")
            parent = self._ensure_parent(parts)
            leaf = parts[-1]
            if leaf not in parent.children:
                parent.children[leaf] = ContextFSNode(leaf, is_dir=False)
            node = parent.children[leaf]
            node.is_dir = False
            node.content = content
            node.loaded = True
            node.modified_at = time.time()
            if self._storage:
                await self._storage.set(f"ctx:{caller_pid}:{path}", content)
            self._touch_cache(path)

    async def list_dir(self, path: str, caller_pid: str) -> list[str]:
        """列目录 (类比 ls / readdir)。并发安全。"""
        async with self._lock:
            node = self._find_node(path)
            if node is None:
                raise FileNotFoundError(f"目录不存在: {path}")
            if not node.is_dir:
                raise NotADirectoryError(f"不是目录: {path}")
            return sorted(node.children.keys())

    async def delete(self, path: str, caller_pid: str) -> bool:
        """删除文件/目录 (类比 rm, 高危操作)。并发安全。"""
        async with self._lock:
            parts = self._normalize_path(path)
            if not parts:
                raise ValueError("不能删除根目录")
            parent = self._ensure_parent(parts)
            leaf = parts[-1]
            if leaf not in parent.children:
                return False
            parent.children.pop(leaf)
            if self._storage:
                await self._storage.delete(f"ctx:{caller_pid}:{path}")
            # 清理缓存
            self._cache_lru.pop(path, None)
            return True

    async def mkdir(self, path: str, caller_pid: str) -> None:
        """创建目录 (类比 mkdir, 含父目录自动创建)。并发安全。"""
        async with self._lock:
            parts = self._normalize_path(path)
            current = self._root
            for part in parts:
                if part not in current.children:
                    current.children[part] = ContextFSNode(part, is_dir=True)
                current = current.children[part]
                if not current.is_dir:
                    raise FileExistsError(f"路径已存在且非目录: {part}")

    async def stat(self, path: str) -> dict[str, Any] | None:
        """获取文件元信息 (类比 stat)。"""
        async with self._lock:
            node = self._find_node(path)
            if node is None:
                return None
            return node.to_dict()

    async def exists(self, path: str) -> bool:
        """路径是否存在。"""
        return self._find_node(path) is not None

    async def walk(self, path: str = "/") -> list[tuple[str, list[str], list[str]]]:
        """遍历目录树 (类比 os.walk)。

        Returns:
            [(dirpath, [subdirs], [files]), ...]
        """
        result: list[tuple[str, list[str], list[str]]] = []

        def _walk(node: ContextFSNode, current_path: str) -> None:
            if not node.is_dir:
                return
            subdirs: list[str] = []
            files: list[str] = []
            for name, child in node.children.items():
                if child.is_dir:
                    subdirs.append(name)
                else:
                    files.append(name)
            result.append((current_path, sorted(subdirs), sorted(files)))
            for subdir in subdirs:
                _walk(node.children[subdir], ContextFS.join(current_path, subdir))

        root_node = self._find_node(path) if path != "/" else self._root
        if root_node and root_node.is_dir:
            _walk(root_node, path if path.endswith("/") else path + "/")
        return result

    def get_stats(self) -> dict[str, Any]:
        """文件系统统计 (类比 df)。"""
        total_files = 0
        total_dirs = 0
        total_size = 0

        def _count(node: ContextFSNode) -> None:
            nonlocal total_files, total_dirs, total_size
            if node.is_dir:
                total_dirs += 1
                for child in node.children.values():
                    _count(child)
            else:
                total_files += 1
                total_size += len(node.content)

        _count(self._root)
        return {
            "total_files": total_files,
            "total_dirs": total_dirs,
            "total_size_bytes": total_size,
            "total_size_kb": round(total_size / 1024, 2),
            **self.cache_stats(),
        }


__all__ = ["ContextFS", "ContextFSNode"]
