"""
MFA 存储层(Phase 2.4)。

提供四类存储:
    1. MFAFactorStore:       用户已绑定的 MFA 因子(TOTP secret / SMS 手机号 / EMAIL)
    2. RecoveryCodeStore:    备用恢复码(SHA256 哈希,一次性)
    3. OTPChallengeStore:    短信/邮箱 OTP challenge(短期,5min TTL)
    4. MFAEnforcementStore:  MFA 强制策略(按角色)

设计要点:
    - 同 LDAP/SSO,统一使用内存实现(MFA 配置不常变,重启后可通过 admin API 重建)
    - TOTP secret 在 to_dict() 时默认隐藏(避免泄露)
    - 恢复码只存哈希,明文仅生成时返回一次
    - OTP challenge 5 分钟自动过期(consume 或 expire)
    - 强制策略:管理员配置某些角色必须开 MFA(如 admin / finance)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from fnixagent.core.security.auth.mfa import (
    FACTOR_EMAIL,
    FACTOR_SMS,
    FACTOR_TOTP,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_COOLDOWN_SECONDS,
    OTP_TTL_SECONDS,
    OTPChallenge,
    OTPClient,
)

# ---------------------------------------------------------------------------
# 因子 DTO
# ---------------------------------------------------------------------------


@dataclass
class MFAFactorDTO:
    """用户已绑定的 MFA 因子。"""

    id: int
    user_id: int
    factor_type: str  # "totp" / "sms" / "email"
    secret: str = ""  # TOTP Base32 secret(敏感)
    phone: str = ""  # SMS 手机号
    email: str = ""  # EMAIL 邮箱
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self, include_secret: bool = False) -> dict:
        d = {
            "id": self.id,
            "user_id": self.user_id,
            "factor_type": self.factor_type,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.factor_type == FACTOR_TOTP:
            if include_secret:
                d["secret"] = self.secret
        elif self.factor_type == FACTOR_SMS:
            d["phone"] = OTPClient.mask_target(self.phone, FACTOR_SMS)
        elif self.factor_type == FACTOR_EMAIL:
            d["email"] = OTPClient.mask_target(self.email, FACTOR_EMAIL)
        return d


@dataclass
class RecoveryCodeDTO:
    """备用恢复码记录。"""

    id: int
    user_id: int
    code_hash: str  # SHA256
    used: bool = False
    used_at: datetime | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "used": self.used,
            "used_at": self.used_at.isoformat() if self.used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class MFAEnforcementDTO:
    """MFA 强制策略(按角色)。"""

    id: int
    role: str
    factor_type: str  # "totp" / "any"
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "factor_type": self.factor_type,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ---------------------------------------------------------------------------
# 内存实现:因子存储
# ---------------------------------------------------------------------------


class InMemoryMFAFactorStore:
    """内存 MFA 因子存储(开发/测试用)。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._factors: dict[int, MFAFactorDTO] = {}
        self._next_id = 1

    def list_by_user(self, user_id: int, include_disabled: bool = True) -> list[MFAFactorDTO]:
        with self._lock:
            result = [f for f in self._factors.values() if f.user_id == user_id]
            if not include_disabled:
                result = [f for f in result if f.enabled]
            return sorted(result, key=lambda x: x.id)

    def get(self, factor_id: int) -> MFAFactorDTO | None:
        with self._lock:
            return self._factors.get(factor_id)

    def get_totp(self, user_id: int) -> MFAFactorDTO | None:
        with self._lock:
            for f in self._factors.values():
                if f.user_id == user_id and f.factor_type == FACTOR_TOTP and f.enabled:
                    return f
            return None

    def get_sms(self, user_id: int) -> MFAFactorDTO | None:
        with self._lock:
            for f in self._factors.values():
                if f.user_id == user_id and f.factor_type == FACTOR_SMS and f.enabled:
                    return f
            return None

    def get_email(self, user_id: int) -> MFAFactorDTO | None:
        with self._lock:
            for f in self._factors.values():
                if f.user_id == user_id and f.factor_type == FACTOR_EMAIL and f.enabled:
                    return f
            return None

    def has_enabled_factor(self, user_id: int) -> bool:
        with self._lock:
            return any(f.user_id == user_id and f.enabled for f in self._factors.values())

    def create(self, user_id: int, factor_type: str, **kwargs) -> MFAFactorDTO:
        with self._lock:
            fid = self._next_id
            self._next_id += 1
            now = datetime.utcnow()
            factor = MFAFactorDTO(
                id=fid,
                user_id=user_id,
                factor_type=factor_type,
                secret=kwargs.get("secret", ""),
                phone=kwargs.get("phone", ""),
                email=kwargs.get("email", ""),
                enabled=kwargs.get("enabled", True),
                created_at=now,
                updated_at=now,
            )
            self._factors[fid] = factor
            return factor

    def update(self, factor_id: int, **kwargs) -> MFAFactorDTO | None:
        with self._lock:
            factor = self._factors.get(factor_id)
            if not factor:
                return None
            for k in ("secret", "phone", "email", "enabled"):
                if k in kwargs and kwargs[k] is not None:
                    setattr(factor, k, kwargs[k])
            factor.updated_at = datetime.utcnow()
            return factor

    def delete(self, factor_id: int) -> bool:
        with self._lock:
            if factor_id not in self._factors:
                return False
            del self._factors[factor_id]
            return True

    def delete_all_by_user(self, user_id: int) -> int:
        with self._lock:
            to_del = [fid for fid, f in self._factors.items() if f.user_id == user_id]
            for fid in to_del:
                del self._factors[fid]
            return len(to_del)


