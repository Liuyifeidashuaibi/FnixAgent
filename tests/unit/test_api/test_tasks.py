"""
tasks 路由单元测试。

覆盖:
  - 创建任务(成功/参数校验)
  - 查询任务(成功/不存在)
  - 任务状态查询
  - 步骤管理(添加/查询)
  - 任务生命周期(start/complete/fail/cancel/retry)
  - 列表查询(过滤)
"""
import pytest


class TestCreateTask:
    """任务创建。"""

    def test_create_task_default_mode(self, client):
        resp = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "论文检索"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == 1
        assert data["intent"] == "论文检索"
        assert data["reasoning_mode"] == "react"  # 默认
        assert data["status"] == "pending"
        assert data["id"] >= 1

    def test_create_task_with_mode(self, client):
        resp = client.post(
            "/api/v1/tasks/",
            json={
                "session_id": 2,
                "intent": "Word编辑",
                "reasoning_mode": "plan_execute",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["reasoning_mode"] == "plan_execute"

    def test_create_task_alt_route(self, client):
        """别名路由 /tasks/create。"""
        resp = client.post(
            "/api/v1/tasks/create",
            json={"session_id": 1, "intent": "测试"},
        )
        assert resp.status_code == 200


class TestGetTask:
    def test_get_existing(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        resp = client.get(f"/api/v1/tasks/{tid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == tid

    def test_get_not_found(self, client):
        resp = client.get("/api/v1/tasks/9999")
        assert resp.status_code == 404


class TestTaskStatus:
    def test_status_pending(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        resp = client.get(f"/api/v1/tasks/{tid}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["progress"] == 0.0

    def test_status_with_steps(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        # 添加 2 步
        client.post(f"/api/v1/tasks/{tid}/steps", params={"description": "step1", "tool_name": "tool_a"})
        client.post(f"/api/v1/tasks/{tid}/steps", params={"description": "step2", "tool_name": "tool_b"})
        resp = client.get(f"/api/v1/tasks/{tid}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_steps"] == 2

    def test_status_task_not_found(self, client):
        resp = client.get("/api/v1/tasks/9999/status")
        assert resp.status_code == 404


class TestTaskSteps:
    def test_add_and_list_steps(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]

        # 添加步骤
        s1 = client.post(
            f"/api/v1/tasks/{tid}/steps",
            params={"description": "搜索论文", "tool_name": "search_paper"},
        )
        assert s1.status_code == 200
        assert s1.json()["step_no"] == 1

        s2 = client.post(
            f"/api/v1/tasks/{tid}/steps",
            params={"description": "下载PDF", "tool_name": "download"},
        )
        assert s2.json()["step_no"] == 2

        # 查询步骤
        resp = client.get(f"/api/v1/tasks/{tid}/steps")
        assert resp.status_code == 200
        steps = resp.json()
        assert len(steps) == 2
        assert steps[0]["description"] == "搜索论文"
        assert steps[1]["tool_name"] == "download"

    def test_steps_for_nonexistent_task(self, client):
        resp = client.get("/api/v1/tasks/9999/steps")
        assert resp.status_code == 404


class TestTaskLifecycle:
    """任务生命周期: pending → running → succeeded/failed。"""

    def test_full_success_flow(self, client):
        # 1. 创建
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        assert create.json()["status"] == "pending"

        # 2. 启动
        start = client.post(f"/api/v1/tasks/{tid}/start")
        assert start.status_code == 200
        assert start.json()["status"] == "running"
        assert start.json()["started_at"] is not None

        # 3. 完成
        complete = client.post(
            f"/api/v1/tasks/{tid}/complete",
            json={"answer": "done"},
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "succeeded"
        assert complete.json()["finished_at"] is not None

    def test_fail_flow(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/start")
        fail = client.post(
            f"/api/v1/tasks/{tid}/fail",
            params={"error": "工具执行超时"},
        )
        assert fail.status_code == 200
        assert fail.json()["status"] == "failed"

    def test_start_non_pending_rejected(self, client):
        """已 running 的任务不能再次 start。"""
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/start")
        resp = client.post(f"/api/v1/tasks/{tid}/start")
        assert resp.status_code == 409


class TestCancelTask:
    def test_cancel_pending(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        resp = client.post(f"/api/v1/tasks/{tid}/cancel")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        # 确认状态
        assert client.get(f"/api/v1/tasks/{tid}").json()["status"] == "cancelled"

    def test_cancel_running(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/start")
        resp = client.post(f"/api/v1/tasks/{tid}/cancel")
        assert resp.status_code == 200

    def test_cancel_succeeded_rejected(self, client):
        """已成功的任务不能取消。"""
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/start")
        client.post(f"/api/v1/tasks/{tid}/complete", json={})
        resp = client.post(f"/api/v1/tasks/{tid}/cancel")
        assert resp.status_code == 409

    def test_cancel_not_found(self, client):
        resp = client.post("/api/v1/tasks/9999/cancel")
        assert resp.status_code == 404


class TestRetryTask:
    def test_retry_failed_task(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/start")
        client.post(f"/api/v1/tasks/{tid}/fail", params={"error": "err"})

        # 重试
        resp = client.post(f"/api/v1/tasks/{tid}/retry")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["started_at"] is None
        assert data["finished_at"] is None

    def test_retry_resets_steps(self, client):
        create = client.post(
            "/api/v1/tasks/",
            json={"session_id": 1, "intent": "X"},
        )
        tid = create.json()["id"]
        client.post(f"/api/v1/tasks/{tid}/steps", params={"description": "s1"})
        client.post(f"/api/v1/tasks/{tid}/start")
        client.post(f"/api/v1/tasks/{tid}/fail", params={"error": "err"})

        client.post(f"/api/v1/tasks/{tid}/retry")
        steps = client.get(f"/api/v1/tasks/{tid}/steps").json()
        # 步骤记录保留,但状态重置为 pending
        assert all(s["status"] == "pending" for s in steps)


class TestListTasks:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/tasks/list")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_tasks(self, client):
        client.post("/api/v1/tasks/", json={"session_id": 1, "intent": "A"})
        client.post("/api/v1/tasks/", json={"session_id": 2, "intent": "B"})
        resp = client.get("/api/v1/tasks/list")
        assert len(resp.json()) == 2

    def test_list_filter_by_status(self, client):
        t1 = client.post("/api/v1/tasks/", json={"session_id": 1, "intent": "A"}).json()["id"]
        client.post("/api/v1/tasks/", json={"session_id": 2, "intent": "B"})
        # 把第一个跑成功
        client.post(f"/api/v1/tasks/{t1}/start")
        client.post(f"/api/v1/tasks/{t1}/complete", json={})

        # 过滤 succeeded
        resp = client.get("/api/v1/tasks/list?status=succeeded")
        assert len(resp.json()) == 1
        assert resp.json()[0]["status"] == "succeeded"

        # 过滤 pending
        resp = client.get("/api/v1/tasks/list?status=pending")
        assert len(resp.json()) == 1
        assert resp.json()[0]["status"] == "pending"
