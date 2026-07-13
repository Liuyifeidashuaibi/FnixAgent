"""
代码执行沙箱 (Code Sandbox)。

在受限环境中执行动态代码,防止恶意操作:
  1. 受限 globals: 移除危险内置函数(open/exec/eval/compile/__import__等)
  2. 超时强制: 主线程 join(timeout) 后标记超时,daemon 线程随进程退出
  3. 内存监控: tracemalloc 跟踪内存,超限终止
  4. stdout/stderr 捕获: contextlib.redirect_stdout/stderr
  5. 异常隔离: 子线程崩溃不影响主进程(try/except 兜底)

原理(参考 RestrictedPython 设计理念):
  Python 的 exec() 本身不提供沙箱,但可以通过限制 globals 中的
  __builtins__ 来移除危险函数,配合超时和内存监控实现"足够安全"的隔离。

注意: 纯 Python 沙箱无法做到 100% 安全(存在逃逸路径),
生产环境应配合 Docker/gVisor 容器隔离使用。
"""
from __future__ import annotations

import io
import time
import tracemalloc
import threading
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from typing import Any, Optional

from fnixagent.core.config import ToolConfig
from fnixagent.core.exceptions import ToolSandboxError
from fnixagent.core.tools.sandbox.policy import SandboxPolicy


@dataclass
class SandboxResult:
    """沙箱执行结果。

    Attributes:
        success: 是否成功执行
        output: 代码中 ``result`` 变量的值(约定)
        error: 错误信息(失败/超时/内存超限时填写)
        stdout: 捕获的标准输出
        stderr: 捕获的标准错误
        duration_ms: 执行耗时(毫秒)
        violations: 静态检查命中的违规列表
        timed_out: 是否超时
        memory_exceeded: 是否内存超限
    """
    success: bool
    output: Any = None
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    violations: list[str] = field(default_factory=list)
    timed_out: bool = False
    memory_exceeded: bool = False