# ---------------------------------------------------------------------------
# 内存实现:恢复码存储
# ---------------------------------------------------------------------------


class InMemoryRecoveryCodeStore:
    """内存恢复码存储。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._codes: dict[int, RecoveryCodeDTO] = {}
        self._next_id = 1

    def list_by_user(self, user_id: int, include_used: bool = True) -> list[RecoveryCodeDTO]:
        with self._lock:
            result = [c for c in self._codes.values() if c.user_id == user_id]
            if not include_used:
                result = [c for c in result if not c.used]
            return sorted(result, key=lambda x: x.id)

    def count_unused(self, user_id: int) -> int:
        with self._lock:
            return sum(1 for c in self._codes.values() if c.user_id == user_id and not c.used)

    def create(self, user_id: int, code_hash: str) -> RecoveryCodeDTO:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
            now = datetime.utcnow()
            code = RecoveryCodeDTO(
                id=cid,
                user_id=user_id,
                code_hash=code_hash,
                used=False,
                created_at=now,
            )
            self._codes[cid] = code
            return code

    def find_unused_by_hash(self, user_id: int, code_hash: str) -> RecoveryCodeDTO | None:
        with self._lock:
            for c in self._codes.values():
                if c.user_id == user_id and not c.used and c.code_hash == code_hash:
                    return c
            return None

    def mark_used(self, code_id: int) -> bool:
        with self._lock:
            c = self._codes.get(code_id)
            if not c or c.used:
                return False
            c.used = True
            c.used_at = datetime.utcnow()
            return True

    def delete_all_by_user(self, user_id: int) -> int:
        with self._lock:
            to_del = [cid for cid, c in self._codes.items() if c.user_id == user_id]
            for cid in to_del:
                del self._codes[cid]
            return len(to_del)


# ---------------------------------------------------------------------------
# 内存实现:OTP challenge 存储
# ---------------------------------------------------------------------------


class InMemoryOTPChallengeStore:
    """内存 OTP challenge 存储(短信/邮箱)。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._challenges: dict[str, OTPChallenge] = {}

    def create(
        self,
        user_id: int,
        factor_type: str,
        target: str,
        code_hash: str,
        ttl: int = OTP_TTL_SECONDS,
    ) -> OTPChallenge:
        import secrets as _secrets

        with self._lock:
            challenge_id = _secrets.token_urlsafe(16)
            now = time.time()
            challenge = OTPChallenge(
                challenge_id=challenge_id,
                user_id=user_id,
                factor_type=factor_type,
                target=target,
                code_hash=code_hash,
                expires_at=now + ttl,
                attempts=0,
                consumed=False,
                created_at=now,
            )
            self._challenges[challenge_id] = challenge
            return challenge

    def get(self, challenge_id: str) -> OTPChallenge | None:
        with self._lock:
            c = self._challenges.get(challenge_id)
            if c is None:
                return None
            return OTPChallenge(
                challenge_id=c.challenge_id,
                user_id=c.user_id,
                factor_type=c.factor_type,
                target=c.target,
                code_hash=c.code_hash,
                expires_at=c.expires_at,
                attempts=c.attempts,
                consumed=c.consumed,
                created_at=c.created_at,
            )

    def get_active_by_user(self, user_id: int, factor_type: str) -> OTPChallenge | None:
        with self._lock:
            now = time.time()
            for c in self._challenges.values():
                if (
                    c.user_id == user_id
                    and c.factor_type == factor_type
                    and not c.consumed
                    and c.expires_at > now
                ):
                    return c
            return None

    def check_resend_cooldown(self, user_id: int, factor_type: str) -> bool:
        """检查是否在重发冷却期内。

        Returns:
            True=可以发送(已过冷却期), False=冷却中
        """
        with self._lock:
            now = time.time()
            for c in self._challenges.values():
                if (
                    c.user_id == user_id
                    and c.factor_type == factor_type
                    and not c.consumed
                    and (now - c.created_at) < OTP_RESEND_COOLDOWN_SECONDS
                ):
                    return False
            return True

    def increment_attempts(self, challenge_id: str) -> OTPChallenge | None:
        with self._lock:
            c = self._challenges.get(challenge_id)
            if c is None:
                return None
            c.attempts += 1
            if c.attempts >= OTP_MAX_ATTEMPTS:
                c.consumed = True
            return c

    def consume(self, challenge_id: str) -> bool:
        with self._lock:
            c = self._challenges.get(challenge_id)
            if c is None or c.consumed:
                return False
            c.consumed = True
            return True

    def cleanup_expired(self) -> int:
        with self._lock:
            now = time.time()
            expired = [cid for cid, c in self._challenges.items() if c.expires_at <= now]
            for cid in expired:
                del self._challenges[cid]
            return len(expired)


