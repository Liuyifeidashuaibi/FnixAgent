"""
DiffEngine - 原子多文件编辑引擎
================================
对齐工程实践 diff apply 和 多文件编辑, 基于 AgentOS 构建编码 Agent 的原子编辑层。

设计要点:
  - 原子性: 变更集内全部成功才提交, 任一失败自动回滚已应用的变更
  - 可回滚: 保留变更历史, 支持按 changeset_id 撤销
  - 冲突检测: 基于 mtime + 内容 hash 检测并发编辑
  - Dry-run: 仅预检查不落盘, 用于预览变更效果
  - 零外部依赖: 仅 Python stdlib (difflib / hashlib / pathlib / uuid)

Usage:
    engine = DiffEngine(project_root="/path/to/project")

    # 构建变更集 (流式 API)
    cs = (ChangeSetBuilder("重构: 拆分 utils")
          .modify_file("src/utils.py", old_content, new_content)
          .create_file("src/utils_new.py", new_file_content)
          .build())

    # 原子应用
    result = await engine.apply(cs)
    if not result.success:
        print(f"应用失败: {result.error}")

    # 回滚
    await engine.rollback(cs.id)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import difflib
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

from fnixagent.core.agent.types import utcnow_iso

# ============================================================================
# 变更类型与数据结构
# ============================================================================


class ChangeType(Enum):
    """变更类型。

    对齐 Git 的 add/modify/delete, 描述单个文件的操作语义。
    """

    CREATE = "create"  # 创建新文件 (文件不能已存在)
    MODIFY = "modify"  # 修改已有文件 (old_content 必须与磁盘匹配)
    DELETE = "delete"  # 删除文件 (文件必须存在)


@dataclass
class FileChange:
    """单个文件变更。

    Attributes:
        path: 文件路径 (相对于 project_root 或绝对路径)
        change_type: 变更类型 (CREATE / MODIFY / DELETE)
        old_content: MODIFY/DELETE 时为原内容, CREATE 时为 None
        new_content: CREATE/MODIFY 时为新内容, DELETE 时为 None
    """

    path: str
    change_type: ChangeType
    old_content: str | None = None  # MODIFY/DELETE 时为原内容
    new_content: str | None = None  # CREATE/MODIFY 时为新内容

    def to_diff(self) -> str:
        """生成 unified diff (使用 difflib.unified_diff)。

        CREATE: 从空内容到新内容的 diff (fromfile=/dev/null)
        MODIFY: 从 old_content 到 new_content 的 diff
        DELETE: 从 old_content 到空内容的 diff (tofile=/dev/null)

        Returns:
            unified diff 文本, 多行字符串。
        """
        if self.change_type == ChangeType.CREATE:
            # 创建: 从空文件到新内容
            old_lines: list[str] = []
            new_lines = (self.new_content or "").splitlines(keepends=True)
            fromfile = "/dev/null"
            tofile = self.path
        elif self.change_type == ChangeType.MODIFY:
            # 修改: 从旧内容到新内容
            old_lines = (self.old_content or "").splitlines(keepends=True)
            new_lines = (self.new_content or "").splitlines(keepends=True)
            fromfile = self.path
            tofile = self.path
        else:
            # 删除: 从旧内容到空文件
            old_lines = (self.old_content or "").splitlines(keepends=True)
            new_lines = []
            fromfile = self.path
            tofile = "/dev/null"

        diff_lines = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=fromfile,
            tofile=tofile,
        )
        return "".join(diff_lines)


@dataclass
class ChangeSet:
    """变更集 (多文件原子编辑)。

    变更集是 DiffEngine 的最小原子单位, 内部所有 FileChange 要么全部成功,
    要么全部回滚。每个变更集有唯一 ID, 用于历史追溯和回滚。

    Attributes:
        changes: 文件变更列表
        message: 变更描述 (类似 commit message)
        id: 变更集唯一标识 (12 位 hex)
        created_at: 创建时间 (UTC ISO 字符串)
    """

    changes: list[FileChange] = field(default_factory=list)
    message: str = ""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: utcnow_iso())

    def add_change(self, change: FileChange) -> None:
        """添加文件变更到变更集。

        Args:
            change: 要添加的文件变更。
        """
        self.changes.append(change)

    def get_files(self) -> list[str]:
        """获取变更集涉及的文件路径列表。

        Returns:
            所有变更涉及的文件路径列表 (按变更顺序)。
        """
        return [c.path for c in self.changes]

    def to_diff(self) -> str:
        """生成完整 diff (拼接所有文件变更的 unified diff)。

        Returns:
            完整 diff 文本, 以变更集 message 作为注释头。
        """
        parts: list[str] = []
        if self.message:
            parts.append(f"# {self.message}\n")
        for change in self.changes:
            diff = change.to_diff()
            if diff:
                parts.append(diff)
        return "".join(parts)


# ============================================================================
# 变更集构建器 (流式 API)
# ============================================================================


class ChangeSetBuilder:
    """变更集构建器 (流式 API)。

    提供链式调用构建 ChangeSet, 对齐工程实践 的 edit block 构建方式。

    Usage:
        cs = (ChangeSetBuilder("重构: 拆分 utils")
              .create_file("src/new.py", content)
              .modify_file("src/old.py", old, new)
              .delete_file("src/deprecated.py", old_content)
              .build())
    """

    def __init__(self, message: str = ""):
        """初始化构建器。

        Args:
            message: 变更集描述信息 (类似 commit message)。
        """
        self._changeset = ChangeSet(message=message)

    def create_file(self, path: str, content: str) -> ChangeSetBuilder:
        """添加一个创建文件变更。

        Args:
            path: 要创建的文件路径。
            content: 文件内容。

        Returns:
            构建器自身 (用于链式调用)。
        """
        self._changeset.add_change(
            FileChange(
                path=path,
                change_type=ChangeType.CREATE,
                new_content=content,
            )
        )
        return self

    def modify_file(self, path: str, old: str, new: str) -> ChangeSetBuilder:
        """添加一个修改文件变更。

        Args:
            path: 要修改的文件路径。
            old: 原文件内容 (必须与磁盘内容匹配, 否则冲突)。
            new: 修改后的文件内容。

        Returns:
            构建器自身 (用于链式调用)。
        """
        self._changeset.add_change(
            FileChange(
                path=path,
                change_type=ChangeType.MODIFY,
                old_content=old,
                new_content=new,
            )
        )
        return self

    def delete_file(self, path: str, old: str) -> ChangeSetBuilder:
        """添加一个删除文件变更。

        Args:
            path: 要删除的文件路径。
            old: 原文件内容 (用于回滚恢复)。

        Returns:
            构建器自身 (用于链式调用)。
        """
        self._changeset.add_change(
            FileChange(
                path=path,
                change_type=ChangeType.DELETE,
                old_content=old,
            )
        )
        return self

    def build(self) -> ChangeSet:
        """构建并返回变更集。

        Returns:
            构建完成的 ChangeSet。
        """
        return self._changeset


# ============================================================================
# 应用结果
# ============================================================================


@dataclass
class ApplyResult:
    """应用结果。

    Attributes:
        success: 是否全部成功应用
        changeset_id: 对应的变更集 ID
        applied_files: 已成功应用的文件列表 (回滚时可用)
        failed_file: 失败的文件路径 (成功时为 None)
        error: 失败原因描述 (成功时为 None)
        duration_sec: 应用耗时 (秒)
    """

    success: bool
    changeset_id: str
    applied_files: list[str] = field(default_factory=list)
    failed_file: str | None = None
    error: str | None = None
    duration_sec: float = 0.0


# ============================================================================
# 原子多文件编辑引擎
# ============================================================================


class DiffEngine:
    """原子多文件编辑引擎。

    功能:
      1. 原子应用 (全部成功才提交, 任一失败回滚)
      2. 变更历史 (可撤销)
      3. 冲突检测 (并发编辑检测, 基于 mtime)
      4. Dry-run 模式 (只预览不写入)

    对齐工程实践 diff apply 和 多文件编辑, 提供编码智能体的原子编辑能力。

    Attributes:
        _root: 项目根目录 (用于解析相对路径)
        _history: 变更历史列表, 每项为 (变更集, 应用结果) 元组
    """

    def __init__(self, project_root: str = "."):
        """初始化 DiffEngine。

        Args:
            project_root: 项目根目录路径, FileChange 中的相对路径基于此解析。
        """
        self._root = Path(project_root)
        self._history: list[tuple[ChangeSet, ApplyResult]] = []

    # ------------------------------------------------------------------------
    # 路径解析
    # ------------------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        """将文件路径解析为绝对路径，并强制限制在 project_root 内。

        Args:
            path: 文件路径 (绝对或相对)。

        Returns:
            解析后的绝对 Path 对象。

        Raises:
            ValueError: 路径逃逸 project_root。
        """
        root = self._root.resolve()
        raw = (path or "").strip()
        if not raw:
            raise ValueError("path is empty")

        p = Path(raw)
        target = p.resolve() if p.is_absolute() else (root / p).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path escapes project root: {path}") from exc
        return target

    # ------------------------------------------------------------------------
    # 原子应用
    # ------------------------------------------------------------------------

    async def apply(self, changeset: ChangeSet, *, dry_run: bool = False) -> ApplyResult:
        """原子应用变更集。

        流程:
          1. 预检查所有文件 (存在性 + 内容匹配 + 基本字段验证)
          2. 冲突检测 (并发编辑检测)
          3. 逐个应用 (写入磁盘)
          4. 任一失败 → 回滚所有已应用的
          5. 记录历史 (仅成功时)

        Args:
            changeset: 要应用的变更集。
            dry_run: 是否仅预检查不落盘。True 时只做预检查和冲突检测,
                不实际写入文件, applied_files 为空。

        Returns:
            ApplyResult 描述应用结果。success=True 表示全部成功,
            success=False 时 failed_file 和 error 描述失败原因。
        """
        start = time.perf_counter()

        # 1. 预检查: 基本字段验证 + 冲突检测
        for change in changeset.changes:
            # 基本字段验证
            field_err = self._validate_change_fields(change)
            if field_err:
                duration = time.perf_counter() - start
                return ApplyResult(
                    success=False,
                    changeset_id=changeset.id,
                    failed_file=change.path,
                    error=field_err,
                    duration_sec=duration,
                )

            # 冲突检测 (存在性 + 内容匹配)
            conflict = self._check_conflict(change)
            if conflict:
                duration = time.perf_counter() - start
                return ApplyResult(
                    success=False,
                    changeset_id=changeset.id,
                    failed_file=change.path,
                    error=conflict,
                    duration_sec=duration,
                )

        # 2. dry_run: 只预检查, 不写入
        if dry_run:
            duration = time.perf_counter() - start
            result = ApplyResult(
                success=True,
                changeset_id=changeset.id,
                applied_files=[],
                duration_sec=duration,
            )
            # preview/dry_run 仍需登记历史, 否则下游 file_change 事件与
            # Review 阶段取 diff 会拿不到变更集（preview 模式静默失效）。
            self._history.append((changeset, result))
            return result

        # 3. 逐个应用, 跟踪已应用的变更 (用于失败回滚)
        applied: list[FileChange] = []
        for change in changeset.changes:
            try:
                self._apply_one(change)
                applied.append(change)
            except Exception as exc:
                # 4. 任一失败 → 回滚所有已应用的 (逆序回滚)
                for done in reversed(applied):
                    try:
                        self._rollback_one(done)
                    except Exception:
                        # 回滚失败不阻断, 尽力恢复
                        pass
                duration = time.perf_counter() - start
                return ApplyResult(
                    success=False,
                    changeset_id=changeset.id,
                    applied_files=[c.path for c in applied],
                    failed_file=change.path,
                    error=f"应用失败: {exc}",
                    duration_sec=duration,
                )

        # 5. 全部成功, 记录历史
        duration = time.perf_counter() - start
        result = ApplyResult(
            success=True,
            changeset_id=changeset.id,
            applied_files=[c.path for c in changeset.changes],
            duration_sec=duration,
        )
        self._history.append((changeset, result))
        return result

    # ------------------------------------------------------------------------
    # 回滚
    # ------------------------------------------------------------------------

    async def rollback(self, changeset_id: str) -> bool:
        """回滚指定变更集 (从历史中恢复)。

        在历史中查找对应变更集, 逆序回滚每个文件变更, 恢复到应用前的状态。
        仅能回滚成功应用过的变更集。

        Args:
            changeset_id: 要回滚的变更集 ID。

        Returns:
            True 表示回滚成功, False 表示变更集未找到或回滚过程中出错。
        """
        # 在历史中查找成功应用的变更集
        target: ChangeSet | None = None
        for cs, result in self._history:
            if cs.id == changeset_id and result.success:
                target = cs
                break

        if target is None:
            return False

        # 逆序回滚每个变更 (后应用的先回滚)
        for change in reversed(target.changes):
            try:
                self._rollback_one(change)
            except Exception:
                return False

        return True

    # ------------------------------------------------------------------------
    # 历史
    # ------------------------------------------------------------------------

    def get_history(self) -> list[tuple[ChangeSet, ApplyResult]]:
        """获取变更历史。

        Returns:
            变更历史列表, 每项为 (变更集, 应用结果) 元组, 按时间顺序排列。
        """
        return list(self._history)

    # ------------------------------------------------------------------------
    # 冲突检测
    # ------------------------------------------------------------------------

    def _check_conflict(self, change: FileChange) -> str | None:
        """冲突检测 (mtime + 内容 hash)。

        检查文件当前状态是否与变更预期一致:
          - CREATE: 文件不能已存在
          - MODIFY: 文件必须存在且磁盘内容 hash 与 old_content hash 一致
          - DELETE: 文件必须存在

        Args:
            change: 要检查的文件变更。

        Returns:
            冲突描述字符串, None 表示无冲突。
        """
        full = self._resolve(change.path)

        if change.change_type == ChangeType.CREATE:
            # 创建: 文件不能已存在
            if full.exists():
                return f"文件已存在, 无法创建: {change.path}"

        elif change.change_type == ChangeType.MODIFY:
            # 修改: 文件必须存在, 且内容 hash 必须匹配
            if not full.exists():
                return f"文件不存在, 无法修改: {change.path}"
            disk_content = full.read_text(encoding="utf-8")
            disk_hash = hashlib.sha256(disk_content.encode("utf-8")).hexdigest()
            old_hash = hashlib.sha256((change.old_content or "").encode("utf-8")).hexdigest()
            if disk_hash != old_hash:
                # 内容不匹配, 说明被并发编辑
                mtime = full.stat().st_mtime
                return f"文件内容已变更 (并发编辑冲突), path={change.path}, mtime={mtime}"

        elif change.change_type == ChangeType.DELETE:
            # 删除: 文件必须存在
            if not full.exists():
                return f"文件不存在, 无法删除: {change.path}"

        return None

    # ------------------------------------------------------------------------
    # 单文件应用与回滚
    # ------------------------------------------------------------------------

    def _apply_one(self, change: FileChange) -> None:
        """应用单个文件变更 (实际写入磁盘)。

        CREATE: 创建父目录并写入新内容
        MODIFY: 覆盖写入新内容
        DELETE: 删除文件

        Args:
            change: 要应用的文件变更。

        Raises:
            OSError: 文件系统操作失败时抛出。
        """
        full = self._resolve(change.path)

        if change.change_type == ChangeType.CREATE:
            # 创建: 确保父目录存在, 写入新内容
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(change.new_content or "", encoding="utf-8")

        elif change.change_type == ChangeType.MODIFY:
            # 修改: 覆盖写入新内容
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(change.new_content or "", encoding="utf-8")

        elif change.change_type == ChangeType.DELETE:
            # 删除: 移除文件
            full.unlink()

    def _rollback_one(self, change: FileChange) -> None:
        """回滚单个文件变更。

        CREATE 回滚 → 删除文件 (恢复到不存在的状态)
        MODIFY 回滚 → 写回 old_content (恢复原内容)
        DELETE 回滚 → 写回 old_content (重新创建文件)

        Args:
            change: 要回滚的文件变更。

        Raises:
            OSError: 文件系统操作失败时抛出。
        """
        full = self._resolve(change.path)

        if change.change_type == ChangeType.CREATE:
            # 创建的回滚 = 删除 (恢复到文件不存在的状态)
            if full.exists():
                full.unlink()

        elif change.change_type == ChangeType.MODIFY:
            # 修改的回滚 = 写回原内容
            full.write_text(change.old_content or "", encoding="utf-8")

        elif change.change_type == ChangeType.DELETE:
            # 删除的回滚 = 重新创建文件并写回原内容
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(change.old_content or "", encoding="utf-8")

    # ------------------------------------------------------------------------
    # 辅助: 字段验证
    # ------------------------------------------------------------------------

    @staticmethod
    def _validate_change_fields(change: FileChange) -> str | None:
        """验证变更字段完整性。

        CREATE: 必须有 new_content
        MODIFY: 必须有 old_content 和 new_content
        DELETE: 必须有 old_content

        Args:
            change: 要验证的文件变更。

        Returns:
            错误描述字符串, None 表示验证通过。
        """
        if change.change_type == ChangeType.CREATE:
            if change.new_content is None:
                return "CREATE 变更缺少 new_content"
        elif change.change_type == ChangeType.MODIFY:
            if change.old_content is None:
                return "MODIFY 变更缺少 old_content"
            if change.new_content is None:
                return "MODIFY 变更缺少 new_content"
        elif change.change_type == ChangeType.DELETE:
            if change.old_content is None:
                return "DELETE 变更缺少 old_content"
        return None


__all__ = [
    "ApplyResult",
    "ChangeSet",
    "ChangeSetBuilder",
    "ChangeType",
    "DiffEngine",
    "FileChange",
]
