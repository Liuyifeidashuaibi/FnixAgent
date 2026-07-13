"""
OfficeAgent Coding - 编码智能体能力层
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

from officeagent.core.coding.code_indexer import (
    CodeIndexer, CodeSlice, SymbolInfo, SymbolKind, IndexStats, Location,
)
from officeagent.core.coding.context_builder import (
    ContextBuilder, BuiltContext, ContextPriority,
)
from officeagent.core.coding.diff_engine import (
    DiffEngine, ChangeSet, FileChange, ChangeSetBuilder, ApplyResult,
    ChangeType,
)
from officeagent.core.coding.code_tools import CodeTools
from officeagent.core.coding.coding_agent import (
    CodingAgent, CodingTask, TaskResult, TaskStep,
)
from officeagent.core.coding.ide_server import IDEServer

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
