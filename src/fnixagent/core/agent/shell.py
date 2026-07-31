"""
AgentShell - AgentOS 用户接口层 (User Interface Shell)
=========================================================
类比 Unix Shell (bash/zsh), 是用户/Agent 与 AgentKernel 交互的入口。

设计要点:
  - 命令行接口 (CLI): spawn/kill/ps/exec/mem/fs/a2a/skill/stats/audit/...
  - 自然语言接口 (NL): 将用户输入转发为 LLM_COMPLETE syscall
  - Skill 加载器: 从目录加载 Skill 脚本 (类比 shell 脚本)
  - 交互式 REPL: 支持 REPL 模式
  - 异步: 所有命令异步执行

命令清单 (类比 Unix 命令):
  boot              - 启动内核 (类比 init)
  shutdown          - 关闭内核
  spawn <name>      - 创建 Agent (类比 fork+exec)
  kill <pid>        - 终止 Agent (类比 kill -9)
  ps                - 列出 Agent (类比 ps)
  exec <syscall>    - 执行 syscall (类比 syscall)
  fs.<op>           - 文件系统操作 (read/write/list/mkdir/delete)
  mem.<op>          - 记忆操作 (recall/store/search/forget)
  a2a.<op>          - A2A 通信 (discover/send/broadcast)
  tool.<op>         - 工具调用 (list/invoke)
  llm <prompt>      - LLM 推理 (类比 echo | llm)
  skill.<op>        - Skill 管理 (list/load/run)
  policy.<op>       - 策略管理 (list/add)
  guardrail.<op>    - 护栏管理 (list/add)
  audit             - 查询审计日志
  stats             - 内核统计
  help              - 帮助
  exit              - 退出 REPL

零外部依赖: 仅 asyncio/json/sys/asyncio.inspect
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fnixagent.core.agent.kernel import AgentKernel, get_kernel
from fnixagent.core.agent.syscall import (
    SyscallRequest,
    SyscallType,
)
from fnixagent.core.agent.types import (
    AgentPriority,
)

# ============================================================================
# Shell 命令结果
# ============================================================================


@dataclass
class ShellResult:
    """Shell 命令执行结果。"""

    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    @classmethod
    def ok(cls, output: Any = None, *, duration_ms: float = 0.0) -> ShellResult:
        return cls(success=True, output=output, duration_ms=duration_ms)

    @classmethod
    def err(cls, error: str, *, duration_ms: float = 0.0) -> ShellResult:
        return cls(success=False, error=error, duration_ms=duration_ms)

    def format(self, *, json_mode: bool = False) -> str:
        """格式化输出。"""
        if json_mode:
            return json.dumps(
                {
                    "success": self.success,
                    "output": self.output,
                    "error": self.error,
                    "duration_ms": round(self.duration_ms, 3),
                },
                ensure_ascii=False,
                default=str,
                indent=2,
            )
        if not self.success:
            return f"ERROR: {self.error}"
        if self.output is None:
            return "OK"
        if isinstance(self.output, (dict, list)):
            return json.dumps(self.output, ensure_ascii=False, default=str, indent=2)
        return str(self.output)


# ============================================================================
# Skill 抽象 (类比 shell 脚本)
# ============================================================================


@dataclass
class Skill:
    """Skill 定义 (类比 shell 脚本 / callable)。

    Attributes:
        name: Skill 名称 (唯一标识)
        description: Skill 描述
        handler: 异步处理函数 (kernel, args) -> Any
        capabilities: 该 Skill 需要的能力集
        source_path: Skill 源文件路径 (动态加载时记录)
    """

    name: str
    description: str = ""
    handler: Callable[..., Awaitable[Any]] | None = None
    capabilities: set[str] = field(default_factory=set)
    source_path: str = ""


class SkillRegistry:
    """Skill 注册表 (类比 PATH 中的可执行文件)。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """注册 Skill。"""
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> bool:
        """注销 Skill。"""
        return self._skills.pop(name, None) is not None

    def get(self, name: str) -> Skill | None:
        """获取 Skill。"""
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        """列出所有 Skill。"""
        return list(self._skills.values())

    def load_from_directory(self, dir_path: str) -> int:
        """从目录批量加载 Skill 脚本 (类比 shell PATH)。

        每个 .py 文件视为一个 Skill 模块, 文件内可定义:
          - SKILL_NAME: str       Skill 名称
          - SKILL_DESCRIPTION: str Skill 描述
          - SKILL_CAPABILITIES: set[str] 所需能力集
          - async def handler(kernel, args): Skill 处理函数

        Args:
            dir_path: 目录路径

        Returns:
            加载的 Skill 数量
        """
        path = Path(dir_path)
        if not path.is_dir():
            return 0
        count = 0
        for py_file in path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                skill = self._load_skill_file(py_file)
                if skill is not None:
                    self.register(skill)
                    count += 1
            except Exception as e:
                print(f"[SkillLoader] 加载 {py_file.name} 失败: {e}", file=sys.stderr)
        return count

    def _load_skill_file(self, file_path: Path) -> Skill | None:
        """加载单个 Skill 文件。"""
        module_name = f"_agentos_skill_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        name = getattr(module, "SKILL_NAME", file_path.stem)
        description = getattr(module, "SKILL_DESCRIPTION", "")
        capabilities = set(getattr(module, "SKILL_CAPABILITIES", set()))
        handler = getattr(module, "handler", None)
        if handler is None or not callable(handler):
            return None
        # 确保是协程函数
        if not inspect.iscoroutinefunction(handler):
            return None
        return Skill(
            name=name,
            description=description,
            handler=handler,
            capabilities=capabilities,
            source_path=str(file_path),
        )


