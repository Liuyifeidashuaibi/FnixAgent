"""
fnixagent Coding - 编码智能体能力层
======================================
对齐工程实践 / 行业编码工具 /  / , 基于 AgentOS 构建编码 Agent。

模块清单:
  code_indexer    - 代码库语义索引 (AST 切片 + 符号表 + 语义检索)
  context_builder - 上下文工程引擎 (组装最优 LLM context)
  diff_engine     - 原子多文件编辑 (变更集 + 回滚)
  code_tools      - 代码工具集 (read/write/edit/search/git/test)
  coding_agent    - 编码智能体 (Plan → Execute → Review)
  ide_server      - IDE 集成 (CLI + MCP Server)

零外部依赖: 仅 Python stdlib (ast / tokenize / hashlib / difflib)
可插拔后端: 复用 retrieval/embedder + retrieval/vectorstore + retrieval/hybrid
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.code.agent import (
    CodingAgent,
    CodingTask,
    TaskResult,
    TaskStep,
)
from fnixagent.core.code.context import (
    BuiltContext,
    ContextBuilder,
    ContextPriority,
)
from fnixagent.core.code.diff import (
    ApplyResult,
    ChangeSet,
    ChangeSetBuilder,
    ChangeType,
    DiffEngine,
    FileChange,
)
from fnixagent.core.code.indexer import (
    CodeIndexer,
    CodeSlice,
    IndexStats,
    Location,
    SymbolInfo,
    SymbolKind,
)
from fnixagent.core.code.server import IDEServer
from fnixagent.core.code.tools import CodeTools

__all__ = [
    "ApplyResult",
    "BuiltContext",
    "ChangeSet",
    "ChangeSetBuilder",
    "ChangeType",
    "CodeIndexer",
    "CodeSlice",
    "CodeTools",
    "CodingAgent",
    "CodingTask",
    "ContextBuilder",
    "ContextPriority",
    "DiffEngine",
    "FileChange",
    "IDEServer",
    "IndexStats",
    "Location",
    "SymbolInfo",
    "SymbolKind",
    "TaskResult",
    "TaskStep",
]

__version__ = "1.0.0"
