"""
fnixagent Coding - 编码智能体能力层
======================================
对标 Codex / Trae / OpenHands / Aider, 基于 AgentOS 构建编码 Agent。

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
from __future__ import annotations

from fnixagent.core.code.indexer import (
    CodeIndexer, CodeSlice, SymbolInfo, SymbolKind, IndexStats, Location,
)
from fnixagent.core.code.context import (
    ContextBuilder, BuiltContext, ContextPriority,
)
from fnixagent.core.code.diff import (
    DiffEngine, ChangeSet, FileChange, ChangeSetBuilder, ApplyResult,
    ChangeType,
)
from fnixagent.core.code.tools import CodeTools
from fnixagent.core.code.agent import (
    CodingAgent, CodingTask, TaskResult, TaskStep,
)
from fnixagent.core.code.server import IDEServer

__all__ = [
    "CodeIndexer", "CodeSlice", "SymbolInfo", "SymbolKind", "IndexStats",
    "Location",
    "ContextBuilder", "BuiltContext", "ContextPriority",
    "DiffEngine", "ChangeSet", "FileChange", "ChangeSetBuilder", "ApplyResult",
    "ChangeType",
    "CodeTools",
    "CodingAgent", "CodingTask", "TaskResult", "TaskStep",
    "IDEServer",
]

__version__ = "1.0.0"
