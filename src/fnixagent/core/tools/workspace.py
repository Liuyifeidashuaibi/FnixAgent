"""
Workspace 工具集 — 对标 Cursor/Trae 的 Agent 工具能力

提供 AI Agent 与本地文件系统和 Shell 交互所需的核心工具:
  - read_file: 读取文件
  - write_file: 写入文件
  - edit_file: 精确字符串替换编辑
  - glob: 文件名模式匹配
  - grep: 文件内容正则搜索
  - ls: 列出目录
  - run_command: 执行 Shell 命令
  - web_search: 网络搜索
  - web_fetch: 获取网页内容

设计原则:
  - 所有路径操作均基于 workspace_root 进行安全检查
  - 防止路径遍历攻击
  - 操作结果可序列化为 LLM 友好格式
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ===== 安全: 防止危险命令 =====
_DANGEROUS_COMMANDS = [
    "rm -rf /", "mkfs.", "dd if=", ":(){ :|:& };:", "> /dev/sda",
    "chmod 777 /", "wget -O - | sh", "curl | sh", "sudo rm",
]


def _is_dangerous_command(cmd: str) -> bool:
    """检查是否为危险命令"""
    cmd_lower = cmd.lower().strip()
    for danger in _DANGEROUS_COMMANDS:
        if danger in cmd_lower:
            return True
    return False


def _safe_path(workspace_root: str, rel_path: str) -> Path:
    """安全解析路径，防止路径遍历攻击"""
    root = Path(workspace_root).resolve()
    target = (root / rel_path).resolve()

    # 确保目标在 workspace 内
    if not str(target).startswith(str(root)):
        raise ValueError(f"路径遍历攻击: {rel_path}")

    return target


# ============================================================
# 工具结果
# ============================================================

@dataclass
class ToolResult:
    """工具调用结果"""
    success: bool
    content: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_context(self) -> str:
        """转换为 LLM 可理解的上下文"""
        if self.success:
            meta = f" ({self.metadata})" if self.metadata else ""
            return f"[成功]{meta}\n{self.content}"
        return f"[失败] {self.error}"


# ============================================================
# 工作区上下文
# ============================================================

class WorkspaceContext:
    """工作区上下文管理器 — 跟踪打开的workspace状态"""

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = str(Path(workspace_root).resolve())
        self.open_files: set[str] = set()
        self.recent_edits: list[dict] = []
        self._env: dict[str, str] = dict(os.environ)

    def get_project_tree(self, max_depth: int = 3) -> str:
        """获取项目目录树"""
        root = Path(self.workspace_root)
        lines = [f"{root.name}/"]

        def _walk(path: Path, depth: int, prefix: str = ""):
            if depth > max_depth:
                return
            try:
                entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
                for i, entry in enumerate(entries):
                    if entry.name.startswith(".") and entry.name not in (".env.example",):
                        continue
                    if entry.name in ("__pycache__", "node_modules", ".git", "dist", "build"):
                        continue
                    is_last = i == len(entries) - 1
                    connector = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
                    if entry.is_dir() and depth < max_depth:
                        next_prefix = prefix + ("    " if is_last else "│   ")
                        _walk(entry, depth + 1, next_prefix)
            except PermissionError:
                pass

        _walk(root, 0)
        return "\n".join(lines)


# ============================================================
# 核心工具
# ============================================================

class WorkspaceTools:
    """
    Workspace 工具集 — 对标 Cursor/Trae 的 Agent 工具

    用法:
        tools = WorkspaceTools(workspace_root="/path/to/project")
        result = tools.read_file("src/main.py")
        result = tools.grep("def main", "src/", "*.py")
        result = await tools.run_command("pytest tests/")
    """

    def __init__(self, workspace_root: str = "."):
        self.ctx = WorkspaceContext(workspace_root)

    @property
    def workspace_root(self) -> str:
        return self.ctx.workspace_root

    # ============================================================
    # 文件读取
    # ============================================================

    def read_file(self, rel_path: str, offset: int = 0, limit: int | None = None) -> ToolResult:
        """读取文件内容

        Args:
            rel_path: 相对于 workspace_root 的文件路径
            offset: 起始行号 (1-based)
            limit: 最大行数
        """
        try:
            target = _safe_path(self.workspace_root, rel_path)
            if not target.exists():
                return ToolResult(success=False, error=f"文件不存在: {rel_path}")
            if not target.is_file():
                return ToolResult(success=False, error=f"不是文件: {rel_path}")

            content = target.read_text(encoding="utf-8", errors="replace")
            lines = content.split("\n")
            total_lines = len(lines)

            if offset > 0:
                lines = lines[offset - 1:]
            if limit is not None:
                lines = lines[:limit]

            # 添加行号
            numbered = []
            start = max(offset, 1)
            for i, line in enumerate(lines):
                numbered.append(f"{start + i}\t{line}")

            return ToolResult(
                success=True,
                content="\n".join(numbered),
                metadata={
                    "path": str(target),
                    "total_lines": total_lines,
                    "shown_lines": len(lines),
                    "offset": offset,
                },
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"读取失败: {e}")

    # ============================================================
    # 文件写入
    # ============================================================

    def write_file(self, rel_path: str, content: str) -> ToolResult:
        """写入文件（覆盖模式）

        Args:
            rel_path: 相对于 workspace_root 的文件路径
            content: 文件内容
        """
        try:
            target = _safe_path(self.workspace_root, rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

            self.ctx.recent_edits.append({
                "action": "write", "path": rel_path,
                "time": time.time(),
            })

            return ToolResult(
                success=True,
                content=f"已写入: {rel_path} ({len(content)} 字符)",
                metadata={"path": str(target), "size": len(content)},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"写入失败: {e}")

    # ============================================================
    # 精确编辑 (字符串替换)
    # ============================================================

    def edit_file(
        self, rel_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> ToolResult:
        """精确字符串替换编辑文件

        Args:
            rel_path: 文件路径
            old_string: 要替换的字符串
            new_string: 替换后的字符串
            replace_all: 是否替换所有匹配项
        """
        try:
            target = _safe_path(self.workspace_root, rel_path)
            if not target.exists():
                return ToolResult(success=False, error=f"文件不存在: {rel_path}")

            content = target.read_text(encoding="utf-8")

            if old_string == new_string:
                return ToolResult(success=False, error="old_string 和 new_string 相同")

            count = content.count(old_string)
            if count == 0:
                return ToolResult(
                    success=False,
                    error=f"未找到匹配字符串。文件: {rel_path}",
                    metadata={"file_content_snippet": content[:500]},
                )

            if not replace_all and count > 1:
                return ToolResult(
                    success=False,
                    error=f"找到 {count} 处匹配，请使用 replace_all=True 或提供更精确的上下文",
                    metadata={"occurrences": count},
                )

            new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
            target.write_text(new_content, encoding="utf-8")

            self.ctx.recent_edits.append({
                "action": "edit", "path": rel_path,
                "replacements": 1 if not replace_all else count,
                "time": time.time(),
            })

            return ToolResult(
                success=True,
                content=f"已编辑: {rel_path} (替换 {count if replace_all else 1} 处)",
                metadata={"path": str(target), "replacements": count if replace_all else 1},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"编辑失败: {e}")

    # ============================================================
    # 文件搜索
    # ============================================================

    def glob(self, pattern: str, path: str = ".") -> ToolResult:
        """文件名模式匹配

        Args:
            pattern: glob 模式，如 "*.py", "src/**/*.ts"
            path: 搜索起始目录，相对于 workspace_root
        """
        try:
            base = _safe_path(self.workspace_root, path)
            if not base.exists():
                return ToolResult(success=False, error=f"目录不存在: {path}")

            matches = list(base.glob(pattern))
            # 过滤隐藏文件
            matches = [m for m in matches if not any(p.startswith(".") for p in m.parts if p not in (".", ".."))]

            # 排序: 目录优先, 按修改时间倒序
            matches.sort(key=lambda p: (not p.is_dir(), -p.stat().st_mtime if p.exists() else 0))

            result_lines = []
            for m in matches[:200]:  # 最多200个结果
                rel = m.relative_to(Path(self.workspace_root))
                result_lines.append(str(rel))

            return ToolResult(
                success=True,
                content="\n".join(result_lines) if result_lines else "(无匹配结果)",
                metadata={"count": len(matches), "pattern": pattern},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {e}")

    def grep(
        self, pattern: str, path: str = ".", glob_filter: str = "*",
        output_mode: str = "content", head_limit: int = 100,
    ) -> ToolResult:
        """文件内容正则搜索

        Args:
            pattern: 正则表达式
            path: 搜索目录
            glob_filter: 文件名过滤
            output_mode: "content" | "files_with_matches" | "count"
            head_limit: 最大结果数
        """
        try:
            base = _safe_path(self.workspace_root, path)
            if not base.exists():
                return ToolResult(success=False, error=f"目录不存在: {path}")

            regex = re.compile(pattern, re.MULTILINE | re.DOTALL)
            results = []

            for file_path in base.rglob(glob_filter):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(Path(self.workspace_root))
                if any(p.startswith(".") for p in rel.parts):
                    continue
                if any(p in ("__pycache__", "node_modules", ".git", "dist", "build") for p in rel.parts):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                if output_mode == "count":
                    count = len(regex.findall(content))
                    if count > 0:
                        results.append(f"{rel}: {count}")
                elif output_mode == "files_with_matches":
                    if regex.search(content):
                        results.append(str(rel))
                else:
                    for i, line in enumerate(content.split("\n"), 1):
                        if regex.search(line):
                            results.append(f"{rel}:{i}: {line.strip()[:200]}")

                if len(results) >= head_limit:
                    break

            return ToolResult(
                success=True,
                content="\n".join(results[:head_limit]) if results else "(无匹配)",
                metadata={"count": len(results), "pattern": pattern},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except re.error as e:
            return ToolResult(success=False, error=f"正则表达式错误: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {e}")

    def ls(self, path: str = ".") -> ToolResult:
        """列出目录内容

        Args:
            path: 目录路径，相对于 workspace_root
        """
        try:
            base = _safe_path(self.workspace_root, path)
            if not base.exists():
                return ToolResult(success=False, error=f"目录不存在: {path}")
            if not base.is_dir():
                return ToolResult(success=False, error=f"不是目录: {path}")

            entries = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name))
            lines = []
            for e in entries:
                if e.name.startswith(".") and e.name not in (".env.example", ".gitignore"):
                    continue
                size = e.stat().st_size if e.is_file() else 0
                type_indicator = "/" if e.is_dir() else ""
                lines.append(f"{e.name}{type_indicator} ({size:,} bytes)" if e.is_file() else f"{e.name}/")

            return ToolResult(
                success=True,
                content="\n".join(lines) if lines else "(空目录)",
                metadata={"count": len(lines), "path": str(base)},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"列出失败: {e}")

    # ============================================================
    # Shell 命令执行
    # ============================================================

    async def run_command(
        self, command: str, cwd: str | None = None, timeout: int = 60,
    ) -> ToolResult:
        """执行 Shell 命令

        Args:
            command: 要执行的命令
            cwd: 工作目录 (相对于 workspace_root)
            timeout: 超时时间(秒)
        """
        if _is_dangerous_command(command):
            return ToolResult(success=False, error=f"危险命令被拦截: {command[:50]}")

        try:
            work_dir = self.workspace_root
            if cwd:
                work_dir = str(_safe_path(self.workspace_root, cwd))

            # Windows 使用 PowerShell
            if os.name == "nt":
                full_cmd = ["powershell", "-Command", command]
            else:
                full_cmd = ["bash", "-c", command]

            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(success=False, error=f"命令超时 ({timeout}s)")

            output = stdout.decode("utf-8", errors="replace").strip()
            error_output = stderr.decode("utf-8", errors="replace").strip()

            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    content=output or "(执行成功, 无输出)",
                    metadata={"exit_code": 0, "duration_ms": 0},
                )
            else:
                return ToolResult(
                    success=False,
                    content=output,
                    error=f"退出码: {process.returncode}\n{error_output}",
                    metadata={"exit_code": process.returncode},
                )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"执行失败: {e}")

    # ============================================================
    # 网络搜索
    # ============================================================

    async def web_search(self, query: str, num: int = 5) -> ToolResult:
        """网络搜索 (使用 DuckDuckGo)

        Args:
            query: 搜索查询
            num: 结果数量
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    headers={"User-Agent": "FnixAgent/1.0"},
                )
                data = resp.json()

                results = []
                abstract = data.get("AbstractText", "")
                if abstract:
                    results.append(f"摘要: {abstract}")

                for topic in data.get("RelatedTopics", [])[:num]:
                    if isinstance(topic, dict):
                        results.append(f"- {topic.get('Text', '')}")

                return ToolResult(
                    success=True,
                    content="\n".join(results) if results else "(无搜索结果)",
                    metadata={"query": query, "results_count": len(results)},
                )
        except ImportError:
            return ToolResult(success=False, error="需要安装 httpx: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {e}")

    async def web_fetch(self, url: str) -> ToolResult:
        """获取网页内容

        Args:
            url: 网页URL
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "FnixAgent/1.0 Mozilla/5.0"},
                )
                resp.raise_for_status()

                # 简单提取文本 (去除HTML标签)
                content = resp.text
                # 移除 script 和 style
                content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r"<[^>]+>", " ", content)
                content = re.sub(r"\s+", " ", content).strip()

                # 截断过长内容
                if len(content) > 10000:
                    content = content[:10000] + "..."

                return ToolResult(
                    success=True,
                    content=content,
                    metadata={"url": url, "content_length": len(content)},
                )
        except ImportError:
            return ToolResult(success=False, error="需要安装 httpx: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, error=f"获取失败: {e}")


# ============================================================
# 工具注册 (注册到 ToolRegistry)
# ============================================================

def register_workspace_tools(registry, workspace_root: str = ".") -> WorkspaceTools:
    """将 workspace 工具注册到全局 ToolRegistry

    Args:
        registry: ToolRegistry 实例
        workspace_root: 工作区根目录

    Returns:
        WorkspaceTools 实例
    """
    from fnixagent.core.tools.protocol import ToolMetadata
    from fnixagent.core.types import ToolPermission

    tools = WorkspaceTools(workspace_root)

    # 同步工具
    registry.register(
        ToolMetadata(
            name="read_file",
            description="读取文件内容。参数: file_path(文件路径), offset(起始行,默认0), limit(最大行数)",
            category="filesystem",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "相对于workspace的文件路径"},
                    "offset": {"type": "integer", "description": "起始行号(1-based)", "default": 0},
                    "limit": {"type": "integer", "description": "最大行数"},
                },
                "required": ["file_path"],
            },
        ),
        lambda args: tools.read_file(
            args.get("file_path", args.get("rel_path", "")),
            args.get("offset", 0),
            args.get("limit"),
        ),
    )

    registry.register(
        ToolMetadata(
            name="write_file",
            description="写入文件(覆盖模式)。参数: file_path(路径), content(内容)",
            category="filesystem",
            permission_level=ToolPermission.MIDDLE,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        ),
        lambda args: tools.write_file(
            args.get("file_path", args.get("rel_path", "")),
            args.get("content", ""),
        ),
    )

    registry.register(
        ToolMetadata(
            name="edit_file",
            description="精确字符串替换编辑文件。参数: file_path, old_string, new_string, replace_all(默认False)",
            category="filesystem",
            permission_level=ToolPermission.MIDDLE,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        ),
        lambda args: tools.edit_file(
            args.get("file_path", args.get("rel_path", "")),
            args.get("old_string", ""),
            args.get("new_string", ""),
            args.get("replace_all", False),
        ),
    )

    registry.register(
        ToolMetadata(
            name="glob",
            description="文件名模式匹配搜索。参数: pattern(glob模式), path(搜索目录,默认'.')",
            category="filesystem",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["pattern"],
            },
        ),
        lambda args: tools.glob(
            args.get("pattern", "*"),
            args.get("path", "."),
        ),
    )

    registry.register(
        ToolMetadata(
            name="grep",
            description="文件内容正则搜索。参数: pattern(正则), path(目录), glob_filter(文件过滤), output_mode(content/files_with_matches/count)",
            category="filesystem",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "glob_filter": {"type": "string", "default": "*"},
                    "output_mode": {"type": "string", "default": "content"},
                },
                "required": ["pattern"],
            },
        ),
        lambda args: tools.grep(
            args.get("pattern", ""),
            args.get("path", "."),
            args.get("glob_filter", "*"),
            args.get("output_mode", "content"),
        ),
    )

    registry.register(
        ToolMetadata(
            name="ls",
            description="列出目录内容。参数: path(目录路径,默认'.')",
            category="filesystem",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                },
            },
        ),
        lambda args: tools.ls(args.get("path", ".")),
    )

    registry.register(
        ToolMetadata(
            name="run_command",
            description="执行Shell命令。参数: command(命令), cwd(工作目录), timeout(超时秒数,默认60)",
            category="system",
            permission_level=ToolPermission.HIGH,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout": {"type": "integer", "default": 60},
                },
                "required": ["command"],
            },
        ),
        lambda args: tools.run_command(
            args.get("command", ""),
            args.get("cwd"),
            args.get("timeout", 60),
        ),
    )

    registry.register(
        ToolMetadata(
            name="web_search",
            description="网络搜索。参数: query(搜索查询), num(结果数量,默认5)",
            category="web",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        lambda args: tools.web_search(
            args.get("query", ""),
            args.get("num", 5),
        ),
    )

    registry.register(
        ToolMetadata(
            name="web_fetch",
            description="获取网页内容。参数: url(网页URL)",
            category="web",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        ),
        lambda args: tools.web_fetch(args.get("url", "")),
    )

    return tools