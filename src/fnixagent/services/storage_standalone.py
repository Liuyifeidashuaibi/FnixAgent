"""
Standalone 模式 JSON 持久化 — 用户数据跨重启保留（无需 PostgreSQL）。

数据目录：``data/standalone/users.json``
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
from datetime import UTC, datetime

from fnixagent.services.storage import StoredUser, UserStore

_store: JsonUserStore | None = None
_lock = threading.Lock()

_DEFAULT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "data",
    "standalone",
)


def _user_to_json(user: StoredUser) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "role": user.role,
        "profile": user.profile,
        "quota_total": user.quota_total,
        "quota_used": user.quota_used,
        "created_at": user.created_at.isoformat(),
    }


def _user_from_json(data: dict) -> StoredUser:
    created = data.get("created_at")
    if isinstance(created, str):
        try:
            created_at = datetime.fromisoformat(created)
        except ValueError:
            created_at = datetime.now(UTC)
    else:
        created_at = datetime.now(UTC)
    return StoredUser(
        id=int(data["id"]),
        username=str(data["username"]),
        email=str(data.get("email") or ""),
        password_hash=str(data["password_hash"]),
        role=str(data.get("role") or "user"),
        profile=dict(data.get("profile") or {}),
        quota_total=int(data.get("quota_total") or 100000),
        quota_used=int(data.get("quota_used") or 0),
        created_at=created_at,
    )


class JsonUserStore(UserStore):
    """内存 UserStore + JSON 文件落盘。"""

    def __init__(self, json_path: str) -> None:
        super().__init__()
        self._json_path = json_path
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(self._json_path):
            return
        try:
            with open(self._json_path, encoding="utf-8") as f:
                rows = json.load(f)
            if not isinstance(rows, list):
                return
            max_id = 0
            for row in rows:
                user = _user_from_json(row)
                self._users[user.id] = user
                self._username_idx[user.username] = user.id
                if user.email:
                    self._email_idx[user.email] = user.id
                max_id = max(max_id, user.id)
            self._next_id = max_id + 1
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    def _save(self) -> None:
        with self._lock:
            rows = [_user_to_json(u) for u in self._users.values()]
        tmp = self._json_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._json_path)

    def create(self, username: str, email: str, password: str, role: str = "user"):
        user, err = super().create(username, email, password, role)
        if user:
            self._save()
        return user, err

    def update_profile(self, user_id: int, profile: dict):
        user = super().update_profile(user_id, profile)
        if user:
            self._save()
        return user

    def update_password(self, user_id: int, password_plain: str) -> bool:
        ok = super().update_password(user_id, password_plain)
        if ok:
            self._save()
        return ok

    def update_role(self, user_id: int, role: str) -> bool:
        ok = super().update_role(user_id, role)
        if ok:
            self._save()
        return ok

    def soft_delete_user(self, user_id: int, retention_days: int = 30) -> bool:
        ok = super().soft_delete_user(user_id, retention_days)
        if ok:
            self._save()
        return ok

    def cancel_soft_delete(self, user_id: int) -> bool:
        ok = super().cancel_soft_delete(user_id)
        if ok:
            self._save()
        return ok

    def hard_delete_user(self, user_id: int) -> bool:
        ok = super().hard_delete_user(user_id)
        if ok:
            self._save()
        return ok


def get_standalone_user_store(data_dir: str | None = None) -> JsonUserStore:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                base = data_dir or _DEFAULT_DIR
                path = os.path.join(base, "users.json")
                _store = JsonUserStore(path)
    return _store
