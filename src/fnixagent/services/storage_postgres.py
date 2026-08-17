"""
PostgreSQL 持久化存储层(Phase 0.8)。

适配器模式:与 services/storage.py 中的内存 Store 接口完全一致,
但底层数据写入 PostgreSQL,重启不丢。

设计要点:
  - 接口签名与 InMemory Store 完全一致(Stored* dataclass 不变)
  - ORM 模型与 Stored* dataclass 之间双向转换
  - 默认租户(tenant_id=1)在首次调用时自动创建
  - quota 信息存入 User.profile JSON 字段
  - 登录失败追踪保持内存模式(短时数据,无需持久化)
  - 文件落盘逻辑与 InMemory 版本一致(本地 data/uploads/)

启用方式:
  设置环境变量 DATABASE_URL=postgresql+psycopg2://user:pass@host:port/db
  工厂函数 get_user_store() 等会自动切换到 Pg 实现。
  未设置 DATABASE_URL 时,回退到内存 Store(开发/测试零依赖)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as SASession

from fnixagent.adapters.db.postgres import DatabaseAdapter
from fnixagent.models.db.models import (
    APICredential,
    Document,
    Task,
    TaskStep,
    Tenant,
    User,
)
from fnixagent.services.storage import (
    ALLOWED_FILE_EXTENSIONS,
    LOGIN_LOCKOUT_SECONDS,
    MAX_LIST_LIMIT,
    MAX_LOGIN_ATTEMPTS,
    MAX_UPLOAD_SIZE_BYTES,
    StoredApiKey,
    StoredDocument,
    StoredTask,
    StoredTaskStep,
    StoredUser,
    hash_password,
    needs_rehash,
    verify_password,
)

# 默认租户 ID(首次调用时自动创建)
_DEFAULT_TENANT_ID: int = 1
_DEFAULT_TENANT_NAME: str = "default"

def _ensure_default_tenant(session: SASession) -> None:
    """确保默认租户存在(幂等)。"""
    tenant = session.get(Tenant, _DEFAULT_TENANT_ID)
    if tenant is None:
        tenant = Tenant(
            id=_DEFAULT_TENANT_ID,
            name=_DEFAULT_TENANT_NAME,
            plan="free",
            quota_tokens=0,
        )
        session.add(tenant)
        session.flush()

# ---------------------------------------------------------------------------
# ORM ↔ Dataclass 转换函数
# ---------------------------------------------------------------------------

def _user_to_stored(u: User) -> StoredUser:
    """User ORM → StoredUser dataclass。quota 信息从 profile JSON 提取。"""
    profile = u.profile or {}
    return StoredUser(
        id=u.id,
        username=u.username,
        email=u.email or "",
        password_hash=u.password_hash or "",
        role=u.role,
        profile={k: v for k, v in profile.items() if k not in ("quota_total", "quota_used")},
        quota_total=profile.get("quota_total", 100000),
        quota_used=profile.get("quota_used", 0),
        created_at=u.created_at,
    )

def _cred_to_stored(c: APICredential, plaintext: str = "") -> StoredApiKey:
    """APICredential ORM → StoredApiKey dataclass。"""
    return StoredApiKey(
        id=c.id,
        user_id=c.user_id,
        api_key=plaintext,
        api_key_hash=c.api_key_hash,
        scopes=c.scopes or ["chat"],
        created_at=c.created_at,
        expires_at=c.expires_at,
        revoked=bool(c.revoked_at),
    )

def _doc_to_stored(d: Document) -> StoredDocument:
    """Document ORM → StoredDocument dataclass。"""
    return StoredDocument(
        id=d.id,
        name=d.name,
        doc_type=d.doc_type,
        source=d.source,
        object_key=d.object_key or "",
        mime_type=d.mime_type or "",
        size_bytes=d.size_bytes or 0,
        checksum=d.checksum or "",
        metadata=d.meta or {},  # type: ignore[attr-defined]
        user_id=d.user_id,
        created_at=d.created_at,
        deleted=bool(d.deleted_at),
    )

def _task_to_stored(t: Task, steps: list[TaskStep]) -> StoredTask:
    """Task ORM + TaskStep 列表 → StoredTask dataclass。"""
    stored_steps = [
        StoredTaskStep(
            step_no=s.step_no,
            description=s.description,
            tool_name=s.tool_name or "",
            status=s.status,
            started_at=s.started_at,
            finished_at=s.finished_at,
            result=None,  # TaskStep ORM 无 result 字段,用 metadata 替代(此处简化)
            error="",  # 同上
        )
        for s in sorted(steps, key=lambda x: x.step_no)
    ]
    return StoredTask(
        id=t.id,
        session_id=t.session_id,
        user_id=t.user_id,
        intent=t.intent or "",
        reasoning_mode=t.reasoning_mode,
        status=t.status,
        steps=stored_steps,
        result=t.result,
        error=t.error or "",
        created_at=t.created_at,
        started_at=t.started_at,
        finished_at=t.finished_at,
    )

# ---------------------------------------------------------------------------
# PgUserStore
# ---------------------------------------------------------------------------

class PgUserStore:
    """PostgreSQL 持久化 UserStore(接口与 UserStore 一致)。"""

    def __init__(self, db: DatabaseAdapter):
        self._db = db
        self._lock = threading.RLock()
        # 登录失败追踪:内存模式(短时数据)
        self._login_attempts: dict[str, list] = {}
        # 初始化默认租户
        with self._db.session() as session:
            _ensure_default_tenant(session)

    def create(
        self, username: str, email: str, password: str, role: str = "user"
    ) -> tuple[StoredUser | None, str]:
        """创建用户。返回 (user, error_msg)。"""
        with self._db.session() as session:
            # 检查用户名唯一
            existing = (
                session.query(User)
                .filter_by(tenant_id=_DEFAULT_TENANT_ID, username=username)
                .first()
            )
            if existing:
                return None, "用户名已存在"
            # 检查邮箱唯一
            if email:
                existing_email = session.query(User).filter_by(email=email).first()
                if existing_email:
                    return None, "邮箱已被注册"
            # 创建用户
            user = User(
                tenant_id=_DEFAULT_TENANT_ID,
                username=username,
                email=email or "",
                password_hash=hash_password(password),
                role=role,
                profile={"quota_total": 100000, "quota_used": 0},
            )
            session.add(user)
            session.flush()
            return _user_to_stored(user), ""

    def get_by_id(self, user_id: int) -> StoredUser | None:
        """根据 ID 获取用户。"""
        with self._db.session() as session:
            user = session.get(User, user_id)
            return _user_to_stored(user) if user else None

    def get_by_username(self, username: str) -> StoredUser | None:
        """根据用户名获取用户。"""
        with self._db.session() as session:
            user = (
                session.query(User)
                .filter_by(tenant_id=_DEFAULT_TENANT_ID, username=username)
                .first()
            )
            return _user_to_stored(user) if user else None

    def get_by_email(self, email: str) -> StoredUser | None:
        """根据邮箱获取用户(用于 LDAP 用户按邮箱映射)。"""
        if not email:
            return None
        with self._db.session() as session:
            user = session.query(User).filter_by(email=email).first()
            return _user_to_stored(user) if user else None

    def get_by_phone(self, phone: str) -> StoredUser | None:
        """根据手机号获取用户(用于手机号验证码登录)。

        手机号存储在 profile JSON 字段的 phone 子键中。
        使用 PostgreSQL JSON 操作符查询:profile->>'phone' = :phone
        """
        if not phone:
            return None
        with self._db.session() as session:
            # profile 是 JSON 列,使用 ->> 操作符提取 phone 字段
            user = session.query(User).filter(User.profile["phone"].astext == phone).first()
            return _user_to_stored(user) if user else None

    def authenticate(self, username: str, password: str) -> StoredUser | None:
        """验证用户名+密码,返回用户或 None。

        安全:登录失败次数追踪,超过阈值后锁定。
        PBKDF2 旧哈希在登录成功后自动升级为 Argon2id。
        """
        now = time.monotonic()
        with self._lock:
            attempt = self._login_attempts.get(username)
            if attempt and attempt[2] > 0 and now < attempt[2]:
                return None  # 锁定中

        user = self.get_by_username(username)
        if not user:
            self._record_failed_login(username)
            return None
        # 禁用用户拒绝登录(立即生效)
        if user.profile and user.profile.get("disabled"):
            return None
        if not verify_password(password, user.password_hash):
            self._record_failed_login(username)
            return None

        # 登录成功:清除失败记录
        with self._lock:
            self._login_attempts.pop(username, None)

        # 自动哈希升级:检测到旧 PBKDF2 哈希时重新哈希为 Argon2id
        if needs_rehash(user.password_hash):
            self.update_password(user.id, password)

        return user

    def _record_failed_login(self, username: str) -> None:
        """记录一次登录失败,达到阈值后锁定。"""
        now = time.monotonic()
        with self._lock:
            attempt = self._login_attempts.get(username)
            if attempt is None or (attempt[2] > 0 and now >= attempt[2]):
                self._login_attempts[username] = [1, now, 0.0]
            else:
                attempt[0] += 1
                if attempt[0] >= MAX_LOGIN_ATTEMPTS:
                    attempt[2] = now + LOGIN_LOCKOUT_SECONDS

    def update_profile(self, user_id: int, profile: dict) -> StoredUser | None:
        """更新用户画像字段。"""
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return None
            # 创建新 dict 触发 SQLAlchemy JSON 列变更检测(原地修改不会标记 dirty)
            current = dict(user.profile or {})
            # 不覆盖 quota 字段
            for k, v in profile.items():
                if k not in ("quota_total", "quota_used"):
                    current[k] = v
            user.profile = current
            session.flush()
            return _user_to_stored(user)

    def update_password(self, user_id: int, password_plain: str) -> bool:
        """更新用户密码(明文传入,内部用 Argon2id 哈希)。"""
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return False
            user.password_hash = hash_password(password_plain)
            return True

    def add_usage(self, user_id: int, tokens: int) -> None:
        """累加 Token 用量(存入 profile JSON)。"""
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return
            # 创建新 dict 触发 SQLAlchemy JSON 列变更检测(原地修改不会标记 dirty)
            profile = dict(user.profile or {})
            profile["quota_used"] = profile.get("quota_used", 0) + tokens
            user.profile = profile

    def get_quota(self, user_id: int) -> dict | None:
        """获取用户 Token 配额信息。"""
        user = self.get_by_id(user_id)
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
        search: str | None = None,
    ) -> tuple[list[StoredUser], int]:
        """列出用户(支持搜索 + 分页)。返回 (users, total)。"""
        with self._db.session() as session:
            q = session.query(User).filter_by(tenant_id=_DEFAULT_TENANT_ID)
            if search:
                like = f"%{search}%"
                q = q.filter((User.username.like(like)) | (User.email.like(like)))
            total = q.count()
            users = (
                q.order_by(User.id.desc())
                .limit(max(1, min(200, limit)))
                .offset(max(0, offset))
                .all()
            )
            return [_user_to_stored(u) for u in users], total

    def set_user_disabled(self, user_id: int, disabled: bool) -> bool:
        """启用/禁用用户(禁用后该用户无法登录)。

        通过 profile.disabled 标记实现,不修改数据库 schema。
        """
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return False
            profile = dict(user.profile or {})
            profile["disabled"] = bool(disabled)
            user.profile = profile
            return True

    def is_user_disabled(self, user_id: int) -> bool:
        """检查用户是否被禁用。"""
        user = self.get_by_id(user_id)
        if not user:
            return True
        return bool(user.profile.get("disabled", False)) if user.profile else False

    # ------------------------------------------------------------------
    # Phase 3.2: 账号注销(软删除 + 30 天硬删除)— Pg 实现
    # ------------------------------------------------------------------

    def soft_delete_user(self, user_id: int, retention_days: int = 30) -> bool:
        """软删除用户(标记为待删除 + 禁用登录)。"""
        from datetime import datetime, timedelta

        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return False
            now = datetime.now(UTC)
            hard_delete_at = now + timedelta(days=retention_days)
            profile = dict(user.profile or {})
            profile["deleted_at"] = now.isoformat()
            profile["hard_delete_at"] = hard_delete_at.isoformat()
            profile["disabled"] = True
            user.profile = profile
            return True

    def cancel_soft_delete(self, user_id: int) -> bool:
        """撤销软删除(在 30 天保留期内可恢复)。"""
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return False
            profile = dict(user.profile or {})
            profile.pop("deleted_at", None)
            profile.pop("hard_delete_at", None)
            profile["disabled"] = False
            user.profile = profile
            return True

    def hard_delete_user(self, user_id: int) -> bool:
        """硬删除用户(从数据库中彻底移除)。"""
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return False
            session.delete(user)
            return True

    def get_soft_deleted_users(self) -> list:
        """获取所有已软删除的用户。"""
        with self._db.session() as session:
            users = session.query(User).filter_by(tenant_id=_DEFAULT_TENANT_ID).all()
            return [_user_to_stored(u) for u in users if u.profile and u.profile.get("deleted_at")]

    def get_users_to_hard_delete(self, before=None) -> list:
        """获取已过保留期、待硬删除的用户。"""
        from datetime import datetime

        if before is None:
            before = datetime.now(UTC)
        with self._db.session() as session:
            users = session.query(User).filter_by(tenant_id=_DEFAULT_TENANT_ID).all()
            result = []
            for u in users:
                if not u.profile:
                    continue
                hard_delete_at_str = u.profile.get("hard_delete_at")
                if not hard_delete_at_str:
                    continue
                try:
                    hard_delete_at = datetime.fromisoformat(hard_delete_at_str)
                except (ValueError, TypeError):
                    continue
                if hard_delete_at <= before:
                    result.append(_user_to_stored(u))
            return result

    def is_user_deleted(self, user_id: int) -> bool:
        """检查用户是否已软删除。"""
        user = self.get_by_id(user_id)
        if not user:
            return True
        return bool(user.profile.get("deleted_at")) if user.profile else False

    def update_role(self, user_id: int, role: str) -> bool:
        """更新用户角色(user/admin)。"""
        if role not in ("user", "admin"):
            return False
        with self._db.session() as session:
            user = session.get(User, user_id)
            if not user:
                return False
            user.role = role
            return True

    @property
    def count(self) -> int:
        """已注册用户数量。"""
        with self._db.session() as session:
            return session.query(User).filter_by(tenant_id=_DEFAULT_TENANT_ID).count()

# ---------------------------------------------------------------------------
# PgApiKeyStore
# ---------------------------------------------------------------------------

class PgApiKeyStore:
    """PostgreSQL 持久化 ApiKeyStore。"""

    def __init__(self, db: DatabaseAdapter):
        self._db = db
        self._lock = threading.RLock()

    def create(
        self, user_id: int, scopes: list | None = None, expires_days: int = 365
    ) -> StoredApiKey:
        """为用户创建 API Key。明文 key 只返回一次。"""
        with self._lock, self._db.session() as session:
            plaintext = f"sk-fnixagent-{secrets.token_urlsafe(32)}"
            key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
            cred = APICredential(
                user_id=user_id,
                api_key_hash=key_hash,
                scopes=scopes or ["chat"],
                expires_at=datetime.now(UTC) + timedelta(days=expires_days),
            )
            session.add(cred)
            session.flush()
            return _cred_to_stored(cred, plaintext)

    def revoke(self, key_id: int, user_id: int) -> bool:
        """吊销 API Key(仅本人)。"""
        with self._db.session() as session:
            cred = session.get(APICredential, key_id)
            if not cred or cred.user_id != user_id or cred.revoked_at:
                return False
            cred.revoked_at = datetime.now(UTC)
            return True

    def list_by_user(self, user_id: int) -> list[StoredApiKey]:
        """列出指定用户的所有 API Key(不含已吊销)。"""
        with self._db.session() as session:
            creds = (
                session.query(APICredential)
                .filter_by(user_id=user_id, revoked_at=None)
                .order_by(APICredential.created_at.desc())
                .all()
            )
            return [_cred_to_stored(c) for c in creds]

# ---------------------------------------------------------------------------
# PgDocumentStore
# ---------------------------------------------------------------------------

class PgDocumentStore:
    """PostgreSQL 持久化 DocumentStore(文件落盘 + 元数据入库)。"""

    def __init__(self, db: DatabaseAdapter, storage_dir: str | None = None):
        self._db = db
        self._lock = threading.RLock()
        self._storage_dir = storage_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "data",
            "uploads",
        )
        os.makedirs(self._storage_dir, exist_ok=True)

    @property
    def storage_dir(self) -> str:
        """本地文件存储目录。"""
        return self._storage_dir

    def _detect_doc_type(self, filename: str) -> str:
        """根据扩展名推断文档类型。"""
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        mapping = {
            "pdf": "pdf",
            "docx": "docx",
            "doc": "docx",
            "txt": "markdown",
            "md": "markdown",
            "png": "chart",
            "jpg": "chart",
            "jpeg": "chart",
            "csv": "table",
            "xlsx": "table",
        }
        return mapping.get(ext, "unknown")

    def _detect_mime(self, filename: str) -> str:
        """根据扩展名推断 MIME 类型。"""
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        mimes = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "txt": "text/plain",
            "md": "text/markdown",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return mimes.get(ext, "application/octet-stream")

    def _save_file(self, object_key: str, content: bytes) -> str:
        """将文件内容写入本地存储,返回绝对路径。"""
        file_path = os.path.join(self._storage_dir, object_key)
        with open(file_path, "wb") as f:
            f.write(content)
        return file_path

    def save_upload(
        self,
        filename: str,
        content: bytes,
        user_id: int = 0,
        metadata: dict | None = None,
    ) -> StoredDocument:
        """保存上传文件,返回文档记录。

        安全校验:文件大小 / 扩展名白名单 / 文件名净化(与内存版一致)。
        路径穿越检查优先于扩展名检查(安全优先,拒绝可疑文件名再处理)。
        """
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise ValueError(f"文件大小 {len(content)} 字节超过上限 {MAX_UPLOAD_SIZE_BYTES} 字节")
        # 安全校验:路径穿越检测(优先于扩展名检查)
        # 原始文件名中含 ".." 或路径分隔符即视为攻击,直接拒绝
        if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
            raise ValueError("非法文件名")
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        if ext not in ALLOWED_FILE_EXTENSIONS:
            raise ValueError(f"不支持的文件类型 '.{ext}',允许: {sorted(ALLOWED_FILE_EXTENSIONS)}")
        safe_name = os.path.basename(filename).replace(os.sep, "_").replace("..", "_")
        if not safe_name or safe_name.startswith("."):
            raise ValueError("非法文件名")

        with self._lock, self._db.session() as session:
            doc_type = self._detect_doc_type(filename)
            # 先创建记录获取 ID,再拼接 object_key
            doc = Document(
                tenant_id=_DEFAULT_TENANT_ID,
                user_id=user_id,
                name=safe_name,
                doc_type=doc_type,
                source="upload",
                mime_type=self._detect_mime(filename),
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                meta=metadata or {},  # type: ignore[arg-type]
            )
            session.add(doc)
            session.flush()
            # 拼接 object_key 并落盘
            doc.object_key = f"{doc.id}_{safe_name}"
            self._save_file(doc.object_key, content)
            return _doc_to_stored(doc)

    def create_generated(
        self,
        name: str,
        doc_type: str,
        content: bytes,
        user_id: int = 0,
        metadata: dict | None = None,
    ) -> StoredDocument:
        """Agent 生成的文档。"""
        with self._lock, self._db.session() as session:
            safe_name = os.path.basename(name).replace(os.sep, "_")
            doc = Document(
                tenant_id=_DEFAULT_TENANT_ID,
                user_id=user_id,
                name=name,
                doc_type=doc_type,
                source="generated",
                mime_type=self._detect_mime(name),
                size_bytes=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                meta=metadata or {},  # type: ignore[arg-type]
            )
            session.add(doc)
            session.flush()
            doc.object_key = f"{doc.id}_{safe_name}"
            self._save_file(doc.object_key, content)
            return _doc_to_stored(doc)

    def get(self, doc_id: int) -> StoredDocument | None:
        """根据 ID 获取未删除的文档。"""
        with self._db.session() as session:
            doc = session.get(Document, doc_id)
            if not doc or doc.deleted_at:
                return None
            return _doc_to_stored(doc)

    def get_file_path(self, doc_id: int) -> str | None:
        """获取文档落盘文件的绝对路径,文件缺失返回 None。"""
        doc = self.get(doc_id)
        if not doc:
            return None
        path = os.path.join(self._storage_dir, doc.object_key)
        return path if os.path.exists(path) else None

    def list(
        self,
        user_id: int | None = None,
        doc_type: str | None = None,
        limit: int = 50,
    ) -> list[StoredDocument]:
        """查询文档列表,支持按用户/类型过滤。"""
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        with self._db.session() as session:
            q = session.query(Document).filter(Document.deleted_at.is_(None))
            if user_id is not None:
                q = q.filter(Document.user_id == user_id)
            if doc_type:
                q = q.filter(Document.doc_type == doc_type)
            docs = q.order_by(Document.created_at.desc()).limit(limit).all()
            return [_doc_to_stored(d) for d in docs]

    def delete(self, doc_id: int) -> bool:
        """软删除(置 deleted_at,保留文件)。"""
        with self._db.session() as session:
            doc = session.get(Document, doc_id)
            if not doc or doc.deleted_at:
                return False
            doc.deleted_at = datetime.now(UTC)
            return True

    @property
    def count(self) -> int:
        """未删除的文档数量。"""
        with self._db.session() as session:
            return session.query(Document).filter(Document.deleted_at.is_(None)).count()

# ---------------------------------------------------------------------------
# PgTaskStore
# ---------------------------------------------------------------------------

class PgTaskStore:
    """PostgreSQL 持久化 TaskStore。"""

    def __init__(self, db: DatabaseAdapter):
        self._db = db
        self._lock = threading.RLock()
        # 确保 session 表中存在一个默认 session(id=1)供无 session 场景使用
        self._ensure_default_session()

    def _ensure_default_session(self) -> None:
        """确保默认 session 存在(Task.session_id 是 NOT NULL FK)。"""
        from fnixagent.models.db.models import Session

        with self._db.session() as session:
            _ensure_default_tenant(session)
            existing = session.get(Session, 1)
            if existing is None:
                default_session = Session(
                    id=1,
                    tenant_id=_DEFAULT_TENANT_ID,
                    user_id=1,
                    title="default",
                    context={},
                    status="active",
                )
                session.add(default_session)
                session.flush()

    def create(
        self,
        session_id: int,
        intent: str,
        reasoning_mode: str = "react",
        user_id: int = 0,
    ) -> StoredTask:
        """创建 pending 状态的任务记录。"""
        with self._lock, self._db.session() as session:
            # 确保 session_id 有效(不存在则用默认 session)
            valid_session_id = session_id
            if session_id <= 0:
                valid_session_id = 1
            task = Task(
                session_id=valid_session_id,
                user_id=user_id,
                intent=intent,
                reasoning_mode=reasoning_mode,
                status="pending",
                plan={},
            )
            session.add(task)
            session.flush()
            return _task_to_stored(task, [])

    def get(self, task_id: int) -> StoredTask | None:
        """根据 ID 获取任务(含步骤)。"""
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            steps = session.query(TaskStep).filter_by(task_id=task_id).all()
            return _task_to_stored(task, steps)

    def start(self, task_id: int) -> StoredTask | None:
        """标记任务开始执行。"""
        with self._lock, self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            task.status = "running"
            task.started_at = datetime.now(UTC)
            return _task_to_stored(task, session.query(TaskStep).filter_by(task_id=task_id).all())

    def add_step(
        self, task_id: int, description: str, tool_name: str = ""
    ) -> StoredTaskStep | None:
        """为任务追加一个步骤,返回新增步骤。"""
        with self._lock, self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            # 计算下一个 step_no
            max_step = (
                session.query(TaskStep)
                .filter_by(task_id=task_id)
                .order_by(TaskStep.step_no.desc())
                .first()
            )
            step_no = (max_step.step_no + 1) if max_step else 1
            step = TaskStep(
                task_id=task_id,
                step_no=step_no,
                description=description,
                tool_name=tool_name,
                status="pending",
                depends_on=[],
            )
            session.add(step)
            session.flush()
            return StoredTaskStep(
                step_no=step.step_no,
                description=step.description,
                tool_name=step.tool_name or "",
                status=step.status,
            )

    def update_step(
        self,
        task_id: int,
        step_no: int,
        status: str,
        result: dict | None = None,
        error: str = "",
    ) -> bool:
        """更新指定步骤的状态/结果,自动维护起止时间。"""
        with self._lock, self._db.session() as session:
            step = session.query(TaskStep).filter_by(task_id=task_id, step_no=step_no).first()
            if not step:
                return False
            step.status = status
            if status == "running" and not step.started_at:
                step.started_at = datetime.now(UTC)
            if status in ("success", "failed") and not step.finished_at:
                step.finished_at = datetime.now(UTC)
            return True

    def complete(self, task_id: int, result: dict | None = None) -> StoredTask | None:
        """标记任务成功完成。"""
        with self._lock, self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            task.status = "succeeded"
            task.finished_at = datetime.now(UTC)
            if result is not None:
                task.result = result
            return _task_to_stored(task, session.query(TaskStep).filter_by(task_id=task_id).all())

    def fail(self, task_id: int, error: str) -> StoredTask | None:
        """标记任务失败并记录错误信息。"""
        with self._lock, self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            task.status = "failed"
            task.finished_at = datetime.now(UTC)
            task.error = error
            return _task_to_stored(task, session.query(TaskStep).filter_by(task_id=task_id).all())

    def cancel(self, task_id: int) -> StoredTask | None:
        """取消任务(仅未完成的任务可取消)。"""
        with self._lock, self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            if task.status in ("succeeded", "failed", "cancelled"):
                return None
            task.status = "cancelled"
            task.finished_at = datetime.now(UTC)
            return _task_to_stored(task, session.query(TaskStep).filter_by(task_id=task_id).all())

    def retry(self, task_id: int) -> StoredTask | None:
        """重置任务状态为 pending,允许重新执行。"""
        with self._lock, self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            task.status = "pending"
            task.started_at = None
            task.finished_at = None
            task.error = ""
            # 重置所有步骤
            steps = session.query(TaskStep).filter_by(task_id=task_id).all()
            for s in steps:
                s.status = "pending"
                s.started_at = None
                s.finished_at = None
            return _task_to_stored(task, steps)

    def list(
        self,
        user_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[StoredTask]:
        """查询任务列表,支持按用户/状态过滤,按创建时间倒序。"""
        limit = max(1, min(limit, MAX_LIST_LIMIT))
        with self._db.session() as session:
            q = session.query(Task)
            if user_id is not None:
                q = q.filter(Task.user_id == user_id)
            if status:
                q = q.filter(Task.status == status)
            tasks = q.order_by(Task.created_at.desc()).limit(limit).all()
            result = []
            for t in tasks:
                steps = session.query(TaskStep).filter_by(task_id=t.id).all()
                result.append(_task_to_stored(t, steps))
            return result

    def get_status(self, task_id: int) -> dict | None:
        """获取任务状态摘要(进度/当前步骤/总步骤数)。"""
        with self._db.session() as session:
            task = session.get(Task, task_id)
            if not task:
                return None
            steps = session.query(TaskStep).filter_by(task_id=task_id).all()
            total = len(steps)
            done = sum(1 for s in steps if s.status in ("success", "failed"))
            current = next((s.step_no for s in steps if s.status == "running"), None)
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
        with self._db.session() as session:
            return session.query(Task).count()

# ---------------------------------------------------------------------------
# 工厂函数(根据 DATABASE_URL 选择实现)
# ---------------------------------------------------------------------------

_db_adapter: DatabaseAdapter | None = None
_db_adapter_lock = threading.Lock()

def get_db_adapter() -> DatabaseAdapter | None:
    """获取 DatabaseAdapter 单例。

    优先级:
      1. 环境变量 DATABASE_URL(production/docker)
      2. 未设置则返回 None(回退到内存 Store)
    """
    global _db_adapter
    if _db_adapter is None:
        with _db_adapter_lock:
            if _db_adapter is None:
                url = os.getenv("DATABASE_URL")
                if not url:
                    return None
                _db_adapter = DatabaseAdapter(url)
    return _db_adapter

def reset_db_adapter() -> None:
    """重置 DatabaseAdapter 单例(用于测试)。"""
    global _db_adapter
    with _db_adapter_lock:
        _db_adapter = None
