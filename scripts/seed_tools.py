# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

"""
种子数据脚本 - 初始化工具元数据。

向 tools 表灌入标准工具定义。
"""
from fnixagent.adapters.db.postgres import DatabaseAdapter
from fnixagent.models.db.models import Tool


def seed_tools(db: DatabaseAdapter):
    """
    添加初始工具元数据。

    Args:
        db: 数据库适配器
    """
    print("Seeding tools metadata...")

    tools_data = [
        # 论文检索工具
        Tool(
            name="search_arxiv",
            description="搜索 arXiv 学术论文库",
            category="search",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            permission_level="low",
            timeout_ms=10000,
            rate_limit=60,
            enabled=True,
        ),

        Tool(
            name="search_semantic_scholar",
            description="搜索 Semantic Scholar 学术论文库",
            category="search",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
            permission_level="low",
            timeout_ms=10000,
            enabled=True,
        ),

        # Word工具
        Tool(
            name="create_docx",
            description="创建 Word 文档",
            category="word",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["content"],
            },
            permission_level="low",
            timeout_ms=30000,
            enabled=True,
        ),

        Tool(
            name="edit_docx",
            description="编辑 Word 文档",
            category="word",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "operation": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["file_path", "operation"],
            },
            permission_level="low",
            timeout_ms=30000,
            enabled=True,
        ),

        # 格式转换工具
        Tool(
            name="convert_document",
            description="文档格式转换",
            category="converter",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "source_format": {"type": "string"},
                    "target_format": {"type": "string"},
                },
                "required": ["file_path", "source_format", "target_format"],
            },
            permission_level="low",
            timeout_ms=60000,
            enabled=True,
        ),

        # PDF生成工具
        Tool(
            name="generate_pdf",
            description="生成 PDF 文档",
            category="pdf",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "template": {"type": "string"},
                },
                "required": ["content"],
            },
            permission_level="low",
            timeout_ms=60000,
            enabled=True,
        ),

        # 图表生成工具
        Tool(
            name="generate_chart",
            description="生成数据可视化图表",
            category="chart",
            input_schema={
                "type": "object",
                "properties": {
                    "data": {"type": "array"},
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "scatter"]},
                },
                "required": ["data", "chart_type"],
            },
            permission_level="low",
            timeout_ms=30000,
            enabled=True,
        ),

        # 文档解析工具
        Tool(
            name="parse_pdf",
            description="解析 PDF 文档提取文本/表格",
            category="parser",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "extract_tables": {"type": "boolean"},
                },
                "required": ["file_path"],
            },
            permission_level="low",
            timeout_ms=30000,
            enabled=True,
        ),

        # 学习辅助工具
        Tool(
            name="summarize",
            description="生成文本摘要",
            category="learning",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "max_length": {"type": "integer"},
                },
                "required": ["text"],
            },
            permission_level="low",
            timeout_ms=20000,
            enabled=True,
        ),
    ]

    # 批量插入
    for tool in tools_data:
        with db.session() as session:
            session.add(tool)

    print(f"Seeded {len(tools_data)} tools successfully!")


if __name__ == "__main__":
    import os

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://fnixagent:password@localhost:5432/fnixagent"
    )

    db = DatabaseAdapter(db_url)
    seed_tools(db)