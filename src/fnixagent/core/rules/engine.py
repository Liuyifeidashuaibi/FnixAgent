"""
项目级 Rules 引擎 (类似 .cursorrules / .traerules)。

从项目根目录的 .fnixrules 文件加载规则,支持三种规则类型:
- always: 始终包含在上下文中的规则
- manual: 由特定关键词触发的规则
- agent_requestable: Agent 可按需请求的规则

设计原则: 纯标准库实现,零外部依赖,解析简洁的 YAML-like 格式。
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

# ---------------------------------------------------------------------------
# 规则数据模型
# ---------------------------------------------------------------------------


@dataclass
class Rule:
    """单条规则。

    Attributes:
        type: 规则类型 (always / manual / agent_requestable)
        description: 规则描述文本
        globs: 文件匹配模式列表 (仅 manual 类型使用)
    """

    type: str
    description: str
    globs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 规则解析器
# ---------------------------------------------------------------------------


class RuleParser:
    """解析 .fnixrules 文件的 YAML-like 格式。

    支持格式:
        # FnixAgent Rules
        ## Rules
        - type: always
          description: 始终使用 Python 3.12+ 类型提示
        - type: manual
          description: 使用 pytest 进行测试
          globs: ["**/*.py"]
    """

    # 匹配规则条目开头的 "- type:" 行
    _TYPE_RE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*-\s*type:\s*(.+)$")
    # 匹配 description 字段
    _DESC_RE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*description:\s*(.+)$")
    # 匹配 globs 字段 (支持 YAML 列表格式,如 ["**/*.py", "tests/**"])
    _GLOBS_RE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*globs:\s*\[(.+)\]$")

    @classmethod
    def parse(cls, content: str) -> list[Rule]:
        """解析 .fnixrules 文件内容,返回规则列表。

        Args:
            content: .fnixrules 文件的原始文本内容

        Returns:
            解析出的 Rule 列表,忽略无法解析的行
        """
        rules: list[Rule] = []
        lines = content.splitlines()

        current_type: str | None = None
        current_description: str | None = None
        current_globs: list[str] = []

        def _flush() -> None:
            """将当前收集到的字段组装为 Rule 并清空暂存。"""
            nonlocal current_type, current_description, current_globs
            if current_type is not None and current_description is not None:
                rules.append(
                    Rule(
                        type=current_type.strip(),
                        description=current_description.strip(),
                        globs=list(current_globs),
                    )
                )
            current_type = None
            current_description = None
            current_globs = []

        for line in lines:
            stripped = line.strip()

            # 跳过空行和注释行
            if not stripped or stripped.startswith("#"):
                continue

            # 匹配 type 字段 (新规则开始)
            type_match = cls._TYPE_RE.match(line)
            if type_match:
                _flush()  # 保存上一条规则
                current_type = type_match.group(1).strip()
                continue

            # 匹配 description 字段
            desc_match = cls._DESC_RE.match(line)
            if desc_match:
                current_description = desc_match.group(1).strip()
                continue

            # 匹配 globs 字段
            globs_match = cls._GLOBS_RE.match(line)
            if globs_match:
                raw = globs_match.group(1)
                current_globs = [g.strip().strip("\"'") for g in raw.split(",") if g.strip()]
                continue

        _flush()  # 保存最后一条规则
        return rules


# ---------------------------------------------------------------------------
# Rules 引擎
# ---------------------------------------------------------------------------


@dataclass
class RulesEngine:
    """项目级 Rules 引擎。

    从项目根目录的 .fnixrules 文件加载规则,按类型分类管理。

    Attributes:
        rules: 所有已加载的规则列表
        project_root: 项目根目录路径
    """

    RULES_FILENAME: ClassVar[str] = ".fnixrules"

    rules: list[Rule]
    project_root: Path

    @classmethod
    def load(cls, project_root: str | Path) -> RulesEngine:
        """从项目根目录加载 .fnixrules 文件。

        如果文件不存在,返回空规则引擎。

        Args:
            project_root: 项目根目录路径

        Returns:
            加载完成的 RulesEngine 实例
        """
        root = Path(project_root).resolve()
        rules_file = root / cls.RULES_FILENAME

        if not rules_file.is_file():
            return cls(rules=[], project_root=root)

        content = rules_file.read_text(encoding="utf-8")
        parsed = RuleParser.parse(content)
        return cls(rules=parsed, project_root=root)

    # ------------------------------------------------------------------
    # 查询方法
    # ------------------------------------------------------------------

    def get_always_rules(self) -> list[str]:
        """获取始终生效的规则描述列表。

        Returns:
            always 类型规则的 description 列表
        """
        return [r.description for r in self.rules if r.type == "always"]

    def get_rules_for_file(self, file_path: str | Path) -> list[str]:
        """获取适用于指定文件的规则描述列表。

        根据 manual 规则的 globs 模式匹配文件路径,同时包含 always 规则。

        Args:
            file_path: 文件路径 (可以是绝对路径或相对于项目根目录的路径)

        Returns:
            匹配的规则描述列表
        """
        file_path = Path(file_path)

        # 尝试将路径转为相对于项目根目录的路径
        try:
            relative = file_path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            relative = file_path

        relative_str = str(relative).replace("\\", "/")

        result: list[str] = []

        for rule in self.rules:
            if rule.type == "always":
                result.append(rule.description)
            elif rule.type == "manual":
                if self._match_globs(relative_str, rule.globs):
                    result.append(rule.description)

        return result

    def get_agent_requestable_rules(self) -> list[str]:
        """获取 Agent 可按需请求的规则描述列表。

        Returns:
            agent_requestable 类型规则的 description 列表
        """
        return [r.description for r in self.rules if r.type == "agent_requestable"]

    # ------------------------------------------------------------------
    # 格式化方法
    # ------------------------------------------------------------------

    def format_for_prompt(self) -> str:
        """格式化所有规则为 LLM prompt 可用的文本。

        Returns:
            格式化的规则文本,可直接嵌入 system prompt 或 context
        """
        parts: list[str] = []

        always = self.get_always_rules()
        if always:
            parts.append("## 始终生效的规则")
            for i, desc in enumerate(always, 1):
                parts.append(f"{i}. {desc}")

        agent_req = self.get_agent_requestable_rules()
        if agent_req:
            parts.append("\n## 可请求的规则 (Agent 可按需获取)")
            for i, desc in enumerate(agent_req, 1):
                parts.append(f"{i}. {desc}")

        if not parts:
            return ""

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _match_globs(file_path: str, globs: list[str]) -> bool:
        """检查文件路径是否匹配任一 glob 模式。

        Args:
            file_path: 文件路径 (已转为正斜杠的相对路径)
            globs: glob 模式列表

        Returns:
            是否匹配
        """
        if not globs:
            return False
        for pattern in globs:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False