# ---------------------------------------------------------------------------
# 内存实现:MFA 强制策略存储
# ---------------------------------------------------------------------------


class InMemoryMFAEnforcementStore:
    """内存 MFA 强制策略存储(按角色)。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._enforcements: dict[int, MFAEnforcementDTO] = {}
        self._role_idx: dict[str, int] = {}
        self._next_id = 1

    def list_all(self) -> list[MFAEnforcementDTO]:
        with self._lock:
            return sorted(self._enforcements.values(), key=lambda x: x.id)

    def list_enabled(self) -> list[MFAEnforcementDTO]:
        with self._lock:
            return [e for e in self._enforcements.values() if e.enabled]

    def get_by_role(self, role: str) -> MFAEnforcementDTO | None:
        with self._lock:
            eid = self._role_idx.get(role)
            if eid is None:
                return None
            return self._enforcements.get(eid)

    def upsert(self, role: str, factor_type: str, enabled: bool = True) -> MFAEnforcementDTO:
        with self._lock:
            existing_id = self._role_idx.get(role)
            now = datetime.utcnow()
            if existing_id is not None:
                e = self._enforcements[existing_id]
                e.factor_type = factor_type
                e.enabled = enabled
                e.updated_at = now
                return e
            eid = self._next_id
            self._next_id += 1
            e = MFAEnforcementDTO(
                id=eid,
                role=role,
                factor_type=factor_type,
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
            self._enforcements[eid] = e
            self._role_idx[role] = eid
            return e

    def delete(self, enforcement_id: int) -> bool:
        with self._lock:
            e = self._enforcements.get(enforcement_id)
            if e is None:
                return False
            del self._enforcements[enforcement_id]
            self._role_idx.pop(e.role, None)
            return True

    def delete_by_role(self, role: str) -> bool:
        with self._lock:
            eid = self._role_idx.pop(role, None)
            if eid is None:
                return False
            del self._enforcements[eid]
            return True

    def is_role_enforced(self, role: str) -> bool:
        with self._lock:
            eid = self._role_idx.get(role)
            if eid is None:
                return False
            return self._enforcements[eid].enabled


# ---------------------------------------------------------------------------
# 工厂单例
# ---------------------------------------------------------------------------


_mfa_factor_store: InMemoryMFAFactorStore | None = None
_mfa_factor_store_lock = threading.Lock()

_recovery_code_store: InMemoryRecoveryCodeStore | None = None
_recovery_code_store_lock = threading.Lock()

_otp_challenge_store: InMemoryOTPChallengeStore | None = None
_otp_challenge_store_lock = threading.Lock()

_mfa_enforcement_store: InMemoryMFAEnforcementStore | None = None
_mfa_enforcement_store_lock = threading.Lock()


def get_mfa_factor_store() -> InMemoryMFAFactorStore:
    global _mfa_factor_store
    if _mfa_factor_store is None:
        with _mfa_factor_store_lock:
            if _mfa_factor_store is None:
                _mfa_factor_store = InMemoryMFAFactorStore()
    return _mfa_factor_store


def reset_mfa_factor_store() -> None:
    global _mfa_factor_store
    with _mfa_factor_store_lock:
        _mfa_factor_store = None


def get_recovery_code_store() -> InMemoryRecoveryCodeStore:
    global _recovery_code_store
    if _recovery_code_store is None:
        with _recovery_code_store_lock:
            if _recovery_code_store is None:
                _recovery_code_store = InMemoryRecoveryCodeStore()
    return _recovery_code_store


def reset_recovery_code_store() -> None:
    global _recovery_code_store
    with _recovery_code_store_lock:
        _recovery_code_store = None


def get_otp_challenge_store() -> InMemoryOTPChallengeStore:
    global _otp_challenge_store
    if _otp_challenge_store is None:
        with _otp_challenge_store_lock:
            if _otp_challenge_store is None:
                _otp_challenge_store = InMemoryOTPChallengeStore()
    return _otp_challenge_store


def reset_otp_challenge_store() -> None:
    global _otp_challenge_store
    with _otp_challenge_store_lock:
        _otp_challenge_store = None


def get_mfa_enforcement_store() -> InMemoryMFAEnforcementStore:
    global _mfa_enforcement_store
    if _mfa_enforcement_store is None:
        with _mfa_enforcement_store_lock:
            if _mfa_enforcement_store is None:
                _mfa_enforcement_store = InMemoryMFAEnforcementStore()
    return _mfa_enforcement_store


def reset_mfa_enforcement_store() -> None:
    global _mfa_enforcement_store
    with _mfa_enforcement_store_lock:
        _mfa_enforcement_store = None


def reset_all_mfa_stores() -> None:
    """重置所有 MFA 存储(测试用)。"""
    reset_mfa_factor_store()
    reset_recovery_code_store()
    reset_otp_challenge_store()
    reset_mfa_enforcement_store()
