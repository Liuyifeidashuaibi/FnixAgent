"""Harness 用户配置 — ~/.fnix/config.toml 与 ~/.fnix/mcp.json。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import fnix_home
from fnixagent.harness.workspace import ensure_home_layout

_logger = logging.getLogger(__name__)


_MCP_DEFAULT = {
    "version": 1,
    "servers": [],
}

_mcp_registry: Any = None
_mcp_lock = threading.Lock()


def get_harness_mcp_registry() -> Any:
    """Harness 级 MCP 注册表（懒加载）。"""
    global _mcp_registry
    if _mcp_registry is None:
        with _mcp_lock:
            if _mcp_registry is None:
                from fnixagent.core.mcp.registry import MCPToolRegistry

                _mcp_registry = MCPToolRegistry()
    return _mcp_registry


def config_toml_path() -> Path:
    return fnix_home() / "config.toml"


def mcp_json_path() -> Path:
    return fnix_home() / "mcp.json"


def read_config_toml() -> dict[str, Any]:
    ensure_home_layout()
    path = config_toml_path()
    if not path.is_file():
        return {}
    try:
        try:
            import tomllib  # Python 3.11+ 标准库
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]  # Python 3.10 回退

        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("read_config_toml failed: %s", e)
        return {}


def _toml_value(value: Any) -> str:
    """把标量/list 值序列化为 TOML 字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'

def write_config_toml(data: dict[str, Any]) -> None:
    """写回 BYOK 配置 — read-modify-write，未知键（如 model_fallbacks）保留。"""
    ensure_home_layout()
    existing = read_config_toml()
    merged: dict[str, Any] = dict(existing)
    for key, value in (data or {}).items():
        if value is not None and value != "":
            merged[str(key)] = value
    mcp_block = merged.pop("mcp", None)

    lines: list[str] = []
    for key in ("provider", "model", "base_url"):
        if key in merged:
            lines.append(f"{key} = {_toml_value(merged.pop(key))}")
    for key, value in merged.items():
        if isinstance(value, dict):
            continue  # 保留未知嵌套段：跳过序列化但不清空语义认知（现有文件仅 mcp 段）
        lines.append(f"{key} = {_toml_value(value)}")
    lines.append("")
    lines.append("[mcp]")
    lines.append("# servers configured via mcp.json")
    config_toml_path().write_text("\n".join(lines), encoding="utf-8")


def read_mcp_config() -> dict[str, Any]:
    ensure_home_layout()
    path = mcp_json_path()
    if not path.is_file():
        default = dict(_MCP_DEFAULT)
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return dict(_MCP_DEFAULT)


def write_mcp_config(data: dict[str, Any]) -> None:
    ensure_home_layout()
    path = mcp_json_path()
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def list_mcp_servers() -> list[dict[str, Any]]:
    cfg = read_mcp_config()
    servers = cfg.get("servers")
    if not isinstance(servers, list):
        return []
    return [s for s in servers if isinstance(s, dict)]


def apply_mcp_to_registry(registry: Any) -> int:
    """将 ~/.fnix/mcp.json 中的 stdio servers 注册到 MCP registry。

    Trust ledger fail-closed: unapproved servers are skipped and logged.
    """
    import logging

    from fnixagent.core.mcp.trust import McpTrustError
    from fnixagent.core.mcp.types import MCPTransport

    log = logging.getLogger("fnix.mcp")
    count = 0
    for server in list_mcp_servers():
        if not server.get("enabled", True):
            continue
        name = str(server.get("name") or "").strip()
        command = server.get("command")
        if not name or not command:
            continue
        try:
            if isinstance(command, str):
                parts = command.split()
            elif isinstance(command, list):
                parts = [str(x) for x in command]
            else:
                continue
            if not parts:
                continue
            registry.register_server(
                server_id=name,
                transport=MCPTransport.STDIO,
                command=parts[0],
                args=parts[1:] or None,
                env=server.get("env") if isinstance(server.get("env"), dict) else None,
                auto_connect=False,
            )
            count += 1
        except McpTrustError as exc:
            log.warning("MCP trust blocked server %s: %s", name, exc)
            continue
        except Exception as exc:
            log.warning("MCP register failed for %s: %s", name, exc)
            continue
    return count


def reload_harness_mcp() -> int:
    """启动或配置更新后重载 MCP。"""
    registry = get_harness_mcp_registry()
    return apply_mcp_to_registry(registry)


def attach_mcp_tools_to_registry(tool_registry: Any, *, connect: bool = True) -> list[str]:
    """将 ~/.fnix/mcp.json 中的 MCP 工具挂到本地 ToolRegistry（best-effort）。

    - 空配置 / 连接失败：返回 []，不抛错，不改变现有 Work 行为
    - 可用环境变量 FNIX_MCP_IN_LOOP=0 关闭挂载
    """
    if os.getenv("FNIX_MCP_IN_LOOP", "1").strip() in ("0", "false", "False", "no"):
        return []
    enabled = [
        s
        for s in list_mcp_servers()
        if s.get("enabled", True) and str(s.get("name") or "").strip() and s.get("command")
    ]
    if not enabled:
        return []
    try:
        mcp = get_harness_mcp_registry()
        apply_mcp_to_registry(mcp)
        if connect:
            for info in mcp.list_servers():
                try:
                    mcp.sync_tools(info.server_id)
                except Exception:
                    _logger.debug("Unhandled exception", exc_info=True)
                    continue
        return mcp.register_to_tool_registry(tool_registry)
    except Exception:
        return []
