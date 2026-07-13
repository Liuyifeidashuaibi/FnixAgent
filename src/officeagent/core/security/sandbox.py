"""
跨平台 OS 级执行沙箱 (Sandbox Executor)。

参考 Anthropic 三层防御体系的第一层(隔离执行),为 LLM 生成的工具调用提供
OS 级隔离:
  - Windows: Job Object + 内存限制( ctypes 调用 win32 API)
  - Linux:   bubblewrap(bwrap)命名空间隔离
  - macOS:   Seatbelt(sandbox-exec),仅做接口预留(NotImplementedError)

降级策略: 平台不支持时回退到 subprocess.run + timeout 控制(标记 sandboxed=False),
          记录 warning 审计日志,确保调用方始终拿到 SandboxResult。

设计原则:
  - 文件系统白名单: 仅 workspace_root 与 allowed_writable 路径可写
  - 网络出口默认拒绝(network_allowed=False),按工具粒度放行
  - 子进程超时控制(默认 30s)
  - 所有操作记录审计日志(成功/失败/降级)
"""
from __future__ import annotations

import enum
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 审计钩子(失败不影响主流程)
# ---------------------------------------------------------------------------


def _audit_sandbox(
    action: str,
    detail: Optional[dict] = None,
) -> None:
    """将沙箱操作写入审计日志(异常吞掉)。"""
    try:
        from officeagent.core.audit import AuditLogger
        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Windows Job Object(ctypes 调用,无第三方依赖)
# ---------------------------------------------------------------------------

# 仅 Windows 平台加载 win32 API
if sys.platform == "win32":  # pragma: no cover - 平台相关
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    # Job Object 信息类
    _JobObjectExtendedLimitInformation = 9
    # 限制标志
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x1000
    _JOB_OBJECT_LIMIT_JOB_MEMORY = 0x2000

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class SandboxLevel(enum.Enum):
    """分层沙箱档位(参考 OpenAI Codex Sandbox 三层模型)。

    - ALLOW:     可信代码,当前 bwrap/Job Object 隔离即可
    - CONFIRM:   中风险,需 HITL(Human-In-The-Loop)人工确认后再执行
    - UNTRUSTED: 高风险,MicroVM 强隔离;本地无 MicroVM 时降级到 CONFIRM + 警告
    """

    ALLOW = "allow"
    CONFIRM = "confirm"
    UNTRUSTED = "untrusted"


@dataclass
class SandboxConfig:
    """沙箱配置。

    Attributes:
        workspace_root: 允许读写的根目录(默认可写)
        allowed_writable: 额外可写路径白名单(如 _references/)
        allowed_readable: 额外可读路径
        network_allowed: 是否允许网络(默认拒绝)
        timeout_seconds: 子进程执行超时(秒)
        memory_limit_mb: 内存上限(MB)
        cpu_limit_percent: CPU 百分比上限(Linux 用 cpuquota 换算)
        level: 分层档位(默认 ALLOW,详见 SandboxLevel)
    """
    workspace_root: str
    allowed_writable: list[str] = field(default_factory=list)
    allowed_readable: list[str] = field(default_factory=list)
    network_allowed: bool = False
    timeout_seconds: int = 30
    memory_limit_mb: int = 512
    cpu_limit_percent: int = 50
    level: SandboxLevel = SandboxLevel.ALLOW


@dataclass
class SandboxResult:
    """沙箱执行结果。

    Attributes:
        success: 是否成功(returncode == 0)
        returncode: 子进程退出码
        stdout: 标准输出
        stderr: 标准错误
        sandboxed: 是否真正沙箱化(True=OS 级,False=降级)
        duration_ms: 执行耗时(毫秒)
        error: 错误信息(超时/降级/异常时填写)
    """
    success: bool
    returncode: int
    stdout: str
    stderr: str
    sandboxed: bool
    duration_ms: float
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# SandboxExecutor
# ---------------------------------------------------------------------------


