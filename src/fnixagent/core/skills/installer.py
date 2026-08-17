"""技能安装器(P2-2)。

负责把市场中的技能(SkillMarketEntry)安装到本地的 ToolRegistry。
核心职责:
  - install:    从市场拉取 entry + version,通过 tool_loader 加载工具函数,注册到 ToolRegistry
  - uninstall:  注销工具,删除安装记录
  - disable:    标记为禁用(ToolMetadata.enabled=False),不删除注册
  - enable:     恢复启用
  - upgrade:    升级到 latest_version(或指定版本)
  - list_installations / get_installation / is_installed

设计要点:
  1. tool_loader 由调用方注入(避免市场层耦合具体工具实现)
     - 签名:(entry: SkillMarketEntry, version: SkillVersion) -> dict[str, ToolFunc]
     - 返回 {tool_name: func},由 installer 逐个注册
     - 加载失败抛异常,installer 自动回滚已注册的工具
  2. 安装范围(scope):project_id / tenant_id / user_id 三级作用域
     - project 级:项目内所有成员可用
     - tenant 级:租户内所有项目可用
     - user 级:仅本人可用
  3. 多版本共存:同一技能在同一作用域仅保留一个版本(install 时若已安装则报错;upgrade 切换版本)
  4. 持久化:本实现为内存版;生产环境可由子类重写 _load/_persist 接入 DB
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from fnixagent.core.skills.market import (
    SkillMarket,
    SkillMarketEntry,
    SkillNotFoundError,
    SkillStatus,
    SkillVersion,
    SkillVersionNotFoundError,
)
from fnixagent.core.tools.protocol import ToolFunc, ToolMetadata

# 沙箱禁用模块(技能安装时不允许访问文件系统/子进程/网络底层)
# 检测机制:扫描 loader 返回的工具函数 __globals__,若包含以下模块则拒绝注册
_SANDBOX_FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "pathlib",
        "subprocess",
        "shutil",
        "sys",
        "socket",
        "ctypes",
        "multiprocessing",
    }
)

# ---------------------------------------------------------------------------
# 类型
# ---------------------------------------------------------------------------

class InstallScope(str, Enum):
    """安装作用域。"""

    PROJECT = "project"  # 项目级:项目内所有成员可用
    TENANT = "tenant"  # 租户级:租户内所有项目可用
    USER = "user"  # 用户级:仅本人可用

class InstallStatus(str, Enum):
    """安装状态。"""

    ACTIVE = "active"  # 已安装且启用
    DISABLED = "disabled"  # 已安装但禁用(ToolMetadata.enabled=False)

# tool_loader 签名:输入 entry + version,输出 {tool_name: (metadata, func)}
# 注意:返回值可包含 ToolMetadata(让 loader 自定义元数据),也可只返回 func(此时由 installer 用默认元数据)
ToolLoader = Callable[
    [SkillMarketEntry, SkillVersion],
    "dict[str, tuple[ToolMetadata, ToolFunc] | ToolFunc]",
]

@dataclass
class SkillInstallation:
    """单次安装记录。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    entry_id: str = ""
    skill_name: str = ""
    version: str = ""
    scope: InstallScope = InstallScope.USER
    scope_id: str = ""  # project_id / tenant_id / user_id(对应 scope)
    installed_by: str = ""  # 安装者用户 ID
    installed_at: datetime = field(default_factory=datetime.utcnow)
    status: InstallStatus = InstallStatus.ACTIVE
    # 已注册的工具名列表(卸载时按此 unregister)
    installed_tool_names: list[str] = field(default_factory=list)
    # 用户提供的安装配置(由 SkillVersion.config_schema 校验)
    config: dict[str, Any] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class SkillInstallerError(Exception):
    """安装器基础异常。"""

class SkillNotPublishedError(SkillInstallerError):
    """技能未发布(不能安装 DRAFT/PENDING_REVIEW/REJECTED/DEPRECATED)。"""

class SkillAlreadyInstalledError(SkillInstallerError):
    """技能已在同作用域安装(需先 uninstall 或 upgrade)。"""

class SkillNotInstalledError(SkillInstallerError):
    """技能未安装(无法 uninstall/disable/enable/upgrade)。"""

class ToolLoaderError(SkillInstallerError):
    """工具加载失败(loader 抛异常或返回空)。"""

class SandboxViolation(SkillInstallerError):
    """沙箱违例(loader 返回的工具函数访问了禁用模块)。"""

# ---------------------------------------------------------------------------
# SkillInstaller
# ---------------------------------------------------------------------------

