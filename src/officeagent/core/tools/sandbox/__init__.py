"""
安全沙箱模块。

提供:
  - SandboxPolicy: 安全策略(高危命令黑名单/网络白名单/文件写白名单)
  - CodeSandbox: 受限代码执行(受限 globals + 内置函数过滤 + 超时 + 内存监控)
"""
from officeagent.core.tools.sandbox.policy import SandboxPolicy
from officeagent.core.tools.sandbox.code_sandbox import CodeSandbox, SandboxResult

__all__ = ["SandboxPolicy", "CodeSandbox", "SandboxResult"]
