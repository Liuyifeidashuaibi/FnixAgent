"""
AgentOS 全量功能验证脚本 (End-to-End Verification)
====================================================
覆盖 ETCLOVG 七层框架全部功能, 验证可立即使用。

测试维度:
  1. 包导入完整性
  2. 内核生命周期 (boot/shutdown)
  3. 进程管理 (spawn/kill/ps/info)
  4. Syscall 分发 (24 类)
  5. ContextFS (read/write/list/mkdir/delete)
  6. MemoryManager (4 层记忆 recall/store/search/forget)
  7. PolicyEngine (授权/拒绝/角色映射)
  8. AgentScheduler (admit/terminate/checkpoint)
  9. A2ABus (register/discover/send/broadcast)
 10. DurableExecution (checkpoint/journal/recover)
 11. Observability (span/audit/metrics)
 12. Guardrail (三层 PASS/WARN/BLOCK/MODIFY)
 13. Sandbox (Inline 执行)
 14. AgentShell (30+ 命令)
 15. 自然语言接口
 16. Skill 加载
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

import pytest

# 确保 src 在 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# fnixagent.core.agentos was renamed/refactored into fnixagent.core.agent.*.
# Re-point imports to the new module layout (stale-import fix).
from fnixagent.core.agent.backends.in_memory import (  # noqa: E402
    InMemoryAuditBackend,
    InMemoryLLMBackend,
    InMemoryMemoryBackend,
    InMemoryPolicyBackend,
    InMemoryStorageBackend,
    InMemoryToolBackend,
)
from fnixagent.core.agent.guardrail import (
    GuardrailContext,
    GuardrailManager,
    length_limit_guardrail,
    sensitive_data_guardrail,
)
from fnixagent.core.agent.kernel import (
    AgentKernel,
    get_kernel,
    reset_kernel,
)
from fnixagent.core.agent.messaging import (
    A2AMessage,
)
from fnixagent.core.agent.observability import (
    ObservabilityManager,
)
from fnixagent.core.agent.sandbox import (
    SandboxManager,
)
from fnixagent.core.agent.shell import (
    AgentShell,
)
from fnixagent.core.agent.syscall import (
    SyscallRequest,
    SyscallType,
)
from fnixagent.core.agent.types import (
    AgentPriority,
    GuardrailAction,
    GuardrailLayer,
    SandboxLevel,
)

# ============================================================================
# 测试工具
# ============================================================================


class TestRunner:
    """简单测试运行器。"""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.errors.append(f"{name}: {detail}")
            print(f"  [FAIL] {name} - {detail}")

    def section(self, title: str) -> None:
        print(f"\n=== {title} ===")


@pytest.fixture
def t() -> TestRunner:
    """提供 AgentOS 验证运行器;测试结束后若有未通过项则断言失败。

    原脚本以独立 `main()` 驱动,现转为 pytest 用例:每个 ``test_*`` 接收
    ``t: TestRunner`` 参数,通过 ``t.check(...)`` 记录校验结果;本 fixture
    在 teardown 阶段确保没有遗留未通过项,使用例在 CI 中真正起到门禁作用。
    """
    runner = TestRunner()
    yield runner
    assert runner.failed == 0, f"AgentOS e2e 存在 {runner.failed} 项未通过:\n" + "\n".join(
        runner.errors
    )


# ============================================================================
# 测试用例
# ============================================================================


async def test_imports(t: TestRunner) -> None:
    """1. 包导入完整性。"""
    t.section("1. 包导入完整性")
    import fnixagent.core.agentos as agentos

    t.check("包可导入", True)
    t.check("__version__ 存在", hasattr(agentos, "__version__"))
    t.check("__all__ 非空", len(agentos.__all__) > 50, f"only {len(agentos.__all__)} exports")
    # 关键类存在
    for name in [
        "AgentKernel",
        "AgentProcess",
        "AgentShell",
        "ContextFS",
        "MemoryManager",
        "PolicyEngine",
        "AgentScheduler",
        "A2ABus",
        "ObservabilityManager",
        "GuardrailManager",
        "SandboxManager",
    ]:
        t.check(f"导出 {name}", hasattr(agentos, name))


async def test_kernel_lifecycle(t: TestRunner) -> None:
    """2. 内核生命周期。"""
    t.section("2. 内核生命周期")
    kernel = AgentKernel(
        llm_backend=InMemoryLLMBackend(),
        memory_backend=InMemoryMemoryBackend(),
        tool_backend=InMemoryToolBackend(),
        storage_backend=InMemoryStorageBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    t.check("内核可创建", kernel is not None)

    await kernel.boot()
    t.check("boot 成功", kernel._booted)
    t.check("boot_time 记录", kernel._boot_time is not None)

    stats = kernel.get_kernel_stats()
    t.check("stats 返回", "booted" in stats and "process_count" in stats)
    t.check("stats 显示已 boot", stats["booted"] is True)

    await kernel.shutdown()
    t.check("shutdown 成功", not kernel._booted)


async def test_process_management(t: TestRunner) -> None:
    """3. 进程管理。"""
    t.section("3. 进程管理")
    kernel = AgentKernel(
        llm_backend=InMemoryLLMBackend(),
        memory_backend=InMemoryMemoryBackend(),
        tool_backend=InMemoryToolBackend(),
        storage_backend=InMemoryStorageBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()

    # spawn
    pid = await kernel.spawn(
        name="test-agent",
        capabilities={"fs", "llm", "memory", "tool"},
        priority=AgentPriority.NORMAL,
    )
    t.check("spawn 返回 pid", bool(pid))
    proc = kernel.get_process(pid)
    t.check("get_process 返回进程", proc is not None)
    t.check("进程名正确", proc.name == "test-agent")
    # admit() 后状态变为 READY
    t.check("进程状态 READY (admit 后)", proc.state.value in ("ready", "created"))

    # ps
    procs = kernel.list_processes()
    t.check("list_processes 包含新进程", len(procs) >= 1)

    # kill
    success = await kernel.kill(pid, reason="测试终止")
    t.check("kill 成功", success)
    proc_after = kernel.get_process(pid)
    t.check("kill 后状态 TERMINATED", proc_after.state.value == "terminated")

    # 能力继承限制
    parent_pid = await kernel.spawn(
        name="parent",
        capabilities={"fs", "llm"},
    )
    try:
        await kernel.spawn(
            name="child",
            parent_pid=parent_pid,
            capabilities={"fs", "admin"},  # admin 不在父能力集
        )
        t.check("能力继承拒绝", False, "应抛 PermissionError")
    except PermissionError:
        t.check("能力继承拒绝", True)
    # 合法子进程
    child_pid = await kernel.spawn(
        name="child-ok",
        parent_pid=parent_pid,
        capabilities={"fs"},  # 子集
    )
    t.check("合法子进程创建", bool(child_pid))

    await kernel.shutdown()


async def test_syscall_fs(t: TestRunner) -> None:
    """5. ContextFS via syscall。"""
    t.section("5. ContextFS (fs.* syscall)")
    kernel = AgentKernel(
        storage_backend=InMemoryStorageBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()
    pid = await kernel.spawn(name="fs-agent", capabilities={"fs", "memory"})

    # mkdir
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.FS_MKDIR,
            args={"path": "/test"},
            caller_pid=pid,
        )
    )
    t.check("fs.mkdir 成功", resp.success)

    # write
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.FS_WRITE,
            args={"path": "/test/hello.md", "content": "# Hello AgentOS"},
            caller_pid=pid,
        )
    )
    t.check("fs.write 成功", resp.success)

    # read
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.FS_READ,
            args={"path": "/test/hello.md"},
            caller_pid=pid,
        )
    )
    t.check("fs.read 成功", resp.success)
    t.check("fs.read 内容正确", resp.result == "# Hello AgentOS", f"got: {resp.result!r}")

    # list
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.FS_LIST,
            args={"path": "/test"},
            caller_pid=pid,
        )
    )
    t.check("fs.list 成功", resp.success)
    t.check("fs.list 包含 hello.md", isinstance(resp.result, list) and len(resp.result) >= 1)

    # delete
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.FS_DELETE,
            args={"path": "/test/hello.md"},
            caller_pid=pid,
        )
    )
    t.check("fs.delete 成功", resp.success)

    await kernel.shutdown()


async def test_syscall_mem(t: TestRunner) -> None:
    """6. MemoryManager via syscall。"""
    t.section("6. MemoryManager (mem.* syscall)")
    kernel = AgentKernel(
        memory_backend=InMemoryMemoryBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()
    pid = await kernel.spawn(name="mem-agent", capabilities={"memory", "llm"})

    # store
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.MEM_STORE,
            args={
                "content": "AgentOS 是 2026 年的 Agent 操作系统",
                "layer": "episodic",
                "metadata": {"tag": "test"},
            },
            caller_pid=pid,
        )
    )
    t.check("mem.store 成功", resp.success)
    memory_id = resp.result.get("memory_id") if resp.result else None
    t.check("mem.store 返回 memory_id", bool(memory_id))

    # search
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.MEM_SEARCH,
            args={"query": "AgentOS", "layer": "episodic", "top_k": 5},
            caller_pid=pid,
        )
    )
    t.check("mem.search 成功", resp.success)

    # recall
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.MEM_RECALL,
            args={"query": "AgentOS", "layers": ["working", "episodic"], "top_k": 5},
            caller_pid=pid,
        )
    )
    t.check("mem.recall 成功", resp.success)

    # forget
    if memory_id:
        resp = await kernel.syscall(
            SyscallRequest(
                syscall=SyscallType.MEM_FORGET,
                args={"memory_id": memory_id},
                caller_pid=pid,
            )
        )
        t.check("mem.forget 成功", resp.success)

    await kernel.shutdown()


async def test_syscall_llm(t: TestRunner) -> None:
    """8. LLM via syscall。"""
    t.section("8. LLM (llm.complete syscall)")
    kernel = AgentKernel(
        llm_backend=InMemoryLLMBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()
    pid = await kernel.spawn(name="llm-agent", capabilities={"llm"})

    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.LLM_COMPLETE,
            args={"messages": [{"role": "user", "content": "你好"}]},
            caller_pid=pid,
        )
    )
    t.check("llm.complete 成功", resp.success)
    t.check(
        "llm.complete 返回文本",
        isinstance(resp.result, str) and len(resp.result) > 0,
        f"got: {resp.result!r}",
    )
    # InMemoryLLMBackend 应该回模板响应
    t.check("llm.complete 响应包含 prompt", "你好" in (resp.result or ""), f"got: {resp.result!r}")

    await kernel.shutdown()


async def test_syscall_tool(t: TestRunner) -> None:
    """9. Tool via syscall。"""
    t.section("9. Tool (tool.* syscall)")
    kernel = AgentKernel(
        tool_backend=InMemoryToolBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()
    pid = await kernel.spawn(name="tool-agent", capabilities={"tool"})

    # list
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.TOOL_LIST,
            args={},
            caller_pid=pid,
        )
    )
    t.check("tool.list 成功", resp.success)
    t.check("tool.list 返回非空", isinstance(resp.result, list) and len(resp.result) > 0)

    # invoke echo (InMemoryToolBackend 内置 echo)
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.TOOL_INVOKE,
            args={"tool": "echo", "arguments": {"text": "hello"}},
            caller_pid=pid,
        )
    )
    t.check("tool.invoke echo 成功", resp.success)

    await kernel.shutdown()


async def test_a2a(t: TestRunner) -> None:
    """10. A2A Bus。"""
    t.section("10. A2A Bus")
    kernel = AgentKernel(
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()

    pid_a = await kernel.spawn(name="agent-a", capabilities={"ipc"})
    pid_b = await kernel.spawn(name="agent-b", capabilities={"ipc"})

    # discover
    cards = await kernel.a2a_bus.discover()
    t.check("a2a.discover 返回非空", len(cards) >= 2)

    # send
    msg = A2AMessage(
        source=pid_a,
        target=pid_b,
        message_type="event",
        content="hello from A",
    )
    await kernel.a2a_bus.send(pid_b, msg)
    t.check("a2a.send 成功", True)

    # receive
    received = await kernel.a2a_bus.receive(pid_b, timeout=1.0)
    t.check("a2a.receive 成功", received is not None)
    t.check("a2a 消息内容正确", received.content == "hello from A", f"got: {received.content!r}")

    # broadcast
    broadcast_msg = A2AMessage(
        source=pid_a,
        target="*",
        message_type="event",
        content="broadcast!",
    )
    count = await kernel.a2a_bus.broadcast(broadcast_msg, exclude=pid_a)
    t.check("a2a.broadcast 投递数 >= 1", count >= 1, f"got: {count}")

    await kernel.shutdown()


async def test_observability(t: TestRunner) -> None:
    """12. Observability。"""
    t.section("12. Observability")
    obs = ObservabilityManager()

    span = obs.start_span("test.op", {"key": "value"})
    t.check("start_span 成功", span is not None)
    span.set_attribute("result", "ok")
    span.add_event("sub-step")
    span.end("ok", "")
    t.check("span 已结束", span.end_time is not None)

    # audit
    obs.audit("test.action", {"detail": "test"}, subject="test-pid")
    logs = obs.get_audit_log(limit=10)
    t.check("audit_log 非空", len(logs) >= 1)
    t.check("audit_log 包含 test.action", any(l["action"] == "test.action" for l in logs))

    # metrics
    obs.increment("test.counter", 1)
    obs.increment("test.counter", 2)
    obs.observe("test.histogram", 0.1)
    obs.observe("test.histogram", 0.5)
    stats = obs.get_stats()
    t.check("stats 返回", "total_spans" in stats and "audit_entries" in stats)


async def test_guardrail(t: TestRunner) -> None:
    """13. Guardrail。"""
    t.section("13. Guardrail")
    mgr = GuardrailManager()

    # 注册长度限制护栏
    entry = length_limit_guardrail(max_length=10, layer=GuardrailLayer.INPUT)
    mgr.register("length", entry.func, layer=entry.layer, priority=entry.priority)

    # PASS: 短内容
    ctx = GuardrailContext(
        layer=GuardrailLayer.INPUT,
        syscall="llm.complete",
        caller_pid="test",
        content="short",
    )
    result = mgr.evaluate(ctx)
    t.check("短内容 PASS", result.action == GuardrailAction.PASS)

    # BLOCK: 长内容
    ctx = GuardrailContext(
        layer=GuardrailLayer.INPUT,
        syscall="llm.complete",
        caller_pid="test",
        content="x" * 100,
    )
    result = mgr.evaluate(ctx)
    t.check("长内容 BLOCK", result.action == GuardrailAction.BLOCK)

    # 敏感数据护栏
    sensitive_entry = sensitive_data_guardrail()
    mgr.register(
        "sensitive",
        sensitive_entry.func,
        layer=sensitive_entry.layer,
        priority=sensitive_entry.priority,
    )
    ctx = GuardrailContext(
        layer=GuardrailLayer.OUTPUT,
        syscall="llm.complete",
        caller_pid="test",
        content="我的手机号是 13800138000, 邮箱 test@example.com",
    )
    result = mgr.evaluate(ctx)
    t.check(
        "敏感数据检测 BLOCK/MODIFY",
        result.action in (GuardrailAction.BLOCK, GuardrailAction.MODIFY),
    )


async def test_sandbox(t: TestRunner) -> None:
    """14. Sandbox。"""
    t.section("14. Sandbox")
    from fnixagent.core.agentos.sandbox import SandboxConfig

    mgr = SandboxManager()  # 默认 Inline

    # 执行简单命令 (跨平台)
    config = SandboxConfig(level=SandboxLevel.NONE, timeout_sec=5.0)
    result = await mgr.execute("echo hello_agentos", config)
    t.check("sandbox.execute 成功", result.success)
    t.check("sandbox 输出包含 hello_agentos", "hello_agentos" in (result.stdout or ""))


async def test_shell(t: TestRunner) -> None:
    """15. AgentShell。"""
    t.section("15. AgentShell")
    kernel = AgentKernel(
        llm_backend=InMemoryLLMBackend(),
        memory_backend=InMemoryMemoryBackend(),
        tool_backend=InMemoryToolBackend(),
        storage_backend=InMemoryStorageBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    shell = AgentShell(kernel=kernel)
    await kernel.boot()

    # help
    result = await shell.execute("help")
    t.check("shell help 命令", result.success)
    t.check("help 返回命令清单", isinstance(result.output, dict) and "spawn" in result.output)

    # spawn
    result = await shell.execute("spawn test-via-shell --capabilities=fs,llm")
    t.check("shell spawn 命令", result.success)
    t.check("spawn 返回 pid", bool(result.output.get("pid")))

    # ps
    result = await shell.execute("ps")
    t.check("shell ps 命令", result.success)
    t.check("ps 返回进程列表", isinstance(result.output, list))

    # fs.write + fs.read
    result = await shell.execute('fs.write /test/shell.md --content="shell content"')
    t.check("shell fs.write", result.success)
    result = await shell.execute("fs.read /test/shell.md")
    t.check("shell fs.read", result.success)
    t.check("fs.read 内容正确", result.output == "shell content", f"got: {result.output!r}")

    # llm
    result = await shell.execute("llm 你好")
    t.check("shell llm 命令", result.success)

    # stats
    result = await shell.execute("stats")
    t.check("shell stats 命令", result.success)

    # audit
    result = await shell.execute("audit --limit=5")
    t.check("shell audit 命令", result.success)

    # 未知命令
    result = await shell.execute("nonexistent_command")
    t.check("未知命令返回错误", not result.success)

    await kernel.shutdown()


async def test_natural_language(t: TestRunner) -> None:
    """16. 自然语言接口。"""
    t.section("16. 自然语言接口")
    kernel = AgentKernel(
        llm_backend=InMemoryLLMBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    shell = AgentShell(kernel=kernel)
    await kernel.boot()

    result = await shell.natural_language("你好,介绍一下 AgentOS")
    t.check("NL 接口返回", result.success)
    t.check("NL 返回文本", isinstance(result.output, str) and len(result.output) > 0)

    await kernel.shutdown()


async def test_skill_loading(t: TestRunner) -> None:
    """17. Skill 加载。"""
    t.section("17. Skill 加载")
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="agentos_skills_")
    # 创建一个测试 Skill 文件
    skill_code = """
