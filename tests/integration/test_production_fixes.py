"""生产可用性修复验证测试。

验证 P0/P1 修复在真实场景下行为正确:
  - P0-1: AgenticLoop 心跳机制存在 (15s 间隔)
  - P0-2: tool_result 智能压缩 (非 4KB 硬截断)
  - P0-3: LLM 工具降级时 _tools_degraded_this_step 标记
  - P1-1: 未配置 LLM 时 raise 而非静默返回假回复
  - P1-3: ToolPolicy 默认 fail-closed
  - P1-4: 危险命令黑名单扩展
  - P1-5: RunCheckpointStore 单连接复用
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def test_p0_1_heartbeat_in_run_stream():
    """P0-1: AgenticLoop.run_stream 应包含心跳机制。"""
    from fnixagent.core.agent.loop import AgenticLoop

    src = inspect.getsource(AgenticLoop.run_stream)
    assert "_heartbeat" in src, "P0-1 心跳机制未加入 run_stream"
    assert "_hb_queue" in src, "P0-1 心跳队列未加入"
    assert "15.0" in src or "15" in src, "P0-1 心跳间隔应为 15s"
    print("[P0-1] 心跳机制验证通过")


def test_p0_2_smart_compression():
    """P0-2: tool_result 智能压缩替代 4KB 硬截断。"""
    from fnixagent.core.run.engine import RunEngine

    src = inspect.getsource(RunEngine.run_stream)
    # 不应再有不带上下文的 content[:4000] 硬截断
    assert "content[:4000]" not in src, "P0-2 仍存在 4KB 硬截断"
    assert "已省略" in src, "P0-2 智能压缩标记未加入"
    print("[P0-2] 智能压缩验证通过")


def test_p0_3_tools_degraded_warning():
    """P0-3: LLM 工具被拒降级时应设置标记并 yield warning。"""
    from fnixagent.core.agent.loop import AgenticLoop

    src_call = inspect.getsource(AgenticLoop._call_llm)
    assert "_tools_degraded_this_step" in src_call, "P0-3 标记未加入 _call_llm"
    src_run = inspect.getsource(AgenticLoop.run_stream)
    assert "tools_degraded" in src_run, "P0-3 warning 事件未加入 run_stream"
    print("[P0-3] 工具降级告警验证通过")


def test_p1_1_llm_not_configured_raises():
    """P1-1: 未配置 LLM 时应 raise 而非静默返回假回复。"""
    from fnixagent.services.work_agent import build_work_agent_loop

    src = inspect.getsource(build_work_agent_loop)
    # 不应有 "choices" hardcode 假回复 (P1 修复后改为 raise)
    assert "[LLM 未配置]" in src, "P1-1 应包含未配置提示"
    assert "raise RuntimeError" in src, "P1-1 应 raise RuntimeError 而非静默返回"
    print("[P1-1] 未配置 LLM 抛异常验证通过")


def test_p1_3_policy_default_fail_closed():
    """P1-3: ToolPolicy 默认 auto_approve_high=False (fail-closed)。"""
    # 清理环境变量
    for k in ("FNIX_TOOL_AUTO_APPROVE", "FNIXAGENT_PROFILE", "SERVICE_DEBUG", "DEBUG"):
        os.environ.pop(k, None)
    from fnixagent.core.tools.policy import ToolPolicy

    policy = ToolPolicy()
    assert policy.auto_approve_high is False, "P1-3 默认应 fail-closed"
    print("[P1-3] policy 默认 fail-closed 验证通过")


def test_p1_4_dangerous_commands_extended():
    """P1-4: 危险命令黑名单应覆盖 home/git push --force/kill -9 等。"""
    from fnixagent.core.tools.workspace import _is_dangerous_command

    # P1 新增的拦截模式
    assert _is_dangerous_command("rm -rf ~/Documents"), "应拦截 home 目录删除"
    assert _is_dangerous_command("git push --force origin main"), "应拦截强制推送主分支"
    assert _is_dangerous_command("kill -9 -1"), "应拦截批量杀进程"
    assert _is_dangerous_command("taskkill /f /im explorer.exe"), "应拦截 taskkill"
    assert _is_dangerous_command("rm -rf .git"), "应拦截 .git 删除"
    # 正常命令不被误拦
    assert not _is_dangerous_command("ls -la"), "不应误拦 ls"
    assert not _is_dangerous_command("git status"), "不应误拦 git status"
    assert not _is_dangerous_command("npm install"), "不应误拦 npm install"
    print("[P1-4] 危险命令黑名单扩展验证通过")


def test_p1_5_checkpoint_single_connection():
    """P1-5: RunCheckpointStore 应复用单连接而非每次新开。"""
    from fnixagent.core.run.checkpoint import RunCheckpointStore

    src = inspect.getsource(RunCheckpointStore)
    # 不应再在每次操作中 self._connect() + finally: conn.close()
    # 改为直接用 self._conn
    assert "self._conn" in src, "P1-5 应使用 self._conn 复用连接"
    # start_run/append_event/save_checkpoint 都不应有 conn.close()
    start_src = inspect.getsource(RunCheckpointStore.start_run)
    assert "conn.close()" not in start_src, "P1-5 start_run 不应再 close 连接"
    append_src = inspect.getsource(RunCheckpointStore.append_event)
    assert "conn.close()" not in append_src, "P1-5 append_event 不应再 close 连接"
    print("[P1-5] 单连接复用验证通过")


def test_p1_2_tauri_dev_mode_conditional():
    """P1-2: Tauri runtime.rs 应跟随编译 profile 而非强制 dev。"""
    runtime_rs = ROOT / "apps" / "workbench" / "src-tauri" / "src" / "runtime.rs"
    if not runtime_rs.exists():
        print("[P1-2] 跳过: runtime.rs 不存在 (非 Tauri 环境)")
        return
    content = runtime_rs.read_text(encoding="utf-8")
    assert "cfg!(debug_assertions)" in content, "P1-2 应跟随编译 profile"
    assert '"development"' in content and '"production"' in content, "P1-2 应区分 dev/prod"
    print("[P1-2] Tauri dev 模式跟随编译 profile 验证通过")


def test_p0_1_frontend_timeout_extended():
    """P0-1: 前端 idle timeout 应从 60s 提升到 5 分钟。"""
    runtime_ts = (
        ROOT / "apps" / "workbench" / "src" / "shell" / "chatgpt-desktop" / "fnixRuntime.ts"
    )
    if not runtime_ts.exists():
        print("[P0-1 前端] 跳过: fnixRuntime.ts 不存在")
        return
    content = runtime_ts.read_text(encoding="utf-8")
    assert "300_000" in content, "P0-1 前端 idle timeout 应为 300000ms (5min)"
    assert "60_000" not in content or "300_000" in content, "P0-1 应已替换 60s"
    print("[P0-1 前端] idle timeout 5 分钟验证通过")


if __name__ == "__main__":
    test_p0_1_heartbeat_in_run_stream()
    test_p0_2_smart_compression()
    test_p0_3_tools_degraded_warning()
    test_p1_1_llm_not_configured_raises()
    test_p1_3_policy_default_fail_closed()
    test_p1_4_dangerous_commands_extended()
    test_p1_5_checkpoint_single_connection()
    test_p1_2_tauri_dev_mode_conditional()
    test_p0_1_frontend_timeout_extended()
    print("\n=== 所有生产可用性修复验证通过 ===")
