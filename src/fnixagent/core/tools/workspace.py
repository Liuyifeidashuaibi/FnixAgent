"""
Workspace 工具集 — 参考主流 Agent 工具 的 Agent 工具能力

提供 AI Agent 与本地文件系统和 Shell 交互所需的核心工具:
  - read_file: 读取文件
  - write_file: 写入文件
  - edit_file: 精确字符串替换编辑
  - delete_file: 删除工作区内文件
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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


# ===== 安全: 防止危险命令（子串匹配；保守拦截） =====
# P1 加固: 扩展危险模式覆盖 home 目录/用户目录/强制推送/进程杀死等
_DANGEROUS_COMMANDS = [
    # 根目录删除
    "rm -rf /",
    "rm -rf/*",
    "rm -fr /",
    # 用户目录删除 (P1 新增)
    "rm -rf ~",
    "rm -rf $home",
    "rm -rf /users",
    "rm -rf /home",
    "del /s /q %userprofile%",
    "del /f /s /q",
    "rd /s /q c:\\",
    # 磁盘格式化
    "mkfs.",
    "dd if=",
    "format c:",
    # fork bomb
    ":(){ :|:& };:",
    # 设备覆写
    "> /dev/sda",
    # 权限滥用
    "chmod 777 /",
    "chown -r /",
    # 远程脚本执行
    "wget -o - | sh",
    "curl | sh",
    "curl | bash",
    "wget | bash",
    "wget | sh",
    # sudo 危险操作
    "sudo rm",
    "sudo dd",
    "sudo mkfs",
    "sudo chmod 777",
    # 系统关机/重启 (P1 新增)
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    # 注册表删除
    "reg delete",
    # Git 强制推送主分支 (P1 新增)
    "git push --force",
    "git push -f origin main",
    "git push -f origin master",
    # 进程批量杀死 (P1 新增)
    "kill -9 -1",
    "taskkill /f /im",
    # 危险环境变量清空 (P1 新增)
    "rm -rf .git",
    "rm -rf node_modules",
]


def _is_dangerous_command(cmd: str) -> bool:
    """检查是否为危险命令"""
    cmd_lower = cmd.lower().strip()
    for danger in _DANGEROUS_COMMANDS:
        if danger in cmd_lower:
            return True
    # P1 加固: 管道执行远程脚本 — 匹配 "curl ... | bash/sh" 和 "wget ... | bash/sh"
    # 原黑名单只匹配 "curl | bash" (带空格), 但 "curl http://x | bash" 不会匹配
    import re

    if re.search(r"(curl|wget)\s+[^|]+\|\s*(bash|sh|zsh|fish)", cmd_lower):
        return True
    return False


# 内置浏览器优先：识别"用系统默认浏览器打开网址"的命令形态
# （start/explorer/xdg-open/open/Start-Process/Invoke-Item + http(s):// 或 www.）。
# 这类命令会唤起用户的系统浏览器、抢走焦点，违反"不干扰用户"原则。
_OPEN_URL_IN_SYSTEM_BROWSER = re.compile(
    r"""(?ix)
    ^\s*
    (?:cmd(?:\.exe)?\s+/c\s+)?              # 可选 cmd /c 前缀
    (?:
        start(?:-process)?\s+(?:"[^"]*"\s+)?   # start ["标题"] / Start-Process
      | explorer(?:\.exe)?\s+                  # explorer <url>
      | xdg-open\s+                            # Linux
      | invoke-item\s+                         # PowerShell
      | open\s+                                # macOS
    )
    ["']?(?:https?://|www\.)                   # 目标是网址
    """
)


def _opens_url_in_system_browser(cmd: str) -> bool:
    """命令是否会唤起系统默认浏览器打开网址（内置浏览器优先策略检查点）。"""
    return bool(_OPEN_URL_IN_SYSTEM_BROWSER.match((cmd or "").strip()))


def _safe_path(workspace_root: str, rel_path: str) -> Path:
    """安全解析路径，防止路径遍历与同前缀兄弟目录逃逸。"""
    root = Path(workspace_root).resolve()
    raw = (rel_path or "").strip()
    if not raw:
        raise ValueError("路径为空")

    candidate = Path(raw)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径遍历攻击: {rel_path}") from exc
    return target


_CODE_EXTS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".py",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".json",
    ".vue",
    ".svelte",
}

_STUB_HINTS = (
    "创建文件",
    "创建项目",
    "实现逻辑",
    "定义网站",
    "定义样式",
    "基础结构",
    "样式表",
    "javascript文件",
    "css样式文件",
    "html页面",
)


def _reject_stub_source(rel_path: str, content: str) -> str | None:
    """拒绝把「说明文字」当成源码写入代码文件。"""
    suffix = Path(rel_path).suffix.lower()
    if suffix not in _CODE_EXTS:
        return None
    text = (content or "").strip()
    codeish = sum(text.count(ch) for ch in "{}[];=<>/\\`'\"()")
    # 词边界匹配，避免 "display titles with class 'list-item'" 误判为代码；
    # "=>" 作为 TS/JS 箭头函数信号单独保留。关键词集合已扩充常见代码起始
    # token（print/from/if/for/while/with/assert/async/await/yield/try/else/
    # elif/raise/pass/break/continue/lambda/del），否则极简合法脚本
    # (print('hi') / x = 1) 会被误判为"说明文字"而拒绝写入。
    looks_like_code = (
        re.search(
            r"\b(def|class|import|export|function|const|let|return|print|"
            r"from|if|for|while|with|assert|async|await|yield|try|else|"
            r"elif|raise|pass|break|continue|lambda|del)\b", text) is not None
        or "=>" in text
        or "=" in text
    )
    looks_like_markup = "<" in text and ">" in text
    looks_like_css = "{" in text and "}" in text
    if len(text) < 40:
        # Allow short but real snippets (CSS rules, tiny HTML, one-liners).
        if (
            (looks_like_code and codeish >= 2)
            or (suffix in {".html", ".htm"} and looks_like_markup and len(text) >= 15)
            or (suffix == ".css" and looks_like_css and len(text) >= 8)
            or (suffix in {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"} and codeish >= 2)
        ):
            pass
        else:
            return (
                f"拒绝写入 {rel_path}：内容过短（{len(text)} 字符）。"
                "请提供完整可运行源码，不要只写一句话说明。"
            )
    lower = text.lower()
    # 纯中文短说明、且几乎没有代码标点
    if codeish < 2 and any(h in lower or h in text for h in _STUB_HINTS):
        return (
            f"拒绝写入 {rel_path}：看起来是任务说明而不是源码。"
            "请把完整 HTML/CSS/JS/代码写入 content 字段。"
        )
    if suffix in {".html", ".htm"} and "<" not in text:
        return f"拒绝写入 {rel_path}：HTML 文件缺少标签，请写入完整 HTML。"
    if suffix == ".css" and "{" not in text:
        return f"拒绝写入 {rel_path}：CSS 文件缺少规则块，请写入完整样式。"
    if suffix in {".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx"} and codeish < 2:
        return f"拒绝写入 {rel_path}：脚本内容不像代码，请写入完整逻辑。"
    return None


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
# Windows Job Object 软沙箱接入 (run_command 子进程树兜底)
# ============================================================


def _attach_job_sandbox(pid: int) -> Any | None:
    """把刚 spawn 的子进程纳入 per-call 的 Job Object 软沙箱。

    行为约定:
      - 默认开启; 设置环境变量 FNIX_SANDBOX_JOB=0 可显式退出
      - 仅 Windows 生效, 其他平台直接返回 None
      - fail-open: 任何失败只记 warning 并返回 None, 绝不影响命令执行
      - 返回的 job 必须作为调用方局部变量使用(不可跨协程共享),
        命令结束后由调用方 close(); 超时 kill 场景先 kill() 再 close()

    Args:
        pid: 子进程 PID

    Returns:
        WinJobObject 实例; 沙箱不可用/被禁用/失败时返回 None
    """
    try:
        if os.name != "nt":
            return None
        if str(os.environ.get("FNIX_SANDBOX_JOB", "")).strip() == "0":
            return None

        # 延迟导入: 非 Windows / 循环导入场景都安全
        from fnixagent.core.sandbox import WinJobObject

        job = WinJobObject()
        if not job.create():
            return None
        if not job.assign_pid(pid):
            job.close()
            return None
        _logger.debug("run_command 子进程已纳入 Job Object 沙箱: pid=%s", pid)
        return job
    except Exception as exc:  # fail-open: 沙箱故障绝不阻塞业务
        _logger.warning("Job Object 沙箱接入失败(fail-open, 不影响执行): %s", exc)
        return None


# ============================================================
# 核心工具
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
    Workspace 工具集 — 参考主流 Agent 工具 的 Agent 工具

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
                lines = lines[offset - 1 :]
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

    def write_file(
        self,
        rel_path: str,
        content: str,
        *,
        craft_artifacts: bool = False,
    ) -> ToolResult:
        """写入文件（覆盖模式）

        Args:
            rel_path: 相对于 workspace_root 的文件路径
            content: 文件内容
            craft_artifacts: Craft 模式下强制写入 `.fnix/artifacts/`
        """
        try:
            path = (rel_path or "").strip()
            mirror_rel: str | None = None
            if craft_artifacts:
                norm = path.replace("\\", "/").strip().lstrip("/")
                already_artifact = (
                    norm.lower().startswith(".fnix/artifacts/")
                    or norm.lower().startswith("artifacts/")
                )
                if not already_artifact:
                    if norm:
                        # 写到 agent 指定的「自然路径」：就地编辑现有文件 / 任务隐含的
                        # 相对路径（如 src/components/...、index.html），保证评测器与用户
                        # 能在预期位置找到产物；同时镜像一份到 .fnix/artifacts/ 供预览面板。
                        mirror_rel = f".fnix/artifacts/{norm}"
                    else:
                        path = ".fnix/artifacts/output.txt"
                        mirror_rel = None
            stub_err = _reject_stub_source(path, content or "")
            if stub_err:
                return ToolResult(success=False, error=stub_err)

            target = _safe_path(self.workspace_root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

            if mirror_rel:
                try:
                    mtarget = _safe_path(self.workspace_root, mirror_rel)
                    mtarget.parent.mkdir(parents=True, exist_ok=True)
                    mtarget.write_text(content, encoding="utf-8")
                except Exception:
                    mirror_rel = None  # 镜像失败不影响主写入

            self.ctx.recent_edits.append(
                {
                    "action": "write",
                    "path": path,
                    "time": time.time(),
                }
            )

            msg = f"已写入: {path} ({len(content)} 字符)"
            if mirror_rel:
                msg += f"；预览镜像: {mirror_rel}"
            return ToolResult(
                success=True,
                content=msg,
                metadata={"path": str(target), "size": len(content), "rel_path": path,
                          "mirror": mirror_rel},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"写入失败: {e}")

    def delete_file(self, rel_path: str) -> ToolResult:
        """删除工作区内的文件（不允许删目录）。"""
        try:
            target = _safe_path(self.workspace_root, rel_path)
            if not target.exists():
                return ToolResult(success=False, error=f"文件不存在: {rel_path}")
            if target.is_dir():
                return ToolResult(
                    success=False,
                    error="拒绝删除目录；请仅删除文件，或使用受控的整理流程",
                )
            target.unlink()
            self.ctx.recent_edits.append(
                {
                    "action": "delete",
                    "path": rel_path,
                    "time": time.time(),
                }
            )
            return ToolResult(
                success=True,
                content=f"已删除: {rel_path}",
                metadata={"path": str(target)},
            )
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"删除失败: {e}")

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

            new_content = (
                content.replace(old_string, new_string)
                if replace_all
                else content.replace(old_string, new_string, 1)
            )
            target.write_text(new_content, encoding="utf-8")

            self.ctx.recent_edits.append(
                {
                    "action": "edit",
                    "path": rel_path,
                    "replacements": 1 if not replace_all else count,
                    "time": time.time(),
                }
            )

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
            matches = [
                m
                for m in matches
                if not any(p.startswith(".") for p in m.parts if p not in (".", ".."))
            ]

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
        self,
        pattern: str,
        path: str = ".",
        glob_filter: str = "*",
        output_mode: str = "content",
        head_limit: int = 100,
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
                if any(
                    p in ("__pycache__", "node_modules", ".git", "dist", "build") for p in rel.parts
                ):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    _logger.debug("Unhandled exception", exc_info=True)
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
                lines.append(
                    f"{e.name}{type_indicator} ({size:,} bytes)" if e.is_file() else f"{e.name}/"
                )

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
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 60,
    ) -> ToolResult:
        """执行 Shell 命令

        Windows 下默认将子进程树纳入 Job Object 软沙箱(整树兜底击杀);
        设置环境变量 FNIX_SANDBOX_JOB=0 可显式关闭。

        Args:
            command: 要执行的命令
            cwd: 工作目录 (相对于 workspace_root)
            timeout: 超时时间(秒)
        """
        if _is_dangerous_command(command):
            return ToolResult(success=False, error=f"危险命令被拦截: {command[:50]}")

        # 内置浏览器优先：禁止用系统浏览器打开网页（start/explorer + URL），
        # 引导走 browser_act(action="goto") —— 页面在内置浏览器面板中打开，不打扰用户默认浏览器
        if _opens_url_in_system_browser(command):
            return ToolResult(
                success=False,
                error=(
                    "打开网页请使用内置浏览器工具 browser_act(action=\"goto\", url=...)："
                    "url 可直接传网址或搜索关键词，页面会在应用内置浏览器中打开并展示截图。"
                    "禁止用 start / explorer 等命令唤起系统浏览器（会打扰用户）。"
                ),
            )

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

            # 软沙箱: spawn 成功后把子进程树纳入 per-call Job Object。
            # 局部变量保证并发调用互不干扰; 接入失败返回 None(fail-open)。
            sandbox_job = _attach_job_sandbox(process.pid)

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except TimeoutError:
                # 优先用 TerminateJobObject 终结整棵进程树(比 taskkill 更快更可靠,
                # 且天然覆盖沙箱接入后新生的孙子进程); 沙箱不可用时回退 taskkill
                if sandbox_job is not None:
                    sandbox_job.kill()
                # Windows 上 process.kill() 只终止主进程不终止子进程树，
                # 使用 taskkill /F /T /PID 确保终止整个进程树
                if os.name == "nt" and process.pid:
                    try:
                        import subprocess as _sp
                        _sp.run(
                            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                            capture_output=True,
                            timeout=5,
                        )
                    except Exception:
                        process.kill()
                else:
                    process.kill()
                return ToolResult(success=False, error=f"命令超时 ({timeout}s)")
            finally:
                # 命令结束(正常/超时)后释放 job 句柄;
                # KILL_ON_JOB_CLOSE 兜底确保不遗留孤儿进程树
                if sandbox_job is not None:
                    sandbox_job.close()

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
        """网络搜索 (使用 DuckDuckGo Lite 解析版)

        P3 修复: DuckDuckGo HTML 版 (html.duckduckgo.com/html/) 已返回反爬挑战页,
        改用 Lite 版 (lite.duckduckgo.com/lite/) 结构更简洁且不受反爬影响。

        Args:
            query: 搜索查询
            num: 结果数量 (默认 5, 上限 10)
        """
        num = max(1, min(int(num or 5), 10))
        try:
            import re

            import httpx

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query, "kl": "us-en"},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                    },
                )
                html = resp.text or ""

                # 解析 DuckDuckGo Lite 搜索结果
                # Lite 版结构: <a rel="nofollow" href="//duckduckgo.com/l/?uddg=URL">Title</a>
                # 摘要在后续 <td> 中
                results = []

                # 提取标题+URL (Lite 版用 rel="nofollow" 标记结果链接)
                link_pattern = re.compile(
                    r'<a[^>]*rel="nofollow"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    re.DOTALL,
                )

                # 去 HTML 标签的辅助函数
                def _strip_tags(s: str) -> str:
                    return re.sub(r"<[^>]+>", "", s).strip()

                from urllib.parse import unquote

                links = link_pattern.findall(html)
                for i, (url, title) in enumerate(links[:num]):
                    title_clean = _strip_tags(title)
                    if not title_clean or len(title_clean) < 3:
                        continue
                    # DuckDuckGo 重定向 URL 解包 (//duckduckgo.com/l/?uddg=实际URL)
                    if "uddg=" in url:
                        m = re.search(r"uddg=([^&]+)", url)
                        if m:
                            url = unquote(m.group(1))
                    elif url.startswith("//"):
                        url = "https:" + url
                    results.append(f"[{i + 1}] {title_clean}\n    URL: {url}")

                # 如果 Lite 版无结果, 回退到 HTML 版 (可能在某些网络环境下可用)
                if not results:
                    try:
                        resp2 = await client.get(
                            "https://html.duckduckgo.com/html/",
                            params={"q": query, "kl": "cn-zh"},
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                            },
                        )
                        html2 = resp2.text or ""
                        title_pattern2 = re.compile(
                            r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                            re.DOTALL,
                        )
                        titles2 = title_pattern2.findall(html2)
                        # P2: 同时解析 result__snippet 摘要块 — DDG HTML 版中
                        # snippet 与标题按结果顺序一一对应
                        snippet_pattern2 = re.compile(
                            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                            re.DOTALL | re.IGNORECASE,
                        )
                        snippets2 = snippet_pattern2.findall(html2)
                        for i, (url, title) in enumerate(titles2[:num]):
                            title_clean = _strip_tags(title)
                            if "uddg=" in url:
                                m = re.search(r"uddg=([^&]+)", url)
                                if m:
                                    url = unquote(m.group(1))
                            snippet_clean = (
                                _strip_tags(snippets2[i]).strip()[:300]
                                if i < len(snippets2)
                                else ""
                            )
                            entry = f"[{i + 1}] {title_clean}\n    URL: {url}"
                            if snippet_clean:
                                entry += f"\n    {snippet_clean}"
                            results.append(entry)
                    except Exception:  # noqa: S110 — HTML 版失败时静默降级
                        pass  # HTML 版失败时静默降级

                return ToolResult(
                    success=True,
                    content="\n\n".join(results)
                    if results
                    else "(无搜索结果, 建议用 web_fetch 直接抓取已知 URL)",
                    metadata={"query": query, "results_count": len(results)},
                )
        except ImportError:
            return ToolResult(success=False, error="需要安装 httpx: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {e}")

    async def web_fetch(self, url: str) -> ToolResult:
        """获取网页内容 (结构化提取, 保留语义标签)

        P1 优化: 原 web_fetch 简单剥离 HTML 标签导致 SPA 页面内容过短。
        改进策略:
          1. 模拟真实浏览器 User-Agent
          2. 优先提取 main/article/div 正文, 移除 nav/footer/header/script
          3. 保留段落结构 (\\n\\n 分段)
          4. 提取 title/meta description 作为摘要

        Args:
            url: 网页URL
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    },
                )
                resp.raise_for_status()

                html = resp.text or ""

                # 提取 title
                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE
                )
                title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

                # 提取 meta description
                meta_match = re.search(
                    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
                    html,
                    re.IGNORECASE,
                )
                description = meta_match.group(1) if meta_match else ""

                # 移除无关标签 (script/style/nav/footer/header/aside/svg/iframe)
                for tag in [
                    "script",
                    "style",
                    "nav",
                    "footer",
                    "header",
                    "aside",
                    "svg",
                    "iframe",
                    "noscript",
                    "form",
                ]:
                    html = re.sub(
                        rf"<{tag}[^>]*>.*?</{tag}>",
                        "",
                        html,
                        flags=re.DOTALL | re.IGNORECASE,
                    )

                # 优先提取正文区域 (main/article/content)
                main_match = re.search(
                    r"<(main|article)[^>]*>(.*?)</\1>",
                    html,
                    re.DOTALL | re.IGNORECASE,
                )
                if main_match:
                    html = main_match.group(2)

                # 段落级提取: 把 <p>, <li>, <h1>-<h6>, <td> 替换为换行
                html = re.sub(r"<(p|li|h[1-6]|td|tr|div)[^>]*>", "\n", html, flags=re.IGNORECASE)
                html = re.sub(r"</(p|li|h[1-6]|td|tr|div)>", "\n", html, flags=re.IGNORECASE)
                # 剥离剩余 HTML 标签
                html = re.sub(r"<[^>]+>", " ", html)
                # 解码 HTML 实体
                import html as html_module

                html = html_module.unescape(html)
                # 清理空白
                content = re.sub(r"[ \t]+", " ", html)
                content = re.sub(r"\n{3,}", "\n\n", content)
                content = content.strip()

                # 组装最终内容: 标题 + 摘要 + 正文
                parts = []
                if title:
                    parts.append(f"# {title}")
                if description and description != title:
                    parts.append(f"摘要: {description}")
                if content:
                    parts.append(content)
                final_content = (
                    "\n\n".join(parts) if parts else "(页面无文本内容, 可能是纯 JS 渲染页面)"
                )

                # 截断过长内容
                if len(final_content) > 15000:
                    final_content = final_content[:15000] + "\n\n... [已截断, 原文更长]"

                return ToolResult(
                    success=True,
                    content=final_content,
                    metadata={"url": url, "content_length": len(final_content), "title": title},
                )
        except ImportError:
            return ToolResult(success=False, error="需要安装 httpx: pip install httpx")
        except Exception as e:
            return ToolResult(success=False, error=f"获取失败: {e}")

    # ============================================================
    # 图片分析 (多模态能力 — GAIA Level 2/3 图片识别需求)
    # ============================================================

    def image_analyze(self, file_path: str, ocr: bool = True) -> ToolResult:
        """分析图片: 提取元数据 + OCR 文字识别。

        能力:
          1. PIL 提取图片元数据 (格式/尺寸/色彩模式/文件大小)
          2. pytesseract OCR 识别图片中的文字 (如安装了 tesseract)
          3. 主色调提取 (最常出现的颜色)

        Args:
            file_path: 图片路径 (png/jpg/jpeg/gif/bmp/webp)
            ocr: 是否执行 OCR 文字识别
        """
        safe_path = _safe_path(self.workspace_root, file_path)
        if not safe_path.exists() or not safe_path.is_file():
            return ToolResult(success=False, error=f"图片文件不存在: {file_path}")

        ext = safe_path.suffix.lower().lstrip(".")
        if ext not in ("png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff"):
            return ToolResult(success=False, error=f"不支持的图片格式: {ext}")

        try:
            from PIL import Image
        except ImportError:
            return ToolResult(
                success=False,
                error="需要安装 Pillow: pip install Pillow",
            )

        try:
            img = Image.open(safe_path)
            # 提取元数据
            info = {
                "format": img.format or ext,
                "size": f"{img.width}x{img.height}",
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "file_size_bytes": safe_path.stat().st_size,
            }

            # 主色调提取 (缩放到 32x32 后取最常出现的颜色)
            try:
                thumb = img.copy()
                thumb.thumbnail((32, 32))
                colors = thumb.getcolors(maxcolors=1024)
                if colors:
                    dominant = max(colors, key=lambda c: c[0])
                    info["dominant_color_rgb"] = dominant[1]
            except Exception:
                _logger.debug("Unhandled exception", exc_info=True)

            parts = [
                f"图片格式: {info['format']}",
                f"尺寸: {info['size']} 像素",
                f"色彩模式: {info['mode']}",
                f"文件大小: {info['file_size_bytes'] / 1024:.1f} KB",
            ]
            if "dominant_color_rgb" in info:
                r, g, b = info["dominant_color_rgb"][:3]
                parts.append(f"主色调: RGB({r}, {g}, {b})")

            # OCR 文字识别
            if ocr:
                try:
                    import pytesseract

                    # 转灰度提升 OCR 精度
                    gray = img.convert("L") if img.mode != "L" else img
                    text = pytesseract.image_to_string(gray, lang="chi_sim+eng")
                    text = text.strip()
                    if text:
                        parts.append(f"\nOCR 识别文字:\n{text[:2000]}")
                        info["ocr_text"] = text[:2000]
                    else:
                        parts.append("\nOCR: 未识别到文字")
                except ImportError:
                    parts.append("\nOCR: 未安装 pytesseract (pip install pytesseract)")
                except Exception as e:
                    parts.append(f"\nOCR 失败: {e}")

            return ToolResult(
                success=True,
                content="\n".join(parts),
                metadata=info,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"图片分析失败: {e}")

    # ============================================================
    # 安全计算器 (替代 run_command 跑 python 的重方案)
    # ============================================================

    def calculate(self, expression: str) -> ToolResult:
        """安全数学表达式计算。

        支持: + - * / % ** () 和 math 函数 (sin/cos/tan/sqrt/log/abs/floor/ceil/round)
        安全: 白名单 AST 校验, 拒绝 import/eval/exec/attribute access

        Args:
            expression: 数学表达式, 如 '(10-8)/8*100' 或 'sqrt(144) + sin(0)'
        """
        if not expression or not isinstance(expression, str):
            return ToolResult(success=False, error="表达式不能为空")

        expr = expression.strip()
        if len(expr) > 500:
            return ToolResult(success=False, error="表达式过长 (上限 500 字符)")

        try:
            import ast
            import math
            import operator

            # 安全的运算符映射
            _SAFE_OPS = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Mod: operator.mod,
                ast.Pow: operator.pow,
                ast.USub: operator.neg,
                ast.UAdd: operator.pos,
                ast.FloorDiv: operator.floordiv,
            }

            # 安全的函数映射
            _SAFE_FUNCS = {
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "sqrt": math.sqrt,
                "log": math.log,
                "log10": math.log10,
                "abs": abs,
                "floor": math.floor,
                "ceil": math.ceil,
                "round": round,
                "min": min,
                "max": max,
                "pow": pow,
                "pi": math.pi,
                "e": math.e,
            }

            def _eval_node(node):
                """递归求值, 只允许白名单内的操作"""
                if isinstance(node, ast.Expression):
                    return _eval_node(node.body)
                elif isinstance(node, ast.Num):  # Python < 3.8
                    return node.n
                elif isinstance(node, ast.Constant):
                    if isinstance(node.value, (int, float)):
                        return node.value
                    raise ValueError(f"不允许的常量类型: {type(node.value)}")
                elif isinstance(node, ast.BinOp):
                    op_type = type(node.op)
                    if op_type not in _SAFE_OPS:
                        raise ValueError(f"不允许的运算符: {op_type.__name__}")
                    return _SAFE_OPS[op_type](_eval_node(node.left), _eval_node(node.right))
                elif isinstance(node, ast.UnaryOp):
                    op_type = type(node.op)
                    if op_type not in _SAFE_OPS:
                        raise ValueError(f"不允许的一元运算符: {op_type.__name__}")
                    return _SAFE_OPS[op_type](_eval_node(node.operand))
                elif isinstance(node, ast.Call):
                    if not isinstance(node.func, ast.Name):
                        raise ValueError("不允许的函数调用方式")
                    func_name = node.func.id
                    if func_name not in _SAFE_FUNCS:
                        raise ValueError(f"不允许的函数: {func_name}")
                    args = [_eval_node(a) for a in node.args]
                    return _SAFE_FUNCS[func_name](*args)
                elif isinstance(node, ast.Name):
                    if node.id in _SAFE_FUNCS and not callable(_SAFE_FUNCS[node.id]):
                        return _SAFE_FUNCS[node.id]  # 常量如 pi, e
                    raise ValueError(f"不允许的变量: {node.id}")
                else:
                    raise ValueError(f"不允许的语法: {type(node).__name__}")

            tree = ast.parse(expr, mode="eval")
            result = _eval_node(tree)

            # 格式化结果
            if isinstance(result, float):
                if result.is_integer():
                    result_str = str(int(result))
                else:
                    result_str = f"{result:.10g}"
            else:
                result_str = str(result)

            return ToolResult(
                success=True,
                content=f"{expression} = {result_str}",
                metadata={"expression": expression, "result": result},
            )
        except ValueError as e:
            return ToolResult(success=False, error=f"表达式不安全或无效: {e}")
        except ZeroDivisionError:
            return ToolResult(success=False, error="除零错误")
        except Exception as e:
            return ToolResult(success=False, error=f"计算失败: {e}")


