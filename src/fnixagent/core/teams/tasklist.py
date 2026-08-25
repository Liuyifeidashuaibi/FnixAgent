"""共享任务清单 — 团队协作的协调骨干。

对齐 Claude Code Agent Teams 的任务清单语义:
  - 三态: pending / in_progress / completed (+ failed / blocked 派生态)
  - 依赖: depends_on 中全部 completed 后任务才可认领(自动解锁)
  - 认领: 原子性由"版本号乐观锁"保证 —— 读(version=v) → 改 → 写前校验 v
    未变才落盘; 冲突则重读重试(规避 Claude Code 裸文件锁的 ~50ms 双抢竞态)

存储: {team_dir}/tasks.json, 原子写(tmp + os.replace)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_progress", "failed", "cancelled"},
    "in_progress": {"completed", "failed", "pending"},  # 失败可退回待办供他人接手
    "completed": set(),
    "failed": {"pending"},  # 可重开
    "blocked": {"pending"},
    "cancelled": set(),
}


class TaskListConflict(Exception):
    """乐观锁冲突(并发写竞争, 重试即可)。"""


class SharedTaskList:
    """团队共享任务清单(JSON 文件持久化 + 版本号乐观锁)。"""

    def __init__(self, team_dir: str) -> None:
        self._dir = str(team_dir)
        self._path = os.path.join(self._dir, "tasks.json")
        self._lock = threading.Lock()  # 进程内串行化; 跨进程靠版本号
        os.makedirs(self._dir, exist_ok=True)
        if not os.path.exists(self._path):
            self._write({"version": 0, "seq": 0, "tasks": []})

    # -- 底层读写 ------------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"version": 0, "seq": 0, "tasks": []}

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path)  # 同卷原子替换

    def _mutate(self, mutator, *, retries: int = 6) -> Any:
        """带跨进程乐观校验的读-改-写。

        - 进程内锁串行化;
        - 写前重读磁盘比对 version, 检测跨进程并发修改并退避重试;
        - mutator 抛 TaskListConflict 时仍持久化已发生的部分变更
          (如 claim 因依赖未满足而写入的 blocked 标记), 再向上传播。
        """
        last_err: TaskListConflict | None = None
        for attempt in range(retries):
            with self._lock:
                data = self._read()
                version = int(data.get("version", 0))
                try:
                    result = mutator(data)
                except TaskListConflict:
                    self._write(data)  # 持久化部分变更(blocked 等)
                    raise
                # 跨进程乐观校验
                if int(self._read().get("version", 0)) != version:
                    last_err = TaskListConflict("concurrent modification detected")
                    time.sleep(0.005 * (attempt + 1))  # 线性退避
                    continue
                data["version"] = version + 1
                self._write(data)
                return result
        raise last_err or TaskListConflict(f"task list busy after {retries} retries")

    # -- 对外操作 ------------------------------------------------------------

    def create_batch(self, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """批量创建任务。spec: {subject, detail?, depends_on?, priority?}"""

        def _add(data: dict[str, Any]) -> list[dict[str, Any]]:
            seq = int(data.get("seq", 0))
            now = time.time()
            created = []
            for spec in specs:
                seq += 1
                task = {
                    "id": f"T{seq}",
                    "subject": str(spec.get("subject", ""))[:300],
                    "detail": str(spec.get("detail", ""))[:4000],
                    "status": "pending",
                    "depends_on": list(spec.get("depends_on") or []),
                    "priority": float(spec.get("priority", 0)),
                    "claimed_by": "",
                    "result_summary": "",
                    "artifact_path": "",
                    "error": "",
                    "created_at": now,
                    "updated_at": now,
                }
                data["tasks"].append(task)
                created.append(dict(task))
            data["seq"] = seq
            return created

        return self._mutate(_add)

    def _find(self, data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
        for t in data["tasks"]:
            if t["id"] == task_id:
                return t
        return None

    def _deps_satisfied(self, data: dict[str, Any], task: dict[str, Any]) -> bool:
        for dep_id in task.get("depends_on") or []:
            dep = self._find(data, dep_id)
            if dep is None or dep["status"] != "completed":
                return False
        return True

    def claim(self, task_id: str, agent: str) -> dict[str, Any]:
        """认领任务: 仅 pending 且依赖已满足时可认领 → in_progress。"""

        def _claim(data: dict[str, Any]) -> dict[str, Any]:
            task = self._require(data, task_id)
            if task["status"] != "pending":
                raise TaskListConflict(f"{task_id} 状态为 {task['status']}, 不可认领")
            if not self._deps_satisfied(data, task):
                missing = [
                    d
                    for d in task["depends_on"]
                    if (self._find(data, d) or {}).get("status") != "completed"
                ]
                task["status"] = "blocked"
                task["updated_at"] = time.time()
                raise TaskListConflict(f"{task_id} 依赖未完成: {missing}")
            task["status"] = "in_progress"
            task["claimed_by"] = agent
            task["updated_at"] = time.time()
            return dict(task)

        return self._mutate(_claim)

    def complete(
        self,
        task_id: str,
        agent: str,
        result_summary: str = "",
        artifact_path: str = "",
    ) -> dict[str, Any]:
        """完成任务(仅认领者本人)。依赖它的 pending 任务自动回到可认领态。"""

        def _complete(data: dict[str, Any]) -> dict[str, Any]:
            task = self._require(data, task_id)
            if task["status"] not in ("in_progress", "blocked"):
                raise TaskListConflict(f"{task_id} 状态为 {task['status']}, 不可完成")
            if task.get("claimed_by") and task["claimed_by"] != agent:
                raise TaskListConflict(f"{task_id} 由 {task['claimed_by']} 认领, 非 {agent}")
            task["status"] = "completed"
            task["result_summary"] = str(result_summary)[:2000]
            task["artifact_path"] = str(artifact_path)[:1000]
            task["updated_at"] = time.time()
            # 解锁因它而 blocked 的后继
            for other in data["tasks"]:
                if (
                    other["status"] == "blocked"
                    and task_id in (other.get("depends_on") or [])
                    and self._deps_satisfied(data, other)
                ):
                    other["status"] = "pending"
                    other["updated_at"] = time.time()
            return dict(task)

        return self._mutate(_complete)

    def fail(self, task_id: str, agent: str, error: str = "", *, retryable: bool = True) -> dict[str, Any]:
        """标记失败。

        Args:
            retryable: True=退回 pending 供重试/他人接手(如 LLM 瞬断);
                       False=终态 failed(如角色不存在, 重试无意义)。
        """

        def _fail(data: dict[str, Any]) -> dict[str, Any]:
            task = self._require(data, task_id)
            if task["status"] not in ("in_progress", "pending", "blocked"):
                raise TaskListConflict(f"{task_id} 状态为 {task['status']}, 不可标失败")
            task["status"] = "pending" if retryable else "failed"
            if not retryable:
                task["claimed_by"] = agent or task.get("claimed_by", "")
            else:
                task["claimed_by"] = ""
            task["error"] = str(error)[:2000]
            task["updated_at"] = time.time()
            return dict(task)

        return self._mutate(_fail)

    def get(self, task_id: str) -> dict[str, Any] | None:
        data = self._read()
        task = self._find(data, task_id)
        return dict(task) if task else None

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(t) for t in self._read().get("tasks", [])]

    def available(self) -> list[dict[str, Any]]:
        """当前可认领(pending 且依赖满足), 按优先级降序。"""
        data = self._read()
        ready = [
            dict(t)
            for t in data.get("tasks", [])
            if t["status"] == "pending" and self._deps_satisfied(data, t)
        ]
        ready.sort(key=lambda t: -t.get("priority", 0))
        return ready

    def stats(self) -> dict[str, Any]:
        tasks = self.list_all()
        by_status: dict[str, int] = {}
        for t in tasks:
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        done = by_status.get("completed", 0)
        return {
            "total": len(tasks),
            "by_status": by_status,
            "completed_ratio": round(done / len(tasks), 3) if tasks else 0.0,
        }

    def _require(self, data: dict[str, Any], task_id: str) -> dict[str, Any]:
        task = self._find(data, task_id)
        if task is None:
            raise KeyError(f"任务不存在: {task_id}")
        return task


__all__ = ["SharedTaskList", "TaskListConflict"]
