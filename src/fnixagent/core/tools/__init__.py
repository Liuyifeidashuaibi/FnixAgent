"""
工具执行平台 (Tool Platform)。

提供:
  - ToolMetadata / RegisteredTool: 工具元数据与注册项
  - ToolLayer: 工具层级(L1_OFFICE/L2_ECOSYSTEM/INFRA,P2-4)
  - ToolRegistry: 工具注册中心(注册/查询/列出)
  - ToolExecutor: 执行器(单工具/串行/并行/DAG 拓扑编排)
  - ToolRetriever: 工具检索器(向量相似度 + L1 加权,P2-4)
  - CodeSandbox / SandboxPolicy: 安全沙箱(受限 exec + 高危拦截)
"""
from fnixagent.core.tools.protocol import (
    ToolLayer,
    ToolMetadata,
    RegisteredTool,
    validate_arguments,
)
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.tools.executor import ToolExecutor
from fnixagent.core.tools.retriever import ToolRetriever
from fnixagent.core.tools.sandbox.policy import SandboxPolicy
from fnixagent.core.tools.sandbox.executor import CodeSandbox, SandboxResult

__all__ = [
    "ToolLayer",
    "ToolMetadata",
    "RegisteredTool",
    "validate_arguments",
    "ToolRegistry",
    "ToolExecutor",
    "ToolRetriever",
    "SandboxPolicy",
    "CodeSandbox",
    "SandboxResult",
]
