"""
存储层 - 业务实体的内存存储(默认) + 可选 DB 持久化。

提供 UserStore / DocumentStore / TaskStore / ApiKeyStore 四类存储,
供 API 路由(auth/documents/tasks)使用,替换之前的 Mock 实现。

设计要点:
  - 默认内存存储(无 DB 也能跑),保证开发/测试环境零依赖启动
  - 真实逻辑:密码哈希(passlib)、文件落盘、任务生命周期
  - 线程安全(threading.Lock),支持并发请求
  - 可选 DB 适配器注入:有 PostgreSQL 时切换到持久化存储
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 安全常量(防止 DoS / 暴力破解 / 资源滥用)
# ---------------------------------------------------------------------------

# 上传文件大小上限:50MB(防止内存耗尽 DoS)
MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024

# 允许的文件扩展名白名单(防止上传可执行文件/脚本)
ALLOWED_FILE_EXTENSIONS: frozenset[str] = frozenset({
    "pdf", "docx", "doc", "txt", "md", "csv", "xlsx",
    "png", "jpg", "jpeg", "gif", "svg",
})

# 登录失败锁定:5 次失败后锁定 15 分钟(防止暴力破解)
MAX_LOGIN_ATTEMPTS: int = 5
LOGIN_LOCKOUT_SECONDS: int = 900  # 15 分钟

# 列表查询最大返回条数(防止超大结果集耗尽内存)
MAX_LIST_LIMIT: int = 200

# ---------------------------------------------------------------------------
# 密码哈希(Phase 0.4 升级为 Argon2id,向后兼容 PBKDF2)
# ---------------------------------------------------------------------------
# 实际实现委托给 core/security/auth/password.py,此处保留函数名以维持
# 向后兼容(services/storage.py 内部调用 + 现有测试直接导入)。

from fnixagent.core.security.auth.password import (
    hash_password,                # 默认 Argon2id
    verify_password,              # 自动识别 Argon2id / PBKDF2
    needs_rehash,                 # 检测旧哈希是否需升级
)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class StoredUser:
    """用户记录。"""
    id: int
    username: str
    email: str
    password_hash: str
    role: str = "user"
    profile: dict = field(default_factory=dict)
    quota_total: int = 100000
    quota_used: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """转换为字典(不含密码哈希)。"""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "profile": self.profile,
            "quota_total": self.quota_total,
            "quota_used": self.quota_used,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class StoredApiKey:
    """API Key 记录。"""
    id: int
    user_id: int
    api_key: str  # 明文只返回一次,数据库存哈希
    api_key_hash: str
    scopes: list = field(default_factory=lambda: ["chat"])
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    revoked: bool = False


@dataclass
class StoredDocument:
    """文档记录。"""
    id: int
    name: str
    doc_type: str
    source: str = "upload"
    object_key: str = ""  # 本地文件相对路径
    mime_type: str = ""
    size_bytes: int = 0
    checksum: str = ""
    metadata: dict = field(default_factory=dict)
    user_id: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    deleted: bool = False

    def to_dict(self) -> dict:
        """转换为字典(含完整元数据)。"""
        return {
            "id": self.id,
            "name": self.name,
            "doc_type": self.doc_type,
            "source": self.source,
            "object_key": self.object_key,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
            "user_id": self.user_id,
            "deleted": self.deleted,
        }


@dataclass
class StoredTaskStep:
    """任务步骤。"""
    step_no: int
    description: str
    tool_name: str = ""
    status: str = "pending"  # pending/running/success/failed
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: str = ""


@dataclass
class StoredTask:
    """任务记录。"""
    id: int
    session_id: int
    user_id: int = 0
    intent: str = ""
    reasoning_mode: str = "react"
    status: str = "pending"  # pending/running/succeeded/failed/cancelled
    steps: list = field(default_factory=list)  # list[StoredTaskStep]
    result: Optional[dict] = None
    error: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """转换为字典(不含步骤明细)。"""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "intent": self.intent,
            "reasoning_mode": self.reasoning_mode,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# UserStore
# ---------------------------------------------------------------------------


class UserStore:
    """用户存储(线程安全的内存实现)。"""

    def __init__(self):
        self._users: dict[int, StoredUser] = {}
        self._username_idx: dict[str, int] = {}  # username -> user_id
        self._email_idx: dict[str, int] = {}  # email -> user_id
        self._next_id = 1
        self._lock = threading.RLock()
        # 登录失败追踪:username -> (失败次数, 首次失败时间戳, 锁定截止时间戳)
        self._login_attempts: dict[str, list] = {}

    def create(self, username: str, email: str, password: str, role: str = "user") -> tuple[Optional[StoredUser], str]:
        """创建用户。返回 (user, error_msg)。"""
        with self._lock:
            if username in self._username_idx:
                return None, "用户名已存在"
            if email and email in self._email_idx:
                return None, "邮箱已被注册"
            uid = self._next_id
            self._next_id += 1
            user = StoredUser(
                id=uid,
                username=username,
                email=email or "",
                password_hash=hash_password(password),
                role=role,
            )
            self._users[uid] = user
            self._username_idx[username] = uid
            if email:
                self._email_idx[email] = uid
            return user, ""

    def get_by_id(self, user_id: int) -> Optional[StoredUser]:
        """根据 ID 获取用户。"""
        with self._lock:
            return self._users.get(user_id)

    def get_by_username(self, username: str) -> Optional[StoredUser]:
        """根据用户名获取用户。"""
        with self._lock:
            uid = self._username_idx.get(username)
            return self._users.get(uid) if uid else None

    def get_by_email(self, email: str) -> Optional[StoredUser]:
        """根据邮箱获取用户(用于 LDAP 用户按邮箱映射)。"""
        if not email:
            return None
        with self._lock:
            uid = self._email_idx.get(email)
            return self._users.get(uid) if uid else None

    def get_by_phone(self, phone: str) -> Optional[StoredUser]:
        """根据手机号获取用户(用于手机号验证码登录)。

        手机号存储在 profile.phone 字段中。
        """
        if not phone:
            return None
        with self._lock:
            for user in self._users.values():
                if user.profile.get("phone") == phone:
                    return user
            return None

    def authenticate(self, username: str, password: str) -> Optional[StoredUser]:
        """
        验证用户名+密码,返回用户或 None。

        安全:登录失败次数追踪,超过 MAX_LOGIN_ATTEMPTS 次后锁定 LOGIN_LOCKOUT_SECONDS 秒。
        """
        now = time.monotonic()

        with self._lock:
            # 检查是否被锁定(attempt = [失败次数, 首次失败时间, 锁定截止时间])
            attempt = self._login_attempts.get(username)
            if attempt and attempt[2] > 0 and now < attempt[2]:
                return None  # 锁定中,直接拒绝(不区分用户是否存在,防信息泄露)

        user = self.get_by_username(username)
        if not user:
            self._record_failed_login(username)
            return None
        # 禁用用户拒绝登录(立即生效)
        if user.profile.get("disabled"):
            return None
        if not verify_password(password, user.password_hash):
            self._record_failed_login(username)
            return None

        # 登录成功:清除失败记录
        with self._lock:
            self._login_attempts.pop(username, None)
        return user

    def _record_failed_login(self, username: str) -> None:
        """记录一次登录失败,达到阈值后锁定。"""
        now = time.monotonic()
        with self._lock:
            attempt = self._login_attempts.get(username)
            # attempt = [失败次数, 首次失败时间, 锁定截止时间(0=未锁定)]
            if attempt is None or (attempt[2] > 0 and now >= attempt[2]):
                # 首次失败 或 锁定已过期:重置计数
                self._login_attempts[username] = [1, now, 0.0]
            else:
                attempt[0] += 1
                if attempt[0] >= MAX_LOGIN_ATTEMPTS:
                    attempt[2] = now + LOGIN_LOCKOUT_SECONDS  # 设置锁定截止时间

    def update_profile(self, user_id: int, profile: dict) -> Optional[StoredUser]:
        """更新用户画像字段,返回更新后的用户或 None。"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return None
            user.profile.update(profile)
            return user

    def update_password(self, user_id: int, password_plain: str) -> bool:
        """更新用户密码(明文传入,内部用 Argon2id 哈希)。

        用于 Phase 0.4 自动哈希升级:检测到老 PBKDF2 哈希时,
        登录成功后调用此方法重新哈希为 Argon2id。

        Args:
            user_id: 用户 ID
            password_plain: 密码明文(已通过校验)

        Returns:
            是否更新成功
        """
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            user.password_hash = hash_password(password_plain)
            return True

    def add_usage(self, user_id: int, tokens: int) -> None:
        """累加 Token 用量。"""
        with self._lock:
            user = self._users.get(user_id)
            if user:
                user.quota_used += tokens

    def get_quota(self, user_id: int) -> Optional[dict]:
        """获取用户 Token 配额信息。"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return None
            return {
                "user_id": user_id,
                "total_quota": user.quota_total,
                "used_quota": user.quota_used,
                "remaining_quota": max(0, user.quota_total - user.quota_used),
            }

    def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> tuple[list[StoredUser], int]:
        """列出用户(支持搜索 + 分页)。返回 (users, total)。"""
        with self._lock:
            users = list(self._users.values())
            if search:
                s = search.lower()
                users = [
                    u for u in users
                    if s in u.username.lower() or s in (u.email or "").lower()
                ]
            users.sort(key=lambda u: u.id, reverse=True)
            total = len(users)
            limit = max(1, min(200, limit))
            offset = max(0, offset)
            return users[offset:offset + limit], total

    def set_user_disabled(self, user_id: int, disabled: bool) -> bool:
        """启用/禁用用户(禁用后该用户无法登录)。"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            user.profile["disabled"] = bool(disabled)
            return True

    def is_user_disabled(self, user_id: int) -> bool:
        """检查用户是否被禁用。"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return True
            return bool(user.profile.get("disabled", False))

    # ------------------------------------------------------------------
    # Phase 3.2: 账号注销(软删除 + 30 天硬删除)
    # ------------------------------------------------------------------

    def soft_delete_user(self, user_id: int, retention_days: int = 30) -> bool:
        """软删除用户(标记为待删除 + 禁用登录)。

        - 在 profile 中写入 deleted_at(ISO 字符串)和 hard_delete_at
        - 同时设置 disabled=True,立即阻止登录
        - 保留期内可调用 cancel_soft_delete 撤销
        - 保留期过后由后台任务硬删除

        Args:
            user_id: 用户 ID
            retention_days: 保留天数(默认 30 天)

        Returns:
            是否标记成功
        """
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            now = datetime.utcnow()
            from datetime import timedelta
            hard_delete_at = now + timedelta(days=retention_days)
            user.profile["deleted_at"] = now.isoformat()
            user.profile["hard_delete_at"] = hard_delete_at.isoformat()
            user.profile["disabled"] = True
            return True

    def cancel_soft_delete(self, user_id: int) -> bool:
        """撤销软删除(在 30 天保留期内可恢复)。

        - 清除 profile 中的 deleted_at / hard_delete_at
        - 恢复 disabled=False

        Returns:
            是否撤销成功
        """
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            user.profile.pop("deleted_at", None)
            user.profile.pop("hard_delete_at", None)
            user.profile["disabled"] = False
            return True

    def hard_delete_user(self, user_id: int) -> bool:
        """硬删除用户(从存储中彻底移除)。

        ⚠️ 不可恢复。仅由后台清理任务或管理员手动调用。

        Returns:
            是否删除成功
        """
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            # 清理索引
            self._username_idx.pop(user.username, None)
            if user.email:
                self._email_idx.pop(user.email, None)
            # 删除主记录
            self._users.pop(user_id, None)
            return True

    def get_soft_deleted_users(self) -> list[StoredUser]:
        """获取所有已软删除的用户(供后台清理任务使用)。"""
        with self._lock:
            return [
                u for u in self._users.values()
                if u.profile.get("deleted_at")
            ]

    def get_users_to_hard_delete(self, before: Optional[datetime] = None) -> list[StoredUser]:
        """获取已过保留期、待硬删除的用户。

        Args:
            before: 截止时间(默认当前时间)

        Returns:
            待硬删除的用户列表
        """
        if before is None:
            before = datetime.utcnow()
        with self._lock:
            result: list[StoredUser] = []
            for u in self._users.values():
                hard_delete_at_str = u.profile.get("hard_delete_at")
                if not hard_delete_at_str:
                    continue
                try:
                    hard_delete_at = datetime.fromisoformat(hard_delete_at_str)
                except (ValueError, TypeError):
                    continue
                if hard_delete_at <= before:
                    result.append(u)
            return result

    def is_user_deleted(self, user_id: int) -> bool:
        """检查用户是否已软删除。"""
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return True
            return bool(user.profile.get("deleted_at"))

    def update_role(self, user_id: int, role: str) -> bool:
        """更新用户角色(user/admin)。"""
        if role not in ("user", "admin"):
            return False
        with self._lock:
            user = self._users.get(user_id)
            if not user:
                return False
            user.role = role
            return True

    @property
    def count(self) -> int:
        """已注册用户数量。"""
        with self._lock:
            return len(self._users)


# ---------------------------------------------------------------------------
# ApiKeyStore
# ---------------------------------------------------------------------------


class ApiKeyStore:
    """API Key 存储。"""

    def __init__(self):
        self._keys: dict[int, StoredApiKey] = {}
        self._hash_idx: dict[str, int] = {}  # api_key_hash -> key_id
        self._next_id = 1
        self._lock = threading.RLock()

    def create(self, user_id: int, scopes: Optional[list] = None, expires_days: int = 365) -> StoredApiKey:
        """为用户创建 API Key。明文 key 只返回一次。"""
        with self._lock:
            kid = self._next_id
            self._next_id += 1
            plaintext = f"sk-fnixagent-{secrets.token_urlsafe(32)}"
            key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
            record = StoredApiKey(
                id=kid,
                user_id=user_id,
                api_key=plaintext,
                api_key_hash=key_hash,
                scopes=scopes or ["chat"],
                expires_at=datetime.utcnow() + timedelta(days=expires_days),
            )
            self._keys[kid] = record
            self._hash_idx[key_hash] = kid
            return record

    def revoke(self, key_id: int, user_id: int) -> bool:
        """吊销 API Key(仅本人)。"""
        with self._lock:
            rec = self._keys.get(key_id)
            if not rec or rec.user_id != user_id:
                return False
            rec.revoked = True
            return True

    def list_by_user(self, user_id: int) -> list[StoredApiKey]:
        """列出指定用户的所有 API Key。"""
        with self._lock:
            return [k for k in self._keys.values() if k.user_id == user_id]


# ---------------------------------------------------------------------------
# DocumentStore
# ---------------------------------------------------------------------------


class DocumentStore:
    """文档存储(内存索引 + 本地文件落盘)。"""

    def __init__(self, storage_dir: Optional[str] = None):
        self._docs: dict[int, StoredDocument] = {}
        self._next_id = 1
        self._lock = threading.RLock()
        # 本地文件存储目录
        self._storage_dir = storage_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "data", "uploads"
        )
        os.makedirs(self._storage_dir, exist_ok=True)

    @property
    def storage_dir(self) -> str:
        """本地文件存储目录。"""
        return self._storage_dir

    def _detect_doc_type(self, filename: str) -> str:
        """根据扩展名推断文档类型(paper/docx/pdf/markdown/chart/table)。"""
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        mapping = {
            "pdf": "pdf",
            "docx": "docx", "doc": "docx",
            "txt": "markdown", "md": "markdown",
            "png": "chart", "jpg": "chart", "jpeg": "chart",
            "csv": "table", "xlsx": "table",
        }
        return mapping.get(ext, "unknown")

    def _detect_mime(self, filename: str) -> str:
        """根据扩展名推断 MIME 类型。"""
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        mimes = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain", "md": "text/markdown",
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return mimes.get(ext, "application/octet-stream")

    def save_upload(
        self,
        filename: str,
        content: bytes,
        user_id: int = 0,
        metadata: Optional[dict] = None,
    ) -> StoredDocument:
        """
        保存上传文件,返回文档记录。

        安全校验:
          - 文件大小不超过 MAX_UPLOAD_SIZE_BYTES(防 DoS)
          - 扩展名必须在白名单内(防恶意文件)
          - 文件名净化(防路径穿越)
        """
        # 安全校验:文件大小
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise ValueError(
                f"文件大小 {len(content)} 字节超过上限 {MAX_UPLOAD_SIZE_BYTES} 字节"
            )
        # 安全校验:扩展名白名单
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        if ext not in ALLOWED_FILE_EXTENSIONS:
            raise ValueError(
                f"不支持的文件类型 '.{ext}',允许: {sorted(ALLOWED_FILE_EXTENSIONS)}"
            )
        # 安全校验:文件名净化(防路径穿越攻击)
        safe_name = os.path.basename(filename).replace(os.sep, "_").replace("..", "_")
        if not safe_name or safe_name.startswith("."):
            raise ValueError("非法文件名")

        with self._lock:
            did = self._next_id
            self._next_id += 1
            doc_type = self._detect_doc_type(filename)
            object_key = f"{did}_{safe_name}"
            file_path = os.path.join(self._storage_dir, object_key)
            with open(file_path, "wb") as f:
                f.write(content)
            checksum = hashlib.sha256(content).hexdigest()
            doc = StoredDocument(
                id=did,
                name=safe_name,
                doc_type=doc_type,
                source="upload",
                object_key=object_key,
                mime_type=self._detect_mime(filename),
                size_bytes=len(content),
                checksum=checksum,
                metadata=metadata or {},
                user_id=user_id,
            )
            self._docs[did] = doc
            return doc

    def create_generated(
        self,
        name: str,
        doc_type: str,
        content: bytes,
        user_id: int = 0,
        metadata: Optional[dict] = None,
    ) -> StoredDocument:
        """Agent 生成的文档。"""
        with self._lock:
            did = self._next_id
            self._next_id += 1
            safe_name = os.path.basename(name).replace(os.sep, "_")
            object_key = f"{did}_{safe_name}"
            file_path = os.path.join(self._storage_dir, object_key)
            with open(file_path, "wb") as f:
                f.write(content)
            doc = StoredDocument(
                id=did,
                name=name,
                doc_type=doc_type,
                source="generated",
                object_key=object_key,
                mime_type=self._detect_mime(name),
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                metadata=metadata or {},
                user_id=user_id,
            )
            self._docs[did] = doc
            return doc

    def get(self, doc_id: int) -> Optional[StoredDocument]:
        """根据 ID 获取未删除的文档。"""
        with self._lock:
            doc = self._docs.get(doc_id)
            if doc and not doc.deleted:
                return doc
            return None

    def get_file_path(self, doc_id: int) -> Optional[str]:
        """获取文档落盘文件的绝对路径,文件缺失返回 None。"""
        doc = self.get(doc_id)
        if not doc:
            return None
        path = os.path.join(self._storage_dir, doc.object_key)
        return path if os.path.exists(path) else None

    def list(
        self,
        user_id: Optional[int] = None,
        doc_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[StoredDocument]:
        # 限制最大返回条数,防止超大结果集耗尽内存
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        with self._lock:
            results = []
            for doc in self._docs.values():
                if doc.deleted:
                    continue
                if user_id is not None and doc.user_id != user_id:
                    continue
                if doc_type and doc.doc_type != doc_type:
                    continue
                results.append(doc)
            return results[:limit]

    def delete(self, doc_id: int) -> bool:
        """软删除(保留文件,仅置标记)。"""
        with self._lock:
            doc = self._docs.get(doc_id)
            if not doc or doc.deleted:
                return False
            doc.deleted = True
            return True

    @property
    def count(self) -> int:
        """未删除的文档数量。"""
        with self._lock:
            return sum(1 for d in self._docs.values() if not d.deleted)


# ---------------------------------------------------------------------------
# TaskStore
# ---------------------------------------------------------------------------


class TaskStore:
    """任务存储(线程安全内存实现)。"""

    def __init__(self):
        self._tasks: dict[int, StoredTask] = {}
        self._next_id = 1
        self._lock = threading.RLock()

    def create(
        self,
        session_id: int,
        intent: str,
        reasoning_mode: str = "react",
        user_id: int = 0,
    ) -> StoredTask:
        """创建 pending 状态的任务记录。"""
        with self._lock:
            tid = self._next_id
            self._next_id += 1
            task = StoredTask(
                id=tid,
                session_id=session_id,
                user_id=user_id,
                intent=intent,
                reasoning_mode=reasoning_mode,
                status="pending",
            )
            self._tasks[tid] = task
            return task

    def get(self, task_id: int) -> Optional[StoredTask]:
        """根据 ID 获取任务。"""
        with self._lock:
            return self._tasks.get(task_id)

    def start(self, task_id: int) -> Optional[StoredTask]:
        """标记任务开始执行。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = "running"
            task.started_at = datetime.utcnow()
            return task

    def add_step(self, task_id: int, description: str, tool_name: str = "") -> Optional[StoredTaskStep]:
        """为任务追加一个步骤,返回新增步骤。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            step_no = len(task.steps) + 1
            step = StoredTaskStep(
                step_no=step_no,
                description=description,
                tool_name=tool_name,
            )
            task.steps.append(step)
            return step

    def update_step(self, task_id: int, step_no: int, status: str,
                    result: Optional[dict] = None, error: str = "") -> bool:
        """更新指定步骤的状态/结果,自动维护起止时间。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            for s in task.steps:
                if s.step_no == step_no:
                    s.status = status
                    if status == "running" and not s.started_at:
                        s.started_at = datetime.utcnow()
                    if status in ("success", "failed") and not s.finished_at:
                        s.finished_at = datetime.utcnow()
                    if result is not None:
                        s.result = result
                    if error:
                        s.error = error
                    return True
            return False

    def complete(self, task_id: int, result: Optional[dict] = None) -> Optional[StoredTask]:
        """标记任务成功完成。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = "succeeded"
            task.finished_at = datetime.utcnow()
            if result is not None:
                task.result = result
            return task

    def fail(self, task_id: int, error: str) -> Optional[StoredTask]:
        """标记任务失败并记录错误信息。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = "failed"
            task.finished_at = datetime.utcnow()
            task.error = error
            return task

    def cancel(self, task_id: int) -> Optional[StoredTask]:
        """取消任务(仅未完成的任务可取消),成功返回任务,否则 None。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            # 只能取消未完成的任务
            if task.status in ("succeeded", "failed", "cancelled"):
                return None
            task.status = "cancelled"
            task.finished_at = datetime.utcnow()
            return task

    def retry(self, task_id: int) -> Optional[StoredTask]:
        """重置任务状态为 pending,允许重新执行。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = "pending"
            task.started_at = None
            task.finished_at = None
            task.error = ""
            # 重置步骤状态
            for s in task.steps:
                s.status = "pending"
                s.started_at = None
                s.finished_at = None
                s.error = ""
            return task

    def list(
        self,
        user_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[StoredTask]:
        """查询任务列表,支持按用户/状态过滤,按创建时间倒序。"""
        # 限制最大返回条数,防止超大结果集耗尽内存
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        with self._lock:
            results = []
            for task in self._tasks.values():
                if user_id is not None and task.user_id != user_id:
                    continue
                if status and task.status != status:
                    continue
                results.append(task)
            # 按创建时间倒序
            results.sort(key=lambda t: t.created_at, reverse=True)
            return results[:limit]

    def get_status(self, task_id: int) -> Optional[dict]:
        """获取任务状态摘要(进度/当前步骤/总步骤数)。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            total = len(task.steps)
            done = sum(1 for s in task.steps if s.status in ("success", "failed"))
            current = next((s.step_no for s in task.steps if s.status == "running"), None)
            progress = (done / total) if total > 0 else (1.0 if task.status == "succeeded" else 0.0)
            return {
                "task_id": task_id,
                "status": task.status,
                "progress": round(progress, 2),
                "current_step": current,
                "total_steps": total or None,
            }

    @property
    def count(self) -> int:
        """任务总数。"""
        with self._lock:
            return len(self._tasks)


# ---------------------------------------------------------------------------
# 全局单例(供 API 路由直接使用)
# ---------------------------------------------------------------------------
# 工厂模式:若设置了 DATABASE_URL 环境变量,自动切换到 PostgreSQL 持久化 Store;
# 否则回退到内存 Store(开发/测试零依赖)。
# 两种 Store 接口签名完全一致(适配器模式)。

_user_store: Optional[Any] = None
_apikey_store: Optional[Any] = None
_document_store: Optional[Any] = None
_task_store: Optional[Any] = None
_store_lock = threading.Lock()


def _use_pg() -> bool:
    """是否启用 PostgreSQL 持久化(检查 DATABASE_URL 与导入可用性)。"""
    if not os.getenv("DATABASE_URL"):
        return False
    try:
        from fnixagent.services.storage_postgres import get_db_adapter  # noqa: F401
        return True
    except ImportError:
        return False


def get_user_store() -> Any:
    """获取 UserStore 全局单例(双重检查锁定,懒加载)。

    DATABASE_URL 已设置时返回 PgUserStore,否则返回内存 UserStore。
    """
    global _user_store
    if _user_store is None:
        with _store_lock:
            if _user_store is None:
                if _use_pg():
                    from fnixagent.services.storage_postgres import PgUserStore, get_db_adapter
                    db = get_db_adapter()
                    _user_store = PgUserStore(db)  # type: ignore[arg-type]
                else:
                    _user_store = UserStore()
    return _user_store


def get_apikey_store() -> Any:
    """获取 ApiKeyStore 全局单例(双重检查锁定,懒加载)。"""
    global _apikey_store
    if _apikey_store is None:
        with _store_lock:
            if _apikey_store is None:
                if _use_pg():
                    from fnixagent.services.storage_postgres import PgApiKeyStore, get_db_adapter
                    db = get_db_adapter()
                    _apikey_store = PgApiKeyStore(db)  # type: ignore[arg-type]
                else:
                    _apikey_store = ApiKeyStore()
    return _apikey_store


def get_document_store() -> Any:
    """获取 DocumentStore 全局单例(双重检查锁定,懒加载)。"""
    global _document_store
    if _document_store is None:
        with _store_lock:
            if _document_store is None:
                if _use_pg():
                    from fnixagent.services.storage_postgres import PgDocumentStore, get_db_adapter
                    db = get_db_adapter()
                    _document_store = PgDocumentStore(db)  # type: ignore[arg-type]
                else:
                    _document_store = DocumentStore()
    return _document_store


def get_task_store() -> Any:
    """获取 TaskStore 全局单例(双重检查锁定,懒加载)。"""
    global _task_store
    if _task_store is None:
        with _store_lock:
            if _task_store is None:
                if _use_pg():
                    from fnixagent.services.storage_postgres import PgTaskStore, get_db_adapter
                    db = get_db_adapter()
                    _task_store = PgTaskStore(db)  # type: ignore[arg-type]
                else:
                    _task_store = TaskStore()
    return _task_store


def reset_stores() -> None:
    """重置全部存储(用于测试)。"""
    global _user_store, _apikey_store, _document_store, _task_store
    with _store_lock:
        _user_store = None
        _apikey_store = None
        _document_store = None
        _task_store = None
    # 同步重置 Pg 适配器单例
    try:
        from fnixagent.services.storage_postgres import reset_db_adapter
        reset_db_adapter()
    except ImportError:
        pass
