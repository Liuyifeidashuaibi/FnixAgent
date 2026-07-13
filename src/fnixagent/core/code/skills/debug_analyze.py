"""
Skill: 调试分析 (Debug Analysis)
==================================
分析错误栈, 定位 bug 根因。
"""
import re

SKILL_NAME = "debug_analyze"
SKILL_DESCRIPTION = "分析错误栈, 定位 bug 根因"
SKILL_CAPABILITIES = {"code.read", "code.search"}


async def handler(kernel, args):
    """分析错误栈。

    Args:
        kernel: AgentKernel 实例
        args: {"traceback": "错误栈文本"} 或 {"error": "错误消息"}
    """
    traceback_text = args.get("traceback", "")
    error_msg = args.get("error", "")

    if not traceback_text and not error_msg:
        return {"error": "缺少 traceback 或 error 参数"}

    # 解析 traceback
    frames: list[dict[str, str]] = []

    # Python traceback 格式: File "path", line N, in func
    frame_pattern = re.compile(
        r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'
    )
    for match in frame_pattern.finditer(traceback_text):
        frames.append({
            "file": match.group(1),
            "line": int(match.group(2)),
            "function": match.group(3),
        })

    # 提取错误类型和消息 (最后一行)
    error_line = ""
    error_type = ""
    error_detail = ""
    lines = traceback_text.strip().splitlines()
    if lines:
        error_line = lines[-1].strip()
        if ":" in error_line:
            parts = error_line.split(":", 1)
            error_type = parts[0].strip()
            error_detail = parts[1].strip() if len(parts) > 1 else ""
        else:
            error_type = error_line

    # 读取出错文件的相关行
    context: list[dict[str, str]] = []
    if frames:
        last_frame = frames[-1]
        from fnixagent.core.agent.syscall import SyscallRequest, SyscallType
        req = SyscallRequest(
            syscall=SyscallType.FS_READ,
            args={"path": f"/workspace/{last_frame['file']}"},
            caller_pid="kernel",
        )
        resp = await kernel.syscall(req)
        if resp.success:
            source_lines = (resp.result or "").splitlines()
            line_num = last_frame["line"]
            start = max(0, line_num - 5)
            end = min(len(source_lines), line_num + 5)
            for i in range(start, end):
                context.append({
                    "line": i + 1,
                    "content": source_lines[i] if i < len(source_lines) else "",
                    "is_error_line": (i + 1 == line_num),
                })

    # 生成分析建议
    suggestions: list[str] = []
    common_errors = {
        "AttributeError": "检查对象是否为 None, 或属性名是否拼写正确",
        "KeyError": "检查字典 key 是否存在, 使用 dict.get(key, default)",
        "IndexError": "检查索引是否越界, 列表可能为空",
        "TypeError": "检查参数类型是否正确, 可能缺少参数或类型不匹配",
        "ValueError": "检查参数值是否在有效范围内",
        "ImportError": "检查模块名是否正确, 或是否已安装依赖",
        "FileNotFoundError": "检查文件路径是否正确, 是否使用绝对路径",
        "PermissionError": "检查文件权限, 或是否被其他进程占用",
        "RecursionError": "检查递归终止条件, 可能无限递归",
        "ZeroDivisionError": "检查除数是否为 0",
    }
    if error_type in common_errors:
        suggestions.append(common_errors[error_type])

    if not suggestions:
        suggestions.append("查看完整 traceback, 定位第一个非标准库的调用帧")

    return {
        "error_type": error_type,
        "error_detail": error_detail,
        "error_line": error_line,
        "stack_frames": frames,
        "root_cause_frame": frames[-1] if frames else None,
        "source_context": context,
        "suggestions": suggestions,
    }
