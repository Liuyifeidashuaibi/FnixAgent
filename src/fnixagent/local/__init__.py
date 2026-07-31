"""fnix-local — 本地算力 sidecar（索引 / 上下文 / 命令执行）。

Phase 2: Python MVP（CodeIndexer + WorkspaceTools）。
Phase 3+: 可替换为 FnixAi Rust 二进制，HTTP 契约保持不变。
"""

from fnixagent.local.sidecar_app import create_app

__all__ = ["create_app"]