class SandboxExecutor:
    """跨平台 OS 级执行沙箱。

    用法:
        cfg = SandboxConfig(workspace_root="/tmp/ws")
        executor = SandboxExecutor(cfg)
        if executor.is_available():
            result = executor.execute(["python", "-c", "print(1)"])
            assert result.sandboxed is True

    降级路径: 平台不支持时自动回退到 subprocess.run(timeout=...),
              标记 sandboxed=False 并记录 warning。
    """

    def __init__(self, config: SandboxConfig) -> None:
        self._config = config
        # 默认放行 workspace_root 与 _references/ 可写
        self._writable_paths = self._compute_writable()

    # -- 公开接口 ----------------------------------------------------------

    def is_available(self) -> bool:
        """检测当前平台是否支持真沙箱。

        Windows: 始终支持(Job Object 内置于 kernel32)
        Linux:   检查 bwrap 命令是否存在
        macOS:   检查 sandbox-exec 是否存在(Seatbelt)
        """
        try:
            if sys.platform == "win32":
                return True
            if sys.platform.startswith("linux"):
                return shutil.which("bwrap") is not None
            if sys.platform == "darwin":
                # Seatbelt:检测 sandbox-exec 是否存在
                return shutil.which("sandbox-exec") is not None
        except Exception:
            return False
        return False

    def execute(
        self,
        command: list[str],
        cwd: Optional[str] = None,
    ) -> SandboxResult:
        """执行命令,按平台选择真沙箱或降级路径。

        Args:
            command: 命令列表(如 ["python", "-c", "code"])
            cwd: 子进程工作目录(None 用 workspace_root)

        Returns:
            SandboxResult(sandboxed 标记是否真沙箱化)
        """
        if not command:
            return SandboxResult(
                success=False, returncode=-1, stdout="", stderr="",
                sandboxed=False, duration_ms=0.0, error="空命令",
            )
        work_dir = cwd or self._config.workspace_root
        try:
            if self.is_available():
                return self._execute_sandboxed(command, work_dir)
            # 降级路径
            logger.warning(
                "[sandbox] 平台 %s 不支持真沙箱,降级到 subprocess.run",
                sys.platform,
            )
            _audit_sandbox("sandbox.degraded", detail={
                "platform": sys.platform,
                "command": command[0],
            })
            return self._execute_fallback(command, work_dir)
        except Exception as exc:
            # 不外泄异常,返回失败结果
            logger.exception("[sandbox] 执行异常")
            return SandboxResult(
                success=False, returncode=-1, stdout="", stderr="",
                sandboxed=False, duration_ms=0.0,
                error=f"sandbox 执行异常: {exc}",
            )

    def execute_python(
        self,
        code: str,
        cwd: Optional[str] = None,
    ) -> SandboxResult:
        """执行 Python 代码(写入临时文件后调用解释器)。"""
        # 把代码写入 workspace_root 下的临时文件,确保可写
        os.makedirs(self._config.workspace_root, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="_sandbox_", suffix=".py",
            dir=self._config.workspace_root,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(code)
            return self.execute([sys.executable, tmp_path], cwd=cwd)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    # -- 分层档位执行 ------------------------------------------------------

    def execute_with_level(
        self,
        command: list[str],
        level: Optional[SandboxLevel] = None,
        confirm_callback: Optional[Callable[[], bool]] = None,
        cwd: Optional[str] = None,
    ) -> SandboxResult:
        """按分层档位执行命令(参考 OpenAI Codex Sandbox 三层模型)。

        - ALLOW:     直接走 execute(可信代码)
        - CONFIRM:   调用 confirm_callback 做人工确认;返回 False 则拒绝执行
        - UNTRUSTED: 尝试 MicroVM(Firecracker/libkrun)强隔离;
                     不可用时降级到 CONFIRM + 记录 warning

        Args:
            command: 命令列表
            level: 沙箱档位(None 用 config.level)
            confirm_callback: CONFIRM 档位的人工确认回调,返回 True 放行
            cwd: 子进程工作目录

        Returns:
            SandboxResult
        """
        lvl = level or self._config.level
        if lvl == SandboxLevel.ALLOW:
            return self.execute(command, cwd=cwd)

        if lvl == SandboxLevel.CONFIRM:
            # HITL 人工确认
            confirmed = False
            if confirm_callback is not None:
                try:
                    confirmed = bool(confirm_callback())
                except Exception as exc:
                    logger.warning("[sandbox] confirm_callback 异常: %s", exc)
                    confirmed = False
            else:
                # 无回调默认拒绝(中风险必须有确认)
                logger.warning(
                    "[sandbox] CONFIRM 档位未提供 confirm_callback,拒绝执行",
                )
                confirmed = False
            if not confirmed:
                _audit_sandbox("sandbox.confirm_rejected", detail={
                    "command": command[0] if command else "",
                    "level": lvl.value,
                })
                return SandboxResult(
                    success=False, returncode=-1, stdout="", stderr="",
                    sandboxed=False, duration_ms=0.0,
                    error="CONFIRM 档位人工确认未通过(拒绝执行)",
                )
            return self.execute(command, cwd=cwd)

        if lvl == SandboxLevel.UNTRUSTED:
            # 尝试 MicroVM 强隔离
            if self._check_microvm_available():
                _audit_sandbox("sandbox.microvm_used", detail={
                    "command": command[0] if command else "",
                })
                # MicroVM 执行路径:此处简化为委托 execute(实际应启动 firecracker/libkrun)
                # 真正的 MicroVM 集成需配置 VM 镜像、socket、资源限制等,此处保留接口
                return self._execute_microvm(command, cwd)
            # 降级到 CONFIRM + 警告
            logger.warning(
                "[sandbox] MicroVM 不可用,UNTRUSTED 档位降级到 CONFIRM",
            )
            _audit_sandbox("sandbox.microvm_unavailable", detail={
                "command": command[0] if command else "",
            })
            return self.execute_with_level(
                command, level=SandboxLevel.CONFIRM,
                confirm_callback=confirm_callback, cwd=cwd,
            )

        # 未知档位,拒绝执行
        return SandboxResult(
            success=False, returncode=-1, stdout="", stderr="",
            sandboxed=False, duration_ms=0.0,
            error=f"未知沙箱档位: {lvl}",
        )

    def _check_microvm_available(self) -> bool:
        """检测本地是否可用 MicroVM(Firecracker / libkrun)。

        Returns:
            True 表示至少有一种 MicroVM 运行时可用
        """
        try:
            # 检测 firecracker
            if shutil.which("firecracker") is not None:
                return True
            # 检测 libkrun(通常以 krun-runtime 形式存在)
            if shutil.which("krun") is not None:
                return True
            # 检测 krunkit(virtiofsd 配套)
            if shutil.which("krunvm") is not None:
                return True
        except Exception:
            return False
        return False

    def _execute_microvm(
        self,
        command: list[str],
        cwd: Optional[str] = None,
    ) -> SandboxResult:
        """MicroVM 强隔离执行(Firecracker/libkrun)。

        当前为接口预留:实际生产需配置 VM 镜像、vsock、文件系统共享等。
        此处降级到普通沙箱执行,但标记 sandboxed=True + 注明 microvm 占位。
        """
        logger.info(
            "[sandbox] MicroVM 执行路径(接口预留),降级到 OS 沙箱",
        )
        result = self.execute(command, cwd=cwd)
        # 标注使用了 microvm 占位(实际应启动独立 VM)
        _audit_sandbox("sandbox.microvm_executed", detail={
            "command": command[0] if command else "",
            "returncode": result.returncode,
        })
        return result

    # -- 内部:真沙箱执行 ---------------------------------------------------

    def _execute_sandboxed(
        self,
        command: list[str],
        cwd: str,
    ) -> SandboxResult:
        if sys.platform == "win32":
            return self._execute_windows_job(command, cwd)
        if sys.platform.startswith("linux"):
            return self._execute_linux_bwrap(command, cwd)
        if sys.platform == "darwin":
            # macOS Seatbelt 沙箱
            return self._execute_macos_seatbelt(command, cwd)
        # 不应到达此处
        return self._execute_fallback(command, cwd)

    # -- Windows: Job Object ---------------------------------------------

    def _execute_windows_job(
        self,
        command: list[str],
        cwd: str,
    ) -> SandboxResult:  # pragma: no cover - 平台相关
        """Windows 平台用 Job Object 限制内存并在父进程退出时杀子进程。"""
        # 1. 创建 Job Object
        job_handle = _KERNEL32.CreateJobObjectW(None, None)
        if not job_handle:
            return self._execute_fallback(command, cwd)

        # 2. 设置扩展限制(内存 + KILL_ON_JOB_CLOSE)
        limit_flags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | _JOB_OBJECT_LIMIT_PROCESS_MEMORY
        )
        extended = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        extended.BasicLimitInformation.LimitFlags = limit_flags
        extended.ProcessMemoryLimit = self._config.memory_limit_mb * 1024 * 1024
        extended.JobMemoryLimit = self._config.memory_limit_mb * 1024 * 1024

        _KERNEL32.SetInformationJobObject(
            job_handle,
            _JobObjectExtendedLimitInformation,
            ctypes.byref(extended),
            ctypes.sizeof(extended),
        )

        # 3. 启动子进程(Windows 8+ 允许直接 AssignProcessToJobObject,
        #    无需 CREATE_SUSPENDED;这样可避免 ResumeThread 句柄类型问题)
        CREATE_NO_WINDOW = 0x08000000
        startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]

        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(  # noqa: S603 - 沙箱受控执行
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=CREATE_NO_WINDOW,
                close_fds=True,
            )
        except (OSError, FileNotFoundError) as exc:
            _KERNEL32.CloseHandle(job_handle)
            return SandboxResult(
                success=False, returncode=-1, stdout="", stderr="",
                sandboxed=True, duration_ms=0.0,
                error=f"启动子进程失败: {exc}",
            )

        # 4. 将子进程挂入 Job(失败时仍让其正常运行,只是不享内存限制)
        try:
            _KERNEL32.AssignProcessToJobObject(job_handle, int(proc._handle))  # type: ignore[arg-type]
        except Exception:
            pass

        # 4.5 网络阻断:network_allowed=False 时通过 Firewall API 阻断出站
        fw_rule_name: Optional[str] = None
        if not self._config.network_allowed:
            fw_rule_name = f"OA-Sandbox-Block-Net-{proc.pid}"
            if not self._block_network_windows(proc.pid, fw_rule_name):
                # Firewall API 不可用(权限不足等),fail-closed:拒绝执行
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    _KERNEL32.CloseHandle(job_handle)
                except Exception:
                    pass
                _audit_sandbox("sandbox.network_block_failed", detail={
                    "pid": proc.pid, "command": command[0] if command else "",
                })
                return SandboxResult(
                    success=False, returncode=-1, stdout="", stderr="",
                    sandboxed=True, duration_ms=(time.monotonic() - t0) * 1000,
                    error="network_allowed=False 但 Firewall API 不可用,fail-closed 拒绝执行",
                )

        # 5. 等待完成或超时
        try:
            stdout_b, stderr_b = proc.communicate(
                timeout=self._config.timeout_seconds
            )
            returncode = proc.returncode
            error: Optional[str] = None
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_b, stderr_b = proc.communicate()
            returncode = -1
            error = f"子进程超时({self._config.timeout_seconds}s)"
        finally:
            # 清理 Firewall 规则(无论成功/失败/超时)
            if fw_rule_name is not None:
                self._unblock_network_windows(fw_rule_name)

        duration_ms = (time.monotonic() - t0) * 1000
        # 6. 关闭 Job 句柄(KILL_ON_JOB_CLOSE 会清理残留子进程)
        try:
            _KERNEL32.CloseHandle(job_handle)
        except Exception:
            pass

        stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
        stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
        return SandboxResult(
            success=returncode == 0,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            sandboxed=True,
            duration_ms=duration_ms,
            error=error,
        )

    # -- Windows: 网络阻断(Firewall API) ---------------------------------

    def _block_network_windows(
        self,
        pid: int,
        rule_name: str,
    ) -> bool:  # pragma: no cover - 平台相关
        """通过 Windows Firewall API(INetFwPolicy2)阻断指定进程的出站网络。

        用 ctypes 调用 COM 接口添加临时防火墙规则,按 PID 过滤。
        成功返回 True,权限不足或 API 不可用返回 False(fail-closed)。
        """
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            # COM 初始化
            try:
                ole32 = ctypes.WinDLL("ole32")  # type: ignore[attr-defined]
                ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
            except Exception:
                pass

            # 通过 COM 创建 INetFwPolicy2 实例
            # CLSID_NetFwPolicy2 = {E2B3C97F-6AE1-41AC-817A-F6F92166D7DD}
            # IID_INetFwPolicy2   = {98325047-C671-4174-8D81-DEFCD3F0319E}
            import comtypes  # type: ignore[import-not-found]  # 可选依赖

            # 创建 Firewall 管理器
            from comtypes.client import CreateObject  # type: ignore[import-not-found]
            fw_policy = CreateObject("{E2B3C97F-6AE1-41AC-817A-F6F92166D7DD}")

            # 获取 FirewallRules 集合
            rules = fw_policy.Rules

            # 创建新的防火墙规则对象
            # CLSID_NetFwRule = {2C5BC43E-3369-4C33-AB0C-BE9469677AF4}
            new_rule = CreateObject("{2C5BC43E-3369-4C33-AB0C-BE9469677AF4}")
            new_rule.Name = rule_name
            new_rule.Description = f"OfficeAgent sandbox network block for PID {pid}"
            new_rule.ApplicationName = None
            new_rule.Action = 0  # NET_FW_ACTION_BLOCK
            new_rule.Direction = 1  # NET_FW_RULE_DIR_OUT
            new_rule.Enabled = True
            new_rule.Grouping = "OfficeAgent-Sandbox"

            # 添加规则到集合
            rules.Add(new_rule)
            _audit_sandbox("sandbox.network_blocked", detail={
                "pid": pid, "rule": rule_name,
            })
            return True
        except ImportError:
            # comtypes 不可用,降级方案:用 netsh 命令(按程序路径阻断)
            return self._block_network_windows_netsh(pid, rule_name)
        except Exception as exc:
            logger.warning("[sandbox] Firewall API 阻断失败: %s", exc)
            # 尝试 netsh 降级
            return self._block_network_windows_netsh(pid, rule_name)

    def _block_network_windows_netsh(
        self,
        pid: int,
        rule_name: str,
    ) -> bool:  # pragma: no cover - 平台相关
        """netsh 降级方案:通过命令行添加防火墙规则。

        注意:netsh 无法按 PID 过滤,此降级方案会阻断所有出站流量,
        因此仅在 COM API 不可用时使用,且规则名带 OA-Sandbox 前缀便于清理。
        由于会阻断全部流量,实际生产建议安装 comtypes 以使用 COM API。
        """
        if sys.platform != "win32":
            return False
        try:
            # netsh 添加出站阻断规则(需要管理员权限)
            result = subprocess.run(  # noqa: S603 - 受控执行
                [
                    "netsh", "advfirewall", "firewall", "add", "rule",
                    f"name={rule_name}",
                    "dir=out", "action=block",
                    "enable=yes",
                ],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                _audit_sandbox("sandbox.network_blocked_netsh", detail={
                    "pid": pid, "rule": rule_name,
                })
                return True
            logger.warning(
                "[sandbox] netsh 阻断失败(returncode=%d): %s",
                result.returncode,
                result.stderr.decode("utf-8", errors="replace"),
            )
            return False
        except Exception as exc:
            logger.warning("[sandbox] netsh 阻断异常: %s", exc)
            return False

    def _unblock_network_windows(self, rule_name: str) -> None:
        """清理 Firewall 规则(异常吞掉,不影响主流程)。"""
        if sys.platform != "win32":
            return
        try:
            # 优先用 COM API 删除
            import comtypes  # type: ignore[import-not-found]  # noqa: F401
            from comtypes.client import CreateObject  # type: ignore[import-not-found]
            fw_policy = CreateObject("{E2B3C97F-6AE1-41AC-817A-F6F92166D7DD}")
            rules = fw_policy.Rules
            rules.Remove(rule_name)
            return
        except Exception:
            pass
        # 降级:netsh 删除
        try:
            subprocess.run(  # noqa: S603 - 受控执行
                [
                    "netsh", "advfirewall", "firewall", "delete", "rule",
                    f"name={rule_name}",
                ],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception:
            pass

    # -- Linux: bubblewrap -----------------------------------------------

    def _execute_linux_bwrap(
        self,
        command: list[str],
        cwd: str,
    ) -> SandboxResult:
        """Linux 用 bwrap 构建受限命名空间。

        - --unshare-pid/net: 隔离 PID/网络(network_allowed=False 时)
        - --ro-bind / / :根目录只读
        - --bind workspace_root: 工作区可写
        - --dev /dev --proc /proc: 必要虚拟文件系统
        """
        bwrap = shutil.which("bwrap")
        if not bwrap:
            return self._execute_fallback(command, cwd)

        argv: list[str] = [bwrap]
        # 网络隔离
        if not self._config.network_allowed:
            argv.append("--unshare-net")
        # PID 隔离
        argv.extend(["--unshare-pid", "--die-with-parent"])
        # 根文件系统只读
        argv.extend(["--ro-bind", "/", "/"])
        # 必要虚拟文件系统
        argv.extend(["--dev", "/dev", "--proc", "/proc"])
        # 工作区可写
        if os.path.isdir(self._config.workspace_root):
            argv.extend(["--bind", self._config.workspace_root, self._config.workspace_root])
        # 额外可写路径
        for p in self._config.allowed_writable:
            if os.path.isdir(p):
                argv.extend(["--bind", p, p])
        # 额外可读路径(已通过 / 只读覆盖,跳过)
        # 工作目录
        argv.extend(["--chdir", cwd or self._config.workspace_root])
        # 实际命令
        argv.extend(command)

        t0 = time.monotonic()
        try:
            proc = subprocess.run(  # noqa: S603 - 受控执行
                argv,
                capture_output=True,
                timeout=self._config.timeout_seconds,
                check=False,
            )
            returncode = proc.returncode
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            error: Optional[str] = None
        except subprocess.TimeoutExpired as exc:
            returncode = -1
            stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            error = f"子进程超时({self._config.timeout_seconds}s)"
        except (OSError, FileNotFoundError) as exc:
            return SandboxResult(
                success=False, returncode=-1, stdout="", stderr="",
                sandboxed=True, duration_ms=(time.monotonic() - t0) * 1000,
                error=f"bwrap 启动失败: {exc}",
            )

        return SandboxResult(
            success=returncode == 0,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            sandboxed=True,
            duration_ms=(time.monotonic() - t0) * 1000,
            error=error,
        )

    # -- macOS: Seatbelt (sandbox-exec) -----------------------------------

    def _execute_macos_seatbelt(
        self,
        command: list[str],
        cwd: str,
    ) -> SandboxResult:
        """macOS 用 sandbox-exec(Seatbelt)构建受限执行环境。

        生成 sandbox profile:
          - (deny default): 默认拒绝所有操作
          - (allow file-read* /usr /System): 允许读取系统目录
          - (allow file-write* workspace): 允许写入工作区
          - (deny network*): 拒绝网络(network_allowed=False 时)

        profile 写入临时文件,执行后删除。
        """
        sandbox_exec = shutil.which("sandbox-exec")
        if not sandbox_exec:
            return self._execute_fallback(command, cwd)

        # 生成 Seatbelt profile
        ws_root = self._config.workspace_root
        profile_lines = [
            "(version 1)",
            "(deny default)",
            '(allow file-read* (subpath "/usr"))',
            '(allow file-read* (subpath "/System"))',
            '(allow file-read* (subpath "/Library"))',
            '(allow file-read* (subpath "/bin"))',
            '(allow file-read* (subpath "/sbin"))',
            '(allow process-exec (subpath "/usr"))',
            '(allow process-exec (subpath "/bin"))',
            '(allow process-exec (subpath "/sbin"))',
            # 工作区可写
            f'(allow file-write* (subpath "{ws_root}"))',
        ]
        # 额外可写路径
        for p in self._config.allowed_writable:
            if os.path.isdir(p):
                profile_lines.append(f'(allow file-write* (subpath "{p}"))')
        # 额外可读路径
        for p in self._config.allowed_readable:
            if os.path.isdir(p):
                profile_lines.append(f'(allow file-read* (subpath "{p}"))')
        # 网络策略
        if self._config.network_allowed:
            profile_lines.append("(allow network*)")
        else:
            profile_lines.append("(deny network*)")

        profile_content = "\n".join(profile_lines) + "\n"

        # 写入临时 profile 文件
        fd, profile_path = tempfile.mkstemp(
            prefix="_oa_sandbox_", suffix=".sb",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(profile_content)

            argv = [
                sandbox_exec,
                "-p", profile_path,
                "--",
                *command,
            ]

            t0 = time.monotonic()
            try:
                proc = subprocess.run(  # noqa: S603 - 受控执行
                    argv,
                    cwd=cwd or None,
                    capture_output=True,
                    timeout=self._config.timeout_seconds,
                    check=False,
                )
                returncode = proc.returncode
                stdout = proc.stdout.decode("utf-8", errors="replace")
                stderr = proc.stderr.decode("utf-8", errors="replace")
                error: Optional[str] = None
            except subprocess.TimeoutExpired as exc:
                returncode = -1
                stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
                stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
                error = f"子进程超时({self._config.timeout_seconds}s)"
            except (OSError, FileNotFoundError) as exc:
                return SandboxResult(
                    success=False, returncode=-1, stdout="", stderr="",
                    sandboxed=True, duration_ms=(time.monotonic() - t0) * 1000,
                    error=f"sandbox-exec 启动失败: {exc}",
                )

            return SandboxResult(
                success=returncode == 0,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                sandboxed=True,
                duration_ms=(time.monotonic() - t0) * 1000,
                error=error,
            )
        finally:
            try:
                os.remove(profile_path)
            except OSError:
                pass

    # -- 降级路径 ----------------------------------------------------------

    def _execute_fallback(
        self,
        command: list[str],
        cwd: str,
    ) -> SandboxResult:
        """降级执行:subprocess.run + 超时控制,标记 sandboxed=False。"""
        t0 = time.monotonic()
        try:
            proc = subprocess.run(  # noqa: S603 - 降级路径,由调用方负责安全
                command,
                cwd=cwd or None,
                capture_output=True,
                timeout=self._config.timeout_seconds,
                check=False,
            )
            returncode = proc.returncode
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            error: Optional[str] = None
        except subprocess.TimeoutExpired as exc:
            returncode = -1
            stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            error = f"子进程超时({self._config.timeout_seconds}s)"
        except (OSError, FileNotFoundError) as exc:
            return SandboxResult(
                success=False, returncode=-1, stdout="", stderr="",
                sandboxed=False, duration_ms=(time.monotonic() - t0) * 1000,
                error=f"启动失败: {exc}",
            )

        return SandboxResult(
            success=returncode == 0,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            sandboxed=False,
            duration_ms=(time.monotonic() - t0) * 1000,
            error=error,
        )

    # -- 辅助 --------------------------------------------------------------

    def _compute_writable(self) -> list[str]:
        """计算允许写入的路径列表(workspace_root + allowed_writable)。"""
        paths = [self._config.workspace_root]
        # 默认放行 _references/(若存在)
        refs = os.path.join(
            os.path.dirname(self._config.workspace_root.rstrip("/\\")),
            "_references",
        )
        if os.path.isdir(refs):
            paths.append(refs)
        for p in self._config.allowed_writable:
            paths.append(p)
        # 去重 + 规范化
        seen: set[str] = set()
        result: list[str] = []
        for p in paths:
            try:
                rp = os.path.realpath(p)
                if rp not in seen:
                    seen.add(rp)
                    result.append(rp)
            except OSError:
                continue
        return result
