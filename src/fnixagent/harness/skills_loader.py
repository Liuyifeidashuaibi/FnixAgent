"""从 {workspace}/.fnix/skills 加载 Markdown 技能（Spec 7 扩展 frontmatter）。

支持两种格式：
  1. 纯 Markdown（向后兼容）：整段内容作为技能描述
  2. YAML frontmatter + Markdown（Spec 7 新增）：
     ---
     name: my-skill           # 可选，缺省用文件名
     description: 简短描述     # 可选，用于技能列表预览
     triggers: [关键词1, 关键词2]  # 可选，用于召回匹配
     priority: high            # 可选，high/normal/low
     ---
     技能正文 Markdown...

YAML frontmatter 解析零依赖（不引入 pyyaml），仅支持简单 key: value + list。
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from fnixagent.harness.paths import project_skills_dir

_cache: dict[str, list[HarnessSkill]] = {}
_cache_lock = threading.Lock()


@dataclass
class HarnessSkill:
    name: str
    path: str
    content: str
    # Spec 7: frontmatter 字段（可选，向后兼容纯 Markdown）
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    priority: str = "normal"  # high / normal / low
    # Trae Skill 系统：启用/禁用（frontmatter.enabled，缺省 true）
    enabled: bool = True


_FRONTMATTER_RE = re.compile(
    r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$",
    re.DOTALL,
)


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """解析 YAML frontmatter（零依赖，仅支持简单 key: value + list）。

    Returns:
        (metadata_dict, body_text)
    """
    if not text.startswith("---"):
        return {}, text
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw_meta = m.group(1)
    body = m.group(2).strip()
    meta: dict[str, object] = {}
    current_key: str | None = None
    current_list: list[str] | None = None
    for line in raw_meta.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # list item: - value
        if stripped.startswith("- ") and current_key is not None:
            val = stripped[2:].strip().strip('"').strip("'")
            if current_list is None:
                current_list = []
                meta[current_key] = current_list
            elif not isinstance(meta.get(current_key), list):
                # 之前是非 list 值，转换为 list
                prev = meta[current_key]
                current_list = [str(prev)] if prev else []
                meta[current_key] = current_list
            else:
                current_list = meta[current_key]  # type: ignore
            current_list.append(val)  # type: ignore
            continue
        # key: value
        if ":" in stripped:
            if current_list is not None:
                current_list = None  # 退出 list 模式
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            meta[key] = val
            current_key = key
    return meta, body


def _skill_name(path: Path, meta: dict[str, object]) -> str:
    """技能名优先级：frontmatter.name > 文件名（README 用父目录名）。"""
    name = meta.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    stem = path.stem
    if stem.lower() == "readme":
        return path.parent.name
    return stem


def load_workspace_skills(workspace: str, *, use_cache: bool = True) -> list[HarnessSkill]:
    """扫描 workspace/.fnix/skills/*.md（支持 frontmatter）。"""
    norm = os.path.normpath(os.path.abspath(workspace))
    if use_cache:
        with _cache_lock:
            cached = _cache.get(norm)
            if cached is not None:
                return list(cached)

    skills_dir = project_skills_dir(workspace)
    if not skills_dir.is_dir():
        return []

    found: list[HarnessSkill] = []
    for path in sorted(skills_dir.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not text:
            continue
        # 短 README 仅作说明跳过
        if path.name.lower() == "readme.md" and len(text) < 80:
            continue

        meta, body = _parse_frontmatter(text)
        content = body if body else text
        triggers_raw = meta.get("triggers")
        triggers = [str(t) for t in triggers_raw] if isinstance(triggers_raw, list) else []
        # enabled 字段：frontmatter.enabled = "false" / "true"（字符串，零依赖解析）
        enabled_raw = str(meta.get("enabled", "true")).strip().lower()
        enabled = enabled_raw not in ("false", "0", "no", "off", "disabled")
        found.append(
            HarnessSkill(
                name=_skill_name(path, meta),
                path=str(path),
                content=content[:8000],
                description=str(meta.get("description", ""))[:500],
                triggers=triggers,
                priority=str(meta.get("priority", "normal")).lower(),
                enabled=enabled,
            )
        )

    with _cache_lock:
        _cache[norm] = found
    return list(found)


def reload_workspace_skills(workspace: str) -> list[HarnessSkill]:
    """清除缓存并重新加载。"""
    norm = os.path.normpath(os.path.abspath(workspace))
    with _cache_lock:
        _cache.pop(norm, None)
    return load_workspace_skills(workspace, use_cache=False)


def format_skills_block(skills: list[HarnessSkill]) -> str:
    """格式化为 system prompt 追加块（跳过 enabled=False 的技能）。"""
    enabled_skills = [s for s in skills if s.enabled]
    if not enabled_skills:
        return ""
    lines = ["\n\n## 项目技能（.fnix/skills）"]
    for skill in enabled_skills[:12]:
        preview = skill.content.replace("\n", " ")[:240]
        if skill.description:
            lines.append(f"- **{skill.name}** [{skill.priority}]: {skill.description}")
            lines.append(f"  详情: {preview}")
        else:
            lines.append(f"- **{skill.name}**: {preview}")
        if skill.triggers:
            lines.append(f"  触发词: {', '.join(skill.triggers[:8])}")
    lines.append("执行时优先匹配上述技能描述。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trae Skill 系统：写入/删除/启停静态技能（对标 Trae Skills + Cursor Rules）
# ---------------------------------------------------------------------------


def _skill_file_path(workspace: str, name: str) -> Path:
    """返回 workspace/.fnix/skills/{name}.md 路径（自动加 .md 后缀）。"""
    skills_dir = project_skills_dir(workspace)
    safe_name = re.sub(r"[^\w\-\.]", "_", name.strip())
    if not safe_name.lower().endswith(".md"):
        safe_name += ".md"
    return skills_dir / safe_name


def _format_frontmatter(meta: dict[str, object]) -> str:
    """把 dict 格式化为 YAML frontmatter 文本（零依赖，简单 key: value + list）。"""
    lines = ["---"]
    for k, v in meta.items():
        if v is None or v == "":
            continue
        if isinstance(v, list):
            if not v:
                continue
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def write_workspace_skill(
    workspace: str,
    name: str,
    content: str,
    *,
    description: str = "",
    triggers: list[str] | None = None,
    priority: str = "normal",
    enabled: bool = True,
) -> HarnessSkill:
    """写入或更新一个静态技能到 .fnix/skills/{name}.md。"""
    path = _skill_file_path(workspace, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta: dict[str, object] = {
        "name": name,
        "description": description,
        "priority": priority,
        "enabled": enabled,
    }
    if triggers:
        meta["triggers"] = triggers
    text = f"{_format_frontmatter(meta)}\n\n{content.strip()}\n"
    path.write_text(text, encoding="utf-8")
    # 清缓存，确保下次 load 读到最新
    norm = os.path.normpath(os.path.abspath(workspace))
    with _cache_lock:
        _cache.pop(norm, None)
    # 返回新加载的技能
    skills = load_workspace_skills(workspace, use_cache=False)
    for s in skills:
        if s.name == name:
            return s
    # 兜底：直接构造
    return HarnessSkill(
        name=name,
        path=str(path),
        content=content[:8000],
        description=description[:500],
        triggers=triggers or [],
        priority=priority.lower(),
        enabled=enabled,
    )


def delete_workspace_skill(workspace: str, name: str) -> bool:
    """删除 .fnix/skills/{name}.md，返回是否删除成功。"""
    path = _skill_file_path(workspace, name)
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    norm = os.path.normpath(os.path.abspath(workspace))
    with _cache_lock:
        _cache.pop(norm, None)
    return True


def toggle_workspace_skill(workspace: str, name: str, enabled: bool) -> HarnessSkill | None:
    """切换技能 enabled 状态（重写 frontmatter）。"""
    skills = load_workspace_skills(workspace, use_cache=False)
    target = next((s for s in skills if s.name == name), None)
    if target is None:
        return None
    # 读原始文件，解析 frontmatter + body
    try:
        text = Path(target.path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta, body = _parse_frontmatter(text)
    meta["enabled"] = enabled
    new_text = f"{_format_frontmatter(meta)}\n\n{body.strip()}\n"
    Path(target.path).write_text(new_text, encoding="utf-8")
    norm = os.path.normpath(os.path.abspath(workspace))
    with _cache_lock:
        _cache.pop(norm, None)
    return HarnessSkill(
        name=target.name,
        path=target.path,
        content=body[:8000],
        description=target.description,
        triggers=target.triggers,
        priority=target.priority,
        enabled=enabled,
    )
