"""TodoStore 单元测试 — load-bearing state 外化 (对标 Claude Code TodoWrite)。

覆盖:
- add / update_status / remove / clear_completed
- get_pending / get_in_progress
- format_for_prompt (system prompt 注入)
- 持久化 (磁盘读写)
- 线程安全

设计原则: 纯本地逻辑, 无 LLM/网络依赖。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from fnixagent.core.skills.todos import TodoItem, TodoStore


@pytest.fixture
def store(tmp_path: Path) -> TodoStore:
    return TodoStore(str(tmp_path))


class TestAdd:
    def test_add_basic(self, store: TodoStore):
        item = TodoItem(id="t1", content="读取 sales.xlsx")
        assert store.add(item) is True
        assert len(store.todos) == 1
        assert store.todos[0].created_at > 0

    def test_add_duplicate_id_rejected(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务1"))
        assert store.add(TodoItem(id="t1", content="重复")) is False
        assert len(store.todos) == 1

    def test_add_empty_id_rejected(self, store: TodoStore):
        assert store.add(TodoItem(id="", content="x")) is False

    def test_add_empty_content_rejected(self, store: TodoStore):
        assert store.add(TodoItem(id="t1", content="")) is False


class TestUpdateStatus:
    def test_update_to_in_progress(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        assert store.update_status("t1", "in_progress") is True
        assert store.todos[0].status == "in_progress"
        assert store.todos[0].updated_at > 0

    def test_update_to_completed(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        store.update_status("t1", "completed")
        assert store.todos[0].status == "completed"
        assert store.todos[0].completed_at > 0

    def test_update_to_failed_with_note(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        store.update_status("t1", "failed", note="文件不存在")
        assert store.todos[0].status == "failed"
        assert store.todos[0].note == "文件不存在"

    def test_update_invalid_status_rejected(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        assert store.update_status("t1", "invalid") is False

    def test_update_nonexistent_rejected(self, store: TodoStore):
        assert store.update_status("nonexistent", "completed") is False


class TestRemove:
    def test_remove_existing(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        assert store.remove("t1") is True
        assert len(store.todos) == 0

    def test_remove_nonexistent(self, store: TodoStore):
        assert store.remove("nonexistent") is False


class TestClearCompleted:
    def test_clear_completed(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务1"))
        store.add(TodoItem(id="t2", content="任务2"))
        store.add(TodoItem(id="t3", content="任务3"))
        store.update_status("t1", "completed")
        store.update_status("t2", "failed")
        cleared = store.clear_completed()
        assert cleared == 2
        assert len(store.todos) == 1

    def test_clear_when_none_completed(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        assert store.clear_completed() == 0


class TestQueries:
    def test_get_pending(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务1"))
        store.add(TodoItem(id="t2", content="任务2"))
        store.update_status("t1", "completed")
        pending = store.get_pending()
        assert len(pending) == 1
        assert pending[0].id == "t2"

    def test_get_in_progress(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务1"))
        store.add(TodoItem(id="t2", content="任务2"))
        store.update_status("t1", "in_progress")
        in_progress = store.get_in_progress()
        assert in_progress is not None
        assert in_progress.id == "t1"

    def test_get_in_progress_none(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务"))
        assert store.get_in_progress() is None


class TestFormatForPrompt:
    def test_empty_store(self, store: TodoStore):
        assert store.format_for_prompt() == ""

    def test_with_todos(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="读取文件", priority="high"))
        store.add(TodoItem(id="t2", content="生成报告"))
        store.update_status("t1", "completed")
        block = store.format_for_prompt()
        assert "当前任务清单" in block
        assert "读取文件" in block
        assert "生成报告" in block
        assert "进度" in block
        assert "1/2 完成" in block

    def test_status_icons(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="待办"))
        store.add(TodoItem(id="t2", content="进行中"))
        store.add(TodoItem(id="t3", content="完成"))
        store.add(TodoItem(id="t4", content="失败"))
        store.update_status("t2", "in_progress")
        store.update_status("t3", "completed")
        store.update_status("t4", "failed")
        block = store.format_for_prompt()
        assert "○" in block  # pending
        assert "◐" in block  # in_progress
        assert "●" in block  # completed
        assert "✗" in block  # failed


class TestPersistence:
    def test_save_and_reload(self, tmp_path: Path):
        store1 = TodoStore(str(tmp_path))
        store1.add(TodoItem(id="t1", content="持久化任务", priority="high"))
        store1.update_status("t1", "in_progress")

        store2 = TodoStore(str(tmp_path))
        assert len(store2.todos) == 1
        assert store2.todos[0].id == "t1"
        assert store2.todos[0].content == "持久化任务"
        assert store2.todos[0].status == "in_progress"
        assert store2.todos[0].priority == "high"

    def test_corrupted_file_handled(self, tmp_path: Path):
        """损坏的 todos.json 应静默降级为空列表, 不抛异常。"""
        fnix_dir = tmp_path / ".fnix"
        fnix_dir.mkdir(parents=True)
        (fnix_dir / "todos.json").write_text("not valid json {", encoding="utf-8")
        store = TodoStore(str(tmp_path))
        assert store.todos == []

    def test_no_file_starts_empty(self, tmp_path: Path):
        store = TodoStore(str(tmp_path))
        assert store.todos == []


class TestStats:
    def test_stats_structure(self, store: TodoStore):
        store.add(TodoItem(id="t1", content="任务1"))
        store.add(TodoItem(id="t2", content="任务2"))
        store.add(TodoItem(id="t3", content="任务3"))
        store.update_status("t1", "completed")
        store.update_status("t2", "in_progress")
        store.update_status("t3", "failed")
        stats = store.stats()
        assert stats["total"] == 3
        assert stats["pending"] == 0
        assert stats["in_progress"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1


class TestThreadSafety:
    def test_concurrent_adds(self, tmp_path: Path):
        store = TodoStore(str(tmp_path))
        errors: list[Exception] = []

        def worker(idx: int):
            try:
                store.add(TodoItem(id=f"t{idx}", content=f"任务{idx}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发不应产生异常: {errors}"
        assert len(store.todos) == 20

    def test_concurrent_update_same_todo(self, tmp_path: Path):
        store = TodoStore(str(tmp_path))
        store.add(TodoItem(id="t1", content="任务"))
        errors: list[Exception] = []

        def worker(status: str):
            try:
                store.update_status("t1", status)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=("in_progress",)),
            threading.Thread(target=worker, args=("completed",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert store.todos[0].status in ("in_progress", "completed")
