"""
ContextBuilder - 上下文工程引擎
================================
对标 Trae Context Engineering 和 Codex 上下文组装。

设计要点:
  - 优先级驱动的上下文组装 (系统 > 任务 > 约定 > 代码 > 依赖 > 历史 > 仓库地图)
  - Token 预算内按优先级截断 (超限时丢弃低优先级条目)
  - 多源融合: CodeIndexer 语义切片 + 符号定义 + MemoryManager 历史 + 项目约定
  - 零外部依赖: 仅 Python stdlib (pathlib / re / tomllib)

组装策略 (对标 Trae Context Engineering):
  1. 任务相关代码切片 (CodeIndexer.search_code)
  2. 依赖符号定义 (CodeIndexer.get_symbol_info)
  3. 历史上下文 (MemoryManager)
  4. 项目约定 (文件读取)
  5. Token 预算内优先级排序

Usage:
    builder = ContextBuilder(indexer, memory_manager)
    ctx = await builder.build_context(task, token_budget=32000)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ============================================================================
# 数据结构
# ============================================================================

class ContextPriority(Enum):
    """上下文优先级 (数值越小优先级越高)。"""
    SYSTEM = 0          # 系统提示 (最高)
    TASK = 1            # 任务描述
    CONVENTIONS = 2     # 项目约定
    RELEVANT_CODE = 3   # 相关代码切片
    DEPENDENCIES = 4    # 依赖符号定义
    HISTORY = 5         # 历史上下文
    REPO_MAP = 6        # 仓库地图
    EXTRA = 7           # 额外信息


@dataclass
class ContextEntry:
    """上下文条目。

    Attributes:
        priority: 优先级 (数值越小越重要)
        content: 条目文本内容
        source: 来源描述 (例如文件路径 / "CodeIndexer.search_code")
        token_estimate: 估算 token 数
        metadata: 附加元数据
    """
    priority: ContextPriority
    content: str
    source: str = ""                        # 来源描述
    token_estimate: int = 0                 # 估算 token 数
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuiltContext:
    """构建完成的上下文。

    Attributes:
        messages: LLM 消息列表 (role/content)
        total_tokens: 总 token 估算
        entries: 所有条目 (含被截断的, 便于调试)
        truncated: 是否因 token 预算被截断
    """
    messages: list[dict[str, str]]          # LLM 消息列表
    total_tokens: int                       # 总 token 估算
    entries: list[ContextEntry]             # 所有条目
    truncated: bool = False                 # 是否被截断


# ============================================================================
# ContextBuilder 主类
# ============================================================================

# 默认系统提示 (编码智能体通用)
_DEFAULT_SYSTEM_PROMPT = (
    "你是一名资深编码智能体。请基于提供的项目约定、相关代码切片、"
    "依赖符号定义和历史上下文, 准确理解任务并生成高质量的代码变更。"
    "严格遵循项目既有风格与约定, 不臆造未提供的符号或接口。"
)

# CJK 统一表意文字范围 (用于 token 估算的中英文区分)
_CJK_RANGE = re.compile(
    "[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    "\U00020000-\U0002a6df\U0002a700-\U0002b73f]"
)

# 标识符提取正则 (CamelCase / snake_case, 长度 >= 3)
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")


class ContextBuilder:
    """上下文工程引擎 (对标 Trae Context Engineering)。

    组装策略:
      1. 任务相关代码切片 (CodeIndexer.search_code)
      2. 依赖符号定义 (CodeIndexer.get_symbol_info)
      3. 历史上下文 (MemoryManager)
      4. 项目约定 (文件读取)
      5. Token 预算内优先级排序

    Usage:
        builder = ContextBuilder(indexer, memory_manager)
        ctx = await builder.build_context(task, token_budget=32000)
    """

    # 项目约定候选文件 (按优先级)
    _CONVENTIONS_FILES: tuple[str, ...] = (
        "CONVENTIONS.md",
        "conventions.md",
        ".editorconfig",
        "pyproject.toml",
    )

    def __init__(
        self,
        indexer: Any,
        memory_manager: Any | None = None,
        project_root: str = ".",
    ) -> None:
        """初始化上下文构建器。

        Args:
            indexer: CodeIndexer 实例 (提供 search_code / get_symbol_info / get_repo_map)
            memory_manager: 可选的 MemoryManager 实例 (提供 load_context)
            project_root: 项目根目录 (用于读取约定文件)
        """
        self._indexer = indexer
        self._memory = memory_manager
        self._root = Path(project_root).resolve()

    # ========================================================================
    # 主入口
    # ========================================================================

    async def build_context(
        self,
        task: str,
        *,
        token_budget: int = 32000,
        system_prompt: str = "",
    ) -> BuiltContext:
        """组装编码任务上下文。

        流程:
          1. 系统提示 (优先级 0)
          2. 任务描述 (优先级 1)
          3. 项目约定 (优先级 2, 读取 CONVENTIONS.md / .editorconfig / pyproject.toml)
          4. 相关代码切片 (优先级 3, CodeIndexer.search_code)
          5. 依赖符号定义 (优先级 4, CodeIndexer.get_symbol_info)
          6. 历史上下文 (优先级 5, MemoryManager.load_context)
          7. 仓库地图 (优先级 6, CodeIndexer.get_repo_map)
          8. Token 预算内按优先级排序, 超限截断

        Args:
            task: 编码任务描述 (自然语言)
            token_budget: Token 预算上限
            system_prompt: 自定义系统提示 (为空则使用默认编码智能体提示)

        Returns:
            BuiltContext 构建完成的上下文
        """
        sys_prompt = system_prompt.strip() or _DEFAULT_SYSTEM_PROMPT
        entries: list[ContextEntry] = []

        # 1. 系统提示 (优先级 0)
        entries.append(ContextEntry(
            priority=ContextPriority.SYSTEM,
            content=sys_prompt,
            source="system_prompt",
            token_estimate=self._estimate_tokens(sys_prompt),
        ))

        # 2. 任务描述 (优先级 1)
        task_text = task.strip()
        if task_text:
            entries.append(ContextEntry(
                priority=ContextPriority.TASK,
                content=task_text,
                source="user_task",
                token_estimate=self._estimate_tokens(task_text),
            ))

        # 3. 项目约定 (优先级 2)
        conventions = self._read_conventions()
        if conventions:
            entries.append(ContextEntry(
                priority=ContextPriority.CONVENTIONS,
                content=conventions,
                source="project_conventions",
                token_estimate=self._estimate_tokens(conventions),
            ))

        # 4. 相关代码切片 (优先级 3)
        relevant_slices: list[Any] = []
        try:
            relevant_slices = await self._indexer.search_code(task, top_k=10)
        except Exception as exc:  # noqa: BLE001
            entries.append(ContextEntry(
                priority=ContextPriority.RELEVANT_CODE,
                content=f"(代码切片检索失败: {type(exc).__name__}: {exc})",
                source="CodeIndexer.search_code",
                token_estimate=20,
                metadata={"error": str(exc)},
            ))
        if relevant_slices:
            code_text = self._format_code_slices(relevant_slices)
            entries.append(ContextEntry(
                priority=ContextPriority.RELEVANT_CODE,
                content=code_text,
                source="CodeIndexer.search_code",
                token_estimate=self._estimate_tokens(code_text),
                metadata={"slice_count": len(relevant_slices)},
            ))

        # 5. 依赖符号定义 (优先级 4)
        deps_text = self._collect_dependency_definitions(task, relevant_slices)
        if deps_text:
            entries.append(ContextEntry(
                priority=ContextPriority.DEPENDENCIES,
                content=deps_text,
                source="CodeIndexer.get_symbol_info",
                token_estimate=self._estimate_tokens(deps_text),
            ))

        # 6. 历史上下文 (优先级 5)
        history_text = self._collect_history(task)
        if history_text:
            entries.append(ContextEntry(
                priority=ContextPriority.HISTORY,
                content=history_text,
                source="MemoryManager.load_context",
                token_estimate=self._estimate_tokens(history_text),
            ))

        # 7. 仓库地图 (优先级 6)
        repo_map_text = ""
        try:
            repo_map_text = self._indexer.get_repo_map(max_tokens=2048)
        except Exception:  # noqa: BLE001
            repo_map_text = ""
        if repo_map_text:
            entries.append(ContextEntry(
                priority=ContextPriority.REPO_MAP,
                content=repo_map_text,
                source="CodeIndexer.get_repo_map",
                token_estimate=self._estimate_tokens(repo_map_text),
            ))

        # 8. Token 预算内按优先级排序, 超限截断
        kept_entries, truncated = self._truncate_by_budget(entries, token_budget)
        total_tokens = sum(e.token_estimate for e in kept_entries)

        # 组装 LLM 消息
        messages = self._build_messages(kept_entries, sys_prompt)

        return BuiltContext(
            messages=messages,
            total_tokens=total_tokens,
            entries=kept_entries,
            truncated=truncated,
        )

    # ========================================================================
    # 内部: Token 估算
    # ========================================================================

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数 (中文 1.5 字/token, 英文 4 字符/token)。

        采用混合折中策略:
          - CJK 字符按 1.5 字/token 估算 (中文信息密度高)
          - 非 CJK 字符按 4 字符/token 估算 (英文/代码平均)
          - 混合文本按字符类别分别累计后求和

        Args:
            text: 待估算文本

        Returns:
            估算的 token 数 (至少为 1, 当文本非空时)
        """
        if not text:
            return 0
        cjk_count = len(_CJK_RANGE.findall(text))
        non_cjk_count = len(text) - cjk_count
        # 中文 ~1.5 字/token, 英文 ~4 字符/token
        tokens = cjk_count / 1.5 + non_cjk_count / 4.0
        return max(1, int(round(tokens)))

    # ========================================================================
    # 内部: 项目约定读取
    # ========================================================================

    def _read_conventions(self) -> str:
        """读取项目约定文件 (CONVENTIONS.md / .editorconfig / pyproject.toml [tool.ruff])。

        依次尝试读取项目根目录下的:
          1. CONVENTIONS.md (或 conventions.md) — 全文
          2. .editorconfig — 全文
          3. pyproject.toml — 仅提取 [tool.ruff] 段

        Returns:
            拼接后的约定文本 (各段以标题分隔); 无可用文件时返回空字符串
        """
        sections: list[str] = []

        # 1. CONVENTIONS.md
        for name in ("CONVENTIONS.md", "conventions.md"):
            fp = self._root / name
            if fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
                if content:
                    sections.append(f"### 项目约定 ({name})\n{content}")
                break

        # 2. .editorconfig
        ec_path = self._root / ".editorconfig"
        if ec_path.is_file():
            try:
                content = ec_path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                content = ""
            if content:
                sections.append(f"### 编辑器配置 (.editorconfig)\n{content}")

        # 3. pyproject.toml [tool.ruff] 段
        pp_path = self._root / "pyproject.toml"
        if pp_path.is_file():
            ruff_section = self._extract_ruff_section(pp_path)
            if ruff_section:
                sections.append(
                    f"### 代码风格 (pyproject.toml [tool.ruff])\n{ruff_section}"
                )

        return "\n\n".join(sections)

    def _extract_ruff_section(self, pyproject_path: Path) -> str:
        """从 pyproject.toml 中提取 [tool.ruff] 段内容。

        优先使用 stdlib tomllib (Python 3.11+); 不可用时回退到正则启发式提取。

        Args:
            pyproject_path: pyproject.toml 路径

        Returns:
            [tool.ruff] 段的文本表示; 不存在时返回空字符串
        """
        try:
            raw = pyproject_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

        # 优先使用 tomllib 精确解析
        try:
            import tomllib  # type: ignore[import-not-found]
            try:
                data = tomllib.loads(raw)
                ruff_cfg = data.get("tool", {}).get("ruff")
                if ruff_cfg:
                    return self._format_ruff_config(ruff_cfg)
            except Exception:  # noqa: BLE001
                pass
        except ImportError:
            pass

        # 回退: 正则提取 [tool.ruff] 段 (到下一个 [...] 段或文件末尾)
        pattern = re.compile(
            r"^\[tool\.ruff[^\]]*\]\s*\n(.*?)(?=^\[|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(raw)
        if match:
            return match.group(1).strip()
        return ""

    def _format_ruff_config(self, ruff_cfg: dict[str, Any]) -> str:
        """将 tomllib 解析出的 [tool.ruff] dict 格式化为可读文本。

        Args:
            ruff_cfg: ruff 配置字典

        Returns:
            格式化后的文本
        """
        lines: list[str] = []
        for key, value in ruff_cfg.items():
            if isinstance(value, (list, tuple)):
                items = ", ".join(str(v) for v in value)
                lines.append(f"{key} = [{items}]")
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, (list, tuple)):
                        items = ", ".join(str(v) for v in sub_value)
                        lines.append(f"{key}.{sub_key} = [{items}]")
                    else:
                        lines.append(f"{key}.{sub_key} = {sub_value}")
            else:
                lines.append(f"{key} = {value}")
        return "\n".join(lines)

    # ========================================================================
    # 内部: 代码切片格式化
    # ========================================================================

    def _format_code_slices(self, slices: list[Any]) -> str:
        """格式化代码切片列表为可读文本。

        Args:
            slices: CodeSlice 列表

        Returns:
            格式化后的代码切片文本
        """
        parts: list[str] = []
        for sl in slices:
            file_path = getattr(sl, "file", "<unknown>")
            symbol = getattr(sl, "symbol_name", "<unknown>")
            start_line = getattr(sl, "start_line", 0)
            end_line = getattr(sl, "end_line", 0)
            content = getattr(sl, "content", "")
            header = f"### {file_path} :: {symbol} (L{start_line}-{end_line})"
            parts.append(f"{header}\n```\n{content}\n```")
        return "\n\n".join(parts)

    # ========================================================================
    # 内部: 依赖符号定义收集
    # ========================================================================

    def _collect_dependency_definitions(
        self,
        task: str,
        slices: list[Any],
    ) -> str:
        """收集任务和代码切片中引用的符号定义。

        策略:
          1. 从代码切片的 symbol_name 字段收集符号名
          2. 从任务文本中提取标识符 (CamelCase / snake_case)
          3. 去重后调用 indexer.get_symbol_info 获取定义
          4. 格式化为 "签名 + 位置 + docstring" 文本

        Args:
            task: 任务描述
            slices: 相关代码切片

        Returns:
            依赖符号定义文本; 无可用符号时返回空字符串
        """
        # 收集候选符号名
        candidates: list[str] = []
        seen: set[str] = set()

        for sl in slices:
            name = getattr(sl, "symbol_name", "")
            if name and name not in seen:
                seen.add(name)
                candidates.append(name)

        for match in _IDENTIFIER_RE.finditer(task):
            name = match.group(0)
            if name not in seen:
                seen.add(name)
                candidates.append(name)

        # 查询定义 (限制数量避免上下文爆炸)
        definitions: list[str] = []
        max_defs = 15
        for name in candidates:
            if len(definitions) >= max_defs:
                break
            try:
                sym = self._indexer.get_symbol_info(name)
            except Exception:  # noqa: BLE001
                sym = None
            if sym is None:
                continue
            # 跳过已经在相关代码切片中完整呈现的符号
            if any(getattr(sl, "symbol_name", "") == name for sl in slices):
                continue
            definitions.append(self._format_symbol_definition(sym))

        return "\n\n".join(definitions)

    def _format_symbol_definition(self, symbol: Any) -> str:
        """格式化单个符号定义为可读文本。

        Args:
            symbol: SymbolInfo 实例

        Returns:
            格式化后的符号定义文本
        """
        name = getattr(symbol, "name", "<unknown>")
        signature = getattr(symbol, "signature", "") or f"(symbol: {name})"
        docstring = getattr(symbol, "docstring", "") or ""
        location = getattr(symbol, "location", None)
        kind = getattr(getattr(symbol, "kind", None), "value", "unknown")

        loc_str = ""
        if location is not None:
            file_path = getattr(location, "file", "<unknown>")
            start_line = getattr(location, "start_line", 0)
            loc_str = f" @ {file_path}:L{start_line}"

        parts = [f"- **{name}** ({kind}){loc_str}", f"  `{signature}`"]
        if docstring:
            # docstring 首行 + 缩进展示
            first_line = docstring.strip().splitlines()[0]
            parts.append(f"  {first_line}")
        return "\n".join(parts)

    # ========================================================================
    # 内部: 历史上下文收集
    # ========================================================================

    def _collect_history(self, task: str) -> str:
        """从 MemoryManager 加载历史上下文。

        Args:
            task: 当前任务 (作为检索 query)

        Returns:
            格式化后的历史上下文文本; 无 MemoryManager 或无历史时返回空字符串
        """
        if self._memory is None:
            return ""
        try:
            ctx = self._memory.load_context(query=task, user_id="")
        except Exception:  # noqa: BLE001
            return ""
        if not ctx:
            return ""

        parts: list[str] = []

        # 短期对话历史
        short_term = ctx.get("short_term") or []
        if short_term:
            history_lines: list[str] = []
            for msg in short_term:
                role = self._get_msg_role(msg)
                content = self._get_msg_content(msg)
                if content:
                    history_lines.append(f"[{role}] {content}")
            if history_lines:
                parts.append("#### 对话历史\n" + "\n".join(history_lines))

        # 长期记忆
        long_term = ctx.get("long_term") or []
        if long_term:
            memory_lines: list[str] = []
            for item in long_term:
                content = getattr(item, "content", "") or str(item)
                if content:
                    memory_lines.append(f"- {content}")
            if memory_lines:
                parts.append("#### 长期记忆\n" + "\n".join(memory_lines))

        # 实体 (用户画像等)
        entity = ctx.get("entity")
        if entity is not None:
            ent_name = getattr(entity, "name", "")
            ent_type = getattr(entity, "entity_type", "")
            attrs = getattr(entity, "attributes", {}) or {}
            if ent_name or attrs:
                attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items())
                parts.append(
                    f"#### 实体 ({ent_type}: {ent_name})\n{attr_str}"
                )

        return "\n\n".join(parts)

    @staticmethod
    def _get_msg_role(msg: Any) -> str:
        """从消息对象提取 role 字符串。

        Args:
            msg: Message 对象或 dict

        Returns:
            role 字符串
        """
        role = getattr(msg, "role", None)
        if role is not None:
            return getattr(role, "value", str(role))
        if isinstance(msg, dict):
            return str(msg.get("role", "?"))
        return "?"

    @staticmethod
    def _get_msg_content(msg: Any) -> str:
        """从消息对象提取 content 字符串。

        Args:
            msg: Message 对象或 dict

        Returns:
            content 字符串
        """
        content = getattr(msg, "content", None)
        if content is not None:
            return str(content)
        if isinstance(msg, dict):
            return str(msg.get("content", ""))
        return ""

    # ========================================================================
    # 内部: 预算截断
    # ========================================================================

    def _truncate_by_budget(
        self,
        entries: list[ContextEntry],
        token_budget: int,
    ) -> tuple[list[ContextEntry], bool]:
        """按优先级截断条目以适配 token 预算。

        策略:
          - 按 ContextPriority 数值升序排序 (数值越小优先级越高)
          - 同优先级保持原始顺序 (稳定排序)
          - 依次纳入条目, 累计 token; 超预算时停止
          - SYSTEM 优先级条目强制保留 (即使超预算)

        Args:
            entries: 全部候选条目
            token_budget: token 预算上限

        Returns:
            (保留的条目列表, 是否发生截断)
        """
        # 稳定排序: 按 priority.value 升序
        ordered = sorted(
            entries,
            key=lambda e: (e.priority.value,),
        )

        kept: list[ContextEntry] = []
        accumulated = 0
        truncated = False

        for entry in ordered:
            # SYSTEM 强制保留
            if entry.priority == ContextPriority.SYSTEM:
                kept.append(entry)
                accumulated += entry.token_estimate
                continue
            # 预算检查
            if accumulated + entry.token_estimate > token_budget:
                truncated = True
                continue
            kept.append(entry)
            accumulated += entry.token_estimate

        return kept, truncated

    # ========================================================================
    # 内部: 消息组装
    # ========================================================================

    def _build_messages(
        self,
        entries: list[ContextEntry],
        system_prompt: str,
    ) -> list[dict[str, str]]:
        """将条目转换为 LLM 消息列表。

        规则:
          - 第一条为 system 消息, 内容为 system_prompt
          - 其余非 SYSTEM 条目按优先级合并为一条 user 消息
          - 每个条目以优先级名称作为分节标题

        Args:
            entries: 保留的上下文条目 (已按预算截断)
            system_prompt: 系统提示文本

        Returns:
            LLM 消息列表, 每条形如 {"role": "system"/"user", "content": "..."}
        """
        messages: list[dict[str, str]] = []

        # 第一条 system 消息
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 非 SYSTEM 条目合并为 user 消息
        user_sections: list[str] = []
        # 按优先级排序, 保持可读顺序
        non_system = sorted(
            [e for e in entries if e.priority != ContextPriority.SYSTEM],
            key=lambda e: (e.priority.value,),
        )
        for entry in non_system:
            section_title = entry.priority.name
            source_tag = f" ({entry.source})" if entry.source else ""
            header = f"## {section_title}{source_tag}"
            user_sections.append(f"{header}\n{entry.content}")

        if user_sections:
            user_content = "\n\n".join(user_sections)
            messages.append({"role": "user", "content": user_content})

        return messages


__all__ = [
    "ContextBuilder", "BuiltContext", "ContextEntry", "ContextPriority",
]