class SkillInstaller:
    """技能安装器。

    用法:
        installer = SkillInstaller(market=market, tool_registry=registry)
        installer.set_tool_loader(my_loader)  # 必须先设置 loader

        # 安装
        installation = installer.install(
            entry_id="abc123",
            scope=InstallScope.PROJECT,
            scope_id="proj-001",
            installed_by="user-001",
            config={"api_key": "xxx"},
        )

        # 升级
        installer.upgrade(installation_id=installation.id)

        # 卸载
        installer.uninstall(installation_id=installation.id)
    """

    def __init__(
        self,
        market: SkillMarket,
        tool_registry: Any,  # 避免硬依赖 ToolRegistry(鸭子类型)
        tool_loader: ToolLoader | None = None,
    ) -> None:
        """
        Args:
            market: 技能市场实例
            tool_registry: 工具注册中心(需实现 register/unregister 接口)
            tool_loader: 工具加载器(可选,可用 set_tool_loader 后设置)
        """
        self._market = market
        self._registry = tool_registry
        self._loader: ToolLoader | None = tool_loader
        self._installations: dict[str, SkillInstallation] = {}  # id → installation
        # 索引:(scope, scope_id, skill_name) → installation_id(确保同作用域不重复)
        self._scope_index: dict[tuple[str, str, str], str] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # loader 设置
    # ------------------------------------------------------------------

    def set_tool_loader(self, loader: ToolLoader) -> SkillInstaller:
        """设置工具加载器(链式调用)。"""
        self._loader = loader
        return self

    def _ensure_loader(self) -> ToolLoader:
        if self._loader is None:
            raise ToolLoaderError("tool_loader not set; call set_tool_loader() first")
        return self._loader

    # ------------------------------------------------------------------
    # 安装
    # ------------------------------------------------------------------

    def install(
        self,
        entry_id: str,
        scope: InstallScope = InstallScope.USER,
        scope_id: str = "",
        installed_by: str = "",
        version: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> SkillInstallation:
        """安装技能到指定作用域。

        Args:
            entry_id: 市场 entry ID
            scope: 安装作用域(PROJECT/TENANT/USER)
            scope_id: 作用域 ID(project_id / tenant_id / user_id)
            installed_by: 安装者用户 ID
            version: 指定版本(None 表示 latest_version)
            config: 安装配置(由 SkillVersion.config_schema 校验)

        Returns:
            SkillInstallation 记录

        Raises:
            SkillNotPublishedError: 技能非 PUBLISHED 状态
            SkillAlreadyInstalledError: 同作用域已安装该技能
            ToolLoaderError: loader 未设置或加载失败
        """
        loader = self._ensure_loader()
        config = config or {}

        with self._lock:
            # 1. 从市场获取 entry + version
            entry = self._market.get_entry(entry_id)
            if entry is None:
                raise SkillNotFoundError(f"Skill entry '{entry_id}' not found")
            if entry.status != SkillStatus.PUBLISHED:
                raise SkillNotPublishedError(
                    f"Skill '{entry.name}' is {entry.status.value}, "
                    "cannot install (only PUBLISHED skills are installable)"
                )
            try:
                skill_version = self._market.get_version(entry_id, version)
            except SkillVersionNotFoundError as e:
                raise SkillInstallerError(str(e)) from e

            # 2. 校验 config(简易:必填字段检查;生产可换成 jsonschema)
            self._validate_config(skill_version, config)

            # 3. 检查同作用域是否已安装
            scope_key = (scope.value, scope_id, entry.name)
            if scope_key in self._scope_index:
                raise SkillAlreadyInstalledError(
                    f"Skill '{entry.name}' already installed in "
                    f"scope {scope.value}::{scope_id}; "
                    "use upgrade() to switch versions or uninstall() first"
                )

            # 4. 调用 loader 加载工具函数
            installation_id = uuid.uuid4().hex[:16]
            try:
                loaded = loader(entry, skill_version)
            except Exception as e:
                raise ToolLoaderError(f"tool_loader failed for skill '{entry.name}': {e}") from e

            if not loaded:
                raise ToolLoaderError(f"tool_loader returned empty for skill '{entry.name}'")

            # 5. 逐个注册到 ToolRegistry(失败自动回滚)
            #    注册前进行沙箱校验:禁止工具函数访问文件系统/子进程等危险模块
            installed_tool_names: list[str] = []
            try:
                for tool_name, item in loaded.items():
                    if isinstance(item, tuple) and len(item) == 2:
                        metadata, func = item
                        # 覆盖 metadata.name 以确保一致
                        metadata.name = tool_name
                    else:
                        # loader 只返回 func,用默认元数据
                        func = item
                        metadata = self._make_default_metadata(entry, skill_version, tool_name)
                    # 沙箱校验:扫描函数 __globals__,拒绝访问禁用模块
                    self._check_sandbox(tool_name, func)
                    self._registry.register(metadata, func)
                    installed_tool_names.append(tool_name)
            except Exception as e:
                # 回滚已注册的工具
                for name in installed_tool_names:
                    try:
                        self._registry.unregister(name)
                    except Exception:
                        pass
                raise ToolLoaderError(
                    f"Failed to register tools for skill '{entry.name}': {e}"
                ) from e

            # 6. 创建安装记录
            installation = SkillInstallation(
                id=installation_id,
                entry_id=entry_id,
                skill_name=entry.name,
                version=skill_version.version,
                scope=scope,
                scope_id=scope_id,
                installed_by=installed_by,
                status=InstallStatus.ACTIVE,
                installed_tool_names=installed_tool_names,
                config=config,
            )
            self._installations[installation_id] = installation
            self._scope_index[scope_key] = installation_id

            # 7. 增加市场安装计数
            self._market.increment_install_count(entry_id, +1)

            return installation

    def uninstall(self, installation_id: str) -> SkillInstallation:
        """卸载技能(从 ToolRegistry 注销全部工具)。

        Raises:
            SkillNotInstalledError: installation_id 不存在
        """
        with self._lock:
            installation = self._installations.get(installation_id)
            if installation is None:
                raise SkillNotInstalledError(f"Installation '{installation_id}' not found")
            # 逐个注销工具(忽略错误,确保流程完成)
            for tool_name in installation.installed_tool_names:
                try:
                    self._registry.unregister(tool_name)
                except Exception:
                    pass

            # 清理索引与记录
            scope_key = (
                installation.scope.value,
                installation.scope_id,
                installation.skill_name,
            )
            self._scope_index.pop(scope_key, None)
            del self._installations[installation_id]

            # 减少市场安装计数
            try:
                self._market.increment_install_count(installation.entry_id, -1)
            except SkillNotFoundError:
                pass  # 市场条目已被删除,忽略

            return installation

    # ------------------------------------------------------------------
    # 启用/禁用
    # ------------------------------------------------------------------

    def disable(self, installation_id: str) -> SkillInstallation:
        """禁用已安装的技能(ToolMetadata.enabled=False,不卸载)。

        禁用后工具仍注册在 registry,但 LLM 不可见(由 ToolExecutor 过滤)。
        """
        with self._lock:
            installation = self._get_installation_or_raise(installation_id)
            if installation.status == InstallStatus.DISABLED:
                return installation  # 幂等
            for tool_name in installation.installed_tool_names:
                self._set_tool_enabled(tool_name, enabled=False)
            installation.status = InstallStatus.DISABLED
            return installation

    def enable(self, installation_id: str) -> SkillInstallation:
        """启用已禁用的技能。"""
        with self._lock:
            installation = self._get_installation_or_raise(installation_id)
            if installation.status == InstallStatus.ACTIVE:
                return installation  # 幂等
            for tool_name in installation.installed_tool_names:
                self._set_tool_enabled(tool_name, enabled=True)
            installation.status = InstallStatus.ACTIVE
            return installation

    def _set_tool_enabled(self, tool_name: str, enabled: bool) -> None:
        """设置工具 enabled 状态(尝试访问 registry 内部 _tools)。

        兼容 ToolRegistry 的实现:直接修改 metadata.enabled。
        若 registry 不暴露内部结构,则忽略(由 ToolExecutor 在调度时检查 installation.status)。
        """
        try:
            tools = getattr(self._registry, "_tools", None)
            if tools and tool_name in tools:
                tools[tool_name].metadata.enabled = enabled
        except Exception:
            pass  # 容错:registry 实现不暴露内部结构时忽略

    # ------------------------------------------------------------------
    # 升级
    # ------------------------------------------------------------------

    def upgrade(
        self,
        installation_id: str,
        target_version: str | None = None,
    ) -> SkillInstallation:
        """升级到指定版本(target_version=None 表示 latest_version)。

        实现策略:uninstall 旧版 + install 新版(同作用域、同 entry)。
        保留原 config(若新版 config_schema 不兼容则报错)。

        Returns:
            新的 SkillInstallation 记录(原记录被删除,id 不同)
        """
        with self._lock:
            old = self._get_installation_or_raise(installation_id)
            entry_id = old.entry_id
            scope = old.scope
            scope_id = old.scope_id
            installed_by = old.installed_by
            config = dict(old.config)

            # 先卸载
            self.uninstall(installation_id)

            # 再安装(指定版本)
            return self.install(
                entry_id=entry_id,
                scope=scope,
                scope_id=scope_id,
                installed_by=installed_by,
                version=target_version,
                config=config,
            )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_installations(
        self,
        scope: InstallScope | None = None,
        scope_id: str | None = None,
        skill_name: str | None = None,
        status: InstallStatus | None = None,
    ) -> list[SkillInstallation]:
        """列出安装记录(支持过滤)。"""
        with self._lock:
            results = list(self._installations.values())
            if scope is not None:
                results = [i for i in results if i.scope == scope]
            if scope_id is not None:
                results = [i for i in results if i.scope_id == scope_id]
            if skill_name is not None:
                results = [i for i in results if i.skill_name == skill_name]
            if status is not None:
                results = [i for i in results if i.status == status]
            results.sort(key=lambda i: i.installed_at, reverse=True)
            return results

    def get_installation(self, installation_id: str) -> SkillInstallation | None:
        """按 ID 获取安装记录。"""
        with self._lock:
            return self._installations.get(installation_id)

    def is_installed(
        self,
        skill_name: str,
        scope: InstallScope,
        scope_id: str,
    ) -> bool:
        """检查技能是否在指定作用域已安装。"""
        with self._lock:
            scope_key = (scope.value, scope_id, skill_name)
            return scope_key in self._scope_index

    def find_installations(
        self,
        skill_name: str,
        scope: InstallScope | None = None,
        scope_id: str | None = None,
    ) -> list[SkillInstallation]:
        """按技能名查找所有安装记录(支持 scope 过滤)。"""
        with self._lock:
            results = [i for i in self._installations.values() if i.skill_name == skill_name]
            if scope is not None:
                results = [i for i in results if i.scope == scope]
            if scope_id is not None:
                results = [i for i in results if i.scope_id == scope_id]
            return results

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """安装器统计。"""
        with self._lock:
            installs = list(self._installations.values())
            by_scope: dict[str, int] = {}
            by_status: dict[str, int] = {}
            for i in installs:
                by_scope[i.scope.value] = by_scope.get(i.scope.value, 0) + 1
                by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
            return {
                "total": len(installs),
                "by_scope": by_scope,
                "by_status": by_status,
                "active": sum(1 for i in installs if i.status == InstallStatus.ACTIVE),
            }

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _get_installation_or_raise(self, installation_id: str) -> SkillInstallation:
        installation = self._installations.get(installation_id)
        if installation is None:
            raise SkillNotInstalledError(f"Installation '{installation_id}' not found")
        return installation

    def _validate_config(
        self,
        version: SkillVersion,
        config: dict[str, Any],
    ) -> None:
        """简易 config 校验:检查 required 字段是否存在。

        生产环境可换成完整 jsonschema 校验。
        """
        schema = version.config_schema or {}
        if not schema:
            return
        required = schema.get("required", [])
        missing = [f for f in required if f not in config]
        if missing:
            raise SkillInstallerError(
                f"Config validation failed: missing required fields {missing}"
            )

    def _make_default_metadata(
        self,
        entry: SkillMarketEntry,
        version: SkillVersion,
        tool_name: str,
    ) -> ToolMetadata:
        """当 loader 只返回 func 时,生成默认 ToolMetadata。"""
        return ToolMetadata(
            name=tool_name,
            description=f"{entry.display_name} - {tool_name}",
            category=entry.category,
            skill_level=version.skill_level,
            version=version.version,
        )

    @staticmethod
    def _check_sandbox(tool_name: str, func: Any) -> None:
        """沙箱校验:检查工具函数是否访问了禁用模块。

        扫描函数的 __globals__(模块级导入),若发现 os/pathlib/subprocess 等
        危险模块,则拒绝注册。这是最佳努力(best-effort)防护:
          - 能拦截直接导入禁用模块的函数
          - 无法拦截通过间接方式(如 importlib)访问的恶意代码
          - 生产环境应配合容器/沙箱隔离使用

        Args:
            tool_name: 工具名(用于错误信息)
            func: 工具函数

        Raises:
            SandboxViolation: 函数访问了禁用模块
        """
        func_globals = getattr(func, "__globals__", None)
        if not isinstance(func_globals, dict):
            return  # 内置函数/C 方法无 __globals__,跳过
        # 扫描函数模块级 globals 中的导入
        leaked: list[str] = []
        for key, value in func_globals.items():
            module_name = getattr(value, "__name__", None)
            if module_name and module_name in _SANDBOX_FORBIDDEN_MODULES:
                leaked.append(f"{key}={module_name}")
        if leaked:
            raise SandboxViolation(
                f"Tool '{tool_name}' accesses forbidden modules "
                f"in sandbox mode: {leaked}. "
                "Skill tools must not touch filesystem/subprocess."
            )
