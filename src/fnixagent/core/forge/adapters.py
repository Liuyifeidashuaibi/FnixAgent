"""FnixForge — 被测 Agent（SUT）驱动适配器。

用户的半成品 Agent 形态各异：CLI、HTTP 服务、Python 可调用入口。
Forge 不假设形态，统一收敛为一次 `invoke(prompt, workspace) -> TargetResponse`：

  for task in suite:
      resp = adapter.invoke(task.prompt, sandbox_dir)
      checks = run_checks(task, resp, sandbox_dir)

适配器配置由 probe 自动生成，可落盘为目标项目根目录的 `forge.config.json`，
也可由用户在 CLI / API 中显式覆盖。命令模板占位符：
  {prompt_b64}  — base64 后的 prompt（避免 shell 引号地狱，推荐）
  {prompt}      — 原始 prompt（仅 http body_template / 无特殊字符时用）
  {workspace}   — 沙箱目录绝对路径
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

_logger = logging.getLogger(__name__)

CONFIG_FILENAME = "forge.config.json"


@dataclass
class TargetResponse:
    """一次被测 Agent 调用的完整轨迹。"""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    # http 模式下结构化回复文本（供 output_contract checks）
    message: str = ""
    elapsed_s: float = 0.0
    error: str = ""            # 适配器层错误（超时 / 连接失败），exit_code 语义外的失败
    files_before: dict[str, str] = field(default_factory=dict)  # relpath -> sha1
    files_after: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> dict[str, str]:
        """运行时实际发生改动的路径（新增 / 修改）。"""
        out: dict[str, str] = {}
        for p, h in self.files_after.items():
            if self.files_before.get(p) != h:
                out[p] = h
        return out

    @property
    def removed(self) -> list[str]:
        return [p for p in self.files_before if p not in self.files_after]


class TargetAdapter(Protocol):
    """SUT 驱动协议。"""

    name: str

    def invoke(self, prompt: str, workspace: Path, *, timeout_s: int) -> TargetResponse: ...


@dataclass
class AdapterConfig:
    """目标 Agent 接入配置（落盘文件 forge.config.json 的 schema）。"""

    type: str = "cli"                    # cli | http | callable
    # --- cli ---
    command: str = ""                    # 模板；占位符见模块 docstring
    cwd: str = "."                       # 相对目标项目根目录
    env: dict[str, str] = field(default_factory=dict)
    capture_output: bool = True
    # --- http ---
    endpoint: str = ""
    method: str = "POST"
    body_template: dict[str, Any] = field(default_factory=dict)  # 值中可用 {prompt}/{workspace}
    response_field: str = ""            # 从 JSON 响应中提取回复文本的 dot 路径，如 "choices.0.message"
    headers: dict[str, str] = field(default_factory=dict)
    # --- 通用 ---
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdapterConfig":
        known = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: v for k, v in data.items() if k in known}
        extra = dict(data.get("extra") or {})
        for k, v in data.items():
            if k not in known:
                extra[k] = v
        kwargs["extra"] = extra
        return cls(**kwargs)

    @classmethod
    def load(cls, target_root: Path) -> "AdapterConfig | None":
        p = Path(target_root) / CONFIG_FILENAME
        if not p.is_file():
            return None
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            _logger.warning("invalid %s: %s", p, e)
            return None

    def save(self, target_root: Path) -> Path:
        p = Path(target_root) / CONFIG_FILENAME
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


def _render(template: str, mapping: dict[str, str]) -> str:
    out = template
    for k, v in mapping.items():
        out = out.replace("{" + k + "}", v)
    return out

_SHELL_METACHAR_CHARS = set("|&;<>`")
_SHELL_METACHAR_TOKENS = ("$(",)

def _has_shell_metachars(command: str) -> bool:
    """扫描**引号外**是否存在 shell 元字符。

    `python -c \"assert a==b; print(x)\"` 里的分号在引号内，不算 shell 语法。
    """
    in_single = in_double = False
    prev = ""
    for ch in command:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not (in_single or in_double):
            if ch in _SHELL_METACHAR_CHARS:
                return True
        prev = ch
    if "$" in command:
        # $VAR / ${VAR} 环境量展开需要 shell（CliAdapter 已手动替换过已知量）
        return True
    for tok in _SHELL_METACHAR_TOKENS:
        if tok in command:
            return True
    return False

def split_or_shell(command: str) -> tuple[list[str] | str, bool]:
    """尽量用 shell=False 执行（沙箱友好）；仅当引号外存在 shell 元字符时才启用 shell。

    返回 (args, use_shell)。
    """
    if _has_shell_metachars(command):
        return command, True
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        return command, True
    if not parts:
        return command, True
    return parts, False


class CliAdapter:
    """命令行 SUT：每个任务在沙箱中执行一条命令。"""

    name = "cli"

    def __init__(self, target_root: Path, config: AdapterConfig) -> None:
        self.target_root = Path(target_root)
        self.config = config

    def invoke(self, prompt: str, workspace: Path, *, timeout_s: int) -> TargetResponse:
        resp = TargetResponse()
        mapping = {
            "prompt": prompt,
            "prompt_b64": base64.b64encode(prompt.encode("utf-8")).decode("ascii"),
            "workspace": str(workspace),
        }
        rendered = _render(self.config.command, mapping)
        # 常见写法 `python main.py "$FNIX_FORGE_WORKSPACE"` 在 shell=False 下不会展开，
        # 这里手动替换，保证两种执行模式行为一致。
        rendered = rendered.replace("$FNIX_FORGE_WORKSPACE", str(workspace))
        rendered = rendered.replace("""'$FNIX_FORGE_WORKSPACE'""", str(workspace))
        rendered = rendered.replace("$FNIX_FORGE_PROMPT_B64", mapping["prompt_b64"])
        cwd = self.target_root / self.config.cwd if self.config.cwd != "." else self.target_root
        env = dict(os.environ)
        env.update(self.config.env)
        env.setdefault("FNIX_FORGE_WORKSPACE", str(workspace))
        env.setdefault("FNIX_FORGE_PROMPT_B64", mapping["prompt_b64"])
        args, use_shell = split_or_shell(rendered)
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                args,
                shell=use_shell,
                cwd=str(cwd),
                env=env,
                capture_output=self.config.capture_output,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s or None,
            )
            resp.exit_code = int(proc.returncode or 0)
            resp.stdout = proc.stdout or ""
            resp.stderr = proc.stderr or ""
        except subprocess.TimeoutExpired as e:
            resp.error = f"timeout after {timeout_s}s"
            resp.stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            resp.stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            resp.exit_code = -1
        except Exception as e:
            resp.error = str(e)
            resp.exit_code = -1
        resp.elapsed_s = time.perf_counter() - t0
        return resp


class HttpAdapter:
    """HTTP 服务形态 SUT：POST prompt 到其 endpoint。"""

    name = "http"

    def __init__(self, target_root: Path, config: AdapterConfig) -> None:
        self.target_root = Path(target_root)
        self.config = config

    def _render_body(self, template: Any, mapping: dict[str, str]) -> Any:
        if isinstance(template, str):
            return _render(template, mapping)
        if isinstance(template, dict):
            return {k: self._render_body(v, mapping) for k, v in template.items()}
        if isinstance(template, list):
            return [self._render_body(v, mapping) for v in template]
        return template

    def invoke(self, prompt: str, workspace: Path, *, timeout_s: int) -> TargetResponse:
        resp = TargetResponse()
        mapping = {"prompt": prompt, "workspace": str(workspace)}
        body = self._render_body(self.config.body_template or {"prompt": "{prompt}"}, mapping)
        headers = {"Content-Type": "application/json", **self.config.headers}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.config.endpoint, data=data, method=self.config.method or "POST", headers=headers
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s or 120) as r:
                raw = r.read().decode("utf-8", errors="replace")
                resp.stdout = raw
                resp.exit_code = int(r.status)
                try:
                    payload = json.loads(raw)
                    node: Any = payload
                    for part in (self.config.response_field or "").split("."):
                        if not part:
                            continue
                        if isinstance(node, list) and part.isdigit():
                            node = node[int(part)]
                        elif isinstance(node, dict):
                            node = node.get(part, "")
                        else:
                            node = ""
                    resp.message = node if isinstance(node, str) else json.dumps(node, ensure_ascii=False)
                except Exception:
                    resp.message = raw
        except urllib.error.HTTPError as e:
            resp.exit_code = int(e.code)
            resp.error = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as e:
            resp.error = str(e)
            resp.exit_code = -1
        resp.elapsed_s = time.perf_counter() - t0
        return resp


class CallableAdapter:
    """测试 / mock 用：直接注入 Python 可调用。"""

    name = "callable"

    def __init__(self, fn: Callable[[str, Path], Any]) -> None:
        self.fn = fn

    def invoke(self, prompt: str, workspace: Path, *, timeout_s: int) -> TargetResponse:
        resp = TargetResponse()
        t0 = time.perf_counter()
        try:
            out = self.fn(prompt, workspace)
            if isinstance(out, TargetResponse):
                out.elapsed_s = time.perf_counter() - t0
                return out
            if isinstance(out, str):
                resp.stdout = out
                resp.message = out
            elif isinstance(out, dict):
                resp.message = json.dumps(out, ensure_ascii=False)
        except Exception as e:
            resp.error = str(e)
            resp.exit_code = -1
        resp.elapsed_s = time.perf_counter() - t0
        return resp


def make_adapter(config: AdapterConfig, target_root: Path) -> CliAdapter | HttpAdapter:
    if config.type == "cli":
        return CliAdapter(target_root, config)
    if config.type == "http":
        return HttpAdapter(target_root, config)
    raise ValueError(f"unsupported adapter type: {config.type!r} (use cli|http; callable is programmatic)")


def resolve_adapter(target_root: Path, config: AdapterConfig | None) -> CliAdapter | HttpAdapter:
    """优先级：显式 config > 目标项目 forge.config.json > probe 自动建议。"""
    cfg = config or AdapterConfig.load(target_root)
    if cfg is None:
        from fnixagent.core.forge.probe import probe_target

        proposal = probe_target(target_root)
        if proposal.config is None:
            raise RuntimeError(
                f"无法自动探测 {target_root} 的调用方式；"
                f"请在其根目录创建 {CONFIG_FILENAME} 或以 --config 显式提供适配器配置"
            )
        cfg = proposal.config
    return make_adapter(cfg, target_root)


def shlex_quote(s: str) -> str:
    return shlex.quote(s)
