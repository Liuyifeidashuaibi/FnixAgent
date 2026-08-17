"""办公场景 KTG 种子 + STP 技能绑定。

这是 FnixAgent 相对 行业编码工具/行业编码工具 的核心差异化能力，不是可选项：
  - KTG：四层知识拓扑（目标→概念→规则→事实）
  - STP：L2 概念 ↔ Office/检索技能突触
  - 由 build_graph() 在启动时强制播种
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fnixagent.core.skills.protocol import SkillBindingProtocol
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import EdgeType, NodeType, SkillLevel, TopologyLayer

# L2 概念 → 主技能（可一对多：额外技能写在 sibling_skills）
_OFFICE_CONCEPTS: list[dict[str, Any]] = [
    {
        "id": "L2:doc_edit",
        "name": "文档编辑",
        "content": "Word 文档创建、编辑与排版",
        "skill": "create_docx",
        "sibling_skills": ["edit_docx", "format_docx"],
        "rules": [
            ("L3:doc_need_content", "创建文档需提供正文内容"),
            ("L3:doc_path_writable", "输出路径所在目录必须可写"),
        ],
        "facts": [
            ("L4:doc_weekly_report", "周报常用 report 模板，标题为本周工作周报"),
        ],
    },
    {
        "id": "L2:spreadsheet",
        "name": "表格分析",
        "content": "Excel 创建、数据分析与报表",
        "skill": "create_xlsx",
        "sibling_skills": [],
        "rules": [
            ("L3:xlsx_need_data", "创建表格应提供 data 或 sheets"),
        ],
        "facts": [
            ("L4:xlsx_sheet1", "默认 sheet_name=Sheet1"),
        ],
    },
    {
        "id": "L2:presentation",
        "name": "演示文稿",
        "content": "PPT 创建与幻灯片编排",
        "skill": "create_pptx",
        "sibling_skills": [],
        "rules": [
            ("L3:pptx_need_title", "演示文稿应有标题页"),
        ],
        "facts": [
            ("L4:pptx_bullets", "内容页优先使用 bullets 列表"),
        ],
    },
    {
        "id": "L2:pdf_doc",
        "name": "PDF 文档",
        "content": "PDF 创建与格式转换",
        "skill": "create_pdf",
        "sibling_skills": ["convert_document"],
        "rules": [
            ("L3:pdf_source_limit", "转换前确认源文件存在"),
        ],
        "facts": [
            ("L4:pdf_a4", "默认 A4 页面"),
        ],
    },
    {
        "id": "L2:paper_search",
        "name": "论文检索",
        "content": "学术文献检索与聚合",
        "skill": "search_paper",
        "sibling_skills": ["search_arxiv", "search_semantic_scholar"],
        "rules": [
            ("L3:search_need_query", "检索需明确关键词或领域"),
        ],
        "facts": [
            ("L4:arxiv_cs_ai", "arXiv cs.AI 按相关性取 Top-10"),
        ],
    },
    {
        "id": "L2:learning_assist",
        "name": "学习辅助",
        "content": "摘要、笔记、概念梳理等学习办公任务",
        "skill": "create_docx",
        "sibling_skills": [],
        "rules": [
            ("L3:summary_cite_source", "摘要应保留来源信息"),
        ],
        "facts": [
            ("L4:summary_md", "短摘要可先写 markdown 再转 docx"),
        ],
    },
]


def seed_office_topology(
    graph: TopologyGraph,
    binding: SkillBindingProtocol | None = None,
) -> dict[str, int]:
    """向空/半空拓扑图播种办公领域四层结构，并绑定 STP。

    Returns:
        {"nodes": N, "edges": M, "bindings": B}
    """
    stats = {"nodes": 0, "edges": 0, "bindings": 0}

    # 已播种则跳过（幂等）
    if "L1:office_agent" in getattr(graph, "_nodes", {}):
        return stats

    goal = graph.add_node(
        layer=TopologyLayer.L1_GOAL,
        node_type=NodeType.GOAL,
        name="智能办公助手",
        content="学习 / 教育 / 办公场景的 AI 工作台（对齐并超越  Work）",
        node_id="L1:office_agent",
    )
    stats["nodes"] += 1

    protocol = binding or SkillBindingProtocol(graph=graph)

    for spec in _OFFICE_CONCEPTS:
        concept = graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name=spec["name"],
            content=spec["content"],
            node_id=spec["id"],
        )
        stats["nodes"] += 1

        graph.add_edge(goal.node_id, concept.node_id, EdgeType.CONTAINS)
        stats["edges"] += 1

        # 主技能 STP 绑定
        try:
            protocol.bind(spec["id"], spec["skill"], SkillLevel.BASIC)
            stats["bindings"] += 1
        except Exception:
            pass

        # 兄弟技能：再建平行 L2 概念节点绑定（STP 一概念一技能）
        for i, sib in enumerate(spec.get("sibling_skills") or []):
            sib_id = f"{spec['id']}:{sib}"
            try:
                graph.add_node(
                    layer=TopologyLayer.L2_CONCEPT,
                    node_type=NodeType.CONCEPT,
                    name=f"{spec['name']}/{sib}",
                    content=f"{spec['content']} · 技能 {sib}",
                    node_id=sib_id,
                )
                stats["nodes"] += 1
                graph.add_edge(goal.node_id, sib_id, EdgeType.CONTAINS)
                stats["edges"] += 1
                protocol.bind(sib_id, sib, SkillLevel.BASIC)
                stats["bindings"] += 1
                # 与主概念关联
                graph.add_edge(spec["id"], sib_id, EdgeType.DERIVES, weight=0.6)
                stats["edges"] += 1
            except Exception:
                pass

        for rule_id, rule_text in spec.get("rules") or []:
            try:
                graph.add_node(
                    layer=TopologyLayer.L3_RULE,
                    node_type=NodeType.RULE,
                    name=rule_text[:40],
                    content=rule_text,
                    node_id=rule_id,
                )
                stats["nodes"] += 1
                graph.add_edge(spec["id"], rule_id, EdgeType.PRECONDITION, weight=0.7)
                stats["edges"] += 1
            except Exception:
                pass

        for fact_id, fact_text in spec.get("facts") or []:
            try:
                graph.add_node(
                    layer=TopologyLayer.L4_FACT,
                    node_type=NodeType.FACT,
                    name=fact_text[:40],
                    content=fact_text,
                    node_id=fact_id,
                )
                stats["nodes"] += 1
                # 事实挂到第一条规则，若无规则则挂概念
                parent = (spec.get("rules") or [(None, None)])[0][0] or spec["id"]
                graph.add_edge(parent, fact_id, EdgeType.DERIVES, weight=0.65)
                stats["edges"] += 1
            except Exception:
                pass

    return stats


__all__ = ["seed_office_topology"]
