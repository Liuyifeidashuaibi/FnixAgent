"""统一 Markdown 渲染器。

把 parser.Element 列表渲染为统一的 GitHub Flavored Markdown 表示。

设计:
  - 复用 parser.py 已有 Element 子类(Title/NarrativeText/Table/ListItem/Image/
    PageBreak/Header/Footer),不重新定义元素类型
  - 按元素 category 派发到对应渲染方法
  - 中英文混排优化:自动在中英文之间补空格
  - 表格使用 GitHub Flavored Markdown 语法
  - 图片用 ![](path) 占位(本地路径或 base64)

可选依赖:无(纯 Python)
"""

from __future__ import annotations

import re
from typing import Any

from fnixagent.office.parser import (
    Footer,
    Header,
    Image,
    ListItem,
    NarrativeText,
    PageBreak,
    Table,
    Title,
)

# 中英文加空格正则:
#   ([a-zA-Z0-9])(CJK)  →  \1 \2
#   (CJK)([a-zA-Z0-9])  →  \1 \2
# 一-鿿 覆盖 CJK 统一表意文字基本区(U+4E00–U+9FFF)
_CJK_RANGE = "一-鿿"
_PATTERN_LATIN_CJK = re.compile(rf"([a-zA-Z0-9])([{_CJK_RANGE}])")
_PATTERN_CJK_LATIN = re.compile(rf"([{_CJK_RANGE}])([a-zA-Z0-9])")


class MarkdownRenderer:
    """把 Element 列表渲染为统一 Markdown。

    用法:
        renderer = MarkdownRenderer()
        md = renderer.render(elements)
    """

    def render(self, elements: list) -> str:
        """渲染 Element 列表为 Markdown 字符串。

        Args:
            elements: Element 实例列表(parser 输出)

        Returns:
            GitHub Flavored Markdown 字符串(元素间以空行分隔)
        """
        parts: list[str] = []
        for el in elements:
            md = self._render_element(el)
            if md:
                parts.append(md)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 派发
    # ------------------------------------------------------------------

    def _render_element(self, element: Any) -> str:
        """按 category 派发到对应渲染方法。"""
        # 优先按类型匹配(性能更好,且不受 to_dict 后 category 丢失影响)
        if isinstance(element, Title):
            return self.render_title(element)
        if isinstance(element, Table):
            return self.render_table(element)
        if isinstance(element, ListItem):
            return self.render_list(element)
        if isinstance(element, Image):
            return self.render_image(element)
        if isinstance(element, PageBreak):
            return "---"
        if isinstance(element, (Header, Footer)):
            text = self._normalize_cjk(element.text or "")
            return f"> {text}" if text else ""
        if isinstance(element, NarrativeText):
            return self.render_narrative(element)
        # 兜底:按 category 字符串匹配(兼容自定义 Element 子类)
        category = getattr(element, "category", "")
        if category == "Title":
            return self.render_title(element)
        if category == "Table":
            return self.render_table(element)
        if category == "ListItem":
            return self.render_list(element)
        if category == "Image":
            return self.render_image(element)
        if category == "Code":
            return self.render_code(element)
        if category == "PageBreak":
            return "---"
        # 其余当作正文
        text = self._normalize_cjk(getattr(element, "text", "") or "")
        return text

    # ------------------------------------------------------------------
    # 各类型渲染
    # ------------------------------------------------------------------

    def render_title(self, element: Any) -> str:
        """渲染标题为 Markdown 标题(# ~ ######)。"""
        text = self._normalize_cjk((getattr(element, "text", "") or "").strip())
        if not text:
            return ""
        level = self._heading_level(element)
        return f"{'#' * level} {text}"

    def render_narrative(self, element: Any) -> str:
        """渲染正文段落。"""
        return self._normalize_cjk((getattr(element, "text", "") or "").strip())

    def render_table(self, element: Any) -> str:
        """渲染表格为 GitHub Flavored Markdown 表格。

        第一行作 header,第二行 --- 分隔,其余作 body。
        """
        rows = getattr(element, "rows", None) or []
        if not rows:
            return ""
        # 规范化每个单元格:转义 | 与换行,中英文加空格
        norm_rows = [
            [
                self._normalize_cjk(str(c) if c is not None else "")
                .replace("|", "\\|")
                .replace("\n", " ")
                .strip()
                for c in row
            ]
            for row in rows
        ]
        # 补齐列数(保证每行列数一致)
        max_cols = max((len(r) for r in norm_rows), default=0)
        if max_cols == 0:
            return ""
        for r in norm_rows:
            while len(r) < max_cols:
                r.append("")
        header = norm_rows[0]
        separator = ["---"] * max_cols
        body = norm_rows[1:] if len(norm_rows) > 1 else []
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row in body:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def render_list(self, element: Any) -> str:
        """渲染列表项为无序列表(-)。"""
        text = self._normalize_cjk((getattr(element, "text", "") or "").strip())
        if not text:
            return ""
        return f"- {text}"

    def render_image(self, element: Any) -> str:
        """渲染图片为 ![alt](path) 占位。

        优先从 metadata 取 src/path;缺失时输出空占位。
        """
        meta = getattr(element, "metadata", {}) or {}
        src = meta.get("src") or meta.get("path") or meta.get("image_path") or ""
        alt = meta.get("alt") or meta.get("name") or "image"
        if not src:
            return ""
        return f"![{alt}]({src})"

    def render_code(self, element: Any) -> str:
        """渲染代码块(用 ``` 包裹,保留缩进)。"""
        text = (getattr(element, "text", "") or "").rstrip()
        meta = getattr(element, "metadata", {}) or {}
        lang = meta.get("language") or meta.get("lang") or ""
        return f"```{lang}\n{text}\n```"

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _heading_level(element: Any) -> int:
        """从元素 metadata 推断标题级别(1-6)。"""
        meta = getattr(element, "metadata", {}) or {}
        # Word 样式: "Heading 2" → 2
        style = meta.get("style", "")
        if isinstance(style, str) and "Heading" in style:
            m = re.search(r"Heading\s*(\d+)", style)
            if m:
                return max(1, min(6, int(m.group(1))))
        # Markdown heading level
        if meta.get("markdown_heading_level"):
            try:
                return max(1, min(6, int(meta["markdown_heading_level"])))
            except (ValueError, TypeError):
                pass
        # HTML tag: h1-h6
        tag = meta.get("tag", "")
        if isinstance(tag, str) and tag.startswith("h") and len(tag) >= 2:
            try:
                return max(1, min(6, int(tag[1:])))
            except (ValueError, IndexError):
                pass
        return 1

    @staticmethod
    def _normalize_cjk(text: str) -> str:
        """中英文混排优化:在中英文之间补空格。

        Args:
            text: 原始文本

        Returns:
            中英文之间加了空格的文本
        """
        if not text:
            return ""
        # Latin/数字 与 CJK 之间加空格(双向)
        text = _PATTERN_LATIN_CJK.sub(r"\1 \2", text)
        text = _PATTERN_CJK_LATIN.sub(r"\1 \2", text)
        return text
