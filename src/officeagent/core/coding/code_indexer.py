"""
CodeIndexer - 代码库语义索引器
================================
对标 Aider RepoMap (tree-sitter 符号图) + Trae 全量索引 + Codex 语义搜索。

设计要点:
  - AST 解析 (Python 内置 ast 模块, 零依赖)
  - 符号表: 函数/类/方法定义位置 + 引用位置
  - 代码切片: 按符号边界切分, 每片含完整语义
  - 增量索引: 文件 hash 变更时只重建该文件
  - 语义检索: 复用 retrieval/embedder + retrieval/vectorstore + retrieval/hybrid
  - 多语言支持: Python 原生 ast, 其余语言正则启发式

零外部依赖: 仅 ast / re / hashlib / pathlib / os
"""
from __future__ import annotations

import ast
import hashlib
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from officeagent.core.retrieval.embedder import BaseEmbedder, HashingEmbedder
from officeagent.core.retrieval.hybrid import BM25Retriever
from officeagent.core.retrieval.vectorstore import (
    BaseVectorStore, InMemoryVectorStore,
)


# ============================================================================
# 数据结构
# ============================================================================

class SymbolKind(Enum):
    """符号类型 (类比 LSP SymbolKind)。"""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"
    IMPORT = "import"
    VARIABLE = "variable"
    UNKNOWN = "unknown"


@dataclass
class Location:
    """代码位置 (类比 LSP Location)。"""
    file: str
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "start_line": self.start_line,
            "end_line": self.end_line, "start_col": self.start_col,
            "end_col": self.end_col,
        }


@dataclass
class SymbolInfo:
    """符号信息 (类比 LSP SymbolInformation)。"""
    name: str
    kind: SymbolKind
    location: Location
    signature: str = ""           # 函数签名 / 类定义行
    docstring: str = ""           # 文档字符串
    parent: str = ""              # 父符号 (类名, 用于方法)
    references: list[Location] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind.value,
            "location": self.location.to_dict(),
            "signature": self.signature, "docstring": self.docstring,
            "parent": self.parent,
            "reference_count": len(self.references),
        }


@dataclass
class CodeSlice:
    """代码切片 (一个完整的语义单元)。"""
    file: str
    symbol_name: str
    kind: SymbolKind
    start_line: int
    end_line: int
    content: str
    signature: str = ""
    docstring: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "symbol_name": self.symbol_name,
            "kind": self.kind.value,
            "start_line": self.start_line, "end_line": self.end_line,
            "content": self.content, "signature": self.signature,
            "docstring": self.docstring,
        }


@dataclass
class IndexStats:
    """索引统计。"""
    total_files: int = 0
    total_symbols: int = 0
    total_slices: int = 0
    indexed_files: int = 0
    skipped_files: int = 0
    errors: list[str] = field(default_factory=list)
    duration_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files": self.total_files,
            "total_symbols": self.total_symbols,
            "total_slices": self.total_slices,
            "indexed_files": self.indexed_files,
            "skipped_files": self.skipped_files,
            "error_count": len(self.errors),
            "duration_sec": round(self.duration_sec, 3),
        }


# ============================================================================
# Python AST 访问器 (提取符号 + 切片)
# ============================================================================