# ============================================================================
# AgentShell 主类
# ============================================================================


class AgentShell:
    """AgentOS 用户接口层 (类比 Unix Shell)。

    提供命令行接口 (CLI) + 自然语言接口 + Skill 加载。

    Usage:
        shell = AgentShell(kernel)
        await shell.boot()
        await shell.execute("spawn my-agent")
        await shell.execute("llm 你好")
        result = await shell.natural_language("帮我搜索关于 AgentOS 的资料")
    """

    def __init__(
        self,
        kernel: AgentKernel | None = None,
        skills_dir: str | None = None,
    ):
        self._kernel = kernel or get_kernel()
        self.skills = SkillRegistry()
        # 当前会话默认 caller_pid (kernel shell-agent 的 PID)
        self._shell_pid: str = "kernel"
        # 默认 spawn 的 Agent 的能力集
        self._default_capabilities: set[str] = {"fs", "memory", "llm", "tool", "ipc"}
        # 命令注册表
        self._commands: dict[str, Callable[..., Awaitable[ShellResult]]] = {}
        self._register_commands()
        # 加载 Skill
        if skills_dir:
            self.skills.load_from_directory(skills_dir)

    # --- 内核访问 ---

    @property
    def kernel(self) -> AgentKernel:
        return self._kernel

    def set_shell_pid(self, pid: str) -> None:
        """设置 shell 调用方 PID (用于 syscall 授权)。"""
        self._shell_pid = pid

    # ========================================================================
    # 命令注册
    # ========================================================================

    def _register_commands(self) -> None:
        """注册所有 shell 命令处理器。"""
        self._commands = {
            "boot": self._cmd_boot,
            "shutdown": self._cmd_shutdown,
            "spawn": self._cmd_spawn,
            "kill": self._cmd_kill,
            "ps": self._cmd_ps,
            "info": self._cmd_info,
            "exec": self._cmd_exec,
            "llm": self._cmd_llm,
            "fs.read": self._cmd_fs_read,
            "fs.write": self._cmd_fs_write,
            "fs.list": self._cmd_fs_list,
            "fs.mkdir": self._cmd_fs_mkdir,
            "fs.delete": self._cmd_fs_delete,
            "mem.recall": self._cmd_mem_recall,
            "mem.store": self._cmd_mem_store,
            "mem.search": self._cmd_mem_search,
            "mem.forget": self._cmd_mem_forget,
            "tool.list": self._cmd_tool_list,
            "tool.invoke": self._cmd_tool_invoke,
            "a2a.discover": self._cmd_a2a_discover,
            "a2a.send": self._cmd_a2a_send,
            "a2a.broadcast": self._cmd_a2a_broadcast,
            "skill.list": self._cmd_skill_list,
            "skill.load": self._cmd_skill_load,
            "skill.run": self._cmd_skill_run,
            "policy.list": self._cmd_policy_list,
            "policy.add": self._cmd_policy_add,
            "guardrail.list": self._cmd_guardrail_list,
            "audit": self._cmd_audit,
            "stats": self._cmd_stats,
            "checkpoint": self._cmd_checkpoint,
            "help": self._cmd_help,
        }

    def list_commands(self) -> list[str]:
        """列出所有可用命令。"""
        return sorted(self._commands.keys())

    # ========================================================================
    # 命令执行入口
    # ========================================================================

    async def execute(self, command_line: str) -> ShellResult:
        """执行 shell 命令行 (类比 sh -c)。

        Args:
            command_line: 命令行 (如 "spawn my-agent --priority=normal")

        Returns:
            ShellResult
        """
        command_line = command_line.strip()
        if not command_line:
            return ShellResult.err("空命令")
        if command_line.startswith("#"):
            return ShellResult.ok(None)  # 注释

        cmd, args = self._parse_command_line(command_line)
        handler = self._commands.get(cmd)
        if handler is None:
            return ShellResult.err(f"未知命令: {cmd} (输入 help 查看可用命令)")

        import time

        start = time.monotonic()
        try:
            result = await handler(args)
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except Exception as e:
            return ShellResult.err(
                f"命令执行异常: {type(e).__name__}: {e}",
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _parse_command_line(self, line: str) -> tuple[str, dict[str, Any]]:
        """解析命令行 (支持 --key=value 和位置参数)。

        Example:
            "spawn my-agent --priority=normal --capabilities=fs,llm"
            → ("spawn", {"_positional": ["my-agent"], "priority": "normal",
                        "capabilities": "fs,llm"})
        """
        # 简单分词 (不支持引号嵌套, 但支持双引号包空白)
        tokens = self._tokenize(line)
        if not tokens:
            return "", {}
        cmd = tokens[0]
        args: dict[str, Any] = {"_positional": []}
        i = 1
        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("--"):
                key_value = tok[2:]
                if "=" in key_value:
                    key, value = key_value.split("=", 1)
                    args[key] = value
                else:
                    # --flag 形式: 取下一个 token 作为值, 无则 True
                    if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                        args[key_value] = tokens[i + 1]
                        i += 1
                    else:
                        args[key_value] = True
            else:
                args["_positional"].append(tok)
            i += 1
        return cmd, args

    @staticmethod
    def _tokenize(line: str) -> list[str]:
        """简单分词 (支持双引号包空白)。"""
        tokens: list[str] = []
        current: list[str] = []
        in_quote = False
        for ch in line:
            if ch == '"':
                in_quote = not in_quote
            elif ch.isspace() and not in_quote:
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(ch)
        if current:
            tokens.append("".join(current))
        return tokens

    # ========================================================================
    # 内核生命周期命令
    # ========================================================================

    async def _cmd_boot(self, args: dict[str, Any]) -> ShellResult:
        """boot - 启动内核。"""
        await self._kernel.boot()
        return ShellResult.ok({"booted": True, "shell_pid": self._shell_pid})

    async def _cmd_shutdown(self, args: dict[str, Any]) -> ShellResult:
        """shutdown - 关闭内核。"""
        await self._kernel.shutdown()
        return ShellResult.ok({"shutdown": True})

    # ========================================================================
    # 进程管理命令
    # ========================================================================

    async def _cmd_spawn(self, args: dict[str, Any]) -> ShellResult:
        """spawn <name> [--priority=normal] [--capabilities=fs,llm] [--parent=<pid>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: spawn <name> [--priority=...] [--capabilities=...]")
        name = positional[0]
        priority_str = args.get("priority", "normal")
        try:
            priority = AgentPriority[priority_str.upper()]
        except KeyError:
            return ShellResult.err(f"无效优先级: {priority_str}")
        caps_str = args.get("capabilities", "")
        capabilities = set(caps_str.split(",")) if caps_str else set(self._default_capabilities)
        capabilities.discard("")
        parent_pid = args.get("parent") or None
        try:
            pid = await self._kernel.spawn(
                name=name,
                parent_pid=parent_pid,
                priority=priority,
                capabilities=capabilities,
            )
            return ShellResult.ok({"pid": pid, "name": name, "priority": int(priority)})
        except PermissionError as e:
            return ShellResult.err(str(e))

    async def _cmd_kill(self, args: dict[str, Any]) -> ShellResult:
        """kill <pid> [--reason=...]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: kill <pid> [--reason=...]")
        pid = positional[0]
        reason = args.get("reason", "")
        success = await self._kernel.kill(pid, reason=reason)
        if not success:
            return ShellResult.err(f"进程不存在: {pid}")
        return ShellResult.ok({"killed": pid})

    async def _cmd_ps(self, args: dict[str, Any]) -> ShellResult:
        """ps - 列出所有 Agent 进程。"""
        processes = self._kernel.list_processes()
        return ShellResult.ok([p.to_dict() for p in processes])

    async def _cmd_info(self, args: dict[str, Any]) -> ShellResult:
        """info <pid> - 查看进程详情。"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: info <pid>")
        pid = positional[0]
        proc = self._kernel.get_process(pid)
        if proc is None:
            return ShellResult.err(f"进程不存在: {pid}")
        return ShellResult.ok(proc.to_dict())

    # ========================================================================
    # Syscall 执行命令
    # ========================================================================

    async def _cmd_exec(self, args: dict[str, Any]) -> ShellResult:
        """exec <syscall> [--arg=value ...] [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: exec <syscall> [--arg=value ...]")
        syscall_name = positional[0]
        try:
            syscall = SyscallType(syscall_name)
        except ValueError:
            return ShellResult.err(f"未知 syscall: {syscall_name}")
        # 构造参数 (排除 _positional 和内置参数)
        syscall_args = {k: v for k, v in args.items() if k != "_positional" and k != "pid"}
        caller_pid = args.get("pid", self._shell_pid)
        req = SyscallRequest(
            syscall=syscall,
            args=syscall_args,
            caller_pid=caller_pid,
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "syscall failed", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    async def _cmd_llm(self, args: dict[str, Any]) -> ShellResult:
        """llm <prompt> [--pid=<caller>] [--system=<system_prompt>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: llm <prompt>")
        prompt = " ".join(positional)
        system_prompt = args.get("system", "你是 fnixagent 内核 Shell 助手。")
        caller_pid = args.get("pid", self._shell_pid)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        req = SyscallRequest(
            syscall=SyscallType.LLM_COMPLETE,
            args={"messages": messages},
            caller_pid=caller_pid,
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "LLM 调用失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    # ========================================================================
    # 文件系统命令
    # ========================================================================

    async def _fs_syscall(
        self, syscall: SyscallType, args: dict[str, Any], caller_pid: str | None = None
    ) -> ShellResult:
        """通用 FS syscall 调用。"""
        req = SyscallRequest(
            syscall=syscall,
            args=args,
            caller_pid=caller_pid or self._shell_pid,
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "fs 操作失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    async def _cmd_fs_read(self, args: dict[str, Any]) -> ShellResult:
        """fs.read <path> [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: fs.read <path>")
        return await self._fs_syscall(SyscallType.FS_READ, {"path": positional[0]}, args.get("pid"))

    async def _cmd_fs_write(self, args: dict[str, Any]) -> ShellResult:
        """fs.write <path> --content=<content> [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: fs.write <path> --content=<content>")
        path = positional[0]
        content = args.get("content", "")
        return await self._fs_syscall(
            SyscallType.FS_WRITE, {"path": path, "content": content}, args.get("pid")
        )

    async def _cmd_fs_list(self, args: dict[str, Any]) -> ShellResult:
        """fs.list [path] [--pid=<caller>]"""
        positional = args.get("_positional", [])
        path = positional[0] if positional else "/"
        return await self._fs_syscall(SyscallType.FS_LIST, {"path": path}, args.get("pid"))

    async def _cmd_fs_mkdir(self, args: dict[str, Any]) -> ShellResult:
        """fs.mkdir <path> [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: fs.mkdir <path>")
        return await self._fs_syscall(
            SyscallType.FS_MKDIR, {"path": positional[0]}, args.get("pid")
        )

    async def _cmd_fs_delete(self, args: dict[str, Any]) -> ShellResult:
        """fs.delete <path> [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: fs.delete <path>")
        return await self._fs_syscall(
            SyscallType.FS_DELETE, {"path": positional[0]}, args.get("pid")
        )

    # ========================================================================
    # 记忆命令
    # ========================================================================

    async def _mem_syscall(
        self, syscall: SyscallType, args: dict[str, Any], caller_pid: str | None = None
    ) -> ShellResult:
        req = SyscallRequest(
            syscall=syscall,
            args=args,
            caller_pid=caller_pid or self._shell_pid,
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "mem 操作失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    async def _cmd_mem_recall(self, args: dict[str, Any]) -> ShellResult:
        """mem.recall <query> [--layers=working,episodic] [--top_k=5]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: mem.recall <query> [--layers=...] [--top_k=...]")
        query = " ".join(positional)
        layers_str = args.get("layers", "working")
        layers = layers_str.split(",") if isinstance(layers_str, str) else layers_str
        top_k = int(args.get("top_k", 5))
        return await self._mem_syscall(
            SyscallType.MEM_RECALL,
            {"query": query, "layers": layers, "top_k": top_k},
            args.get("pid"),
        )

    async def _cmd_mem_store(self, args: dict[str, Any]) -> ShellResult:
        """mem.store --content=<content> [--layer=episodic] [--pid=<caller>]"""
        content = args.get("content")
        if content is None:
            return ShellResult.err("用法: mem.store --content=<content> [--layer=...]")
        layer = args.get("layer", "episodic")
        return await self._mem_syscall(
            SyscallType.MEM_STORE,
            {"content": content, "layer": layer, "metadata": {}},
            args.get("pid"),
        )

    async def _cmd_mem_search(self, args: dict[str, Any]) -> ShellResult:
        """mem.search <query> [--layer=episodic] [--top_k=5]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: mem.search <query> [--layer=...] [--top_k=...]")
        query = " ".join(positional)
        layer = args.get("layer", "episodic")
        top_k = int(args.get("top_k", 5))
        return await self._mem_syscall(
            SyscallType.MEM_SEARCH,
            {"query": query, "layer": layer, "top_k": top_k},
            args.get("pid"),
        )

    async def _cmd_mem_forget(self, args: dict[str, Any]) -> ShellResult:
        """mem.forget <memory_id> [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: mem.forget <memory_id>")
        return await self._mem_syscall(
            SyscallType.MEM_FORGET, {"memory_id": positional[0]}, args.get("pid")
        )

    # ========================================================================
    # 工具命令
    # ========================================================================

    async def _cmd_tool_list(self, args: dict[str, Any]) -> ShellResult:
        """tool.list [--pid=<caller>]"""
        req = SyscallRequest(
            syscall=SyscallType.TOOL_LIST,
            args={},
            caller_pid=args.get("pid", self._shell_pid),
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "tool.list 失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    async def _cmd_tool_invoke(self, args: dict[str, Any]) -> ShellResult:
        """tool.invoke <tool_name> [--args=<json>] [--pid=<caller>]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: tool.invoke <tool_name> [--args=<json>]")
        tool_name = positional[0]
        args_str = args.get("args", "{}")
        try:
            tool_args = json.loads(args_str) if isinstance(args_str, str) else args_str
        except json.JSONDecodeError as e:
            return ShellResult.err(f"args JSON 解析失败: {e}")
        req = SyscallRequest(
            syscall=SyscallType.TOOL_INVOKE,
            args={"tool": tool_name, "arguments": tool_args},
            caller_pid=args.get("pid", self._shell_pid),
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "tool.invoke 失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    # ========================================================================
    # A2A 通信命令
    # ========================================================================

    async def _cmd_a2a_discover(self, args: dict[str, Any]) -> ShellResult:
        """a2a.discover [--capability=<cap>]"""
        capability = args.get("capability")
        cards = await self._kernel.a2a_bus.discover(capability=capability)
        return ShellResult.ok([c.to_dict() for c in cards])

    async def _cmd_a2a_send(self, args: dict[str, Any]) -> ShellResult:
        """a2a.send --target=<pid> --content=<content> [--type=event]"""
        target = args.get("target")
        content = args.get("content")
        if not target or content is None:
            return ShellResult.err("用法: a2a.send --target=<pid> --content=<content>")
        msg_type = args.get("type", "event")
        from fnixagent.core.agent.messaging import A2AMessage

        msg = A2AMessage(
            source=self._shell_pid,
            target=target,
            message_type=msg_type,
            content=content,
        )
        await self._kernel.a2a_bus.send(target, msg)
        return ShellResult.ok({"sent": True, "target": target})

    async def _cmd_a2a_broadcast(self, args: dict[str, Any]) -> ShellResult:
        """a2a.broadcast --content=<content>"""
        content = args.get("content")
        if content is None:
            return ShellResult.err("用法: a2a.broadcast --content=<content>")
        from fnixagent.core.agent.messaging import A2AMessage

        msg = A2AMessage(
            source=self._shell_pid,
            target="*",
            message_type="event",
            content=content,
        )
        count = await self._kernel.a2a_bus.broadcast(msg, exclude=self._shell_pid)
        return ShellResult.ok({"delivered": count})

    # ========================================================================
    # Skill 命令
    # ========================================================================

    async def _cmd_skill_list(self, args: dict[str, Any]) -> ShellResult:
        """skill.list - 列出所有 Skill。"""
        skills = self.skills.list()
        return ShellResult.ok(
            [
                {
                    "name": s.name,
                    "description": s.description,
                    "capabilities": sorted(s.capabilities),
                    "source": s.source_path,
                }
                for s in skills
            ]
        )

    async def _cmd_skill_load(self, args: dict[str, Any]) -> ShellResult:
        """skill.load <dir> - 从目录加载 Skill。"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: skill.load <dir>")
        dir_path = positional[0]
        if not os.path.isdir(dir_path):
            return ShellResult.err(f"目录不存在: {dir_path}")
        count = self.skills.load_from_directory(dir_path)
        return ShellResult.ok({"loaded": count, "dir": dir_path})

    async def _cmd_skill_run(self, args: dict[str, Any]) -> ShellResult:
        """skill.run <name> [--arg=value ...]"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: skill.run <name> [--arg=value ...]")
        skill_name = positional[0]
        skill = self.skills.get(skill_name)
        if skill is None or skill.handler is None:
            return ShellResult.err(f"Skill 不存在: {skill_name}")
        skill_args = {k: v for k, v in args.items() if k != "_positional"}
        try:
            result = await skill.handler(self._kernel, skill_args)
            return ShellResult.ok(result)
        except Exception as e:
            return ShellResult.err(f"Skill 执行失败: {type(e).__name__}: {e}")

    # ========================================================================
    # 策略 / 护栏 / 审计 / 统计命令
    # ========================================================================

    async def _cmd_policy_list(self, args: dict[str, Any]) -> ShellResult:
        """policy.list - 列出策略规则。"""
        return ShellResult.ok(self._kernel.policy.list_rules())

    async def _cmd_policy_add(self, args: dict[str, Any]) -> ShellResult:
        """policy.add --action=<pattern> --effect=<allow|deny> [--subject=*] [--priority=0]"""
        from fnixagent.core.agent.policy import PolicyRule

        action = args.get("action", "*")
        effect = args.get("effect", "allow")
        subject = args.get("subject", "*")
        priority = int(args.get("priority", 0))
        description = args.get("description", "")
        rule = PolicyRule(
            action=action,
            subject=subject,
            effect=effect,
            priority=priority,
            description=description,
        )
        self._kernel.policy.add_rule(rule)
        return ShellResult.ok(
            {
                "added": True,
                "rule": rule.__dict__
                if hasattr(rule, "__dict__")
                else {
                    "action": action,
                    "subject": subject,
                    "effect": effect,
                    "priority": priority,
                },
            }
        )

    async def _cmd_guardrail_list(self, args: dict[str, Any]) -> ShellResult:
        """guardrail.list - 列出护栏。"""
        return ShellResult.ok(self._kernel.guardrail.get_stats())

    async def _cmd_audit(self, args: dict[str, Any]) -> ShellResult:
        """audit [--limit=100] [--action=<filter>]"""
        limit = int(args.get("limit", 100))
        action = args.get("action")
        logs = self._kernel.get_audit_log(limit=limit, action=action)
        return ShellResult.ok(logs)

    async def _cmd_stats(self, args: dict[str, Any]) -> ShellResult:
        """stats - 内核统计。"""
        return ShellResult.ok(self._kernel.get_kernel_stats())

    async def _cmd_checkpoint(self, args: dict[str, Any]) -> ShellResult:
        """checkpoint <pid> - 保存进程检查点。"""
        positional = args.get("_positional", [])
        if not positional:
            return ShellResult.err("用法: checkpoint <pid>")
        pid = positional[0]
        req = SyscallRequest(
            syscall=SyscallType.CHECKPOINT,
            args={},
            caller_pid=pid,
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "checkpoint 失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    async def _cmd_help(self, args: dict[str, Any]) -> ShellResult:
        """help - 显示所有命令。"""
        return ShellResult.ok(
            {cmd: (handler.__doc__ or "").strip() for cmd, handler in self._commands.items()}
        )

    # ========================================================================
    # 自然语言接口
    # ========================================================================

    async def natural_language(
        self,
        text: str,
        *,
        caller_pid: str | None = None,
        system_prompt: str | None = None,
    ) -> ShellResult:
        """自然语言接口 (类比 Copilot)。

        将用户自然语言输入转发为 LLM_COMPLETE syscall。
        系统提示注入内核上下文 (stats + 可用命令), 供 LLM 决策。

        Args:
            text: 用户自然语言输入
            caller_pid: 调用方 PID (None = shell)
            system_prompt: 自定义系统提示 (None = 默认)

        Returns:
            ShellResult (output = LLM 响应文本)
        """
        if system_prompt is None:
            system_prompt = self._build_default_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        req = SyscallRequest(
            syscall=SyscallType.LLM_COMPLETE,
            args={"messages": messages},
            caller_pid=caller_pid or self._shell_pid,
        )
        resp = await self._kernel.syscall(req)
        if not resp.success:
            return ShellResult.err(resp.error or "LLM 推理失败", duration_ms=resp.duration_ms)
        return ShellResult.ok(resp.result, duration_ms=resp.duration_ms)

    def _build_default_system_prompt(self) -> str:
        """构建默认系统提示 (注入内核上下文)。"""
        stats = self._kernel.get_kernel_stats()
        commands = ", ".join(sorted(self._commands.keys()))
        return (
            "你是 fnixagent OS 内核 Shell 助手。"
            f"内核状态: boot={stats.get('booted')}, "
            f"进程数={stats.get('process_count', 0)}。\n"
            f"可用命令: {commands}\n"
            "你可以指导用户使用命令, 或直接回答问题。"
        )

    # ========================================================================
    # REPL (Read-Eval-Print Loop)
    # ========================================================================

    async def repl(
        self,
        *,
        prompt: str = "agentos> ",
        json_mode: bool = False,
        input_stream=None,
        output_stream=None,
    ) -> None:
        """交互式 REPL 模式 (类比 python -i)。

        Args:
            prompt: 提示符
            json_mode: 是否输出 JSON 格式
            input_stream: 输入流 (默认 stdin)
            output_stream: 输出流 (默认 stdout)
        """
        input_stream = input_stream or sys.stdin
        output_stream = output_stream or sys.stdout
        print("fnixagent OS Shell (输入 help 查看命令, exit 退出)", file=output_stream)
        while True:
            try:
                line = await asyncio.to_thread(input_stream.readline)
            except (EOFError, KeyboardInterrupt):
                print("\nbye", file=output_stream)
                break
            if not line:
                print("\nbye", file=output_stream)
                break
            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit"):
                print("bye", file=output_stream)
                break
            result = await self.execute(line)
            print(result.format(json_mode=json_mode), file=output_stream)


# ============================================================================
# 便捷构造函数
# ============================================================================


def create_shell(
    *,
    skills_dir: str | None = None,
    in_memory: bool = True,
    boot: bool = True,
    _loop=None,
) -> AgentShell:
    """便捷构造 Shell (含 boot)。

    Args:
        skills_dir: Skill 加载目录
        in_memory: 是否使用内存后端 (True = 零依赖, False = 使用真实后端)
        boot: 是否自动启动内核
        _loop: 已有事件循环 (避免嵌套 asyncio.run())

    Returns:
        AgentShell 实例
    """
    if in_memory:
        from fnixagent.core.agent.backends import (
            InMemoryAuditBackend,
            InMemoryLLMBackend,
            InMemoryMemoryBackend,
            InMemoryPolicyBackend,
            InMemoryStorageBackend,
            InMemoryToolBackend,
        )

        kernel = AgentKernel(
            llm_backend=InMemoryLLMBackend(),
            memory_backend=InMemoryMemoryBackend(),
            tool_backend=InMemoryToolBackend(),
            storage_backend=InMemoryStorageBackend(),
            policy_backend=InMemoryPolicyBackend(),
            audit_backend=InMemoryAuditBackend(),
            policy_mode="development",
            enable_scheduler_loop=False,  # REPL 不需要后台调度循环
        )
    else:
        kernel = AgentKernel(enable_scheduler_loop=False)
    shell = AgentShell(kernel=kernel, skills_dir=skills_dir)
    if boot:
        if _loop is not None:
            # 在已有事件循环中，由调用方 await 启动
            pass  # 调用方负责: await kernel.boot()
        else:
            asyncio.run(kernel.boot())
    return shell


__all__ = [
    "AgentShell",
    "ShellResult",
    "Skill",
    "SkillRegistry",
    "create_shell",
]
