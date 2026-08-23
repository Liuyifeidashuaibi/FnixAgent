"""
Markdown 记忆存储层。

以 Markdown 文件为源真相，人类可读可编辑。
结构：
- MEMORY.md: 策展的长期事实
- HISTORY.md: 追加式活动历史
- SOUL.md: 人格与身份
- USER.md: 用户画像
- knowledge/: 知识 Wiki

设计原则：
- Markdown 为源真相，索引与存储分离
- 所有写入操作幂等，支持快照与回滚
- 人类可读可编辑，AI 可解析
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """记忆条目。"""

    id: str
    content: str
    category: str = "general"  # fact, decision, preference, event
    tags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class MarkdownMemoryStore:
    """Markdown 记忆存储。

    以 Markdown 文件为源真相，支持：
    - 读取/写入 MEMORY.md (长期事实)
    - 追加 HISTORY.md (活动历史)
    - 管理 knowledge/ 目录 (知识 Wiki)
    """

    def __init__(self, base_dir: str | Path):
        """初始化存储。

        Args:
            base_dir: 记忆目录路径 (如 ~/.fnix/memory)
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 确保子目录存在
        (self.base_dir / "knowledge" / "topics").mkdir(parents=True, exist_ok=True)

        # 初始化核心文件
        self._init_core_files()

    def _init_core_files(self):
        """初始化核心 Markdown 文件。"""
        core_files = {
            "MEMORY.md": "# Long-term Memory\n\nCurated facts and insights.\n\n",
            "HISTORY.md": "# Activity History\n\nAppend-only log of events.\n\n",
            "SOUL.md": "# Soul\n\nIdentity and personality.\n\n",
            "USER.md": "# User Profile\n\nUser preferences and context.\n\n",
        }

        for filename, default_content in core_files.items():
            filepath = self.base_dir / filename
            if not filepath.exists():
                filepath.write_text(default_content, encoding="utf-8")

    # -----------------------------------------------------------------------
    # MEMORY.md 操作
    # -----------------------------------------------------------------------

    def read_memory(self) -> str:
        """读取 MEMORY.md 内容。"""
        filepath = self.base_dir / "MEMORY.md"
        return filepath.read_text(encoding="utf-8")

    def append_memory(self, entry: MemoryEntry) -> None:
        """追加记忆到 MEMORY.md。

        格式：
        ## [Category] Title
        Content

        Tags: tag1, tag2
        Timestamp: 2026-08-17 16:40:00
        """
        filepath = self.base_dir / "MEMORY.md"

        # 格式化条目
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
        tags_str = ", ".join(entry.tags) if entry.tags else "none"

        content = f"\n## [{entry.category}] {entry.id}\n\n"
        content += f"{entry.content}\n\n"
        content += f"Tags: {tags_str}\n"
        content += f"Timestamp: {timestamp_str}\n"
        content += "\n---\n"

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(content)

    def parse_memory(self) -> list[MemoryEntry]:
        """解析 MEMORY.md 为条目列表。"""
        content = self.read_memory()
        entries = []

        # 按分隔符分割
        sections = content.split("\n---\n")

        for section in sections:
            if not section.strip():
                continue

            # 提取标题
            title_match = re.search(r"## \[(\w+)\] (.+)", section)
            if not title_match:
                continue

            category = title_match.group(1)
            entry_id = title_match.group(2).strip()

            # 提取内容
            content_match = re.search(r"## \[\w+\] .+\n\n(.+?)\n\nTags:", section, re.DOTALL)
            entry_content = content_match.group(1).strip() if content_match else ""

            # 提取标签
            tags_match = re.search(r"Tags: (.+)", section)
            tags = [t.strip() for t in tags_match.group(1).split(",")] if tags_match else []
            if tags == ["none"]:
                tags = []

            # 提取时间戳
            timestamp_match = re.search(r"Timestamp: (.+)", section)
            timestamp = time.time()
            if timestamp_match:
                try:
                    timestamp_str = timestamp_match.group(1).strip()
                    timestamp = time.mktime(time.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    pass

            entries.append(
                MemoryEntry(
                    id=entry_id,
                    content=entry_content,
                    category=category,
                    tags=tags,
                    timestamp=timestamp,
                )
            )

        return entries

    # -----------------------------------------------------------------------
    # HISTORY.md 操作
    # -----------------------------------------------------------------------

    def append_history(self, event: str, metadata: dict[str, Any] = None) -> None:
        """追加事件到 HISTORY.md。"""
        filepath = self.base_dir / "HISTORY.md"

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        content = f"\n- [{timestamp}] {event}\n"

        if metadata:
            for key, value in metadata.items():
                content += f"  - {key}: {value}\n"

        with open(filepath, "a", encoding="utf-8") as f:
            f.write(content)

    def read_history(self, limit: int = 100) -> list[str]:
        """读取最近的历史事件。"""
        filepath = self.base_dir / "HISTORY.md"
        content = filepath.read_text(encoding="utf-8")

        # 提取事件行
        events = re.findall(r"- \[.+?\] .+", content)
        return events[-limit:]

    # -----------------------------------------------------------------------
    # Knowledge Wiki 操作
    # -----------------------------------------------------------------------

    def write_knowledge(self, topic: str, content: str) -> None:
        """写入知识主题。"""
        filepath = self.base_dir / "knowledge" / "topics" / f"{topic}.md"
        filepath.write_text(content, encoding="utf-8")

    def read_knowledge(self, topic: str) -> str | None:
        """读取知识主题。"""
        filepath = self.base_dir / "knowledge" / "topics" / f"{topic}.md"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return None

    def list_knowledge_topics(self) -> list[str]:
        """列出所有知识主题。"""
        topics_dir = self.base_dir / "knowledge" / "topics"
        return [f.stem for f in topics_dir.glob("*.md")]

    # -----------------------------------------------------------------------
    # 快照与回滚
    # -----------------------------------------------------------------------

    def create_snapshot(self, snapshot_id: str = None) -> str:
        """创建记忆快照。

        返回快照路径。
        """
        if snapshot_id is None:
            snapshot_id = f"snapshot_{int(time.time())}"

        snapshot_dir = self.base_dir / "snapshots" / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 复制所有 Markdown 文件
        for md_file in self.base_dir.glob("*.md"):
            dest = snapshot_dir / md_file.name
            dest.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")

        # 复制 knowledge 目录
        knowledge_src = self.base_dir / "knowledge"
        knowledge_dest = snapshot_dir / "knowledge"
        if knowledge_src.exists():
            import shutil

            shutil.copytree(knowledge_src, knowledge_dest, dirs_exist_ok=True)

        return str(snapshot_dir)

    def restore_snapshot(self, snapshot_path: str) -> None:
        """从快照恢复记忆。"""
        snapshot_dir = Path(snapshot_path)
        if not snapshot_dir.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

        # 恢复 Markdown 文件
        for md_file in snapshot_dir.glob("*.md"):
            dest = self.base_dir / md_file.name
            dest.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")

        # 恢复 knowledge 目录
        knowledge_src = snapshot_dir / "knowledge"
        knowledge_dest = self.base_dir / "knowledge"
        if knowledge_src.exists():
            import shutil

            shutil.rmtree(knowledge_dest)
            shutil.copytree(knowledge_src, knowledge_dest)
