"""L1 Office 专家能力深化(P2-9)。

顶级 Office 专家层(护城河),11 个 Expert 类:
  - WordExpert:        Word 文档创建/编辑/样式/目录/合并/比较/脱敏/表格/批注
  - ExcelExpert:       Excel 创建/读取/公式/透视表/图表/合并/条件格式/CSV
  - PPTExpert:         PPT 创建/幻灯片/主题/图片/图表/导出图片
  - PDFExpert:         PDF 创建/合并/拆分/提取文本/图片/水印/加密/OCR
  - ConverterExpert:   格式转换(Word↔PDF/Excel↔CSV/PPT↔图片 等)
  - ParserExpert:      文档解析(段落/表格/表单/版式检测,统一 Element 模型)
  - ChartExpert:       图表生成(柱状/折线/饼图/散点 等)
  - ImageExpert:       图像分析(分镜网格定位/图文分离/批量裁剪)
  - TemplateManager:   模板管理(列出/应用/注册/预览)
  - DocumentInspector: 文档检查器(渲染/检查/诊断,render→look→fix 闭环)
  - Evaluator:         声明式评测(借鉴 OfficeBench/SpreadsheetBench,Soft/Hard 双指标)

设计原则:
  - 所有 Expert 继承 BaseExpert,统一接口风格(create/edit/...)
  - 底层依赖可选(python-docx/openpyxl/python-pptx/PyPDF2 等),不可用时降级
  - 工具化:每个 Expert 暴露为 ToolRegistry 中的多个工具(layer=L1_OFFICE)
  - 零硬编码:模板/样式/图表类型由参数驱动,不预置偏好
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.office.base import BaseExpert, ExpertError, ExpertResult
from fnixagent.office.chart import ChartExpert
from fnixagent.office.converter import ConverterExpert
from fnixagent.office.converter_protocol import (
    ConverterEntry,
    ConverterLayer,
    ConverterRegistry,
    DocumentConverter,
    DocumentConverterResult,
    ExcelConverter,
    PDFConverter,
    PPTConverter,
    WordConverter,
    create_default_registry,
)
from fnixagent.office.evaluator import Evaluator
from fnixagent.office.excel import ExcelExpert
from fnixagent.office.format_spec import FormatNormalizer, FormatReport, FormatSpec
from fnixagent.office.image import ImageExpert
from fnixagent.office.inspector import DocumentInspector
from fnixagent.office.markdown import MarkdownRenderer
from fnixagent.office.parser import ParserExpert
from fnixagent.office.pdf import PDFExpert
from fnixagent.office.plugins import PluginEntry, PluginManager, PluginMeta
from fnixagent.office.powerpoint import PPTExpert
from fnixagent.office.run_editor import EditOp, EditReport, RunEditor
from fnixagent.office.template import TemplateManager
from fnixagent.office.word import WordExpert

__all__ = [
    "BaseExpert",
    "ExpertResult",
    "ExpertError",
    "WordExpert",
    "ExcelExpert",
    "PPTExpert",
    "PDFExpert",
    "ConverterExpert",
    "ParserExpert",
    "ChartExpert",
    "ImageExpert",
    "TemplateManager",
    "DocumentInspector",
    "Evaluator",
    # Phase 5.3 / 5.6
    "FormatSpec",
    "FormatReport",
    "FormatNormalizer",
    "RunEditor",
    "EditOp",
    "EditReport",
    # 架构增强:统一 Markdown 渲染器
    "MarkdownRenderer",
    # 架构增强:DocumentConverter 协议 + 三层质量梯度
    "ConverterEntry",
    "ConverterLayer",
    "ConverterRegistry",
    "DocumentConverter",
    "DocumentConverterResult",
    "ExcelConverter",
    "PDFConverter",
    "PPTConverter",
    "WordConverter",
    "create_default_registry",
    # 架构增强:插件生态(entry_points)
    "PluginEntry",
    "PluginManager",
    "PluginMeta",
]