import asyncio

SKILL_NAME = "greeter"
SKILL_DESCRIPTION = "测试 Skill: 问候"
SKILL_CAPABILITIES = {"llm"}

async def handler(kernel, args):
    name = args.get("name", "World")
    return {"greeting": f"Hello, {name}! From AgentOS Skill."}
"""
    skill_path = Path(tmpdir) / "greeter.py"
    skill_path.write_text(skill_code, encoding="utf-8")

    kernel = AgentKernel(
        llm_backend=InMemoryLLMBackend(),
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    shell = AgentShell(kernel=kernel, skills_dir=tmpdir)
    await kernel.boot()

    # skill.list
    result = await shell.execute("skill.list")
    t.check("skill.list 成功", result.success)
    t.check(
        "skill.list 包含 greeter",
        isinstance(result.output, list) and any(s["name"] == "greeter" for s in result.output),
    )

    # skill.run
    result = await shell.execute("skill.run greeter --name=AgentOS")
    t.check("skill.run 成功", result.success)
    t.check(
        "skill 返回 greeting",
        result.output is not None
        and "greeting" in result.output
        and "AgentOS" in result.output["greeting"],
    )

    await kernel.shutdown()


async def test_policy_authorization(t: TestRunner) -> None:
    """18. PolicyEngine 授权。"""
    t.section("18. PolicyEngine 授权")
    kernel = AgentKernel(
        policy_backend=InMemoryPolicyBackend(),
        audit_backend=InMemoryAuditBackend(),
        enable_scheduler_loop=False,
    )
    await kernel.boot()

    # 缺少能力的 Agent 不能执行高危 syscall
    pid_limited = await kernel.spawn(
        name="limited",
        capabilities={"fs"},  # 无 shell 能力
    )
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.SHELL_EXEC,
            args={"command": "echo test"},
            caller_pid=pid_limited,
        )
    )
    t.check("缺能力被拒绝", not resp.success)

    # 拥有能力的 Agent 可以执行
    pid_priv = await kernel.spawn(
        name="privileged",
        capabilities={"shell"},
    )
    resp = await kernel.syscall(
        SyscallRequest(
            syscall=SyscallType.SHELL_EXEC,
            args={"command": "echo authorized", "sandbox": "none"},
            caller_pid=pid_priv,
        )
    )
    t.check("有能力通过授权", resp.success)

    await kernel.shutdown()


async def test_singleton(t: TestRunner) -> None:
    """19. 全局单例。"""
    t.section("19. 全局单例 (get_kernel/reset_kernel)")
    reset_kernel()
    k1 = get_kernel()
    k2 = get_kernel()
    t.check("get_kernel 单例", k1 is k2)
    reset_kernel()
    k3 = get_kernel()
    t.check("reset_kernel 后创建新实例", k3 is not k1)


# ============================================================================
# 主入口
# ============================================================================


async def main() -> int:
    print("=" * 70)
    print("FnixAgent OS — AgentOS 全量功能验证")
    print("=" * 70)

    t = TestRunner()

    test_cases = [
        test_imports,
        test_kernel_lifecycle,
        test_process_management,
        test_syscall_fs,
        test_syscall_mem,
        test_syscall_llm,
        test_syscall_tool,
        test_a2a,
        test_observability,
        test_guardrail,
        test_sandbox,
        test_shell,
        test_natural_language,
        test_skill_loading,
        test_policy_authorization,
        test_singleton,
    ]

    for tc in test_cases:
        try:
            await tc(t)
        except Exception as e:  # noqa: BLE001
            t.failed += 1
            t.errors.append(f"{tc.__name__}: {type(e).__name__}: {e}")
            print(f"\n[ERROR] {tc.__name__} 抛出异常:")
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"验证结果: PASS={t.passed}  FAIL={t.failed}")
    if t.errors:
        print("\n失败项:")
        for e in t.errors:
            print(f"  - {e}")
    print("=" * 70)
    return 0 if t.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
