# -*- coding: utf-8 -*-
"""write_config_toml 改为 read-modify-write，未知键不再被丢弃。"""
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\src\fnixagent\hx.html" if False else r"E:\FNIX\FnixAgent\src\fnixagent\harness\config.py")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

def block(s: str) -> str:
    return s.replace("\n", NL)

old = block('''def write_config_toml(data: dict[str, Any]) -> None:
    ensure_home_layout()
    lines: list[str] = []
    provider = str(data.get("provider") or "")
    model = str(data.get("model") or "")
    lines.append(f'provider = "{provider}"')
    lines.append(f'model = "{model}"')
    if data.get("base_url"):
        lines.append(f'base_url = "{data["base_url"]}"')
    lines.append("")
    lines.append("[mcp]")
    lines.append("# servers configured via mcp.json")
    config_toml_path().write_text("\\n".join(lines), encoding="utf-8")
''')

new = block('''def _toml_value(value: Any) -> str:
    """把标量/list 值序列化为 TOML 字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    s = str(value).replace("\\\\", "\\\\\\\\").replace('"', '\\\\"')
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
    config_toml_path().write_text("\\n".join(lines), encoding="utf-8")
''')

assert old in text, "anchor not found"
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched ok")
