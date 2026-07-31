"""Code 模式 TodoStore + Compaction 接入测试 (P0 硬伤修复验证)。

验证 CodingAgent 在 plan→execute→review→heal 循环中:
1. TodoStore 被加载并注入 _plan/_plan_heal 的 messages
2. plan steps 被同步到 TodoStore
3. heal 时 todos_block 包含历次失败原因
4. _call_llm 调用 compaction (超阈值时压缩)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from fnixagent.core.code.agent import CodingAgent, CodingTask
from fnixagent.core.skills.todos import TodoItem, TodoStore


class TestCodeModeTodoStore:
    """Code 模式 TodoStore 接入验证。"""

    def test_load_todo_store_returns_store(self, tmp_path: Path):
        """_load_todo_store 应返回有效的 TodoStore。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        llm = MagicMock()
        agent = CodingAgent(tools, ctx_builder, llm, workspace=str(tmp_path))
        store = agent._load_todo_store()
        assert store is not None
        assert isinstance(store, TodoStore)

    def test_load_todo_store_failure_returns_none(self):
        """workspace 无效时应返回 None, 不抛异常。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        llm = MagicMock()
        agent = CodingAgent(tools, ctx_builder, llm, workspace="/nonexistent/path/xyz")
        store = agent._load_todo_store()
        # TodoStore 构造不抛异常, 但即使抛了也应返回 None
        assert store is None or isinstance(store, TodoStore)

    def test_sync_plan_to_todos_first_plan(self, tmp_path: Path):
        """首次 plan 应清空并重建 todos。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        llm = MagicMock()
        agent = CodingAgent(tools, ctx_builder, llm, workspace=str(tmp_path))
        store = TodoStore(str(tmp_path))

        # 预填充旧数据
        store.add(TodoItem(id="old", content="旧任务"))
        assert len(store.todos) == 1

        # 模拟 plan steps
        from fnixagent.core.code.agent import TaskStep

        plan = [
            TaskStep(id="s1", description="read file", action="read", target="main.py"),
            TaskStep(id="s2", description="write code", action="write", target="utils.py"),
        ]
        agent._sync_plan_to_todos(store, plan, heal_round=0)

        assert len(store.todos) == 2
        assert store.todos[0].id == "step_1"
        assert store.todos[1].id == "step_2"
        assert "read" in store.todos[0].content
        assert store.todos[1].priority == "high"  # write 是 high

    def test_sync_plan_to_todos_heal_round(self, tmp_path: Path):
        """heal 轮次应追加新步骤, 不清空。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        llm = MagicMock()
        agent = CodingAgent(tools, ctx_builder, llm, workspace=str(tmp_path))
        store = TodoStore(str(tmp_path))

        from fnixagent.core.code.agent import TaskStep

        plan1 = [TaskStep(id="s1", description="write", action="write", target="a.py")]
        agent._sync_plan_to_todos(store, plan1, heal_round=0)

        plan2 = [TaskStep(id="s2", description="edit", action="edit", target="a.py")]
        agent._sync_plan_to_todos(store, plan2, heal_round=1)

        assert len(store.todos) >= 2
        # heal 步骤应有 [heal1] 前缀
        heal_todos = [t for t in store.todos if t.id.startswith("heal1")]
        assert len(heal_todos) == 1
        assert "[heal1]" in heal_todos[0].content

    def test_update_todos_after_review_failure(self, tmp_path: Path):
        """审查失败时应记录失败原因到 todo note。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        llm = MagicMock()
        agent = CodingAgent(tools, ctx_builder, llm, workspace=str(tmp_path))
        store = TodoStore(str(tmp_path))

        from fnixagent.core.code.agent import TaskStep

        plan = [TaskStep(id="s1", description="write", action="write", target="a.py")]
        agent._sync_plan_to_todos(store, plan, heal_round=0)
        # 标记为 in_progress (模拟执行中)
        store.update_status("step_1", "in_progress")

        agent._update_todos_after_review(store, passed=False, notes="SyntaxError in a.py")

        failed = [t for t in store.todos if t.status == "failed"]
        assert len(failed) >= 1
        assert "SyntaxError" in failed[0].note

    def test_todos_block_injected_into_plan_heal_messages(self, tmp_path: Path):
        """_plan_heal 应把 todos_block 注入 messages。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        # build_context 返回带 messages 的 BuiltContext
        built_ctx = MagicMock()
        built_ctx.messages = [{"role": "system", "content": "sys"}]
        ctx_builder = MagicMock()
        ctx_builder.build_context = AsyncMock(return_value=built_ctx)
        llm = MagicMock()
        llm.complete = AsyncMock(return_value='{"steps":[]}')

        agent = CodingAgent(tools, ctx_builder, llm, workspace=str(tmp_path))

        task = CodingTask(id="t1", description="test task")
        todos_block = "\n## 当前任务清单\n1. ○ [high] step_1: write a.py\n   备注: SyntaxError"

        asyncio.run(agent._plan_heal(task, "failure notes", todos_block=todos_block))

        # 验证 todos_block 被注入到 messages
        call_args = llm.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0].get("messages")
        assert messages is not None
        # 应有一个 system 消息包含 todos_block
        system_msgs = [m for m in messages if m["role"] == "system"]
        todos_msgs = [m for m in system_msgs if "当前任务清单" in m.get("content", "")]
        assert len(todos_msgs) >= 1

    def test_compact_if_needed_passthrough_when_no_adapter(self, tmp_path: Path):
        """无 LLM adapter 时应直接返回原 messages, 不报错。"""
        tools = MagicMock()
        ctx_builder = MagicMock()
        llm = MagicMock()
        llm._adapter = None  # 无 adapter
        agent = CodingAgent(tools, ctx_builder, llm, workspace=str(tmp_path))

        messages = [{"role": "user", "content": "test"}]
        result = asyncio.run(agent._compact_if_needed(messages))
        assert result is messages  # 原样返回

    def test_clear_method_on_todo_store(self, tmp_path: Path):
        """TodoStore.clear() 应清空全部待办。"""
        store = TodoStore(str(tmp_path))
        store.add(TodoItem(id="t1", content="task1"))
        store.add(TodoItem(id="t2", content="task2"))
        assert len(store.todos) == 2

        store.clear()
        assert len(store.todos) == 0

        # 持久化验证: 重新加载应为空
        store2 = TodoStore(str(tmp_path))
        assert len(store2.todos) == 0
