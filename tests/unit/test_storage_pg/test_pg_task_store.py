"""
PgTaskStore 单元测试。

验证:
  - create / get / start
  - add_step / update_step
  - complete / fail / cancel / retry
  - list(过滤/分页)
  - get_status(进度计算)
  - 数据持久化
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.services.storage_pg import PgTaskStore


class TestPgTaskStoreCreate:
    """任务创建。"""

    def test_create_returns_task_with_id(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="search_paper", user_id=1)
        assert task.id > 0
        assert task.session_id == 1
        assert task.user_id == 1
        assert task.intent == "search_paper"
        assert task.status == "pending"
        assert task.reasoning_mode == "react"

    def test_create_with_custom_mode(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(
            session_id=1, intent="edit_doc", reasoning_mode="plan_execute", user_id=1
        )
        assert task.reasoning_mode == "plan_execute"

    def test_count_starts_at_zero(self, db_adapter):
        store = PgTaskStore(db_adapter)
        assert store.count == 0

    def test_count_increments(self, db_adapter):
        store = PgTaskStore(db_adapter)
        store.create(session_id=1, intent="a", user_id=1)
        store.create(session_id=1, intent="b", user_id=1)
        assert store.count == 2


class TestPgTaskStoreGet:
    """任务查询。"""

    def test_get_existing(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        fetched = store.get(task.id)
        assert fetched is not None
        assert fetched.intent == "test"

    def test_get_nonexistent(self, db_adapter):
        store = PgTaskStore(db_adapter)
        assert store.get(99999) is None

    def test_get_includes_steps(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.add_step(task.id, "Step 1")
        store.add_step(task.id, "Step 2")
        fetched = store.get(task.id)
        assert len(fetched.steps) == 2
        assert fetched.steps[0].step_no == 1
        assert fetched.steps[1].step_no == 2


class TestPgTaskStoreLifecycle:
    """任务生命周期。"""

    def test_start_changes_status_to_running(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        started = store.start(task.id)
        assert started.status == "running"
        assert started.started_at is not None

    def test_complete_changes_status_to_succeeded(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        result = {"summary": "Done"}
        completed = store.complete(task.id, result=result)
        assert completed.status == "succeeded"
        assert completed.finished_at is not None
        assert completed.result == result

    def test_fail_changes_status_to_failed(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        failed = store.fail(task.id, "Tool error")
        assert failed.status == "failed"
        assert failed.error == "Tool error"
        assert failed.finished_at is not None

    def test_cancel_pending_task(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        cancelled = store.cancel(task.id)
        assert cancelled.status == "cancelled"

    def test_cancel_running_task(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        cancelled = store.cancel(task.id)
        assert cancelled.status == "cancelled"

    def test_cancel_succeeded_rejected(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        store.complete(task.id)
        assert store.cancel(task.id) is None

    def test_cancel_failed_rejected(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        store.fail(task.id, "error")
        assert store.cancel(task.id) is None

    def test_retry_resets_status(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        store.fail(task.id, "error")
        retried = store.retry(task.id)
        assert retried.status == "pending"
        assert retried.started_at is None
        assert retried.finished_at is None
        assert retried.error == ""


class TestPgTaskStoreSteps:
    """任务步骤管理。"""

    def test_add_step_increments_step_no(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        s1 = store.add_step(task.id, "Step 1", "search")
        s2 = store.add_step(task.id, "Step 2", "edit")
        assert s1.step_no == 1
        assert s2.step_no == 2

    def test_add_step_to_nonexistent_task(self, db_adapter):
        store = PgTaskStore(db_adapter)
        assert store.add_step(99999, "Step") is None

    def test_update_step_status(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        step = store.add_step(task.id, "Step 1", "search")
        ok = store.update_step(task.id, step.step_no, "running")
        assert ok is True

    def test_update_step_nonexistent(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        assert store.update_step(task.id, 999, "running") is False

    def test_retry_resets_steps(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.add_step(task.id, "Step 1")
        store.update_step(task.id, 1, "failed")
        store.fail(task.id, "error")
        retried = store.retry(task.id)
        assert all(s.status == "pending" for s in retried.steps)


class TestPgTaskStoreList:
    """任务列表。"""

    def test_list_empty(self, db_adapter):
        store = PgTaskStore(db_adapter)
        assert len(store.list()) == 0

    def test_list_all(self, db_adapter):
        store = PgTaskStore(db_adapter)
        store.create(session_id=1, intent="a", user_id=1)
        store.create(session_id=1, intent="b", user_id=1)
        assert len(store.list()) == 2

    def test_list_filter_by_user(self, db_adapter):
        store = PgTaskStore(db_adapter)
        store.create(session_id=1, intent="a", user_id=1)
        store.create(session_id=1, intent="b", user_id=2)
        assert len(store.list(user_id=1)) == 1

    def test_list_filter_by_status(self, db_adapter):
        store = PgTaskStore(db_adapter)
        t1 = store.create(session_id=1, intent="a", user_id=1)
        store.create(session_id=1, intent="b", user_id=1)
        store.start(t1.id)
        assert len(store.list(status="running")) == 1
        assert len(store.list(status="pending")) == 1

    def test_list_sorted_by_created_at_desc(self, db_adapter):
        store = PgTaskStore(db_adapter)
        t1 = store.create(session_id=1, intent="first", user_id=1)
        t2 = store.create(session_id=1, intent="second", user_id=1)
        tasks = store.list()
        assert tasks[0].id == t2.id  # 最新的在前
        assert tasks[1].id == t1.id


class TestPgTaskStoreStatus:
    """任务状态摘要。"""

    def test_status_pending_no_steps(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        status = store.get_status(task.id)
        assert status["status"] == "pending"
        assert status["progress"] == 0.0
        assert status["total_steps"] is None

    def test_status_with_steps(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.add_step(task.id, "Step 1")
        store.add_step(task.id, "Step 2")
        store.update_step(task.id, 1, "success")
        status = store.get_status(task.id)
        assert status["total_steps"] == 2
        assert status["progress"] == 0.5

    def test_status_nonexistent_task(self, db_adapter):
        store = PgTaskStore(db_adapter)
        assert store.get_status(99999) is None

    def test_status_succeeded_no_steps_progress_1(self, db_adapter):
        store = PgTaskStore(db_adapter)
        task = store.create(session_id=1, intent="test", user_id=1)
        store.start(task.id)
        store.complete(task.id)
        status = store.get_status(task.id)
        assert status["progress"] == 1.0


class TestPgTaskStorePersistence:
    """数据持久化。"""

    def test_tasks_survive_adapter_restart(self, db_adapter):
        store1 = PgTaskStore(db_adapter)
        task = store1.create(session_id=1, intent="persist", user_id=1)
        store1.add_step(task.id, "Step 1")

        store2 = PgTaskStore(db_adapter)
        fetched = store2.get(task.id)
        assert fetched is not None
        assert fetched.intent == "persist"
        assert len(fetched.steps) == 1
