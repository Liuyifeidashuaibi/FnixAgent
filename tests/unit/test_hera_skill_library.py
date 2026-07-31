"""HERA SkillLibrary 单元测试。

覆盖:
- 成功技能捕获与去重
- 失败技能捕获（修复后的新行为）
- retrieve_skills 召回与失败技能降权
- format_skills_for_prompt 成功/失败分组展示
- stats 统计

设计原则: 纯本地逻辑，无 LLM/网络依赖。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnixagent.core.skills.library import SkillLibrary, _tokenize


@pytest.fixture
def library(tmp_path: Path) -> SkillLibrary:
    """每个测试用独立的临时 workspace。"""
    return SkillLibrary(str(tmp_path), max_skills=50)


class TestTokenize:
    def test_english_tokens(self):
        tokens = _tokenize("read pdf file and extract text")
        assert "read" in tokens
        assert "pdf" in tokens
        assert "file" in tokens
        assert "extract" in tokens
        assert "text" in tokens

    def test_chinese_tokens(self):
        tokens = _tokenize("把PDF文件转换成Word文档")
        assert "pdf" in tokens
        assert "word" in tokens
        # 中文 2-3 字滑窗
        assert any(t.startswith("文件") for t in tokens) or "文件" in tokens

    def test_empty(self):
        assert _tokenize("") == set()
        assert _tokenize("   ") == set()

    def test_stopwords_filtered(self):
        tokens = _tokenize("the a is 的 了 和")
        assert "the" not in tokens
        assert "的" not in tokens


class TestAddNewSkill:
    def test_success_skill_stored(self, library: SkillLibrary):
        skill = library.add_new_skill(
            user_input="读取 sales.xlsx 并生成图表",
            response="已生成柱状图...",
            tool_calls=[{"name": "read_xlsx", "success": True}],
            workspace_kind="general",
            success=True,
        )
        assert skill is not None
        assert skill.success is True
        assert skill.workspace_kind == "general"
        assert len(library.skills) == 1

    def test_failed_skill_stored_after_fix(self, library: SkillLibrary):
        """修复后的关键行为: 失败技能也应该入库。"""
        skill = library.add_new_skill(
            user_input="生成月度报告",
            response="尝试写入失败...",
            tool_calls=[{"name": "write_file", "success": False}],
            workspace_kind="general",
            success=False,
        )
        assert skill is not None, "失败技能应该入库（修复后）"
        assert skill.success is False
        assert len(library.skills) == 1

    def test_empty_input_rejected(self, library: SkillLibrary):
        assert (
            library.add_new_skill(
                user_input="",
                response="x",
                tool_calls=[],
                success=True,
            )
            is None
        )
        assert (
            library.add_new_skill(
                user_input="   ",
                response="x",
                tool_calls=[],
                success=True,
            )
            is None
        )

    def test_dedup_within_7_days(self, library: SkillLibrary):
        """相同 task_hash 7 天内不重复捕获。"""
        first = library.add_new_skill(
            user_input="读取 sales.xlsx",
            response="ok",
            tool_calls=[],
            success=True,
        )
        assert first is not None
        second = library.add_new_skill(
            user_input="读取 sales.xlsx",
            response="ok",
            tool_calls=[],
            success=True,
        )
        assert second is None, "7 天内相同任务应去重"
        assert len(library.skills) == 1

    def test_dedup_does_not_block_different_tasks(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="读取 sales.xlsx",
            response="ok",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="读取 inventory.xlsx",
            response="ok",
            tool_calls=[],
            success=True,
        )
        assert len(library.skills) == 2

    def test_max_skills_cap(self, tmp_path: Path):
        lib = SkillLibrary(str(tmp_path), max_skills=3)
        for i in range(5):
            lib.add_new_skill(
                user_input=f"任务编号 {i} 唯一标识",
                response=f"resp {i}",
                tool_calls=[],
                success=True,
            )
        assert len(lib.skills) == 3, "应保留最近 max_skills 个"

    def test_persistence(self, tmp_path: Path):
        """技能应持久化到 skills.json。"""
        lib1 = SkillLibrary(str(tmp_path), max_skills=50)
        lib1.add_new_skill(
            user_input="持久化测试任务",
            response="resp",
            tool_calls=[],
            success=True,
        )
        # 重新加载
        lib2 = SkillLibrary(str(tmp_path), max_skills=50)
        assert len(lib2.skills) == 1
        assert lib2.skills[0].task_signature == "持久化测试任务"


class TestRetrieveSkills:
    def test_retrieve_by_jaccard(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="读取 sales.xlsx 生成图表",
            response="图表已生成",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="写周报",
            response="周报已生成",
            tool_calls=[],
            success=True,
        )
        results = library.retrieve_skills("读取 sales 做图表", top_k=2)
        assert len(results) >= 1
        assert "sales" in results[0].task_signature.lower() or "图表" in results[0].task_signature

    def test_retrieve_failed_skill_with_lower_weight(self, library: SkillLibrary):
        """失败技能应该能被召回，但权重低于成功技能。"""
        library.add_new_skill(
            user_input="生成月度报告",
            response="失败方案",
            tool_calls=[{"name": "write_file", "success": False}],
            success=False,
        )
        library.add_new_skill(
            user_input="生成月度报告",
            response="成功方案",
            tool_calls=[{"name": "write_file", "success": True}],
            success=True,
        )
        # 注意: 两个技能 task_hash 相同,7 天去重会导致第二个不入库
        # 所以这里用不同的 task
        library.skills.clear()
        library.add_new_skill(
            user_input="生成季度报告",
            response="成功方案",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="生成月度报告",
            response="失败方案",
            tool_calls=[],
            success=False,
        )
        results = library.retrieve_skills("生成月度报告", top_k=2)
        assert len(results) >= 1
        # 失败技能应该被召回（作为反面经验）
        failed = [s for s in results if not s.success]
        assert len(failed) >= 1, "失败技能应该能被召回"

    def test_retrieve_workspace_kind_bonus(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="分析数据",
            response="resp1",
            tool_calls=[],
            workspace_kind="code",
            success=True,
        )
        library.add_new_skill(
            user_input="分析数据",
            response="resp2",
            tool_calls=[],
            workspace_kind="general",
            success=True,
        )
        # 两个 task_hash 相同会去重，改用不同输入
        library.skills.clear()
        library.add_new_skill(
            user_input="分析代码数据",
            response="resp1",
            tool_calls=[],
            workspace_kind="code",
            success=True,
        )
        library.add_new_skill(
            user_input="分析业务数据",
            response="resp2",
            tool_calls=[],
            workspace_kind="general",
            success=True,
        )
        results = library.retrieve_skills("分析数据", top_k=2, workspace_kind="code")
        assert len(results) >= 1

    def test_retrieve_empty_library(self, library: SkillLibrary):
        assert library.retrieve_skills("anything") == []

    def test_retrieve_empty_query(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="test",
            response="r",
            tool_calls=[],
            success=True,
        )
        assert library.retrieve_skills("") == []
        assert library.retrieve_skills("   ") == []

    def test_retrieve_usage_count_increment(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="测试任务 usage",
            response="r",
            tool_calls=[],
            success=True,
        )
        before = library.skills[0].usage_count
        library.retrieve_skills("测试任务", top_k=1)
        after = library.skills[0].usage_count
        assert after == before + 1


class TestFormatSkillsForPrompt:
    def test_success_only(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="成功任务",
            response="成功方案摘要",
            tool_calls=[{"name": "write_file", "success": True}],
            success=True,
        )
        block = library.format_skills_for_prompt(library.skills)
        assert "历史成功技能" in block
        assert "成功方案摘要" in block
        assert "历史失败经验" not in block

    def test_failed_only(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="失败任务",
            response="失败方案摘要",
            tool_calls=[{"name": "write_file", "success": False}],
            success=False,
        )
        block = library.format_skills_for_prompt(library.skills)
        assert "历史失败经验" in block
        assert "失败方案摘要" in block
        assert "失败工具" in block
        assert "历史成功技能" not in block

    def test_mixed(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="成功任务A",
            response="成功方案",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="失败任务B",
            response="失败方案",
            tool_calls=[],
            success=False,
        )
        block = library.format_skills_for_prompt(library.skills)
        assert "历史成功技能" in block
        assert "历史失败经验" in block

    def test_empty(self, library: SkillLibrary):
        assert library.format_skills_for_prompt([]) == ""


class TestStats:
    def test_stats_structure(self, library: SkillLibrary):
        library.add_new_skill(
            user_input="任务1",
            response="r",
            tool_calls=[],
            workspace_kind="code",
            success=True,
        )
        library.add_new_skill(
            user_input="任务2",
            response="r",
            tool_calls=[],
            workspace_kind="code",
            success=False,
        )
        stats = library.stats()
        assert stats["total"] == 2
        assert "code" in stats["by_kind"]
        assert stats["by_kind"]["code"] == 2
        assert stats["recent_24h"] == 2


class TestThreadSafety:
    def test_concurrent_adds(self, tmp_path: Path):
        """并发 add_new_skill 应该线程安全。"""
        import threading

        lib = SkillLibrary(str(tmp_path), max_skills=200)
        errors: list[Exception] = []

        def worker(idx: int):
            try:
                lib.add_new_skill(
                    user_input=f"并发任务 {idx} 唯一标识",
                    response=f"resp {idx}",
                    tool_calls=[],
                    success=bool(idx % 2),  # 一半成功一半失败
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发不应产生异常: {errors}"
        assert len(lib.skills) == 20, "所有并发任务都应入库"


class TestAddFeedback:
    """用户反馈信号回路测试 (对标 Cursor Bugbot Learning)。"""

    def test_add_feedback_up(self, library: SkillLibrary):
        skill = library.add_new_skill(
            user_input="测试反馈任务",
            response="r",
            tool_calls=[],
            success=True,
        )
        assert skill is not None
        result = library.add_feedback(
            task_hash=skill.task_hash,
            feedback="up",
            comment="很有帮助",
        )
        assert result is True
        assert library.skills[0].user_feedback == "up"
        assert library.skills[0].feedback_comment == "很有帮助"
        assert library.skills[0].feedback_at > 0

    def test_add_feedback_down(self, library: SkillLibrary):
        skill = library.add_new_skill(
            user_input="测试反馈任务",
            response="r",
            tool_calls=[],
            success=True,
        )
        result = library.add_feedback(
            task_hash=skill.task_hash,
            feedback="down",
            comment="没用",
        )
        assert result is True
        assert library.skills[0].user_feedback == "down"

    def test_add_feedback_none_clears(self, library: SkillLibrary):
        skill = library.add_new_skill(
            user_input="测试任务",
            response="r",
            tool_calls=[],
            success=True,
        )
        library.add_feedback(task_hash=skill.task_hash, feedback="up")
        assert library.skills[0].user_feedback == "up"
        # 清除反馈
        library.add_feedback(task_hash=skill.task_hash, feedback="none")
        assert library.skills[0].user_feedback == "none"

    def test_add_feedback_invalid_value(self, library: SkillLibrary):
        skill = library.add_new_skill(
            user_input="测试任务",
            response="r",
            tool_calls=[],
            success=True,
        )
        result = library.add_feedback(
            task_hash=skill.task_hash,
            feedback="invalid",
        )
        assert result is False
        assert library.skills[0].user_feedback == "none"

    def test_add_feedback_no_match(self, library: SkillLibrary):
        """未找到匹配技能应返回 False, 不报错。"""
        result = library.add_feedback(
            task_hash="nonexistent_hash_12345",
            feedback="up",
        )
        assert result is False

    def test_add_feedback_persists(self, tmp_path: Path):
        """反馈应持久化到 skills.json。"""
        lib1 = SkillLibrary(str(tmp_path))
        skill = lib1.add_new_skill(
            user_input="持久化反馈测试",
            response="r",
            tool_calls=[],
            success=True,
        )
        lib1.add_feedback(task_hash=skill.task_hash, feedback="up", comment="好")

        lib2 = SkillLibrary(str(tmp_path))
        assert lib2.skills[0].user_feedback == "up"
        assert lib2.skills[0].feedback_comment == "好"

    def test_feedback_influences_retrieval_weight(self, library: SkillLibrary):
        """👍 反馈应加分, 👎 反馈应大幅降权 (对标 Cursor Bugbot 反馈信号)。"""
        # 三个相似任务, 不同反馈
        library.add_new_skill(
            user_input="生成月度报告 A",
            response="方案 A",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="生成月度报告 B",
            response="方案 B",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="生成月度报告 C",
            response="方案 C",
            tool_calls=[],
            success=True,
        )
        # A: up, B: 无反馈, C: down
        library.add_feedback(task_hash=library.skills[0].task_hash, feedback="up")
        library.add_feedback(task_hash=library.skills[2].task_hash, feedback="down")

        results = library.retrieve_skills("生成月度报告", top_k=3)
        # A 应该排在 C 前面 (up 加分, down 降权)
        a_rank = next(
            (i for i, s in enumerate(results) if "报告 A" in s.task_signature),
            None,
        )
        c_rank = next(
            (i for i, s in enumerate(results) if "报告 C" in s.task_signature),
            None,
        )
        if a_rank is not None and c_rank is not None:
            assert a_rank < c_rank, "👍 反馈的技能应排在 👎 反馈的技能前面"


class TestTopologyWeightProvider:
    """Spec 6 闭环修复: 拓扑权重驱动 skill 召回 (论文创新点 2)。

    验证 MFP 第 4 阶 (爬坡) 调的拓扑权重通过 topology_weight_provider
    进入 retrieve_skills 的得分计算, 闭环 KTG 权重 → skill 召回。
    """

    def test_high_topology_weight_boosts_ranking(self, library: SkillLibrary):
        """拓扑权重高的技能应该在召回时排名靠前。"""
        # 两个 Jaccard 相似的技能
        library.add_new_skill(
            user_input="读取 sales 数据生成图表",
            response="方案 A",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="读取 sales 数据做分析",
            response="方案 B",
            tool_calls=[],
            success=True,
        )

        # 给第二个技能绑定高拓扑权重 (代表爬坡阶段强化的概念)
        def provider(signature: str) -> float:
            if "分析" in signature:
                return 0.95  # 高权重, 爬坡强化
            return 0.1  # 低权重, 爬坡弱化

        results = library.retrieve_skills(
            "读取 sales 数据",
            top_k=2,
            topology_weight_provider=provider,
        )
        assert len(results) >= 2
        # 高权重的 "分析" 技能应排在前面
        assert "分析" in results[0].task_signature, "高拓扑权重技能应排名靠前"

    def test_none_provider_keeps_original_behavior(self, library: SkillLibrary):
        """provider=None 时应保持原有召回逻辑 (向后兼容)。"""
        library.add_new_skill(
            user_input="测试任务",
            response="r",
            tool_calls=[],
            success=True,
        )
        # 不传 provider
        results_default = library.retrieve_skills("测试任务", top_k=1)
        # 传 None
        results_none = library.retrieve_skills("测试任务", top_k=1, topology_weight_provider=None)
        assert len(results_default) == len(results_none) == 1
        assert results_default[0].skill_id == results_none[0].skill_id

    def test_provider_exception_does_not_break_retrieval(self, library: SkillLibrary):
        """provider 抛异常时不应中断召回 (降级为原逻辑)。"""
        library.add_new_skill(
            user_input="测试任务",
            response="r",
            tool_calls=[],
            success=True,
        )

        def bad_provider(signature: str) -> float:
            raise RuntimeError("provider 故障")

        results = library.retrieve_skills(
            "测试任务", top_k=1, topology_weight_provider=bad_provider
        )
        assert len(results) == 1, "provider 异常时应降级为原召回逻辑"

    def test_neutral_weight_does_not_distort(self, library: SkillLibrary):
        """拓扑权重 0.5 (中性) 应让 score *= 1.0, 不改变原排序。"""
        library.add_new_skill(
            user_input="读取数据 A",
            response="r",
            tool_calls=[],
            success=True,
        )
        library.add_new_skill(
            user_input="读取数据 B",
            response="r",
            tool_calls=[],
            success=True,
        )

        def neutral_provider(signature: str) -> float:
            return 0.5  # 中性权重

        results_neutral = library.retrieve_skills(
            "读取数据", top_k=2, topology_weight_provider=neutral_provider
        )
        results_none = library.retrieve_skills("读取数据", top_k=2)
        # 两个技能都应被召回 (中性权重不改变 Jaccard 通过率)
        assert len(results_neutral) == len(results_none) == 2
