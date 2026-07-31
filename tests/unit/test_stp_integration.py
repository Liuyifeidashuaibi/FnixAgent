"""STP 真接入主路径端到端测试 (论文核心断层修复验证)。

验证 work_pipeline.step5b_stp_select 真正调用 SkillScheduler.select_skills，
并把结果注入 ctx.skills_block 前缀。

论文 ablation 基线: 关闭 step5b 即退化为"无 STP 调度"。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fnixagent.services.work_pipeline import WorkPipeline, WorkPipelineContext


class TestStep5bStpSelect:
    """step5b_stp_select 真接入验证。"""

    def test_no_graph_returns_unchanged(self):
        """无 graph 时应安全降级,不报错。"""
        pipeline = WorkPipeline(graph_components=None)
        ctx = WorkPipelineContext(trace_id="t", user_input="test", workspace=".")
        result = pipeline.step5b_stp_select(ctx)
        assert result.stp_selected_count == 0
        assert result.skills_block == ""

    def test_no_scheduler_returns_unchanged(self):
        """graph 无 scheduler 时应安全降级。"""
        mock_graph = MagicMock()
        mock_graph.scheduler = None
        mock_graph.binding_protocol = MagicMock()
        pipeline = WorkPipeline(graph_components=mock_graph)
        ctx = WorkPipelineContext(trace_id="t", user_input="test", workspace=".")
        result = pipeline.step5b_stp_select(ctx)
        assert result.stp_selected_count == 0

    def test_stp_selects_and_injects_prefix(self):
        """STP 选中技能时应前缀注入 skills_block。"""
        mock_graph = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search_skill"
        mock_tool.description = "搜索技能"
        mock_graph.scheduler.select_skills.return_value = [mock_tool]
        mock_graph.binding_protocol.compute_priority.return_value = 0.85

        pipeline = WorkPipeline(graph_components=mock_graph)
        ctx = WorkPipelineContext(trace_id="t", user_input="test", workspace=".")
        ctx.skills_block = "\n## 已有技能\n- old_skill"
        ctx.concept_ids = ["L2:search"]

        result = pipeline.step5b_stp_select(ctx)
        assert result.stp_selected_count == 1
        # STP 块应前缀到 skills_block
        assert "STP 拓扑调度技能" in result.skills_block
        assert result.skills_block.startswith("\n\n## STP")
        # 原有 skills_block 应保留在后
        assert "old_skill" in result.skills_block
        # 权重应展示
        assert "权重=0.85" in result.skills_block

    def test_stp_empty_selection_no_change(self):
        """STP 未选中技能时不应修改 skills_block。"""
        mock_graph = MagicMock()
        mock_graph.scheduler.select_skills.return_value = []
        mock_graph.binding_protocol = MagicMock()

        pipeline = WorkPipeline(graph_components=mock_graph)
        ctx = WorkPipelineContext(trace_id="t", user_input="test", workspace=".")
        ctx.skills_block = "original"
        ctx.concept_ids = ["L2:test"]

        result = pipeline.step5b_stp_select(ctx)
        assert result.stp_selected_count == 0
        assert result.skills_block == "original"

    def test_stp_uses_ktg_paths_and_concepts(self):
        """STP 应从 KTG paths 和 concept_ids 构造推理路径。"""
        mock_graph = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "bound_skill"
        mock_tool.description = "desc"
        mock_graph.scheduler.select_skills.return_value = [mock_tool]
        mock_graph.binding_protocol.compute_priority.return_value = 0.5

        pipeline = WorkPipeline(graph_components=mock_graph)
        ctx = WorkPipelineContext(trace_id="t", user_input="test", workspace=".")

        # 模拟 KTG path 节点
        mock_path = MagicMock()
        mock_path.nodes = ["L0:root", "L2:concept_a"]
        ctx.ktg_paths = [mock_path]
        ctx.concept_ids = ["L2:concept_b"]

        pipeline.step5b_stp_select(ctx)
        # 验证 select_skills 被调用且 path 包含 KTG + concept 节点
        call_args = mock_graph.scheduler.select_skills.call_args
        path = call_args.kwargs.get("path")
        assert path is not None
        assert "L0:root" in path.nodes
        assert "L2:concept_a" in path.nodes
        assert "L2:concept_b" in path.nodes

    def test_ablation_baseline_without_step5b(self):
        """论文 ablation: 不调用 step5b 时,skills_block 不含 STP 块。"""
        mock_graph = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "skill"
        mock_tool.description = "desc"
        mock_graph.scheduler.select_skills.return_value = [mock_tool]
        mock_graph.binding_protocol.compute_priority.return_value = 0.5

        pipeline = WorkPipeline(graph_components=mock_graph)
        ctx = WorkPipelineContext(trace_id="t", user_input="test", workspace=".")
        ctx.skills_block = "## 已有技能\n- normal_skill"
        ctx.concept_ids = ["L2:test"]

        # 不调用 step5b (ablation 基线)
        assert "STP" not in ctx.skills_block
        assert ctx.stp_selected_count == 0
