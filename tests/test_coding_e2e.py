"""
OfficeAgent Coding 包 — 端到端验证
=====================================
覆盖编码智能体全部模块功能。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from officeagent.core.coding import (
    ChangeSet, ChangeSetBuilder, ChangeType, CodeIndexer, CodeTools,
    ContextBuilder, DiffEngine, FileChange, IDEServer, SymbolKind,
)


class T:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: list[str] = []

    def check(self, name: str, cond: bool, detail: str = ""):
        if cond:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.errors.append(f"{name}: {detail}")
            print(f"  [FAIL] {name} - {detail}")

    def section(self, title: str):
        print(f"\n=== {title} ===")


# ============================================================================
# 测试用例
# ============================================================================

async def test_imports(t: T):
    """1. 包导入完整性。"""
    t.section("1. 包导入完整性")
    import officeagent.core.coding as coding
    t.check("包可导入", True)
    t.check("__all__ 非空", len(coding.__all__) >= 15)
    for name in ["CodeIndexer", "ContextBuilder", "DiffEngine",
                 "CodeTools", "IDEServer"]:
        t.check(f"导出 {name}", hasattr(coding, name))


async def test_code_indexer(t: T):
    """2. CodeIndexer 索引与搜索。"""
    t.section("2. CodeIndexer 索引与搜索")
    # 创建临时项目
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试文件
        (Path(tmpdir) / "__init__.py").write_text("")
        (Path(tmpdir) / "sample.py").write_text('''"""Sample module."""


class Calculator:
    """计算器类。"""

    def add(self, a: int, b: int) -> int:
        """加法。"""
        return a + b

    def divide(self, a: int, b: int) -> float:
        """除法。"""
        if b == 0:
            raise ValueError("除数不能为零")
        return a / b


async def async_helper(x: int) -> str:
    """异步辅助函数。"""
    return f"result: {x}"


def standalone_function():
    """独立函数。"""
    pass
''', encoding="utf-8")

        indexer = CodeIndexer()
        stats = await indexer.index_directory(tmpdir)

        t.check("索引成功", stats.total_files >= 2)
        t.check("索引符号数 > 0", stats.total_symbols > 0,
                f"got {stats.total_symbols}")
        t.check("索引切片数 > 0", stats.total_slices > 0)
        t.check("无错误", len(stats.errors) == 0,
                f"errors: {stats.errors}")

        # 符号查询
        sym = indexer.get_symbol_info("Calculator")
        t.check("get_symbol_info Calculator", sym is not None)
        t.check("Calculator 是 CLASS",
                sym is not None and sym.kind == SymbolKind.CLASS)

        sym = indexer.get_symbol_info("add")
        t.check("get_symbol_info add", sym is not None)

        sym = indexer.get_symbol_info("async_helper")
        t.check("get_symbol_info async_helper", sym is not None)

        # 语义搜索
        results = await indexer.search_code("加法计算", top_k=5)
        t.check("search_code 返回结果", len(results) > 0)

        results = await indexer.search_code("calculator", top_k=5)
        t.check("search_code Calculator", len(results) > 0)

        # 仓库地图
        repo_map = indexer.get_repo_map()
        t.check("get_repo_map 非空", len(repo_map) > 0)
        t.check("repo_map 包含 sample.py", "sample.py" in repo_map)
        t.check("repo_map 包含 Calculator", "Calculator" in repo_map)

        # 引用查找
        refs = indexer.find_references("Calculator")
        t.check("find_references 执行", isinstance(refs, list))

        # 文件符号
        file_syms = indexer.get_file_symbols("sample.py")
        t.check("get_file_symbols 非空", len(file_syms) > 0)

        # 增量索引
        stats2 = await indexer.index_directory(tmpdir, incremental=True)
        t.check("增量索引跳过未变更文件",
                stats2.indexed_files == 0,
                f"got {stats2.indexed_files}")


async def test_diff_engine(t: T):
    """3. DiffEngine 原子编辑。"""
    t.section("3. DiffEngine 原子编辑")
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = DiffEngine(project_root=tmpdir)

        # 创建文件
        builder = ChangeSetBuilder("创建测试文件")
        builder.create_file("a.py", "print('hello')\n")
        builder.create_file("b.py", "# b module\n")
        cs = builder.build()

        result = await engine.apply(cs)
        t.check("apply 创建成功", result.success)
        t.check("文件 a.py 存在", os.path.exists(Path(tmpdir) / "a.py"))
        t.check("文件 b.py 存在", os.path.exists(Path(tmpdir) / "b.py"))

        # 修改文件
        builder2 = ChangeSetBuilder("修改 a.py")
        builder2.modify_file("a.py", "print('hello')\n", "print('world')\n")
        cs2 = builder2.build()
        result2 = await engine.apply(cs2)
        t.check("apply 修改成功", result2.success)
        content = (Path(tmpdir) / "a.py").read_text()
        t.check("修改内容正确", "world" in content)

        # 回滚
        ok = await engine.rollback(cs2.id)
        t.check("rollback 成功", ok)
        content = (Path(tmpdir) / "a.py").read_text()
        t.check("回滚内容正确", "hello" in content)

        # 原子性: 一个失败, 全部回滚
        builder3 = ChangeSetBuilder("原子性测试")
        builder3.create_file("c.py", "c\n")
        builder3.modify_file("nonexistent.py", "old", "new")  # 会失败
        cs3 = builder3.build()
        result3 = await engine.apply(cs3)
        t.check("原子性: 应用失败", not result3.success)
        t.check("原子性: c.py 未创建", not os.path.exists(Path(tmpdir) / "c.py"))

        # dry_run
        builder4 = ChangeSetBuilder("dry run")
        builder4.create_file("d.py", "d\n")
        cs4 = builder4.build()
        result4 = await engine.apply(cs4, dry_run=True)
        t.check("dry_run 预检查通过", result4.success)
        t.check("dry_run 不写入", not os.path.exists(Path(tmpdir) / "d.py"))

        # diff 生成
        diff_text = cs.to_diff()
        t.check("to_diff 非空", len(diff_text) > 0)

        # 历史
        history = engine.get_history()
        t.check("历史记录非空", len(history) >= 2)


async def test_code_tools(t: T):
    """4. CodeTools 代码工具。"""
    t.section("4. CodeTools 代码工具")
    with tempfile.TemporaryDirectory() as tmpdir:
        tools = CodeTools(project_root=tmpdir)

        # write (含多个 return 语句, 供后续多次匹配测试)
        result = await tools.write(
            "test.py",
            "def hello():\n    return 'hi'\n\ndef world():\n    return 'hi'\n",
        )
        t.check("write 成功", result.success)

        # read
        result = await tools.read("test.py")
        t.check("read 成功", result.success)
        t.check("read 内容正确", "hello" in str(result.output))

        # read 行范围
        result = await tools.read("test.py", start_line=1, end_line=1)
        t.check("read 行范围", result.success)

        # edit (唯一匹配)
        result = await tools.edit("test.py", "def hello():", "def greet():")
        t.check("edit 成功", result.success)
        result = await tools.read("test.py")
        t.check("edit 内容正确", "greet" in str(result.output))

        # edit 多次匹配失败 ('hi' 在文件中出现 2 次)
        result = await tools.edit("test.py", "'hi'", "'yo'")
        t.check("edit 多次匹配失败", not result.success,
                f"expected failure, got success={result.success}")

        # 路径穿越防护 (read 内部捕获 ValueError 返回 err)
        result = await tools.read("../../../etc/passwd")
        t.check("路径穿越拒绝", not result.success,
                f"expected failure, got success={result.success}")

        # git 白名单
        t.check("git status 安全", tools._is_safe_git_command(["status"]))
        t.check("git push 禁止", not tools._is_safe_git_command(["push"]))
        t.check("git reset --hard 禁止",
                not tools._is_safe_git_command(["reset", "--hard"]))

        # get_tools
        tool_list = tools.get_tools()
        t.check("get_tools 非空", len(tool_list) >= 6)


async def test_context_builder(t: T):
    """5. ContextBuilder 上下文组装。"""
    t.section("5. ContextBuilder 上下文组装")
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "sample.py").write_text(
            "def foo():\n    return 42\n", encoding="utf-8")

        indexer = CodeIndexer()
        await indexer.index_directory(tmpdir)
        builder = ContextBuilder(indexer, project_root=tmpdir)

        ctx = await builder.build_context(
            "为 foo 函数添加类型注解",
            token_budget=4096,
            system_prompt="你是编码助手",
        )

        t.check("build_context 成功", ctx is not None)
        t.check("消息列表非空", len(ctx.messages) >= 1)
        t.check("第一条是 system", ctx.messages[0]["role"] == "system")
        t.check("total_tokens > 0", ctx.total_tokens > 0)
        t.check("条目非空", len(ctx.entries) > 0)


async def test_coding_agent(t: T):
    """6. CodingAgent 编码智能体。"""
    t.section("6. CodingAgent 编码智能体")
    from officeagent.core.agentos.backends import InMemoryLLMBackend

    with tempfile.TemporaryDirectory() as tmpdir:
        indexer = CodeIndexer()
        await indexer.index_directory(tmpdir)
        diff_engine = DiffEngine(project_root=tmpdir)
        tools = CodeTools(project_root=tmpdir, diff_engine=diff_engine,
                          code_indexer=indexer)
        ctx_builder = ContextBuilder(indexer, project_root=tmpdir)
        llm = InMemoryLLMBackend()

        from officeagent.core.coding.coding_agent import CodingAgent, CodingTask
        agent = CodingAgent(tools, ctx_builder, llm)

        # 执行任务 (InMemoryLLM 返回模板, plan 解析会降级)
        result = await agent.execute_task("创建 hello.py 文件")
        t.check("execute_task 返回结果", result is not None)
        t.check("任务有状态", result.status is not None)
        # InMemoryLLM 不会返回有效 JSON, 会降级为单步


async def test_ide_server(t: T):
    """7. IDEServer CLI + MCP。"""
    t.section("7. IDEServer CLI + MCP")
    with tempfile.TemporaryDirectory() as tmpdir:
        server = IDEServer(project_root=tmpdir)

        # help
        exit_code = await server.run_cli(["help"])
        t.check("help 命令", exit_code == 0)

        # index
        exit_code = await server.run_cli(["index"])
        t.check("index 命令", exit_code == 0)

        # map
        exit_code = await server.run_cli(["map"])
        t.check("map 命令", exit_code == 0)

        # 未知命令
        exit_code = await server.run_cli(["unknown_cmd"])
        t.check("未知命令返回 1", exit_code == 1)

        # MCP list_tools
        tools = server.mcp_list_tools()
        t.check("mcp_list_tools 非空", len(tools) >= 5)

        # MCP call
        result = await server.mcp_call("code.read", {"file_path": "nonexistent.py"})
        t.check("mcp_call 返回", isinstance(result, dict))
        t.check("mcp_call 有 success 字段", "success" in result)


async def test_skills(t: T):
    """8. Skills 加载。"""
    t.section("8. Skills 加载")
    from officeagent.core.agentos.shell import SkillRegistry
    skills_dir = str(Path(__file__).parent.parent / "src" / "officeagent" /
                     "core" / "coding" / "skills")
    registry = SkillRegistry()
    count = registry.load_from_directory(skills_dir)
    t.check("Skill 加载数 >= 3", count >= 3, f"got {count}")
    skills = registry.list()
    skill_names = {s.name for s in skills}
    t.check("code_review 已加载", "code_review" in skill_names)
    t.check("test_generate 已加载", "test_generate" in skill_names)
    t.check("debug_analyze 已加载", "debug_analyze" in skill_names)


async def test_agentos_integration(t: T):
    """9. AgentOS 集成 (ContextFS + syscall)。"""
    t.section("9. AgentOS 集成")
    from officeagent.core.agentos import (
        AgentKernel, AgentShell,
        InMemoryLLMBackend, InMemoryMemoryBackend, InMemoryToolBackend,
        InMemoryStorageBackend, InMemoryPolicyBackend, InMemoryAuditBackend,
    )

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

    # 通过 AgentShell fs.write 写入代码
    r = await shell.execute(
        'fs.write /project/main.py --content="def hello():\\n    return \'world\'"'
    )
    t.check("fs.write 代码文件", r.success)

    # fs.read 读取
    r = await shell.execute("fs.read /project/main.py")
    t.check("fs.read 代码文件", r.success)

    await kernel.shutdown()


# ============================================================================
# 主入口
# ============================================================================

async def main() -> int:
    print("=" * 70)
    print("OfficeAgent Coding — 端到端验证")
    print("=" * 70)

    t = T()
    tests = [
        test_imports,
        test_code_indexer,
        test_diff_engine,
        test_code_tools,
        test_context_builder,
        test_coding_agent,
        test_ide_server,
        test_skills,
        test_agentos_integration,
    ]

    for tc in tests:
        try:
            await tc(t)
        except Exception as e:  # noqa: BLE001
            t.failed += 1
            t.errors.append(f"{tc.__name__}: {type(e).__name__}: {e}")
            print(f"\n[ERROR] {tc.__name__} 异常:")
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