class _PythonSymbolVisitor(ast.NodeVisitor):
    """Python AST 访问器, 提取函数/类/方法符号。"""

    def __init__(self, file_path: str, source: str):
        self.file = file_path
        self.source = source
        self.lines = source.splitlines()
        self.symbols: list[SymbolInfo] = []
        self._class_stack: list[str] = []

    def _extract_docstring(self, node: ast.AST) -> str:
        """提取 docstring。"""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                return node.body[0].value.value
        return ""

    def _make_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """构造函数签名。"""
        args = []
        for arg in node.args.args:
            name = arg.arg
            if arg.annotation:
                name += f": {ast.unparse(arg.annotation)}"
            args.append(name)
        # *args, **kwargs
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        kind = SymbolKind.METHOD if self._class_stack else SymbolKind.FUNCTION
        parent = self._class_stack[-1] if self._class_stack else ""
        sig = self._make_signature(node)
        doc = self._extract_docstring(node)
        loc = Location(
            file=self.file, start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_col=node.col_offset,
            end_col=getattr(node, "end_col_offset", 0) or 0,
        )
        self.symbols.append(SymbolInfo(
            name=node.name, kind=kind, location=loc,
            signature=sig, docstring=doc, parent=parent,
        ))
        # 递归访问函数体 (可能有嵌套函数)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        loc = Location(
            file=self.file, start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_col=node.col_offset,
            end_col=getattr(node, "end_col_offset", 0) or 0,
        )
        # 构造类签名 (含基类)
        bases = [ast.unparse(b) for b in node.bases]
        sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
        doc = self._extract_docstring(node)
        self.symbols.append(SymbolInfo(
            name=node.name, kind=SymbolKind.CLASS, location=loc,
            signature=sig, docstring=doc,
        ))
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()


# ============================================================================
# 通用语言正则启发式 (无 AST 的语言降级方案)
# ============================================================================

# 通用符号正则 (支持 JS/TS/Java/C++/Go/Rust)
_REGEX_PATTERNS: dict[str, list[tuple[SymbolKind, re.Pattern[str]]]] = {
    ".py": [],  # Python 走 AST
    ".js": [
        (SymbolKind.FUNCTION, re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)")),
        (SymbolKind.FUNCTION, re.compile(r"^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:export\s+)?class\s+(\w+)")),
    ],
    ".ts": [
        (SymbolKind.FUNCTION, re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)")),
        (SymbolKind.FUNCTION, re.compile(r"^\s*(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\(")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)")),
    ],
    ".java": [
        (SymbolKind.FUNCTION, re.compile(r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\],\s]+\s+(\w+)\s*\(")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:public\s+)?(?:abstract\s+)?class\s+(\w+)")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:public\s+)?interface\s+(\w+)")),
    ],
    ".go": [
        (SymbolKind.FUNCTION, re.compile(r"^\s*func\s+(?:\([^)]*\)\s+)?(\w+)\s*\(")),
        (SymbolKind.CLASS, re.compile(r"^\s*type\s+(\w+)\s+struct\b")),
    ],
    ".rs": [
        (SymbolKind.FUNCTION, re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:pub\s+)?struct\s+(\w+)")),
        (SymbolKind.CLASS, re.compile(r"^\s*(?:pub\s+)?enum\s+(\w+)")),
    ],
}


def _parse_with_regex(file_path: str, source: str) -> list[SymbolInfo]:
    """正则启发式解析 (无 AST 的语言降级方案)。"""
    ext = Path(file_path).suffix.lower()
    patterns = _REGEX_PATTERNS.get(ext, [])
    if not patterns:
        return []
    symbols: list[SymbolInfo] = []
    lines = source.splitlines()
    for i, line in enumerate(lines, 1):
        for kind, pattern in patterns:
            m = pattern.match(line)
            if m:
                name = m.group(1)
                # 估算结束行 (简单启发: 向下查找下一个同缩进定义)
                end_line = i
                for j in range(i, min(i + 200, len(lines))):
                    if j > i and patterns and any(
                        p.match(lines[j - 1]) for _, p in patterns
                    ):
                        end_line = j - 1
                        break
                else:
                    end_line = min(i + 100, len(lines))
                symbols.append(SymbolInfo(
                    name=name, kind=kind,
                    location=Location(file=file_path, start_line=i, end_line=end_line),
                    signature=line.strip(),
                ))
    return symbols


# ============================================================================
# CodeIndexer 主类
# ============================================================================

