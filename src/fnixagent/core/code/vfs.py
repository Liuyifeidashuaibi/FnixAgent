"""
VirtualFileSystem — Preview 模式下的虚拟文件系统
=================================================
借鉴 SWE-agent "磁盘即真相源" 原则 + OpenHands 事件流状态管理，
在 preview 模式下维护文件最终状态，消除 step.result 内存拼接不可靠问题。

核心原则：
    - 每次 write 覆盖该文件的完整内容
    - 每次 edit 基于当前 VFS 内容做精确替换
    - review/completeness 检查从 VFS 读取最终内容（而非 step.result 拼接）

零外部依赖：仅 Python stdlib
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field


def _norm(path: str) -> str:
    """标准化路径：统一正斜杠、去前导 ./"""
    p = (path or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


@dataclass
class VirtualFileSystem:
    """Preview 模式下的虚拟文件系统 — 模拟磁盘状态。

    原则：每次 write 覆盖该文件的完整内容；
          每次 edit 基于当前 VFS 内容做替换；
          review/completeness 检查从 VFS 读取最终内容。
    """

    _files: dict[str, str] = field(default_factory=dict)

    def write(self, path: str, content: str) -> None:
        """写入完整文件内容（覆盖式，模拟磁盘 write）。"""
        norm = _norm(path)
        if not norm:
            return
        self._files[norm] = content

    def edit(self, path: str, old_text: str, new_text: str) -> tuple[bool, str]:
        """基于当前 VFS 内容做精确替换。

        与 SWE-agent str_replace 一致：只替换第一处匹配。
        如果 old_text 不在当前内容中，返回 (False, error_msg)。

        Returns:
            (success, error_message)
        """
        norm = _norm(path)
        current = self._files.get(norm, "")
        if not current:
            # VFS 中无此文件：可能是 edit 已存在的磁盘文件
            # 返回 False 但不阻止磁盘操作（agent 会 fallback 到磁盘 edit）
            return False, f"VFS 中无文件 {path}（可能是编辑已有磁盘文件）"
        if old_text not in current:
            return False, f"old_text 在 {path} 的 VFS 内容中未找到"
        # 只替换第一处匹配（与 SWE-agent str_replace 一致）
        updated = current.replace(old_text, new_text, 1)
        self._files[norm] = updated
        return True, ""

    def read(self, path: str) -> str:
        """读取 VFS 中的文件内容。"""
        return self._files.get(_norm(path), "")

    def exists(self, path: str) -> bool:
        """判断 VFS 中是否已有该文件。"""
        return _norm(path) in self._files

    def snapshot(self) -> dict[str, str]:
        """返回所有文件的当前快照（浅拷贝，键值对独立）。"""
        return dict(self._files)

    def code_snapshot(self) -> dict[str, str]:
        """返回所有代码文件的快照（仅 .py/.ts/.tsx/.js/.jsx 等）。"""
        code_exts = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go")
        return {
            path: content
            for path, content in self._files.items()
            if path.endswith(code_exts)
        }

    def clear(self) -> None:
        """清空 VFS（新任务开始时调用）。"""
        self._files.clear()

    def list_files(self) -> list[str]:
        """返回 VFS 中所有文件路径列表。"""
        return list(self._files.keys())


__all__ = ["VirtualFileSystem"]
