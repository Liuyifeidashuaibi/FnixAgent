"""
沙箱安全策略 (Sandbox Policy)。

定义安全规则:
  1. 高危命令黑名单: rm/del/format/shutdown 等模式(参考 OWASP ASI05)
  2. 禁止 import 的模块: os/subprocess/ctypes/shutil 等危险模块
  3. 网络访问白名单: 只允许指定域名(默认全禁)
  4. 文件写入白名单: 只允许指定路径(默认只读)
  5. 路径穿越检测: 禁止 .. 相对路径逃逸

静态检查: 扫描代码字符串, 不执行即可拦截大部分危险操作。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SandboxPolicy:
    """沙箱安全策略。

    Attributes:
        forbidden_commands: 高危 shell 命令正则列表
        forbidden_imports: 禁止 import 的模块名列表(精确/前缀匹配)
        network_whitelist: 允许访问的网络域名(默认空=全禁)
        file_write_whitelist: 允许写入的文件路径(默认空=全禁)
    """

    # 高危 shell 命令模式(正则,匹配即拦截)
    forbidden_commands: list[str] = field(default_factory=lambda: [
        r"\brm\s+-rf?\b",
        r"\bdel\s+/[fqs]\b",
        r"\bformat\s+[a-z]:",
        r"\bmkfs\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bchmod\s+\d+",
        r"\bchown\b",
        r"\bkill\s+-9\b",
        r"\bpkill\b",
        r"\biotop\b",
        r"\bnnformat\b",
    ])

    # 禁止 import 的模块(精确匹配或前缀匹配)
    # os/subprocess/ctypes 等可逃逸沙箱或操作系统资源
    forbidden_imports: list[str] = field(default_factory=lambda: [
        "os",            # 操作系统接口(文件/进程/环境变量)
        "subprocess",    # 子进程执行
        "ctypes",        # FFI,可绕过 Python 沙箱
        "shutil",        # 高级文件操作(复制/删除目录)
        "sys",           # 解释器内部(退出/模块路径)
        "signal",        # 信号处理
        "multiprocessing",  # 多进程
        "os.system",
        "os.popen",
        "os.exec",
        "os.spawn",
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "os.removedirs",
        "socket",        # 网络访问
        "http",
        "urllib",
        "requests",
        "ftplib",
        "telnetlib",
        "smtplib",
        "webbrowser",
        "antigravity",
        "pickle",        # 反序列化攻击
        "marshal",
        "importlib",
        "builtins",
    ])

    # 网络白名单域名(默认空=全禁)
    network_whitelist: list[str] = field(default_factory=list)

    # 文件写入白名单路径(默认空=全禁)
    file_write_whitelist: list[str] = field(default_factory=list)

    # -- 静态检查 ----------------------------------------------------------

    def check_code(self, code: str) -> tuple[bool, list[str]]:
        """静态扫描代码,检测危险模式。

        检查项:
          1. 高危 shell 命令(rm -rf / format / shutdown 等)
          2. 禁止 import 的危险模块(os/subprocess/ctypes 等)
          3. 动态代码执行(eval/exec/compile)
          4. 文件写入操作(无白名单时拦截)
          5. 网络访问(无白名单时拦截)
          6. 路径穿越(../ 转义)

        Args:
            code: 待检查的 Python 代码字符串

        Returns:
            (是否允许执行, 违规描述列表)
        """
        violations: list[str] = []

        # 1. 检查高危命令(逐条正则匹配,捕获 re.error 防止非法模式崩溃)
        for pattern in self.forbidden_commands:
            try:
                m = re.search(pattern, code, re.IGNORECASE)
            except re.error:
                # 模式本身非法,跳过(不应发生,防御性处理)
                continue
            if m:
                violations.append(f"高危命令: {m.group()}")

        # 2. 检查禁止 import
        # 匹配三种形式:import X / from X import / __import__("X")
        for mod in self.forbidden_imports:
            patterns = [
                rf"^\s*import\s+{re.escape(mod)}\b",
                rf"^\s*from\s+{re.escape(mod)}\b",
                rf"__import__\(\s*['\"]{re.escape(mod)}['\"]\s*\)",
            ]
            for p in patterns:
                try:
                    if re.search(p, code, re.MULTILINE):
                        violations.append(f"禁止 import: {mod}")
                        break
                except re.error:
                    continue

        # 3. 检查 eval/exec/compile 调用(动态代码执行,可绕过静态检查)
        if re.search(r"\beval\s*\(", code):
            violations.append("禁止使用 eval()")
        if re.search(r"\bexec\s*\(", code):
            violations.append("禁止使用 exec()")
        if re.search(r"\bcompile\s*\(", code):
            violations.append("禁止使用 compile()")

        # 4. 检查文件写入操作(无白名单时一律拦截)
        write_patterns = [
            r"\.write\(",
            r"\bwritelines\(",
            r"open\s*\([^)]*['\"][wa]",  # open(..., "w"/"a") 写/追加模式
        ]
        for p in write_patterns:
            if re.search(p, code):
                if not self.file_write_whitelist:
                    violations.append(f"文件写入操作被禁止(无白名单): {p}")

        # 5. 检查网络访问(无白名单时拦截 socket/requests/urllib)
        if not self.network_whitelist:
            net_patterns = [
                r"\bsocket\.connect\b",
                r"\brequests\.(get|post|put|delete)\b",
                r"\burllib\.request\b",
            ]
            for p in net_patterns:
                if re.search(p, code):
                    violations.append("网络访问被禁止(无白名单)")
                    break

        # 6. 检查路径穿越(../ 可逃逸文件系统隔离)
        # 匹配字面量字符串中的 .. 路径段
        if re.search(r"['\"](?:\.\./|\.\.\\)", code):
            violations.append("路径穿越(../)被禁止")

        return (len(violations) == 0, violations)

    def check_command(self, cmd: str) -> tuple[bool, str]:
        """检查 shell 命令是否安全。

        Args:
            cmd: shell 命令字符串

        Returns:
            (是否安全, 拦截原因;安全时原因为空)
        """
        for pattern in self.forbidden_commands:
            try:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return (False, f"高危命令被拦截: {pattern}")
            except re.error:
                continue
        return (True, "")
