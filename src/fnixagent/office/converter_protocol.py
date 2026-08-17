"""文档转换器统一协议(参考 markitdown)。

定义 DocumentConverter Protocol(accept/convert)与三层质量梯度:
  - L1_LOCAL: 本地解析(python-docx/openpyxl/python-pptx/pypdf)
  - L2_LLM:   LLM 增强(本地解析 + LLM 补全)
  - L3_CLOUD: 云端(Azure Document Intelligence / Content Understanding)

每个 Converter 声明自己的 layer 和优先级;
ConverterRegistry 支持注册/查找/派发,并提供 fallback 降级机制
(高 layer 失败时自动降级到低 layer)。

内置 L1 转换器:
  - WordConverter(.docx/.doc)
  - ExcelConverter(.xlsx/.xls)
  - PPTConverter(.pptx)
  - PDFConverter(.pdf)
  全部基于 ParserExpert.parse_elements + MarkdownRenderer 实现。

设计参考:
  - markitdown/src/markitdown/converters/_base.py(DocumentConverter Protocol)
  - markitdown 的 ConverterRegistry 派发机制
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from fnixagent.office.markdown import MarkdownRenderer
from fnixagent.office.parser import (
    Element,
    Footer,
    Header,
    Image,
    ListItem,
    NarrativeText,
    PageBreak,
    ParserExpert,
    Table,
    Title,
)

# ---------------------------------------------------------------------------
# 三层质量梯度
# ---------------------------------------------------------------------------

class ConverterLayer(Enum):
    """转换器质量层(数值越大质量越高,但成本/延迟越高)。"""

    L1_LOCAL = "local"  # 本地解析
    L2_LLM = "llm"  # LLM 增强
    L3_CLOUD = "cloud"  # 云端

    @classmethod
    def ordered_high_to_low(cls) -> list[ConverterLayer]:
        """从高到低排序(用于 fallback 降级)。"""
        return [cls.L3_CLOUD, cls.L2_LLM, cls.L1_LOCAL]

# ---------------------------------------------------------------------------
# 转换结果
# ---------------------------------------------------------------------------

@dataclass
class DocumentConverterResult:
    """文档转换结果(统一结构)。

    Attributes:
        markdown:     Markdown 表示
        title:        文档标题(若可识别)
        text_content: 纯文本(无 Markdown 标记)
        elements:     Element 列表(parser 输出)
        metadata:     附加元数据
        layer:        实际使用的层
        duration_ms:  执行耗时(毫秒)
    """

    markdown: str = ""
    title: str | None = None
    text_content: str = ""
    elements: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    layer: str = "local"
    duration_ms: float = 0.0

# ---------------------------------------------------------------------------
# DocumentConverter Protocol(参考 markitdown)
# ---------------------------------------------------------------------------

@runtime_checkable
class DocumentConverter(Protocol):
    """所有文档转换器的统一协议(参考 markitdown)。"""

    def accept(self, file_path: str, **kwargs: Any) -> bool:
        """判断是否能处理该文件。"""
        ...

    def convert(self, file_path: str, **kwargs: Any) -> DocumentConverterResult:
        """转换文件为 DocumentConverterResult。"""
        ...

    @property
    def layer(self) -> ConverterLayer:
        """转换器所属质量层。"""
        ...

    @property
    def priority(self) -> int:
        """优先级(数值越小优先级越高)。"""
        ...

# ---------------------------------------------------------------------------
# ConverterEntry / ConverterRegistry
# ---------------------------------------------------------------------------

@dataclass
class ConverterEntry:
    """注册表条目。"""

    converter: DocumentConverter
    layer: ConverterLayer
    priority: int
    name: str

# layer 排序权重(数值越小越靠前,即高 layer 优先)
_LAYER_ORDER = {
    ConverterLayer.L3_CLOUD: 0,
    ConverterLayer.L2_LLM: 1,
    ConverterLayer.L1_LOCAL: 2,
}

class ConverterRegistry:
    """转换器注册表:注册/查找/派发,支持 fallback 降级。

    用法:
        registry = ConverterRegistry()
        registry.register(WordConverter())
        result = registry.convert_with_fallback("a.docx")
    """

    def __init__(self) -> None:
        self._entries: list[ConverterEntry] = []

    def register(
        self,
        converter: DocumentConverter,
        name: str | None = None,
    ) -> None:
        """注册转换器(同名覆盖)。

        Args:
            converter: 实现 DocumentConverter 协议的实例
            name: 注册名;None 取类名
        """
        entry_name = name or converter.__class__.__name__
        # 同名先移除(允许覆盖)
        self._entries = [e for e in self._entries if e.name != entry_name]
        self._entries.append(
            ConverterEntry(
                converter=converter,
                layer=converter.layer,
                priority=converter.priority,
                name=entry_name,
            )
        )
        # 按 layer(高到低)+ priority(小到大)+ name 排序
        self._entries.sort(
            key=lambda e: (
                _LAYER_ORDER.get(e.layer, 99),
                e.priority,
                e.name,
            )
        )

    def unregister(self, name: str) -> None:
        """注销转换器。"""
        self._entries = [e for e in self._entries if e.name != name]

    def find(
        self,
        file_path: str,
        layer: ConverterLayer | None = None,
    ) -> DocumentConverter | None:
        """查找能处理该文件的转换器。

        Args:
            file_path: 文件路径
            layer: 限定层;None 不限(按排序顺序取第一个 accept 的)

        Returns:
            匹配的转换器;无匹配返回 None
        """
        for entry in self._entries:
            if layer is not None and entry.layer is not layer:
                continue
            try:
                if entry.converter.accept(file_path):
                    return entry.converter
            except Exception:
                # 单个 converter accept 异常不影响后续查找
                continue
        return None

    def convert(
        self,
        file_path: str,
        layer: ConverterLayer | None = None,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        """转换文件(指定层或最佳匹配)。

        Args:
            file_path: 文件路径
            layer: 限定层;None 自动选择最高层

        Returns:
            DocumentConverterResult

        Raises:
            ValueError: 无可用转换器
        """
        converter = self.find(file_path, layer=layer)
        if converter is None:
            raise ValueError(f"no converter accepts: {file_path}")
        return converter.convert(file_path, **kwargs)

    def convert_with_fallback(
        self,
        file_path: str,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        """转换文件,高 layer 失败时自动降级到低 layer。

        策略:按 L3 → L2 → L1 顺序尝试,首个成功即返回;
        全部失败时返回包含错误信息的空结果。

        Args:
            file_path: 文件路径

        Returns:
            DocumentConverterResult(成功时含 markdown/elements;
            全部失败时 metadata.error 记录各层错误)
        """
        last_error: str | None = None
        for target_layer in ConverterLayer.ordered_high_to_low():
            converter = self.find(file_path, layer=target_layer)
            if converter is None:
                continue
            try:
                return converter.convert(file_path, **kwargs)
            except Exception as e:
                last_error = f"[{target_layer.value}] {converter.__class__.__name__}: {e}"
                continue
        # 全部失败:返回空结果 + 错误信息
        return DocumentConverterResult(
            markdown="",
            text_content="",
            metadata={"error": last_error or "no converter available"},
            layer="none",
        )

    def list_converters(self) -> list[ConverterEntry]:
        """列出所有已注册转换器(按排序顺序)。"""
        return list(self._entries)

# ---------------------------------------------------------------------------
# 内置 L1 转换器(包装 ParserExpert + MarkdownRenderer)
# ---------------------------------------------------------------------------

# category → Element 子类映射(用于 to_dict 逆序列化)
_CATEGORY_MAP = {
    "Title": Title,
    "NarrativeText": NarrativeText,
    "ListItem": ListItem,
    "Table": Table,
    "Image": Image,
    "Header": Header,
    "Footer": Footer,
    "PageBreak": PageBreak,
}

class _BaseL1Converter:
    """L1 本地转换器基类(包装 ParserExpert + MarkdownRenderer)。

    子类只需覆盖 _accept_exts 返回支持的扩展名元组。
    所有异常不外泄,convert 失败时抛 ValueError(由 registry 捕获降级)。
    """

    # 子类覆盖:支持的扩展名(小写无点)
    _accept_exts: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._parser = ParserExpert()
        self._renderer = MarkdownRenderer()

    @property
    def layer(self) -> ConverterLayer:
        return ConverterLayer.L1_LOCAL

    @property
    def priority(self) -> int:
        return 100  # L1 默认优先级

    def accept(self, file_path: str, **kwargs: Any) -> bool:
        ext = os.path.splitext(file_path)[1].lstrip(".").lower()
        return ext in self._accept_exts

    def convert(self, file_path: str, **kwargs: Any) -> DocumentConverterResult:
        """转换文件为 DocumentConverterResult。

        流程:ParserExpert.parse_elements → 还原 Element → MarkdownRenderer.render
        """
        start = time.time()
        # 调用 ParserExpert.parse_elements 获取 Element 列表(dict 形式)
        result = self._parser.parse_elements(file_path)
        duration_ms = (time.time() - start) * 1000.0
        if not result.success:
            raise ValueError(result.error or "parse failed")
        output = result.output or {}
        # 把 to_dict 后的 dict 列表还原为 Element 实例
        elements = self._restore_elements(output.get("elements", []))
        # 渲染为 Markdown
        markdown = self._renderer.render(elements)
        # 提取文档标题
        title = self._extract_title(elements)
        if title is None:
            title = (output.get("metadata") or {}).get("title") or None
        # 纯文本(无 Markdown 标记)
        text_content = "\n".join(getattr(e, "text", "") for e in elements if getattr(e, "text", ""))
        return DocumentConverterResult(
            markdown=markdown,
            title=title,
            text_content=text_content,
            elements=elements,
            metadata=dict(output.get("metadata", {})),
            layer=self.layer.value,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _restore_elements(raw_list: list) -> list:
        """把 parse_elements 输出的 dict 列表还原为 Element 实例。

        parse_elements 返回的是 to_dict() 后的 dict,这里按 category 重建。
        """
        elements: list[Element] = []
        for d in raw_list:
            if not isinstance(d, dict):
                continue
            cat = d.get("type") or d.get("category") or "UncategorizedText"
            text = d.get("text", "") or ""
            meta = dict(d.get("metadata") or {})
            cls = _CATEGORY_MAP.get(cat)
            if cls is Table:
                rows = d.get("rows") or []
                elements.append(Table(rows=rows, text=text, metadata=meta))
            elif cls is PageBreak:
                elements.append(PageBreak(metadata=meta))
            elif cls is not None:
                elements.append(cls(text=text, metadata=meta))
            else:
                # 未知类别:兜底用基础 Element
                elements.append(Element(text=text, metadata=meta))
        return elements

    @staticmethod
    def _extract_title(elements: list) -> str | None:
        """从元素列表提取第一个 Title 作为文档标题。"""
        for el in elements:
            if isinstance(el, Title) and el.text.strip():
                return el.text.strip()
        return None

class WordConverter(_BaseL1Converter):
    """Word 文档 L1 转换器(.docx/.doc)。"""

    _accept_exts = ("docx", "doc")

class ExcelConverter(_BaseL1Converter):
    """Excel 文档 L1 转换器(.xlsx/.xls)。"""

    _accept_exts = ("xlsx", "xls")

class PPTConverter(_BaseL1Converter):
    """PPT 文档 L1 转换器(.pptx)。"""

    _accept_exts = ("pptx",)

class PDFConverter(_BaseL1Converter):
    """PDF 文档 L1 转换器(.pdf)。"""

    _accept_exts = ("pdf",)

# ---------------------------------------------------------------------------
# 默认注册表工厂
# ---------------------------------------------------------------------------

def create_default_registry() -> ConverterRegistry:
    """创建包含内置 L1 转换器的默认注册表。

    注册顺序:Word / Excel / PPT / PDF(可被插件覆盖)。
    """
    registry = ConverterRegistry()
    registry.register(WordConverter(), name="word")
    registry.register(ExcelConverter(), name="excel")
    registry.register(PPTConverter(), name="ppt")
    registry.register(PDFConverter(), name="pdf")
    return registry
