"""AgentTeam 编排器 — Orchestrator-Worker 模式的落地实现。

职责:
  - 管理团队目录({workspace}/.fnix/teams/{run_id}/)
  - fan_out: 角色化工人并行执行子任务(信号量背压 + 总步数预算 + 墙钟超时)
  - 每个工人生命周期自动联动共享任务清单(认领→完成/失败→解锁后继)
  - 工人产出写结构化交接黑板; 失败自动投递信箱通知 lead

红线(与业界共识一致):
  - 团队工具只注册给主循环; 工人注册表由 SubagentManager 构造,
    天然不含团队工具 → 无嵌套团队
  - 工人写操作仍走 ToolPolicy/HITL 门
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fnixagent.core.agent.subagent import SubagentManager
from fnixagent.core.teams.blackboard import write_handover
from fnixagent.core.teams.ledger import TeamOrchestratorLedger
from fnixagent.core.teams.mailbox import Mailbox
from fnixagent.core.teams.profiles import get_profile
from fnixagent.core.teams.tasklist import SharedTaskList, TaskListConflict

_logger = logging.getLogger(__name__)

LEAD_NAME = "lead"


class AgentTeam:
    """一次协作会话的编排器(一个实例对应一个团队运行)。"""

    def __init__(
        self,
        workspace_root: str,
        llm_factory: Callable[[], tuple[Callable[..., Any], Callable[..., Any] | None]],
        *,
        team_dir: str | None = None,
        max_parallel: int = 3,
        max_total_steps: int = 80,
        wall_timeout_s: float = 900.0,
    ) -> None:
        self.workspace_root = str(workspace_root)
        self._llm_factory = llm_factory
        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self.team_dir = team_dir or str(
            Path(workspace_root) / ".fnix" / "teams" / run_id
        )
        os.makedirs(self.team_dir, exist_ok=True)
        self.tasks = SharedTaskList(self.team_dir)
        self.mailbox = Mailbox(self.team_dir)
        # Magentic-One 式双账本: 跨波次进度追踪 + 卡死检测(阈值≤2, 论文实验值)
        self.ledger = TeamOrchestratorLedger(self.team_dir, max_stall_rounds=2)
        self.max_parallel = max(1, int(max_parallel))
        self.max_total_steps = max(3, int(max_total_steps))
        self.wall_timeout_s = float(wall_timeout_s)

    # -- 工人运行 --------------------------------------------------------------

    async def _run_worker(
        self,
        spec: dict[str, Any],
        task_id: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        """单个工人的完整生命周期: 认领→执行→黑板→清单回写。"""
        role_name = str(spec.get("role", "researcher"))
        profile = get_profile(role_name)
        if profile is None:
            # 未知角色: 清单标失败 + 通知 lead, 保持账实一致
            err = f"未知角色: {role_name}"
            try:
                self.tasks.fail(task_id, agent="system", error=err, retryable=False)
            except TaskListConflict:
                pass
            self.mailbox.send(
                from_agent="system",
                to_agent=LEAD_NAME,
                content=f"任务 {task_id}({spec.get('subject','')}) 派发失败: {err}",
                msg_type="failure",
                meta={"task_id": task_id},
            )
            return {
                "task_id": task_id,
                "role": role_name,
                "status": "failed",
                "summary": "",
                "artifact_path": "",
                "error": err,
            }

        manager = SubagentManager(
            self._llm_factory,
            self.workspace_root,
            allowed_tools=profile.tools,
            system_prompt=profile.system_prompt,
        )

        async with semaphore:
            started = time.time()
            try:
                self.tasks.claim(task_id, agent=f"{role_name}-{task_id}")
            except TaskListConflict as exc:
                return {
                    "task_id": task_id,
                    "role": role_name,
                    "status": "skipped",
                    "summary": "",
                    "artifact_path": "",
                    "error": str(exc),
                }

            try:
                result = await manager.run_subtask(
                    description=spec.get("subject", ""),
                    prompt=str(spec.get("prompt", "")),
                    max_steps=int(spec.get("max_steps") or profile.max_steps),
                )
            except Exception as exc:  # noqa: BLE001 — 工人异常不拖垮整体
                result = {
                    "success": False,
                    "result": "",
                    "steps": 0,
                    "duration_ms": 0.0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            duration_ms = (time.time() - started) * 1000.0

            success = bool(result.get("success"))
            body = str(result.get("result", ""))
            artifact = write_handover(
                self.team_dir,
                task_id=task_id,
                agent=f"{role_name}-{task_id}",
                role=role_name,
                status="success" if success else "failed",
                content=body or result.get("error", ""),
                duration_ms=duration_ms,
                extra_meta={"steps": result.get("steps", 0)},
            )
            summary = body[:500]

            if success:
                self.tasks.complete(task_id, agent=f"{role_name}-{task_id}",
                                    result_summary=summary, artifact_path=artifact)
            else:
                err = str(result.get("error", "worker failed"))
                self.tasks.fail(task_id, agent=f"{role_name}-{task_id}", error=err)
                # 失败必须让 lead 知道(Claude Code Teams 同款语义)
                self.mailbox.send(
                    from_agent=f"{role_name}-{task_id}",
                    to_agent=LEAD_NAME,
                    content=f"任务 {task_id}({spec.get('subject','')}) 失败: {err[:300]}",
                    msg_type="failure",
                    meta={"task_id": task_id},
                )

            return {
                "task_id": task_id,
                "role": role_name,
                "status": "success" if success else "failed",
                "summary": summary,
                "artifact_path": artifact,
                "error": "" if success else str(result.get("error", "")),
                "steps": result.get("steps", 0),
            }

    # -- 核心入口 ---------------------------------------------------------------

    async def fan_out(self, specs: list[dict[str, Any]]) -> dict[str, Any]:
        """并行派发子任务并汇合(阻塞式)。

        Args:
            specs: [{role, subject, prompt, max_steps?}, ...]

        Returns:
            {team_dir, results: [...], stats}
        """
        if not specs:
            return {
                "team_dir": self.team_dir,
                "results": [],
                "stats": self.tasks.stats(),
                "wave": {"wave": 0, "success": 0, "failed": 0, "skipped": 0},
                "progress": self.ledger.evaluate(self.tasks.stats()).to_dict(),
            }
        # 总步数预算约束
        budget_left = self.max_total_steps
        normalized: list[dict[str, Any]] = []
        for spec in specs[:12]:  # 单批上限, 防失控
            s = dict(spec)
            steps = int(s.get("max_steps") or 15)
            s["max_steps"] = max(3, min(steps, budget_left)) if budget_left > 0 else 0
            budget_left -= s["max_steps"]
            if s["max_steps"] <= 0:
                break
            normalized.append(s)

        created = self.tasks.create_batch(
            [
                {
                    "subject": s.get("subject", ""),
                    "detail": s.get("prompt", "")[:1000],
                    "priority": float(s.get("priority", i)),
                }
                for i, s in enumerate(normalized)
            ]
        )

        semaphore = asyncio.Semaphore(self.max_parallel)
        pairs = [(spec, task["id"]) for spec, task in zip(normalized, created)]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(self._run_worker(spec, tid, semaphore) for spec, tid in pairs),
                    return_exceptions=True,
                ),
                timeout=self.wall_timeout_s,
            )
        except TimeoutError:
            results = [
                {
                    "task_id": tid,
                    "role": str(spec.get("role")),
                    "status": "failed",
                    "summary": "",
                    "artifact_path": "",
                    "error": f"团队墙钟超时(>{self.wall_timeout_s}s)",
                }
                for spec, tid in pairs
            ]
            self.mailbox.send(
                from_agent="system",
                to_agent=LEAD_NAME,
                content=f"fan_out 墙钟超时, {len(pairs)} 个任务未正常收尾",
                msg_type="failure",
            )

        clean: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, BaseException):
                clean.append(
                    {"status": "failed", "error": f"{type(r).__name__}: {r}",
                     "task_id": "", "role": "", "summary": "", "artifact_path": ""}
                )
            elif isinstance(r, dict):
                clean.append(r)
        # 双账本: 记录本波 + 产出进度判定(stall 检测/重规划建议)
        snapshot = self.ledger.note_wave(clean)
        stats = self.tasks.stats()
        progress = self.ledger.evaluate(stats).to_dict()
        return {
            "team_dir": self.team_dir,
            "results": clean,
            "stats": stats,
            "wave": snapshot,
            "progress": progress,
        }


def register_team_tools(
    registry,
    workspace_root: str,
    make_llm: Callable[[], tuple[Callable[..., Any], Callable[..., Any] | None]],
) -> AgentTeam:
    """把团队协作工具注册到主循环 registry。

    仅主循环可调用(workers 的注册表来自 workspace 基础工具, 天然无这些)。
    """
    from fnixagent.core.tools.protocol import ToolMetadata
    from fnixagent.core.types import ToolPermission

    team_holder: list[AgentTeam] = []

    def _get_team() -> AgentTeam:
        if not team_holder:
            team_holder.append(
                AgentTeam(workspace_root, make_llm)
            )
        return team_holder[0]

    async def _fan_out(args: dict) -> dict:
        team = _get_team()
        raw_tasks = args.get("tasks") or []
        if not isinstance(raw_tasks, list) or not raw_tasks:
            return {"success": False, "error": "tasks 不能为空"}
        team.max_parallel = int(args.get("max_parallel") or team.max_parallel)
        return await team.fan_out(raw_tasks)

    registry.register(
        ToolMetadata(
            name="team_fan_out",
            description=(
                "并行派发多个角色化子任务给团队工人并等待全部完成。"
                "每个任务: {role(researcher|coder|critic|自定义), subject(一句话), "
                "prompt(详细指令), max_steps?}。返回各任务状态+摘要+交接文档路径。"
                "适合可分解的调研/实施/评审组合工作。"
            ),
            category="team",
            permission_level=ToolPermission.MIDDLE,
            input_schema={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "子任务规格列表(≤12个)",
                    },
                    "max_parallel": {
                        "type": "integer",
                        "description": "最大并行数(默认3)",
                        "default": 3,
                    },
                },
                "required": ["tasks"],
            },
            timeout_ms=1_200_000,
        ),
        _fan_out,
    )

    def _task_status(args: dict) -> dict:
        team = _get_team()
        return {
            "success": True,
            "team_dir": team.team_dir,
            "stats": team.tasks.stats(),
            "available": [t["id"] + ":" + t["subject"] for t in team.tasks.available()],
            "tasks": team.tasks.list_all(),
        }

    registry.register(
        ToolMetadata(
            name="team_task_status",
            description="查看当前团队的任务清单状态(统计/待领/明细)。",
            category="team",
            permission_level=ToolPermission.LOW,
            input_schema={"type": "object", "properties": {}},
        ),
        _task_status,
    )

    def _read_inbox(args: dict) -> dict:
        team = _get_team()
        msgs = team.mailbox.drain(LEAD_NAME)
        return {"success": True, "messages": msgs}

    registry.register(
        ToolMetadata(
            name="team_read_inbox",
            description="读取并清空 lead 信箱(工人失败等事件会投递到这里)。",
            category="team",
            permission_level=ToolPermission.LOW,
            input_schema={"type": "object", "properties": {}},
        ),
        _read_inbox,
    )

    return _get_team()


__all__ = ["AgentTeam", "LEAD_NAME", "register_team_tools"]