# ============================================================
# 工具注册 (注册到 ToolRegistry)
# ============================================================


def register_workspace_tools(
    registry,
    workspace_root: str = ".",
    *,
    craft_artifacts: bool = False,
) -> WorkspaceTools:
    """将 workspace 工具注册到全局 ToolRegistry

    Args:
        registry: ToolRegistry 实例
        workspace_root: 工作区根目录
        craft_artifacts: Craft 模式强制 write_file 落入 `.fnix/artifacts/`

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

    write_desc = "写入文件(覆盖模式)。参数: file_path(路径), content(内容)"
    if craft_artifacts:
        write_desc = (
            "写入文件(覆盖模式)。Craft 交付必须写到 `.fnix/artifacts/`；"
            "若路径不在该目录，系统会自动改写。参数: file_path, content"
        )
    registry.register(
        ToolMetadata(
            name="write_file",
            description=write_desc,
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
        lambda args, _craft=craft_artifacts: tools.write_file(
            args.get("file_path", args.get("rel_path", "")),
            args.get("content", ""),
            craft_artifacts=_craft,
        ),
    )

    registry.register(
        ToolMetadata(
            name="delete_file",
            description="删除工作区内的文件（不可删目录、不可越出 workspace）。参数: file_path",
            category="filesystem",
            permission_level=ToolPermission.MIDDLE,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "相对于workspace的文件路径"},
                },
                "required": ["file_path"],
            },
        ),
        lambda args: tools.delete_file(
            args.get("file_path", args.get("rel_path", "")),
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

    # Spec: inline widget — AI 在对话流内即时渲染可视化（SVG/HTML）
    # 动态 UI 渲染
    # 三层安全：前端 iframe sandbox + CSP + DOMPurify（后端仅透传 code）
    registry.register(
        ToolMetadata(
            name="show_widget",
            description=(
                "在对话流内即时渲染一个可视化 widget（SVG/HTML）。"
                "适用场景：对比矩阵、流程图、数据图表、架构图、决策表、机制示意图。"
                "不适用：长报告、整页应用、纯文本回答、装饰性视觉。"
                "参数 widget_code 是完整的 SVG 或 HTML 字符串（含 <style>），"
                "无需 <!DOCTYPE>/html/head/body 包裹。"
                "硬约束（iframe 沙箱）：禁止外部 CDN/网络请求；"
                "禁止 onclick 等内联事件属性，交互一律在末尾 <script> 内用 addEventListener 绑定；"
                "配色引用宿主 CSS 变量 var(--brand)/var(--surface)/var(--text-primary)/var(--border) 等（自动适配明暗主题）；"
                "需要 AI 继续回答的追问按钮调用 window.sendPrompt('问题文本')。"
                "参数 mode 默认 inline（对话流内）。"
            ),
            category="render",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "widget_code": {
                        "type": "string",
                        "description": "完整的 SVG/HTML 代码（含 <style>）",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["inline", "panel"],
                        "default": "inline",
                        "description": "inline=对话流内（默认），panel=独立面板",
                    },
                    "widget_type": {
                        "type": "string",
                        "description": "类型标签：chart/table/flow/decision/mechanism",
                    },
                },
                "required": ["widget_code"],
            },
        ),
        lambda args: _show_widget(args),
    )

    # 图片分析工具 (P1 新增: 多模态能力, 支持 GAIA Level 2/3 的图片识别需求)
    registry.register(
        ToolMetadata(
            name="image_analyze",
            description=(
                "分析图片文件: 提取元数据(尺寸/格式/色彩) + OCR 文字识别。"
                "用于识别图片中的文字、图表数据、截图内容等。"
                "参数: file_path(图片路径), ocr(是否OCR识别文字, 默认true)"
            ),
            category="multimodal",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "图片路径 (png/jpg/jpeg/gif/bmp/webp)",
                    },
                    "ocr": {"type": "boolean", "description": "是否执行 OCR 文字识别 (默认 true)"},
                },
                "required": ["file_path"],
            },
        ),
        lambda args: tools.image_analyze(
            args.get("file_path", ""),
            args.get("ocr", True),
        ),
    )

    # 计算器工具 (P1 新增: 安全数学计算, 替代 run_command 跑 python 的重方案)
    registry.register(
        ToolMetadata(
            name="calculate",
            description=(
                "安全数学表达式计算。支持 + - * / % ** () 和常见数学函数 "
                "(sin/cos/tan/sqrt/log/abs/floor/ceil/round)。"
                "用于 GAIA 风格的数值计算任务, 比 run_command 更安全。"
                "参数: expression(数学表达式)"
            ),
            category="math",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式, 如 '(10-8)/8*100'",
                    },
                },
                "required": ["expression"],
            },
        ),
        lambda args: tools.calculate(args.get("expression", "")),
    )

    return tools


def _show_widget(args: dict) -> str:
    """show_widget 工具实现 — 后端仅做长度保护与透传，渲染在前端 iframe sandbox。"""
    code = str(args.get("widget_code", ""))
    mode = str(args.get("mode", "inline"))
    widget_type = str(args.get("widget_type", "custom"))
    if not code.strip():
        return "[失败] widget_code 为空"
    if len(code) > 200_000:
        return f"[失败] widget_code 超过 200K 字符限制（当前 {len(code)} 字符）"
    return f"[已渲染] widget ({widget_type}, {len(code)} chars, mode={mode})"
