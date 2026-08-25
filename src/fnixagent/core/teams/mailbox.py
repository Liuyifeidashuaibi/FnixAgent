"""Agent 信箱 — 团队消息传递(JSON 收件箱)。

对齐 Claude Code Agent Teams 的 mailbox 语义:
  - 每个 agent 一个收件箱文件 {team_dir}/inboxes/{name}.json
  - 读取时校验每条消息格式, 非法条目剔除并告警(官方文档记载的痛点)
  - drain = 读取并清空(消费语义); peek 只读不清

v1 用途: 工人失败自动通知 lead; 主 Agent 通过 read_inbox 工具消费。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any

_logger = logging.getLogger(__name__)

_MSG_REQUIRED_KEYS = {"id", "from", "type", "content", "timestamp"}


class Mailbox:
    """团队信箱(每 agent 一个 JSON 收件箱)。"""

    def __init__(self, team_dir: str) -> None:
        self._inbox_dir = os.path.join(str(team_dir), "inboxes")
        os.makedirs(self._inbox_dir, exist_ok=True)
        self._lock = threading.Lock()

    # -- 路径 ----------------------------------------------------------------

    def _path_of(self, agent: str) -> str:
        safe = "".join(c for c in agent if c.isalnum() or c in "-_")
        if not safe:
            safe = "anon"
        return os.path.join(self._inbox_dir, f"{safe}.json")

    # -- 底层 ----------------------------------------------------------------

    def _load(self, agent: str) -> list[dict[str, Any]]:
        path = self._path_of(agent)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        # 校验: 非法条目剔除(Claude Code 文档记载的格式腐坏问题)
        valid: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, dict) and _MSG_REQUIRED_KEYS.issubset(m.keys()):
                valid.append(m)
            else:
                _logger.warning("mailbox %s: dropped malformed entry", agent)
        return valid

    def _save(self, agent: str, messages: list[dict[str, Any]]) -> None:
        path = self._path_of(agent)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"messages": messages}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    # -- 对外操作 --------------------------------------------------------------

    def send(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        msg_type: str = "info",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """投递一条消息到目标收件箱。"""
        message: dict[str, Any] = {
            "id": uuid.uuid4().hex[:12],
            "from": str(from_agent)[:100],
            "to": str(to_agent)[:100],
            "type": str(msg_type)[:40],  # info / warning / failure / handoff
            "content": str(content)[:4000],
            "meta": dict(meta or {}),
            "timestamp": time.time(),
        }
        with self._lock:
            msgs = self._load(to_agent)
            msgs.append(message)
            self._save(to_agent, msgs)
        return message

    def broadcast(
        self, from_agent: str, agents: list[str], content: str, msg_type: str = "info"
    ) -> int:
        """群发。返回投递条数。"""
        n = 0
        for a in agents:
            try:
                self.send(from_agent, a, content, msg_type)
                n += 1
            except OSError as exc:
                _logger.warning("broadcast to %s failed: %s", a, exc)
        return n

    def peek(self, agent: str) -> list[dict[str, Any]]:
        """只读收件箱。"""
        with self._lock:
            return list(self._load(agent))

    def drain(self, agent: str, msg_types: list[str] | None = None) -> list[dict[str, Any]]:
        """读取并消费收件箱。

        Args:
            agent: 收件人
            msg_types: 可选类型过滤(如 ["failure"]); 只消费匹配项,
                其余保留在收件箱(MetaGPT 订阅式过滤的消费语义)。
        """
        with self._lock:
            msgs = self._load(agent)
            if msg_types is None:
                if msgs:
                    self._save(agent, [])
                return msgs
            consume = [m for m in msgs if m.get("type") in set(msg_types)]
            keep = [m for m in msgs if m.get("type") not in set(msg_types)]
            self._save(agent, keep)
            return consume


__all__ = ["Mailbox"]