class CodeSandbox:
    """受限代码执行沙箱。

    用法:
        sandbox = CodeSandbox(policy=SandboxPolicy(), config=tool_config)
        result = sandbox.execute("result = 1 + 2", env={"x": 10})
        print(result.output)  # 3

    安全措施:
        - 内置函数白名单(移除 open/exec/eval/__import__ 等)
        - 静态代码检查(危险模块/命令/写入操作)
        - 超时限制(join timeout,daemon 线程不阻塞主进程退出)
        - 内存限制(tracemalloc 峰值监控)
    """

    # 安全的内置函数白名单
    _SAFE_BUILTINS = {
        # 数学
        "abs": abs, "min": min, "max": max, "sum": sum, "round": round,
        "pow": pow, "divmod": divmod,
        # 类型
        "int": int, "float": float, "str": str, "bool": bool,
        "list": list, "dict": dict, "tuple": tuple, "set": set,
        "frozenset": frozenset, "bytes": bytes, "bytearray": bytearray,
        "complex": complex,
        # 序列
        "len": len, "range": range, "enumerate": enumerate, "zip": zip,
        "sorted": sorted, "reversed": reversed, "filter": filter, "map": map,
        "any": any, "all": all,
        # 类型检查
        "isinstance": isinstance, "issubclass": issubclass,
        "type": type, "id": id, "hash": hash,
        # 字符串格式化
        "format": format, "repr": repr, "chr": chr, "ord": ord,
        "hex": hex, "oct": oct, "bin": bin, "ascii": ascii,
        # 迭代器
        "iter": iter, "next": next,
        # 排序
        "slice": slice,
        # 数学函数(通过 math 模块)
        "print": print,  # 会被 redirect_stdout 捕获
    }

    # 需要从 builtins 移除的危险函数(双重保险,即便白名单已排除)
    _DANGEROUS_BUILTINS = (
        "open", "exec", "eval", "compile", "__import__",
        "globals", "locals", "vars", "dir", "input",
        "breakpoint", "exit", "quit", "help", "copyright",
    )

    def __init__(
        self,
        policy: Optional[SandboxPolicy] = None,
        config: Optional[ToolConfig] = None,
    ) -> None:
        self._policy = policy or SandboxPolicy()
        self._config = config or ToolConfig()

    def execute(
        self,
        code: str,
        env: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> SandboxResult:
        """在受限环境中执行代码。

        流程:
          1. 静态安全检查(policy.check_code)
          2. 构建受限 globals(安全 builtins + 用户 env)
          3. 启动 tracemalloc 内存监控(主线程管理,确保超时后能停止)
          4. daemon 线程执行 exec,主线程 join(timeout) 控制超时
          5. redirect_stdout/stderr 捕获输出
          6. 检查内存峰值,超限标记失败

        Args:
            code: 要执行的 Python 代码字符串
            env: 注入沙箱的全局变量(可选)
            timeout: 超时秒数(None 用 config.sandbox_max_cpu_seconds)

        Returns:
            SandboxResult:含 success/output/error/stdout/stderr/violations
        """
        # 1. 静态检查
        allowed, violations = self._policy.check_code(code)
        if not allowed:
            return SandboxResult(
                success=False,
                error="代码安全检查未通过",
                violations=violations,
            )

        # 2. 构建受限 globals
        safe_builtins = dict(self._SAFE_BUILTINS)
        # 移除危险内置(双重保险)
        for dangerous in self._DANGEROUS_BUILTINS:
            safe_builtins.pop(dangerous, None)

        sandbox_globals: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "__name__": "__sandbox__",
        }
        if env:
            sandbox_globals.update(env)

        # 3. 准备输出捕获
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # 4. 超时和内存控制
        timeout_sec = timeout or self._config.sandbox_max_cpu_seconds
        max_mem = self._config.sandbox_max_memory_mb * 1024 * 1024  # bytes

        result = SandboxResult(success=False)
        memory_exceeded = False
        peak_mem = 0

        # 用 daemon 线程执行,主线程通过 join(timeout) 控制超时
        # daemon=True 确保超时后线程不会阻止主进程退出(避免僵尸线程)
        def _run() -> None:
            nonlocal result
            try:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(code, sandbox_globals)  # noqa: S102 — 沙箱核心,已做静态检查
                # 成功:尝试获取 result 变量(约定: 代码最后赋值给 result)
                result.success = True
                result.output = sandbox_globals.get("result")
            except Exception as exc:
                # 子线程异常隔离:不影响主进程
                result.error = f"{type(exc).__name__}: {exc}"
            except BaseException as exc:  # SystemExit/KeyboardInterrupt 等
                result.error = f"{type(exc).__name__}: {exc}"

        # tracemalloc 在主线程启停,确保超时后也能正确释放
        tracemalloc.start()
        thread = threading.Thread(target=_run, daemon=True)
        t0 = time.monotonic()
        thread.start()
        thread.join(timeout=timeout_sec)

        # 获取内存峰值(无论线程是否完成)
        try:
            _current, peak_mem = tracemalloc.get_traced_memory()
        except Exception:
            peak_mem = 0
        finally:
            tracemalloc.stop()

        if thread.is_alive():
            # 线程仍在运行 = 超时(daemon 线程无法强制 kill,但随主进程退出)
            result.timed_out = True
            result.error = f"执行超时 ({timeout_sec}s)"
            result.success = False
        elif peak_mem > max_mem:
            # 内存超限检查
            memory_exceeded = True
            result.memory_exceeded = True
            result.error = (
                f"内存超限: {peak_mem / 1024 / 1024:.1f}MB > "
                f"{max_mem / 1024 / 1024:.0f}MB"
            )
            result.success = False

        result.duration_ms = (time.monotonic() - t0) * 1000
        result.stdout = stdout_buf.getvalue()
        result.stderr = stderr_buf.getvalue()
        result.violations = violations

        return result
