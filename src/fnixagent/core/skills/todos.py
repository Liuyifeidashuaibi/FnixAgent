"""TodoStore — load-bearing state 外化 (任务状态外化)。(2025-11):
  - "不是让 agent 记住全部上下文, 而是让它能快速理解当前工作状态"
  - JSON 而非 Markdown (模型更不易改坏结构, 不擅自删需求)
  - feature list 初始全标 passes: false (防假性完成)
  - git 历史用于回滚 + 理解演进

任务状态外化设计:
  - 任务状态持久化到文件, compaction 后仍可恢复
  - 跨上下文窗口交接的关键 load-bearing state

设计:
  - 存储路径: {workspace}/.fnix/todos.json
  - 线程安全 (threading.Lock)
  - 每轮 turn 边界写入, compaction 后重新注入 system prompt
  - 简单 JSON 格式, 无外部依赖
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TodoItem:
    """一个待办事项 (对齐  harness 的 feature list item)。

     status 流转: pending → in_progress → completed | failed
    初始全标 pending (防假性完成,)。
    """

    id: str
    content: str  # 任务描述
    status: str = "pending"  # pending / in_progress / completed / failed
    priority: str = "medium"  # high / medium / low
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: float = 0.0
    note: str = ""  # 可选备注 (如失败原因)


@dataclass
class TodoStore:
    """待办事项存储 (任务状态外化)。

    用法:
        store = TodoStore(workspace)
        store.add(TodoItem(id="t1", content="读取 sales.xlsx"))
        store.update_status("t1", "in_progress")
        store.update_status("t1", "completed")
        block = store.format_for_prompt()  # 注入 system prompt
    """

    workspace: str
    todos: list[TodoItem] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _path: Path | None = field(default=None, repr=False)

    def __post_init__(self):
        self._path = Path(self.workspace) / ".fnix" / "todos.json"
        self._load()

    def _load(self):
        """从磁盘加载 todos.json。"""
        if not self._path or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self.todos = [
                TodoItem(
                    id=str(item.get("id", "")),
                    content=str(item.get("content", "")),
                    status=str(item.get("status", "pending")),
                    priority=str(item.get("priority", "medium")),
                    created_at=float(item.get("created_at", 0.0)),
                    updated_at=float(item.get("updated_at", 0.0)),
                    completed_at=float(item.get("completed_at", 0.0)),
                    note=str(item.get("note", "")),
                )
                for item in (data.get("todos") or [])
            ]
        except Exception as e:
            logger.warning("TodoStore load failed: %s", e)
            self.todos = []

    def _save(self):
        """持久化到磁盘 (原子写)。"""
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {"todos": [asdict(t) for t in self.todos], "version": 1}
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            logger.warning("TodoStore save failed: %s", e)

    def add(self, todo: TodoItem) -> bool:
        """添加待办事项。相同 id 不重复添加。"""
        if not todo.id or not todo.content:
            return False
        now = time.time()
        if todo.created_at == 0.0:
            todo.created_at = now
        todo.updated_at = now
        with self._lock:
            for existing in self.todos:
                if existing.id == todo.id:
                    return False
            self.todos.append(todo)
            self._save()
            return True

    def update_status(
        self,
        todo_id: str,
        status: str,
        note: str = "",
    ) -> bool:
        """更新待办状态。status ∈ {pending, in_progress, completed, failed}。"""
        if status not in ("pending", "in_progress", "completed", "failed"):
            return False
        now = time.time()
        with self._lock:
            for t in self.todos:
                if t.id == todo_id:
                    t.status = status
                    t.updated_at = now
                    if note:
                        t.note = note[:500]
                    if status in ("completed", "failed"):
                        t.completed_at = now
                    self._save()
                    return True
            return False

    def remove(self, todo_id: str) -> bool:
        """删除待办事项。"""
        with self._lock:
            before = len(self.todos)
            self.todos = [t for t in self.todos if t.id != todo_id]
            if len(self.todos) < before:
                self._save()
                return True
            return False

    def clear_completed(self) -> int:
        """清除已完成的待办, 返回清除数量。"""
        with self._lock:
            before = len(self.todos)
            self.todos = [t for t in self.todos if t.status not in ("completed", "failed")]
            cleared = before - len(self.todos)
            if cleared > 0:
                self._save()
            return cleared

    def clear(self) -> None:
        """清空全部待办 (Code 模式新任务 plan 阶段重建用)。"""
        with self._lock:
            self.todos = []
            self._save()

    def get_pending(self) -> list[TodoItem]:
        """获取未完成的待办。"""
        with self._lock:
            return [t for t in self.todos if t.status in ("pending", "in_progress")]

    def get_in_progress(self) -> TodoItem | None:
        """获取当前进行中的待办 (对齐 : 每轮只做一个 feature)。"""
        with self._lock:
            for t in self.todos:
                if t.status == "in_progress":
                    return t
            return None

    def format_for_prompt(self) -> str:
        """格式化为 system prompt 注入块 (任务状态外化)。

        compaction 后重新调用此方法, 确保 load-bearing state 不丢失。
        """
        with self._lock:
            if not self.todos:
                return ""
            lines = ["\n\n## 当前任务清单 (load-bearing state, compaction 后保留)"]
            for i, t in enumerate(self.todos, 1):
                status_icon = {
                    "pending": "○",
                    "in_progress": "◐",
                    "completed": "●",
                    "failed": "✗",
                }.get(t.status, "○")
                priority_tag = f"[{t.priority}]" if t.priority != "medium" else ""
                lines.append(f"{i}. {status_icon} {priority_tag} {t.content}")
                if t.note:
                    lines.append(f"   备注: {t.note}")
            pending_count = sum(1 for t in self.todos if t.status in ("pending", "in_progress"))
            completed_count = sum(1 for t in self.todos if t.status == "completed")
            lines.append(f"\n进度: {completed_count}/{len(self.todos)} 完成, {pending_count} 待办")
            if pending_count > 0:
                lines.append("每轮专注推进一个待办, 完成后更新状态。")
            return "\n".join(lines)

    def stats(self) -> dict:
        """统计信息 (用于 UI 展示)。"""
        with self._lock:
            return {
                "total": len(self.todos),
                "pending": sum(1 for t in self.todos if t.status == "pending"),
                "in_progress": sum(1 for t in self.todos if t.status == "in_progress"),
                "completed": sum(1 for t in self.todos if t.status == "completed"),
                "failed": sum(1 for t in self.todos if t.status == "failed"),
            }


__all__ = ["TodoItem", "TodoStore"]