class CodeIndexer:
    """代码库语义索引器 (对标 Aider RepoMap + Trae 全量索引)。

    功能:
      1. AST/正则解析 → 符号表 (定义位置)
      2. 代码切片 → 按符号边界切分, 每片含完整语义
      3. 语义索引 → 复用 retrieval/embedder + vectorstore
      4. 增量更新 → 文件 hash 变更时只重建该文件
      5. 引用查找 → 简单文本匹配 (未来可升级到 LSP)

    Usage:
        indexer = CodeIndexer()
        stats = await indexer.index_directory("/path/to/project")
        slices = await indexer.search_code("AgentKernel")
        refs = indexer.find_references("AgentKernel")

    零外部依赖: Python stdlib only (ast / re / hashlib)
    """

    # 默认忽略目录 (类比 .gitignore)
    IGNORE_DIRS = frozenset({
        "__pycache__", ".git", ".venv", "venv", "node_modules",
        ".idea", ".vscode", "dist", "build", ".mypy_cache", ".ruff_cache",
        ".pytest_cache", ".tox", ".eggs", "htmlcov", "_references",
    })
    # 默认支持扩展名
    SUPPORTED_EXTENSIONS = frozenset({
        ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp",
    })
    # 单文件最大字节数 (避免超大文件拖慢索引)
    MAX_FILE_SIZE = 512 * 1024  # 512KB

    def __init__(
        self,
        embedder: BaseEmbedder | None = None,
        store: BaseVectorStore | None = None,
    ):
        self._embedder = embedder or HashingEmbedder(dim=256)
        self._store = store or InMemoryVectorStore()
        # BM25 关键词检索器
        self._bm25 = BM25Retriever()
        # BM25 待索引文档累积
        self._bm25_docs: list[tuple[str, str]] = []
        # 符号表: name → list[SymbolInfo] (同名符号可能多处定义)
        self._symbols: dict[str, list[SymbolInfo]] = defaultdict(list)
        # 文件 hash: path → md5 (增量索引)
        self._file_hashes: dict[str, str] = {}
        # 文件 → 符号名集合 (反向索引)
        self._file_symbols: dict[str, set[str]] = defaultdict(set)
        # 切片存储: slice_id → CodeSlice
        self._slices: dict[str, CodeSlice] = {}
        # 项目根目录 (find_references 用)
        self._root: str = ""

    # ========================================================================
    # 索引构建
    # ========================================================================

    async def index_directory(
        self,
        root: str,
        *,
        incremental: bool = True,
        extensions: set[str] | None = None,
    ) -> IndexStats:
        """索引目录 (类比 Trae 全量索引)。

        Args:
            root: 项目根目录
            incremental: 增量索引 (只重建变更文件)
            extensions: 自定义扩展名集合 (None = 默认支持的所有)

        Returns:
            IndexStats 索引统计
        """
        import time
        start = time.monotonic()
        stats = IndexStats()
        root_path = Path(root).resolve()
        self._root = str(root_path)
        exts = extensions or self.SUPPORTED_EXTENSIONS

        # 收集所有待索引文件
        files: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            # 过滤忽略目录
            dirnames[:] = [d for d in dirnames if d not in self.IGNORE_DIRS]
            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in exts:
                    fp = Path(dirpath) / fname
                    if fp.stat().st_size <= self.MAX_FILE_SIZE:
                        files.append(fp)
                        stats.total_files += 1

        # 索引每个文件
        for fp in files:
            rel_path = str(fp.relative_to(root_path)).replace("\\", "/")
            try:
                changed = await self._index_file(fp, rel_path, incremental)
                if changed:
                    stats.indexed_files += 1
                else:
                    stats.skipped_files += 1
            except Exception as e:  # noqa: BLE001
                stats.errors.append(f"{rel_path}: {type(e).__name__}: {e}")
                stats.skipped_files += 1

        stats.total_symbols = sum(len(syms) for syms in self._symbols.values())
        stats.total_slices = len(self._slices)
        stats.duration_sec = time.monotonic() - start

        # 构建 BM25 索引 (批量)
        if self._bm25_docs:
            self._bm25.index(self._bm25_docs)
            self._bm25_docs.clear()

        return stats

    async def _index_file(
        self, file_path: Path, rel_path: str, incremental: bool,
    ) -> bool:
        """索引单个文件, 返回是否实际重建。"""
        # 读取文件
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

        # 增量: hash 比较
        file_hash = hashlib.md5(source.encode("utf-8")).hexdigest()
        if incremental and self._file_hashes.get(rel_path) == file_hash:
            return False  # 未变更, 跳过

        # 清除旧索引
        self._remove_file_index(rel_path)

        # 更新 hash
        self._file_hashes[rel_path] = file_hash

        # 解析符号
        ext = file_path.suffix.lower()
        if ext == ".py":
            symbols = self._parse_python(rel_path, source)
        else:
            symbols = _parse_with_regex(rel_path, source)

        # 注册符号 + 创建切片 + 语义索引
        slice_ids: list[str] = []
        slice_vectors: list[list[float]] = []
        slice_metas: list[dict[str, Any]] = []
        for sym in symbols:
            self._symbols[sym.name].append(sym)
            self._file_symbols[rel_path].add(sym.name)

            # 创建代码切片
            slice_content = self._extract_slice(source, sym)
            if slice_content:
                cs = CodeSlice(
                    file=rel_path, symbol_name=sym.name, kind=sym.kind,
                    start_line=sym.location.start_line,
                    end_line=sym.location.end_line,
                    content=slice_content,
                    signature=sym.signature, docstring=sym.docstring,
                )
                slice_id = f"{rel_path}:{sym.name}:{sym.location.start_line}"
                self._slices[slice_id] = cs

                # 语义索引 (同步嵌入 + 累积 BM25 文档)
                text = f"{sym.signature}\n{sym.docstring}\n{slice_content}"
                vec = self._embedder.embed(text)
                slice_ids.append(slice_id)
                slice_vectors.append(vec)
                slice_metas.append({
                    "file": rel_path, "symbol": sym.name,
                    "kind": sym.kind.value, "line": sym.location.start_line,
                })
                self._bm25_docs.append((slice_id, text))

        # 批量写入向量库
        if slice_ids:
            self._store.add(slice_ids, slice_vectors, slice_metas)

        return True

    def _parse_python(self, rel_path: str, source: str) -> list[SymbolInfo]:
        """Python AST 解析。"""
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError:
            return []
        visitor = _PythonSymbolVisitor(rel_path, source)
        visitor.visit(tree)
        return visitor.symbols

    def _extract_slice(self, source: str, sym: SymbolInfo) -> str:
        """从源码中提取符号对应的代码切片。"""
        lines = source.splitlines()
        start = sym.location.start_line - 1  # 0-indexed
        end = sym.location.end_line           # exclusive
        if start >= len(lines):
            return ""
        end = min(end, len(lines))
        return "\n".join(lines[start:end])

    def _remove_file_index(self, rel_path: str) -> None:
        """清除文件的旧索引。"""
        old_symbols = self._file_symbols.pop(rel_path, set())
        for name in old_symbols:
            syms = self._symbols.get(name, [])
            self._symbols[name] = [s for s in syms if s.location.file != rel_path]
            if not self._symbols[name]:
                self._symbols.pop(name, None)
        # 清除切片
        to_remove = [k for k, v in self._slices.items() if v.file == rel_path]
        for k in to_remove:
            del self._slices[k]

    # ========================================================================
    # 查询
    # ========================================================================

    async def search_code(
        self,
        query: str,
        *,
        top_k: int = 10,
        language: str | None = None,
        kind: SymbolKind | None = None,
    ) -> list[CodeSlice]:
        """语义搜索代码 (对标 Codex 语义搜索)。

        双路检索: 向量 (语义) + BM25 (关键词), RRF 融合。
        """
        # 向量检索
        query_vec = self._embedder.embed(query)
        vec_results = self._store.search(query_vec, top_k=top_k * 3)
        # BM25 检索
        bm25_results = self._bm25.search(query, top_k=top_k * 3)

        # RRF 融合
        rrf_k = 60
        scores: dict[str, float] = defaultdict(float)
        for rank, r in enumerate(vec_results):
            scores[r.id] += 1.0 / (rrf_k + rank + 1)
        # BM25 返回 list[tuple[str, float]], 第一个是 doc_id
        for rank, (doc_id, _score) in enumerate(bm25_results):
            scores[doc_id] += 1.0 / (rrf_k + rank + 1)

        # 取 top_k
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k * 2]

        slices: list[CodeSlice] = []
        for slice_id, _score in ranked:
            cs = self._slices.get(slice_id)
            if cs is None:
                continue
            # 过滤
            if language and not cs.file.endswith(f".{language}"):
                continue
            if kind and cs.kind != kind:
                continue
            slices.append(cs)
            if len(slices) >= top_k:
                break
        return slices

    def find_references(self, symbol: str) -> list[Location]:
        """查找符号引用 (对标 IDE Find References)。

        当前实现: 简单文本匹配 (未来可升级到 LSP / tree-sitter)。
        """
        # 先找定义
        defs = self._symbols.get(symbol, [])
        if not defs:
            return []
        # 在所有已索引文件中查找 symbol 出现的位置
        refs: list[Location] = []
        for rel_path in list(self._file_hashes.keys()):
            # 从磁盘读取 (root + rel_path)
            fp = Path(self._root) / rel_path if self._root else Path(rel_path)
            try:
                source = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = source.splitlines()
            for i, line in enumerate(lines, 1):
                # 简单词边界匹配
                if re.search(rf"\b{re.escape(symbol)}\b", line):
                    # 排除定义行本身
                    is_def = any(
                        s.location.file == rel_path and
                        s.location.start_line <= i <= s.location.end_line
                        for s in defs
                    )
                    if not is_def:
                        refs.append(Location(
                            file=rel_path, start_line=i, end_line=i,
                        ))
        return refs

    def get_symbol_info(self, symbol: str) -> SymbolInfo | None:
        """获取符号定义信息 (类比 IDE Go to Definition)。"""
        syms = self._symbols.get(symbol, [])
        return syms[0] if syms else None

    def get_file_symbols(self, file_path: str) -> list[SymbolInfo]:
        """获取文件中的所有符号 (类比 IDE Outline)。"""
        return [s for syms in self._symbols.values() for s in syms
                if s.location.file == file_path]

    def get_repo_map(self, max_tokens: int = 4096) -> str:
        """生成仓库地图 (对标 Aider RepoMap)。

        输出格式:
          path/to/file.py
            class ClassName(BaseClass)
            def function_name(args)
              def method_name(args)
        """
        lines: list[str] = []
        current_tokens = 0
        for file_path in sorted(self._file_symbols.keys()):
            syms = self.get_file_symbols(file_path)
            if not syms:
                continue
            # 文件头
            file_line = f"{file_path}"
            current_tokens += len(file_line) // 4 + 1
            if current_tokens > max_tokens:
                break
            lines.append(file_line)
            # 符号
            for sym in syms:
                indent = "  " if sym.kind == SymbolKind.METHOD else "  "
                sym_line = f"{indent}{sym.signature or sym.name}"
                current_tokens += len(sym_line) // 4 + 1
                if current_tokens > max_tokens:
                    lines.append(f"{indent}... (truncated)")
                    break
                lines.append(sym_line)
            lines.append("")  # 空行分隔
        return "\n".join(lines)

    # ========================================================================
    # 统计
    # ========================================================================

    def get_stats(self) -> dict[str, Any]:
        """索引统计。"""
        return {
            "total_files": len(self._file_hashes),
            "total_symbols": sum(len(syms) for syms in self._symbols.values()),
            "unique_symbols": len(self._symbols),
            "total_slices": len(self._slices),
            "files": sorted(self._file_hashes.keys()),
        }


__all__ = [
    "CodeIndexer", "CodeSlice", "SymbolInfo", "SymbolKind", "IndexStats",
    "Location",
]
