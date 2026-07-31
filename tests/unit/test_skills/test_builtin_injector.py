"""内置 Skill 注入器测试 — format_builtin_skills_block / select_activated_skills。

覆盖：
    1. 索引层：所有启用技能出现在索引行
    2. 激活层：trigger 命中时注入完整 body（含【完整指南】标记）
    3. 禁用过滤：disabled 集合中的技能不注入
    4. 预算：完整 body 数量与字符预算受限
    5. 真实磁盘 builtin 目录可加载且注入不为空
"""

from __future__ import annotations

import pytest

from fnixagent.core.skills.injector import (
    format_builtin_skills_block,
    select_activated_skills,
)
from fnixagent.core.skills.loader import BuiltinSkill
from fnixagent.core.types import SkillLevel


def _mk(
    name: str,
    *,
    triggers: list[str] | None = None,
    tags: list[str] | None = None,
    body: str = "步骤一。步骤二。",
) -> BuiltinSkill:
    return BuiltinSkill(
        name=name,
        description=f"{name} 描述",
        version="1.0.0",
        license="Apache-2.0",
        level=SkillLevel.BASIC,
        triggers=triggers or [],
        tags=tags or [],
        body=body,
    )


class TestSelectActivatedSkills:
    def test_trigger_hit(self):
        skills = [
            _mk("dynamic-ui", triggers=["可视化", "图表"]),
            _mk("pdf", triggers=["pdf"]),
        ]
        hit = select_activated_skills("帮我画个图表对比一下", skills)
        assert [s.name for s in hit] == ["dynamic-ui"]

    def test_no_hit(self):
        skills = [_mk("pdf", triggers=["pdf"])]
        assert select_activated_skills("今天天气如何", skills) == []

    def test_max_full_cap(self):
        skills = [
            _mk("a", triggers=["报告"]),
            _mk("b", triggers=["报告"]),
            _mk("c", triggers=["报告"]),
        ]
        hit = select_activated_skills("写个报告", skills, max_full=2)
        assert len(hit) == 2

    def test_trigger_outranks_tag(self):
        skills = [
            _mk("tag-only", tags=["report"]),
            _mk("trig", triggers=["report"]),
        ]
        hit = select_activated_skills("need a report", skills, max_full=1)
        assert hit[0].name == "trig"


class TestFormatBuiltinSkillsBlock:
    def test_real_builtin_dir_index_and_activation(self):
        """真实磁盘 builtin/：索引含全部技能，触发词激活完整指南。"""
        block = format_builtin_skills_block("帮我做一个方案对比的可视化图表")
        assert "## 内置技能" in block
        assert "- dynamic-ui:" in block
        assert "- pdf:" in block
        # dynamic-ui 的 triggers 含「可视化」「图表」「对比」→ 应展开完整指南
        assert "【完整指南】dynamic-ui" in block
        assert "show_widget" in block

    def test_real_builtin_dir_no_activation(self):
        block = format_builtin_skills_block("你好")
        assert "- dynamic-ui:" in block
        assert "【完整指南】" not in block

    def test_disabled_filter(self):
        block = format_builtin_skills_block(
            "帮我画个图表",
            disabled={"dynamic-ui"},
        )
        assert "- dynamic-ui:" not in block
        assert "【完整指南】dynamic-ui" not in block

    def test_char_budget_truncation(self):
        block = format_builtin_skills_block(
            "帮我做可视化图表",
            full_char_budget=1200,
            max_full=1,
        )
        # body 被截断时带截断标记；无论截断与否 block 长度受控
        assert len(block) < 60_000


class TestNewSkillsLoadable:
    """Phase 1-3 新增技能必须能被 loader 正确解析。"""

    @pytest.mark.parametrize(
        "name",
        [
            "dynamic-ui",
            "html-report",
            "html-deck",
            "doc-writing-guide",
            "research-guide",
            "code-review",
            "security-review",
            "debugging",
        ],
    )
    def test_new_skill_loaded(self, name):
        from fnixagent.core.skills import get_builtin_skill

        skill = get_builtin_skill(name)
        assert skill is not None, f"builtin skill '{name}' 未被加载"
        assert skill.body, f"'{name}' body 为空"
        assert skill.triggers, f"'{name}' 缺少 triggers（无法被激活）"

    def test_manifest_count_matches_disk(self):
        import json
        from pathlib import Path

        from fnixagent.core.skills import list_builtin_skills

        skills = list_builtin_skills()
        manifest_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "fnixagent"
            / "core"
            / "skills"
            / "builtin"
            / "MANIFEST.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["count"] == len(skills)
        assert {s["name"] for s in manifest["skills"]} == {s.name for s in skills}
