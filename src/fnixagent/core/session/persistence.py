"""
会话持久化 — 跨重启保持对话历史和 Agent 状态

支持:
  - 对话消息保存/恢复 (JSON 文件)
  - 执行轨迹保存
  - Agent 状态快照
  - 多会话管理
  - 自动清理过期会话

存储结构:
  ~/.fnixagent/sessions/
    ├── index.json          # 会话索引
    ├── {session_id}/
    │   ├── messages.json   # 对话消息
    │   ├── traces.json     # 执行轨迹
    │   └── state.json      # Agent 状态快照
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


# ============================================================
# 数据模型
# ============================================================

@dataclass
class SessionMeta:
    """会话元数据"""
    session_id: str
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    workspace_root: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SessionMeta:
        return cls(**data)


@dataclass
class PersistedMessage:
    """持久化的消息"""
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> PersistedMessage:
        return cls(**data)


# ============================================================
# 会话持久化管理器
# ============================================================

class SessionStore:
    """
    会话持久化存储

    用法:
        store = SessionStore()
        store.save_session("abc123", messages=[...], workspace="/path")
        session = store.load_session("abc123")
        store.list_sessions()
    """

    DEFAULT_DIR = ".fnixagent/sessions"

    def __init__(self, base_dir: str | None = None):
        """
        Args:
            base_dir: 存储根目录 (默认 ~/.fnixagent/sessions)
        """
        if base_dir:
            self._base = Path(base_dir)
        else:
            self._base = Path.home() / self.DEFAULT_DIR
        self._base.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base / "index.json"

    # ============================================================
    # 会话管理
    # ============================================================

    def create_session(self, session_id: str, title: str = "",
                       workspace_root: str = "") -> SessionMeta:
        """创建新会话"""
        now = datetime.now(timezone.utc).isoformat()
        meta = SessionMeta(
            session_id=session_id,
            title=title or f"Session {session_id[:8]}",
            created_at=now,
            updated_at=now,
            workspace_root=workspace_root,
        )
        # 确保目录存在
        session_dir = self._base / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        # 保存元数据
        self._save_meta(session_id, meta)
        # 更新索引
        self._update_index(meta)
        return meta

    def save_session(
        self,
        session_id: str,
        messages: list | None = None,
        traces: list | None = None,
        state: dict | None = None,
        workspace_root: str = "",
        title: str = "",
    ) -> bool:
        """保存会话数据

        Args:
            session_id: 会话 ID
            messages: 对话消息列表
            traces: 执行轨迹列表
            state: Agent 状态快照
            workspace_root: 工作区路径
            title: 会话标题

        Returns:
            是否保存成功
        """
        try:
            session_dir = self._base / session_id
            session_dir.mkdir(parents=True, exist_ok=True)

            # 保存消息
            if messages is not None:
                msg_data = []
                for m in messages:
                    if hasattr(m, 'to_dict'):
                        msg_data.append(m.to_dict())
                    elif isinstance(m, dict):
                        msg_data.append(m)
                    else:
                        msg_data.append({"role": str(m.role), "content": str(m.content)})
                with open(session_dir / "messages.json", "w", encoding="utf-8") as f:
                    json.dump(msg_data, f, ensure_ascii=False, indent=2)

            # 保存轨迹
            if traces is not None:
                trace_data = []
                for t in traces:
                    if hasattr(t, 'to_dict'):
                        trace_data.append(t.to_dict())
                    elif hasattr(t, 'to_summary'):
                        trace_data.append({"summary": t.to_summary()})
                    elif isinstance(t, dict):
                        trace_data.append(t)
                with open(session_dir / "traces.json", "w", encoding="utf-8") as f:
                    json.dump(trace_data, f, ensure_ascii=False, indent=2)

            # 保存状态
            if state is not None:
                with open(session_dir / "state.json", "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)

            # 更新元数据
            meta = self._load_meta(session_id)
            if meta is None:
                meta = self.create_session(
                    session_id, title=title, workspace_root=workspace_root,
                )
            else:
                meta.updated_at = datetime.now(timezone.utc).isoformat()
                if title:
                    meta.title = title
                if workspace_root:
                    meta.workspace_root = workspace_root
                if messages is not None:
                    meta.message_count = len(messages)
                self._save_meta(session_id, meta)
                self._update_index(meta)

            return True
        except Exception as e:
            print(f"[SessionStore] 保存会话失败: {e}")
            return False

    def load_session(self, session_id: str) -> dict | None:
        """加载会话数据

        Returns:
            {
                "meta": SessionMeta,
                "messages": [...],
                "traces": [...],
                "state": {...},
            }
            会话不存在返回 None
        """
        session_dir = self._base / session_id
        if not session_dir.is_dir():
            return None

        result = {"meta": self._load_meta(session_id)}

        # 加载消息
        msg_file = session_dir / "messages.json"
        if msg_file.exists():
            try:
                with open(msg_file, encoding="utf-8") as f:
                    result["messages"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                result["messages"] = []

        # 加载轨迹
        trace_file = session_dir / "traces.json"
        if trace_file.exists():
            try:
                with open(trace_file, encoding="utf-8") as f:
                    result["traces"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                result["traces"] = []

        # 加载状态
        state_file = session_dir / "state.json"
        if state_file.exists():
            try:
                with open(state_file, encoding="utf-8") as f:
                    result["state"] = json.load(f)
            except (json.JSONDecodeError, OSError):
                result["state"] = {}

        return result

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        session_dir = self._base / session_id
        if not session_dir.is_dir():
            return False

        import shutil
        try:
            shutil.rmtree(session_dir)
            self._remove_from_index(session_id)
            return True
        except Exception as e:
            print(f"[SessionStore] 删除会话失败: {e}")
            return False

    def list_sessions(self, limit: int = 50) -> list[SessionMeta]:
        """列出所有会话 (按更新时间倒序)"""
        index = self._load_index()
        sessions = []
        for entry in list(index.get("sessions", []))[:limit]:
            if isinstance(entry, dict):
                sessions.append(SessionMeta.from_dict(entry))
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    def get_session(self, session_id: str) -> SessionMeta | None:
        """获取会话元数据"""
        return self._load_meta(session_id)

    def cleanup_expired(self, max_age_days: int = 30) -> int:
        """清理过期会话

        Args:
            max_age_days: 保留天数

        Returns:
            清理的会话数
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cleaned = 0
        for session in self.list_sessions(limit=1000):
            try:
                updated = datetime.fromisoformat(session.updated_at.replace("Z", "+00:00"))
                if updated < cutoff:
                    self.delete_session(session.session_id)
                    cleaned += 1
            except (ValueError, TypeError):
                continue
        return cleaned

    # ============================================================
    # 内部方法
    # ============================================================

    def _save_meta(self, session_id: str, meta: SessionMeta) -> None:
        session_dir = self._base / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        with open(session_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)

    def _load_meta(self, session_id: str) -> SessionMeta | None:
        meta_file = self._base / session_id / "meta.json"
        if not meta_file.exists():
            return None
        try:
            with open(meta_file, encoding="utf-8") as f:
                data = json.load(f)
            return SessionMeta.from_dict(data)
        except (json.JSONDecodeError, OSError):
            return None

    def _load_index(self) -> dict:
        if not self._index_path.exists():
            return {"sessions": []}
        try:
            with open(self._index_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"sessions": []}

    def _save_index(self, index: dict) -> None:
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _update_index(self, meta: SessionMeta) -> None:
        index = self._load_index()
        sessions = index.get("sessions", [])
        # 更新或添加
        for i, s in enumerate(sessions):
            if isinstance(s, dict) and s.get("session_id") == meta.session_id:
                sessions[i] = meta.to_dict()
                break
        else:
            sessions.append(meta.to_dict())
        # 限制索引大小
        index["sessions"] = sessions[-200:]
        self._save_index(index)

    def _remove_from_index(self, session_id: str) -> None:
        index = self._load_index()
        index["sessions"] = [
            s for s in index.get("sessions", [])
            if isinstance(s, dict) and s.get("session_id") != session_id
        ]
        self._save_index(index)


# ============================================================
# 便捷函数
# ============================================================

def get_session_store(base_dir: str | None = None) -> SessionStore:
    """获取全局 SessionStore 实例 (单例)"""
    if not hasattr(get_session_store, "_instance"):
        get_session_store._instance = SessionStore(base_dir)  # type: ignore[attr-defined]
    return get_session_store._instance  # type: ignore[attr-defined]


__all__ = [
    "SessionStore", "SessionMeta", "PersistedMessage",
    "get_session_store",
]