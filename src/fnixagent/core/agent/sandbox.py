"""
Sandbox - 沙箱隔离 (Sandbox Isolation)
=======================================
2026 安全共识: 三档沙箱隔离 (Docker → gVisor → Firecracker)。

设计要点:
  - 三档隔离级别: NONE / DOCKER / GVIsOR / FIRECRACKER
  - 可插拔执行器: 每档对应一个 Executor 实现
  - 超时控制: 防止恶意代码无限运行
  - 资源限制: CPU/内存/网络/文件系统
  - 统一接口: execute(command) → result

实现说明:
  - 本模块仅定义接口和内存执行器 (用于测试)
  - Docker/gVisor/Firecracker 执行器需部署对应运行时
  - 生产环境建议 gVisor 或 Firecracker
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from fnixagent.core.agent.types import SandboxLevel, utcnow_iso


@dataclass
class SandboxConfig:
    """沙箱配置 (类比 cgroup limits)。"""

    level: SandboxLevel = SandboxLevel.NONE
    timeout_sec: float = 30.0
    memory_limit_mb: int = 512
    cpu_limit: float = 1.0  # CPU 核数
    network_enabled: bool = False
    filesystem_readonly: bool = True
    env_vars: dict[str, str] = field(default_factory=dict)
    workdir: str = "/tmp/sandbox"
    # Docker 专用
    docker_image: str = "python:3.12-slim"
    # gVisor 专用
    gvisor_runtime: str = "runsc"
    # Firecracker 专用
    firecracker_vm_image: str = ""


@dataclass
class SandboxResult:
    """沙箱执行结果。"""

    success: bool
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = 0.0
    timed_out: bool = False
    error: str | None = None
    executed_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000],  # 截断
            "stderr": self.stderr[:1000],
            "duration_sec": round(self.duration_sec, 3),
            "timed_out": self.timed_out,
            "error": self.error,
            "executed_at": self.executed_at,
        }


@runtime_checkable
class SandboxExecutor(Protocol):
    """沙箱执行器协议。"""

    async def execute(self, command: str, config: SandboxConfig) -> SandboxResult: ...


class InlineExecutor:
    """内联执行器 (无沙箱, 仅开发/测试用)。

    直接在当前进程执行, 使用 asyncio.create_subprocess_exec + 超时控制。
    生产环境务必使用 DockerExecutor / GVisorExecutor / FirecrackerExecutor。
    """

    async def execute(self, command: str, config: SandboxConfig) -> SandboxResult:
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**dict(__import__("os").environ), **config.env_vars},
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=config.timeout_sec
                )
                duration = time.monotonic() - start
                return SandboxResult(
                    success=proc.returncode == 0,
                    exit_code=proc.returncode or 0,
                    stdout=stdout_b.decode("utf-8", errors="replace"),
                    stderr=stderr_b.decode("utf-8", errors="replace"),
                    duration_sec=duration,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    exit_code=-1,
                    stderr=f"超时 ({config.timeout_sec}s)",
                    duration_sec=time.monotonic() - start,
                    timed_out=True,
                )
        except Exception as e:
            return SandboxResult(
                success=False,
                exit_code=-1,
                error=str(e),
                duration_sec=time.monotonic() - start,
            )


class DockerExecutor:
    """Docker 容器执行器 (L1 隔离)。

    使用 docker run 执行命令, 资源限制通过 --memory --cpus 实现。
    需要宿主机安装 Docker。
    """

    def __init__(self, docker_binary: str = "docker"):
        self._docker = docker_binary

    async def execute(self, command: str, config: SandboxConfig) -> SandboxResult:
        start = time.monotonic()
        args = [
            self._docker,
            "run",
            "--rm",
            "--memory",
            f"{config.memory_limit_mb}m",
            "--cpus",
            str(config.cpu_limit),
            "--network",
            "none" if not config.network_enabled else "bridge",
            "--workdir",
            config.workdir,
        ]
        if config.filesystem_readonly:
            args.append("--read-only")
        for k, v in config.env_vars.items():
            args.extend(["-e", f"{k}={v}"])
        args.extend([config.docker_image, "sh", "-c", command])
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=config.timeout_sec
                )
                duration = time.monotonic() - start
                return SandboxResult(
                    success=proc.returncode == 0,
                    exit_code=proc.returncode or 0,
                    stdout=stdout_b.decode("utf-8", errors="replace"),
                    stderr=stderr_b.decode("utf-8", errors="replace"),
                    duration_sec=duration,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    exit_code=-1,
                    stderr=f"超时 ({config.timeout_sec}s)",
                    duration_sec=time.monotonic() - start,
                    timed_out=True,
                )
        except FileNotFoundError:
            return SandboxResult(
                success=False,
                exit_code=-1,
                error="Docker 未安装或不可用",
                duration_sec=time.monotonic() - start,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                exit_code=-1,
                error=str(e),
                duration_sec=time.monotonic() - start,
            )


class GVisorExecutor(DockerExecutor):
    """gVisor 执行器 (L2 隔离, 内核级)。

    继承 DockerExecutor, 仅添加 --runtime=runsc 参数。
    需要宿主机安装 gVisor (runsc) 并注册到 Docker。
    """

    async def execute(self, command: str, config: SandboxConfig) -> SandboxResult:
        config.gvisor_runtime = "runsc"
        # 调用父类但使用 gVisor runtime
        start = time.monotonic()
        args = [
            self._docker,
            "run",
            "--rm",
            "--runtime",
            config.gvisor_runtime,
            "--memory",
            f"{config.memory_limit_mb}m",
            "--cpus",
            str(config.cpu_limit),
            "--network",
            "none" if not config.network_enabled else "bridge",
            "--workdir",
            config.workdir,
        ]
        if config.filesystem_readonly:
            args.append("--read-only")
        for k, v in config.env_vars.items():
            args.extend(["-e", f"{k}={v}"])
        args.extend([config.docker_image, "sh", "-c", command])
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=config.timeout_sec
                )
                duration = time.monotonic() - start
                return SandboxResult(
                    success=proc.returncode == 0,
                    exit_code=proc.returncode or 0,
                    stdout=stdout_b.decode("utf-8", errors="replace"),
                    stderr=stderr_b.decode("utf-8", errors="replace"),
                    duration_sec=duration,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    exit_code=-1,
                    stderr=f"超时 ({config.timeout_sec}s)",
                    duration_sec=time.monotonic() - start,
                    timed_out=True,
                )
        except FileNotFoundError:
            return SandboxResult(
                success=False,
                exit_code=-1,
                error="Docker 或 gVisor (runsc) 未安装",
                duration_sec=time.monotonic() - start,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                exit_code=-1,
                error=str(e),
                duration_sec=time.monotonic() - start,
            )


class FirecrackerExecutor:
    """Firecracker microVM 执行器 (L3 隔离, 最高级别)。

    需要宿主机安装 firecracker 并准备 rootfs 镜像。
    生产环境建议配合 OKA / firecracker-containerd。
    """

    def __init__(self, firecracker_binary: str = "firecracker"):
        self._firecracker = firecracker_binary

    async def execute(self, command: str, config: SandboxConfig) -> SandboxResult:
        # Firecracker 集成较复杂, 需要准备 VM 配置和 rootfs
        # 此处提供接口骨架, 实际部署时需补充 VM 生命周期管理
        return SandboxResult(
            success=False,
            exit_code=-1,
            error="FirecrackerExecutor 需要补充 VM 生命周期管理 (rootfs/kernel/socket)",
        )


class SandboxManager:
    """沙箱管理器 (统一入口)。

    根据 SandboxLevel 选择对应执行器:
      NONE        → InlineExecutor (无沙箱)
      DOCKER      → DockerExecutor (L1)
      GVIsOR      → GVisorExecutor (L2)
      FIRECRACKER → FirecrackerExecutor (L3)

    使用方式:
      mgr = SandboxManager()
      result = await mgr.execute("ls -la", config)
    """

    def __init__(self, default_config: SandboxConfig | None = None):
        self._default_config = default_config or SandboxConfig()
        self._executors: dict[SandboxLevel, SandboxExecutor] = {
            SandboxLevel.NONE: InlineExecutor(),
            SandboxLevel.DOCKER: DockerExecutor(),
            SandboxLevel.GVIsOR: GVisorExecutor(),
            SandboxLevel.FIRECRACKER: FirecrackerExecutor(),
        }
        self._stats = {
            "total_executions": 0,
            "success_count": 0,
            "failure_count": 0,
            "timeout_count": 0,
        }

    def set_executor(self, level: SandboxLevel, executor: SandboxExecutor) -> None:
        """为指定级别设置自定义执行器。"""
        self._executors[level] = executor

    async def execute(self, command: str, config: SandboxConfig | None = None) -> SandboxResult:
        """执行命令。"""
        cfg = config or self._default_config
        executor = self._executors.get(cfg.level)
        if executor is None:
            return SandboxResult(
                success=False,
                exit_code=-1,
                error=f"未注册 {cfg.level.value} 执行器",
            )
        self._stats["total_executions"] += 1
        result = await executor.execute(command, cfg)
        if result.success:
            self._stats["success_count"] += 1
        else:
            self._stats["failure_count"] += 1
        if result.timed_out:
            self._stats["timeout_count"] += 1
        return result

    def get_stats(self) -> dict[str, Any]:
        return dict(self._stats)


__all__ = [
    "DockerExecutor",
    "FirecrackerExecutor",
    "GVisorExecutor",
    "InlineExecutor",
    "SandboxConfig",
    "SandboxExecutor",
    "SandboxManager",
    "SandboxResult",
]
