"""
Skill: 测试生成 (Test Generation)
==================================
为指定函数生成单元测试骨架。
"""

import ast

SKILL_NAME = "test_generate"
SKILL_DESCRIPTION = "为指定函数生成单元测试骨架"
SKILL_CAPABILITIES = {"code.read", "code.search"}


async def handler(kernel, args):
    """生成测试骨架。

    Args:
        kernel: AgentKernel 实例
        args: {"file": "path/to/file.py", "function": "function_name"}
    """
    file_path = args.get("file")
    func_name = args.get("function")
    if not file_path or not func_name:
        return {"error": "缺少 file 或 function 参数"}

    # 读取文件
    from fnixagent.core.agent.syscall import SyscallRequest, SyscallType

    req = SyscallRequest(
        syscall=SyscallType.FS_READ,
        args={"path": f"/workspace/{file_path}"},
        caller_pid="kernel",
    )
    resp = await kernel.syscall(req)
    if not resp.success:
        return {"error": f"读取文件失败: {resp.error}"}

    source = resp.result or ""

    # 解析 AST 找到目标函数
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"error": f"语法错误: {e}"}

    target_func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                target_func = node
                break

    if target_func is None:
        return {"error": f"函数 {func_name} 不存在于 {file_path}"}

    # 提取参数
    params = []
    for arg in target_func.args.args:
        param = arg.arg
        if arg.annotation:
            param += f": {ast.unparse(arg.annotation)}"
        params.append(param)

    is_async = isinstance(target_func, ast.AsyncFunctionDef)

    # 生成测试骨架
    test_func_name = f"test_{func_name}"
    test_code = f'''"""Auto-generated test for {func_name}."""
import pytest
{"import asyncio" if is_async else ""}
from {file_path.replace("/", ".").replace(".py", "")} import {func_name}


class Test{func_name.capitalize()}:
    """{func_name} 的测试套件。"""

    @pytest.mark.parametrize("expected", [
        # TODO: 填入测试用例
        # (input_args, expected_result),
    ])
    def {test_func_name}_cases(self, expected):
        """参数化测试。"""
        # result = {func_name}(...)
        # assert result == expected
        pass

    def {test_func_name}_basic(self):
        """基础功能测试。"""
        # TODO: 实现测试
        # result = {func_name}({", ".join(p.split(":")[0] for p in params)})
        # assert result is not None
        pass

    def {test_func_name}_edge_cases(self):
        """边界条件测试。"""
        # TODO: 测试空输入、最大值、最小值等
        pass

    def {test_func_name}_error_handling(self):
        """异常处理测试。"""
        # TODO: 测试无效输入是否正确抛出异常
        pass
'''

    return {
        "file": file_path,
        "function": func_name,
        "params": params,
        "is_async": is_async,
        "test_code": test_code,
        "test_file": f"tests/test_{func_name}.py",
    }
