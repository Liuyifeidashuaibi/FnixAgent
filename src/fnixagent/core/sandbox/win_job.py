"""
Windows Job Object 软沙箱。

通过 kernel32 的 Job Object API 把子进程及其全部后代纳入一个可统一管控的
"作业对象"(Job Object), 为 run_command 等子进程执行点提供进程树级软隔离:
  1. 进程树兜底击杀: KILL_ON_JOB_CLOSE(句柄关闭时杀整树) + TerminateJobObject
  2. 内存上限: JobMemoryLimit(Job 内全部进程的提交内存总和上限)
  3. 进程数上限: ActiveProcessLimit(Job 内并发活动进程数上限)
  4. 异常即死: DIE_ON_UNHANDLED_EXCEPTION(未处理 SEH 异常直接终止)

设计原则:
  - 纯 ctypes 封装 kernel32, 零第三方依赖
  - 软沙箱(fail-open): 任何一步失败只记 warning 不抛异常, 绝不阻塞调用方
  - 非 Windows 平台整体 no-op(is_windows 为 False 时所有方法安全返回)
  - 实例不共享、不落全局: 每次 spawn 一个 per-call Job, 天然并发安全

注意:
  - 这是"软"沙箱: 只约束进程树生命周期与资源上限, 不做文件系统/注册表/
    网络 ACL 隔离; 强隔离需求应配合容器方案使用。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import ctypes
import logging
import os

_logger = logging.getLogger(__name__)

# 平台探测: 非 Windows 平台整个模块为 no-op
is_windows = os.name == "nt"

# ===== Job Object 限制标志 (winnt.h) =====
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# SetInformationJobObject 的信息类别: JOBOBJECT_EXTENDED_LIMIT_INFORMATION
_JOB_OBJECT_EXTENDED_LIMIT_INFO_CLASS = 9

# OpenProcess 所需权限: 设置配额(内存限制) + 终止
_PROCESS_SET_QUOTA = 0x00000100
_PROCESS_TERMINATE = 0x00000001


# ===== ctypes 结构体定义 (与 winnt.h 声明一一对应) =====


class _IO_COUNTERS(ctypes.Structure):
    """进程/Job 的 IO 计数器 (占位字段, EXTENDED 结构布局所需)。"""

    _pack_ = 8  # x64 对齐: 最大字段对齐宽度为 8 字节

    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    """Job 基础限制信息 (x64 下 sizeof == 64)。"""

    _pack_ = 8  # x64 对齐

    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),  # LARGE_INTEGER
        ("PerJobUserTimeLimit", ctypes.c_longlong),  # LARGE_INTEGER
        ("LimitFlags", ctypes.c_uint32),  # DWORD
        ("MinimumWorkingSetSize", ctypes.c_size_t),  # SIZE_T
        ("MaximumWorkingSetSize", ctypes.c_size_t),  # SIZE_T
        ("ActiveProcessLimit", ctypes.c_uint32),  # DWORD
        ("Affinity", ctypes.c_size_t),  # ULONG_PTR
        ("PriorityClass", ctypes.c_uint32),  # DWORD
        ("SchedulingClass", ctypes.c_uint32),  # DWORD
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    """Job 扩展限制信息 (x64 下 sizeof == 144, 含内存上限字段)。"""

    _pack_ = 8  # x64 对齐

    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),  # SIZE_T
        ("JobMemoryLimit", ctypes.c_size_t),  # SIZE_T
        ("PeakProcessMemoryUsed", ctypes.c_size_t),  # SIZE_T
        ("PeakJobMemoryUsed", ctypes.c_size_t),  # SIZE_T
    ]


# ===== kernel32 动态绑定 (仅 Windows; use_last_error 保证 GetLastError 可读) =====

if is_windows:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    _kernel32.CreateJobObjectW.restype = ctypes.c_void_p  # HANDLE 用指针宽度, 避免 x64 截断
    _kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    _kernel32.SetInformationJobObject.restype = ctypes.c_int  # BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _kernel32.AssignProcessToJobObject.restype = ctypes.c_int  # BOOL
    _kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _kernel32.TerminateJobObject.restype = ctypes.c_int  # BOOL
    _kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    _kernel32.OpenProcess.restype = ctypes.c_void_p
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    _kernel32.CloseHandle.restype = ctypes.c_int  # BOOL
else:
    _kernel32 = None  # 非 Windows: 保持可导入, 所有调用点先检查 is_windows


class WinJobObject:
    """Windows Job Object 软沙箱封装。

    典型用法 (per-call 局部实例, 不要跨协程共享):

        job = WinJobObject()
        if job.create():
            job.assign_pid(process.pid)   # 失败 fail-open, 只返回 False
            try:
                ...等待子进程...
            finally:
                job.close()               # KILL_ON_JOB_CLOSE 兜底杀残留树

    或用 with 语法(退出时自动 kill + close 双重兜底):

        with WinJobObject() as job:
            job.assign_pid(pid)
            ...
    """

    def __init__(self, name: str | None = None) -> None:
        self._name = name
        self._handle: int | None = None  # kernel32 HANDLE (c_void_p 还原后的 int)
        self._limit_flags = 0  # 当前生效的 LimitFlags 合集
        self._limit_values: dict[str, int] = {}  # 与 flags 关联的字段值(重写时需完整携带)

    # ------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def created(self) -> bool:
        """Job Object 是否已创建且句柄有效。"""
        return is_windows and self._handle is not None and self._handle != 0

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<WinJobObject name={self._name!r} handle={self._handle} created={self.created}>"

    # ------------------------------------------------------------
    # 核心方法
    # ------------------------------------------------------------

    def create(self, name: str | None = None) -> bool:
        """创建 Job Object 并施加默认软限制。

        默认限制: KILL_ON_JOB_CLOSE(句柄关闭杀整树) +
        DIE_ON_UNHANDLED_EXCEPTION(未处理异常即死)。
        默认限制设置失败不影响创建结果(尽力而为)。

        Args:
            name: 可选的内核对象名; None 表示匿名 Job(推荐, 无命名冲突风险)

        Returns:
            是否创建成功 (非 Windows 平台恒为 False)
        """
        if not is_windows:
            return False
        if name is not None:
            self._name = name
        if self.created:
            return True
        assert _kernel32 is not None  # is_windows 已保证
        try:
            handle = _kernel32.CreateJobObjectW(None, self._name)
            if not handle:
                _logger.warning(
                    "CreateJobObjectW 失败 (err=%s), 沙箱降级为无 Job 运行",
                    ctypes.get_last_error(),
                )
                return False
            self._handle = int(handle)
            self._limit_flags = (
                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
            )
            if not self._apply_extended_limit(0):
                # 默认限制没写进去也不回滚: 软沙箱尽力而为, 句柄仍可用于 kill/close
                _logger.warning("Job Object 默认限制(KILL_ON_JOB_CLOSE 等)设置失败")
            return True
        except Exception as exc:  # fail-open: 绝不让沙箱故障阻塞业务
            _logger.warning("创建 Job Object 失败(fail-open): %s", exc)
            self._handle = None
            return False

    def assign_pid(self, pid: int) -> bool:
        """把指定 pid 的进程(连同其已有/未来的全部子进程)加入本 Job。

        fail-open 契约: 任何失败(进程已退出/权限不足等)只记 warning 并返回
        False, 不抛异常, 不影响调用方继续执行命令。

        Args:
            pid: 目标进程 ID

        Returns:
            是否分配成功 (非 Windows / 未 create / API 失败均为 False)
        """
        if not is_windows or not self.created:
            return False
        proc_handle: int | None = None
        try:
            assert _kernel32 is not None
            proc_handle = _kernel32.OpenProcess(
                _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, int(pid)
            )
            if not proc_handle:
                _logger.warning(
                    "OpenProcess(pid=%s) 失败 (err=%s), 子进程未被纳入沙箱",
                    pid,
                    ctypes.get_last_error(),
                )
                return False
            ok = bool(_kernel32.AssignProcessToJobObject(self._handle, proc_handle))
            if not ok:
                _logger.warning(
                    "AssignProcessToJobObject(pid=%s) 失败 (err=%s)",
                    pid,
                    ctypes.get_last_error(),
                )
            return ok
        except Exception as exc:  # fail-open
            _logger.warning("assign_pid(%s) 失败(fail-open): %s", pid, exc)
            return False
        finally:
            # 进程句柄用完即关, 防泄漏 (失败也静默, 不影响主流程)
            if proc_handle:
                try:
                    assert _kernel32 is not None
                    _kernel32.CloseHandle(proc_handle)
                except Exception:  # noqa: S110 - 关闭失败无需处理
                    pass

    def set_memory_limit_mb(self, mb: float) -> bool:
        """设置 Job 内全部进程的提交内存总和上限 (JobMemoryLimit, 字节=mb*1MB)。

        Args:
            mb: 上限(MB), 必须 > 0

        Returns:
            是否设置成功
        """
        if mb is None or mb <= 0:
            _logger.warning("set_memory_limit_mb 收到非法值 %r, 忽略", mb)
            return False
        limit_bytes = int(mb * 1024 * 1024)
        return self._apply_extended_limit(JOB_OBJECT_LIMIT_JOB_MEMORY, JobMemoryLimit=limit_bytes)

    def set_process_limit(self, n: int) -> bool:
        """设置 Job 内并发活动进程数上限 (ActiveProcessLimit)。

        Args:
            n: 进程数上限, 必须 >= 1

        Returns:
            是否设置成功
        """
        if n is None or n < 1:
            _logger.warning("set_process_limit 收到非法值 %r, 忽略", n)
            return False
        return self._apply_extended_limit(
            JOB_OBJECT_LIMIT_ACTIVE_PROCESS, ActiveProcessLimit=int(n)
        )

    def kill(self) -> bool:
        """终结 Job 内整棵进程树 (TerminateJobObject, 含孙子进程)。

        Returns:
            是否成功发起终止 (Job 未创建时返回 False)
        """
        if not is_windows or not self.created:
            return False
        try:
            assert _kernel32 is not None
            ok = bool(_kernel32.TerminateJobObject(self._handle, 1))  # 退出码 1
            if not ok:
                _logger.warning("TerminateJobObject 失败 (err=%s)", ctypes.get_last_error())
            return ok
        except Exception as exc:  # fail-open
            _logger.warning("kill Job Object 失败(fail-open): %s", exc)
            return False

    def close(self) -> None:
        """关闭 Job 句柄 (幂等, 未创建时安全)。

        若启用了 KILL_ON_JOB_CLOSE 且 Job 内仍有存活进程, 本次 close 会作为
        最后一道兜底把整棵进程树带走。
        """
        handle, self._handle = self._handle, None
        if not is_windows or not handle:
            return
        self._limit_flags = 0
        self._limit_values = {}
        try:
            assert _kernel32 is not None
            if not _kernel32.CloseHandle(handle):
                _logger.warning("CloseHandle(job) 失败 (err=%s)", ctypes.get_last_error())
        except Exception as exc:  # fail-open
            _logger.warning("close Job Object 失败(fail-open): %s", exc)

    # ------------------------------------------------------------
    # with 语法支持: 退出时 kill + close 双重兜底
    # ------------------------------------------------------------

    def __enter__(self) -> WinJobObject:
        if is_windows and not self.created:
            self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            # 先显式终结残留进程树(空 Job 上是廉价 no-op), 再关句柄兜底
            self.kill()
        finally:
            self.close()
        return False  # 不吞异常

    # ------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------

    def _apply_extended_limit(self, extra_flag: int, **field_values: int) -> bool:
        """写入 JOBOBJECT_EXTENDED_LIMIT_INFORMATION。

        注意两点(均为整体覆盖式语义):
          1. 必须合并历史 LimitFlags 与字段值一起重写, 否则后设置的限制会
             抹掉先前的(例如 set_process_limit 抹掉内存上限);
          2. 实测内核怪癖: 写入带 JOB_OBJECT_LIMIT_JOB_MEMORY 标志的组合时,
             若结构体里 JobMemoryLimit 字段为 0(未随写携带), 会返回
             ERROR_INVALID_PARAMETER。因此本类始终记忆已生效的字段值,
             每次以「完整 flags + 完整 values」一次性提交。
        """
        if not is_windows or not self.created:
            return False
        try:
            assert _kernel32 is not None
            merged_flags = self._limit_flags | extra_flag
            merged_values = dict(self._limit_values)
            merged_values.update(field_values)
            if not self._write_extended_info(merged_flags, merged_values):
                _logger.warning(
                    "SetInformationJobObject 失败 (err=%s, flags=0x%x)",
                    ctypes.get_last_error(),
                    merged_flags,
                )
                return False
            # 仅在成功时更新本地状态, 保证与内核侧一致
            self._limit_flags = merged_flags
            self._limit_values = merged_values
            return True
        except Exception as exc:  # fail-open
            _logger.warning("设置 Job Object 限制失败(fail-open): %s", exc)
            return False

    def _write_extended_info(self, flags: int, field_values: dict[str, int]) -> bool:
        """单次 SetInformationJobObject 写入; 返回是否成功。"""
        assert _kernel32 is not None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = flags
        for field_name, value in field_values.items():
            setattr(info, field_name, value)
        return bool(
            _kernel32.SetInformationJobObject(
                self._handle,
                _JOB_OBJECT_EXTENDED_LIMIT_INFO_CLASS,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
        )
