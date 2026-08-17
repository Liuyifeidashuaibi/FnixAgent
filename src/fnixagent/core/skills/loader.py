"""内置 Skill 加载器 — 扫描 builtin/ 目录解析 SKILL.md。

对齐 Agent Skills 开放标准 (SKILL.md 格式):
    - YAML frontmatter (--- 包围)
    - 必填字段: name / description / version / license
    - 可选字段: level (BASIC/REASONING/META) / output_format / tags / resources
    - Markdown body: 步骤/指南/示例

与 harness/skills_loader.py 的区别:
    - harness 版: 加载 workspace/.fnix/skills/*.md (用户级),零依赖手写解析
    - 本模块:  加载 builtin/<name>/SKILL.md (产品级内置),用 pyyaml 严格解析

容错策略: 单个 skill 解析失败不阻塞其他 skill 加载,错误以日志形式输出。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fnixagent.core.types import SkillLevel

logger = logging.getLogger(__name__)

# 内置 skill 目录(本文件所在目录的 builtin/ 子目录)
_BUILTIN_DIR: Path = Path(__file__).parent / "builtin"

# skill 名校验: 仅小写字母/数字/连字符,1~64 字符(对齐 Anthropic Agent Skills 规范)
_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")
# 语义化版本(semver)宽松匹配
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

# frontmatter 起止分隔符
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# 必填 frontmatter 字段
_REQUIRED_FIELDS: tuple[str, ...] = ("name", "description", "version", "license")

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class BuiltinSkill:
    """单个内置 Skill 的加载结果。

    Attributes:
        name:        skill 唯一标识 (小写字母/数字/连字符, ≤64 字符)
        description: 简短描述 (来自 frontmatter)
        version:     语义化版本号 (如 "1.0.0")
        license:     许可证 (如 "Apache-2.0")
        level:       权限级别 (BASIC/REASONING/META), 缺省 BASIC
        output_format: 输出格式 (如 "pdf" / "docx" / "html"), 可空
        tags:        标签列表 (用于检索/前端展示)
        triggers:    触发关键词 (用于 Work prompt 按需激活完整指南)
        resources:   关联资源 (如对应的 office 模块文件路径)
        body:        Markdown 正文 (含步骤/指南/示例)
        path:        SKILL.md 绝对路径
    """

    name: str
    description: str
    version: str
    license: str
    level: SkillLevel = SkillLevel.BASIC
    output_format: str = ""
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    body: str = ""
    path: str = ""

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class BuiltinSkillLoadError(Exception):
    """内置 Skill 加载异常 (单个 skill 解析失败时抛出,不阻塞其他 skill)。"""

# ---------------------------------------------------------------------------
# BuiltinSkillLoader
# ---------------------------------------------------------------------------

class BuiltinSkillLoader:
    """扫描 builtin/ 目录,解析每个子目录下的 SKILL.md。

    用法::

        loader = BuiltinSkillLoader()
        skills = loader.list_skills()           # 加载全部内置 skill
        pdf = loader.load_by_name("pdf")        # 按名加载单个
    """

    def __init__(self, builtin_dir: Path | None = None) -> None:
        """初始化加载器。

        Args:
            builtin_dir: 内置 skill 根目录 (默认: 本文件同级的 builtin/)
        """
        self._builtin_dir: Path = builtin_dir if builtin_dir is not None else _BUILTIN_DIR
        self._cache: list[BuiltinSkill] | None = None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def list_skills(self, *, refresh: bool = False) -> list[BuiltinSkill]:
        """列出全部内置 skill (按 name 字母序)。

        Args:
            refresh: True 强制重新扫描磁盘 (默认走缓存)

        Returns:
            BuiltinSkill 列表 (单个 skill 解析失败时跳过,不影响其他)
        """
        if self._cache is not None and not refresh:
            return list(self._cache)

        skills: list[BuiltinSkill] = []
        if not self._builtin_dir.is_dir():
            logger.warning("内置 skill 目录不存在: %s", self._builtin_dir)
            self._cache = skills
            return skills

        for sub in sorted(self._builtin_dir.iterdir()):
            if not sub.is_dir():
                continue
            skill_md = sub / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                skill = self._parse_skill_md(skill_md)
            except BuiltinSkillLoadError as e:
                logger.warning("跳过 skill %s: %s", sub.name, e)
                continue
            except Exception as e:
                logger.warning("跳过 skill %s (未预期异常): %s", sub.name, e)
                continue
            skills.append(skill)

        # 去重: 同名 skill (取第一个, 后出现的告警)
        seen: set[str] = set()
        deduped: list[BuiltinSkill] = []
        for s in skills:
            if s.name in seen:
                logger.warning("重复的内置 skill 名 '%s', 仅保留首个", s.name)
                continue
            seen.add(s.name)
            deduped.append(s)

        self._cache = deduped
        return list(deduped)

    def load_by_name(self, name: str) -> BuiltinSkill | None:
        """按 name 加载单个内置 skill。

        Args:
            name: skill 名 (小写字母/数字/连字符)

        Returns:
            BuiltinSkill 或 None (不存在时)
        """
        if not name:
            return None
        for skill in self.list_skills():
            if skill.name == name:
                return skill
        return None

    def refresh(self) -> None:
        """清除缓存,下次 list_skills() 重新扫描磁盘。"""
        self._cache = None

    # ------------------------------------------------------------------
    # 内部: 解析 SKILL.md
    # ------------------------------------------------------------------

    def _parse_skill_md(self, path: Path) -> BuiltinSkill:
        """解析单个 SKILL.md 文件。

        Args:
            path: SKILL.md 绝对路径

        Returns:
            BuiltinSkill 实例

        Raises:
            BuiltinSkillLoadError: frontmatter 缺失/字段非法/必填字段缺失
        """
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise BuiltinSkillLoadError(f"读取文件失败: {e}") from e

        meta, body = self._split_frontmatter(text)
        if meta is None:
            raise BuiltinSkillLoadError("缺少 YAML frontmatter (应以 '---' 开头)")

        # 校验必填字段
        missing = [f for f in _REQUIRED_FIELDS if not meta.get(f)]
        if missing:
            raise BuiltinSkillLoadError(f"frontmatter 缺少必填字段: {missing}")

        name = str(meta["name"]).strip()
        self._validate_name(name)

        version = str(meta["version"]).strip()
        self._validate_version(version)

        description = str(meta["description"]).strip()
        license_str = str(meta["license"]).strip()

        # 可选字段
        level = self._parse_level(meta.get("level"))
        output_format = str(meta.get("output_format", "")).strip()
        tags = self._parse_list(meta.get("tags"))
        triggers = self._parse_list(meta.get("triggers"))
        resources = self._parse_list(meta.get("resources"))

        return BuiltinSkill(
            name=name,
            description=description,
            version=version,
            license=license_str,
            level=level,
            output_format=output_format,
            tags=tags,
            triggers=triggers,
            resources=resources,
            body=body.strip(),
            path=str(path),
        )

    def _split_frontmatter(self, text: str) -> tuple[dict[str, Any] | None, str]:
        """拆分 YAML frontmatter 与 Markdown body。

        Returns:
            (meta_dict, body_str); 无 frontmatter 时返回 (None, text)
        """
        if not text.startswith("---"):
            return None, text
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return None, text
        raw_meta = m.group(1)
        body = m.group(2)
        try:
            meta = yaml.safe_load(raw_meta)
        except yaml.YAMLError as e:
            raise BuiltinSkillLoadError(f"YAML 解析失败: {e}") from e
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            raise BuiltinSkillLoadError(
                f"frontmatter 必须是 YAML 字典, 实际类型: {type(meta).__name__}"
            )
        return meta, body

    # ------------------------------------------------------------------
    # 内部: 字段校验
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_name(name: str) -> None:
        if not _SKILL_NAME_PATTERN.match(name):
            raise BuiltinSkillLoadError(
                f"非法 skill name '{name}': 仅允许小写字母/数字/连字符, 长度 1~64 字符"
            )

    @staticmethod
    def _validate_version(version: str) -> None:
        if not _VERSION_PATTERN.match(version):
            raise BuiltinSkillLoadError(f"非法 version '{version}': 应为 semver 格式 (如 '1.0.0')")

    @staticmethod
    def _parse_level(raw: Any) -> SkillLevel:
        if raw is None:
            return SkillLevel.BASIC
        try:
            return SkillLevel(str(raw).strip().lower())
        except ValueError as e:
            raise BuiltinSkillLoadError(
                f"非法 level '{raw}': 应为 basic/reasoning/meta 之一"
            ) from e

    @staticmethod
    def _parse_list(raw: Any) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw.strip()]
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return [str(raw).strip()]
