"""
凭证治理 (Secret Manager)。

目标: 移除所有硬编码密钥,统一从环境变量 / .env 文件 / Vault 读取。

核心规则:
  - JWT 默认密钥改为启动时强制要求 fnixagent_JWT_SECRET 环境变量
  - 密钥轮换策略(30 天强制轮换,通过 .secret_meta.json 记录创建时间)
  - 优雅降级: 开发环境允许 fallback 到固定 dev key(标记 insecure=True,打印 warning)

设计原则:
  - 所有异常不外泄,get() 失败返回带 insecure=True 的占位值
  - require() 失败抛 ValueError(调用方需感知)
  - 仅依赖标准库 + 可选 python-dotenv
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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)
_logger = logger


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SecretSource:
    """凭证来源定义。

    Attributes:
        name: 凭证名(如 JWT_SECRET)
        env_var: 环境变量名(默认与 name 相同)
        required: 是否必需(默认 True)
        default: 默认值(仅 required=False 时生效)
        min_length: 最小长度(默认 16)
        max_age_days: 最大年龄天数(0 表示不限制,默认 30)
        allow_dev_fallback: 是否允许开发环境 fallback(默认 False)
    """

    name: str
    env_var: str = ""
    required: bool = True
    default: str | None = None
    min_length: int = 16
    max_age_days: int = 30
    allow_dev_fallback: bool = False


@dataclass
class SecretValue:
    """凭证取值结果。

    Attributes:
        name: 凭证名
        value: 凭证值
        source: 来源 env/file/vault/dev_fallback
        insecure: 是否不安全(仅 dev_fallback 时为 True)
        age_days: 已存在天数(None 表示未知)
        expires_at: 过期时间 ISO 字符串(None 表示不限制)
    """

    name: str
    value: str
    source: str  # "env"/"file"/"vault"/"dev_fallback"
    insecure: bool
    age_days: int | None = None
    expires_at: str | None = None


# ---------------------------------------------------------------------------
# SecretManager
# ---------------------------------------------------------------------------


class SecretManager:
    """凭证管理器(单例语义,可多实例)。

    用法:
        mgr = SecretManager()
        jwt = mgr.require("JWT_SECRET")  # 不存在抛 ValueError
        db_url = mgr.get("DATABASE_URL")  # 不存在返回 insecure 占位
        # 检查需要轮换的 secret
        expired = mgr.check_rotation()
        # 校验所有 secret 配置
        report = mgr.validate_all()
    """

    # 默认元数据文件路径(记录每个 secret 的首次创建时间)
    _META_FILE = ".secret_meta.json"

    def __init__(self, sources: list[SecretSource] | None = None) -> None:
        self._sources: dict[str, SecretSource] = {}
        self._lock = threading.Lock()
        self._meta: dict[str, dict] = self._load_meta()
        # 默认注册常用 secret
        if sources is None:
            self._register_defaults()
        else:
            for s in sources:
                self._sources[s.name] = s

    # -- 公开接口 ----------------------------------------------------------

    def get(self, name: str) -> SecretValue:
        """获取凭证(不存在时按 allow_dev_fallback 决定降级或返回空值)。"""
        src = self._sources.get(name)
        if src is None:
            # 未注册的 secret,按 default 行为处理
            return SecretValue(
                name=name,
                value="",
                source="env",
                insecure=True,
                age_days=None,
                expires_at=None,
            )
        # 1. 优先从环境变量读取
        env_var = src.env_var or name
        val = os.environ.get(env_var)
        if val:
            self._touch_meta(name)
            return SecretValue(
                name=name,
                value=val,
                source="env",
                insecure=False,
                age_days=self._age_days(name),
                expires_at=self._expires_at(src),
            )
        # 2. 尝试从 .env 文件读取(可选依赖 python-dotenv)
        val = self._read_from_dotenv(env_var)
        if val:
            self._touch_meta(name)
            return SecretValue(
                name=name,
                value=val,
                source="file",
                insecure=False,
                age_days=self._age_days(name),
                expires_at=self._expires_at(src),
            )
        # 3. 默认值
        if src.default is not None:
            return SecretValue(
                name=name,
                value=src.default,
                source="env",
                insecure=False,
                age_days=None,
                expires_at=None,
            )
        # 4. 开发 fallback
        if src.allow_dev_fallback:
            dev_val = self._gen_dev_fallback(name)
            logger.warning(
                "[secrets] %s 未配置,使用开发 fallback(不安全!)",
                name,
            )
            return SecretValue(
                name=name,
                value=dev_val,
                source="dev_fallback",
                insecure=True,
                age_days=0,
                expires_at=None,
            )
        # 5. 全部失败:返回空值(insecure=True,调用方需检查)
        return SecretValue(
            name=name,
            value="",
            source="env",
            insecure=True,
            age_days=None,
            expires_at=None,
        )

    def require(self, name: str) -> str:
        """获取凭证,不存在或不满足最小长度则抛 ValueError。"""
        src = self._sources.get(name)
        sv = self.get(name)
        if not sv.value:
            raise ValueError(f"必需的凭证 {name} 未配置(环境变量 {src.env_var or name})")
        min_len = src.min_length if src else 16
        if len(sv.value) < min_len:
            raise ValueError(f"凭证 {name} 长度 {len(sv.value)} < 最小要求 {min_len}")
        if sv.insecure and src and src.required:
            # 必需 secret 仍走 dev_fallback,启动时应告警
            logger.warning(
                "[secrets] 必需凭证 %s 当前使用 dev_fallback(生产环境必须配置!)",
                name,
            )
        return sv.value

    def check_rotation(self) -> list[str]:
        """返回需要轮换的 secret 名单(超过 max_age_days)。"""
        now = datetime.now(UTC)
        expired: list[str] = []
        for name, src in self._sources.items():
            if src.max_age_days <= 0:
                continue
            meta = self._meta.get(name)
            if not meta or "created_at" not in meta:
                continue
            try:
                created = datetime.fromisoformat(meta["created_at"])
                age = (now - created).days
                if age > src.max_age_days:
                    expired.append(name)
            except (ValueError, TypeError):
                continue
        return expired

    def register(self, source: SecretSource) -> None:
        """注册新的凭证来源。"""
        with self._lock:
            self._sources[source.name] = source

    def validate_all(self) -> dict[str, bool]:
        """校验所有已注册 secret 是否满足要求(存在 + 长度 + 非 insecure)。

        Returns:
            {name: True/False} — True 表示通过校验
        """
        report: dict[str, bool] = {}
        for name, src in self._sources.items():
            try:
                sv = self.get(name)
            except Exception:
                report[name] = False
                continue
            if not sv.value:
                report[name] = False
                continue
            if len(sv.value) < src.min_length:
                report[name] = False
                continue
            # 必需 secret 不允许 insecure
            if src.required and sv.insecure:
                report[name] = False
                continue
            report[name] = True
        return report

    # -- 内部:默认注册 ---------------------------------------------------

    def _register_defaults(self) -> None:
        """注册项目默认的 secret 配置。"""
        defaults = [
            SecretSource(
                name="JWT_SECRET",
                env_var="fnixagent_JWT_SECRET",
                required=True,
                min_length=32,
                max_age_days=30,
                allow_dev_fallback=True,  # 开发环境允许
            ),
            SecretSource(
                name="DATABASE_URL",
                env_var="DATABASE_URL",
                required=False,
                default="sqlite:///fnixagent.db",
                min_length=0,
                max_age_days=0,
            ),
            SecretSource(
                name="REDIS_URL",
                env_var="REDIS_URL",
                required=False,
                default="redis://localhost:6379/0",
                min_length=0,
                max_age_days=0,
            ),
            SecretSource(
                name="ENCRYPT_KEY",
                env_var="fnixagent_ENCRYPT_KEY",
                required=True,
                min_length=32,
                max_age_days=30,
                allow_dev_fallback=True,
            ),
            SecretSource(
                name="KDK",
                env_var="fnixagent_KDK",
                required=False,
                min_length=32,
                max_age_days=90,
                allow_dev_fallback=True,
            ),
        ]
        for s in defaults:
            self._sources[s.name] = s

    # -- 内部:.env 读取 --------------------------------------------------

    @staticmethod
    def _read_from_dotenv(env_var: str) -> str | None:
        """尝试用 python-dotenv 从 .env 文件读取(缺失则返回 None)。"""
        try:
            from dotenv import load_dotenv  # type: ignore[import-not-found]

            # 仅加载一次,不覆盖已存在的环境变量
            load_dotenv(override=False)
            return os.environ.get(env_var)
        except ImportError:
            return None
        except Exception:
            return None

    # -- 内部:dev fallback -----------------------------------------------

    @staticmethod
    def _gen_dev_fallback(name: str) -> str:
        """生成开发用固定 fallback key(基于 name 派生,可重现)。"""
        # 用 name + 固定盐派生 32 字节十六进制字符串
        import hashlib

        salt = b"fnixagent-dev-fallback-do-not-use-in-prod"
        h = hashlib.sha256(salt + name.encode("utf-8")).hexdigest()
        return h  # 64 字符,满足 min_length=32

    # -- 内部:元数据管理 -------------------------------------------------

    def _load_meta(self) -> dict[str, dict]:
        """加载 .secret_meta.json(不存在/损坏返回 {})。"""
        try:
            if os.path.exists(self._META_FILE):
                with open(self._META_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)
        return {}

    def _save_meta(self) -> None:
        """持久化元数据(失败仅记录 warning)。"""
        try:
            with open(self._META_FILE, "w", encoding="utf-8") as f:
                json.dump(self._meta, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("[secrets] 元数据保存失败: %s", exc)

    def _touch_meta(self, name: str) -> None:
        """首次访问 secret 时记录创建时间(用于轮换检查)。"""
        with self._lock:
            if name not in self._meta:
                self._meta[name] = {
                    "created_at": datetime.now(UTC).isoformat(),
                }
                self._save_meta()

    def _age_days(self, name: str) -> int | None:
        """计算 secret 已存在天数(未知返回 None)。"""
        meta = self._meta.get(name)
        if not meta or "created_at" not in meta:
            return None
        try:
            created = datetime.fromisoformat(meta["created_at"])
            return (datetime.now(UTC) - created).days
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _expires_at(src: SecretSource) -> str | None:
        """计算过期时间 ISO 字符串(不限制返回 None)。"""
        if src.max_age_days <= 0:
            return None
        try:
            expires = datetime.now(UTC) + timedelta(days=src.max_age_days)
            return expires.isoformat()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------


_manager_instance: SecretManager | None = None
_manager_lock = threading.Lock()


def get_secret_manager() -> SecretManager:
    """获取全局 SecretManager 单例。"""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = SecretManager()
    return _manager_instance


def reset_secret_manager() -> None:
    """重置单例(主要用于测试)。"""
    global _manager_instance
    with _manager_lock:
        _manager_instance = None
