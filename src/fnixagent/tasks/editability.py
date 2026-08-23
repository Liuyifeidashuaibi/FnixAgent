"""输出可编辑性保证(Phase 6.5)。

确保 fnixagent 所有输出文档保持可编辑性(非图片/可二次编辑),

核心原则:
  - 输出 docx/xlsx/pptx 而非图片(除非用户明确要求图片)
  - 文档结构完整(段落/表格/样式可编辑)
  - 不嵌入截图替代文本
  - 格式可二次修改

检查项:
  - docx: 段落可编辑(非图片段落)/run 可修改/样式可应用
  - xlsx: 单元格可编辑/公式可修改/格式可调整
  - pptx: 文本框可编辑/形状可选择
  - pdf: 标记为只读(不可编辑,需提示)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from fnixagent.office.base import BaseExpert, ExpertError, ExpertResult

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class EditabilityReport:
    """可编辑性报告。

    Attributes:
        editable: 是否可编辑
        file_type: 文件类型(docx/xlsx/pptx/pdf)
        total_objects: 检查的对象总数(段落/单元格/形状)
        editable_objects: 可编辑对象数
        locked_objects: 锁定对象数(保护/加密)
        image_only_objects: 仅图片对象数(不可编辑文本)
        issues: 问题列表
        recommendations: 建议列表
    """

    editable: bool = True
    file_type: str = ""
    total_objects: int = 0
    editable_objects: int = 0
    locked_objects: int = 0
    image_only_objects: int = 0
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def editability_rate(self) -> float:
        """可编辑率(0-1)。"""
        if self.total_objects == 0:
            return 1.0
        return self.editable_objects / self.total_objects


# ---------------------------------------------------------------------------
# 可编辑性保证器
# ---------------------------------------------------------------------------


class EditabilityGuard(BaseExpert):
    """输出可编辑性保证器(Phase 6.5)。

    检查输出文档是否保持可编辑性,并提供修复建议。

    能力边界:
      - 仅检查本地文件
      - docx/xlsx/pptx 检查结构可编辑性
      - pdf 标记为只读
      - 不修改文件,仅检查与建议
    """

    @property
    def name(self) -> str:
        return "editability_guard"

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def check(self, path: str) -> ExpertResult:
        """检查文件可编辑性。

        Args:
            path: 文件路径

        Returns:
            ExpertResult(output=EditabilityReport, metadata={})
        """
        err = self._validate_path(path, must_exist=True)
        if err:
            return self._failure(err)

        ext = os.path.splitext(path)[1].lstrip(".").lower()
        try:
            if ext == "docx":
                report = self._check_docx(path)
            elif ext == "xlsx":
                report = self._check_xlsx(path)
            elif ext == "pptx":
                report = self._check_pptx(path)
            elif ext == "pdf":
                report = self._check_pdf(path)
            else:
                return self._failure(f"unsupported file type: .{ext}")
        except Exception as e:
            return self._failure(f"check editability failed: {e}")

        return self._success(report)

    def ensure_editable(self, path: str) -> ExpertResult:
        """确保文件可编辑(检查+建议)。

        Args:
            path: 文件路径

        Returns:
            ExpertResult(output=report, metadata={"passed": bool})
        """
        result = self.check(path)
        if not result.success:
            return result
        report: EditabilityReport = result.output
        return self._success(
            report,
            passed=report.editable,
            editability_rate=report.editability_rate,
        )

    # ------------------------------------------------------------------
    # 各格式检查
    # ------------------------------------------------------------------

    def _check_docx(self, path: str) -> EditabilityReport:
        """检查 docx 可编辑性。

        检查项:
          - 文档未加密(可打开)
          - 段落可编辑(非全部图片)
          - run 存在(文本可修改)
          - 启用 track_changes 时提示
        """
        report = EditabilityReport(file_type="docx")
        try:
            docx = self._require_lib("docx")
            doc = docx.Document(path)

            # 段落计数
            paragraphs = doc.paragraphs
            report.total_objects = len(paragraphs)

            # 统计有文本的段落(可编辑)
            text_paragraphs = sum(1 for p in paragraphs if p.text.strip())
            report.editable_objects = text_paragraphs

            # 检查是否图片过多(图片段落不可编辑文本)
            # python-docx 中图片通过 inline shape 体现
            inline_shapes = doc.inline_shapes
            if len(inline_shapes) > 0 and text_paragraphs == 0:
                report.image_only_objects = len(inline_shapes)
                report.issues.append(f"文档仅含 {len(inline_shapes)} 个图片,无文本段落")
                report.recommendations.append("建议添加文本段落以保证可编辑性")
                report.editable = False

            # 检查文档保护(通过 XML 判断)
            try:
                from docx.oxml.ns import qn

                settings = doc.settings.element
                protection = settings.find(qn("w:documentProtection"))
                if protection is not None:
                    report.locked_objects = 1
                    edit_type = protection.get(qn("w:edit"))
                    report.issues.append(f"文档已启用保护模式(edit={edit_type})")
                    report.recommendations.append("如需编辑,请先取消文档保护")
                    report.editable = False
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)

            # 检查修订追踪
            try:
                from docx.oxml.ns import qn

                settings = doc.settings.element
                track_changes = settings.find(qn("w:trackChanges"))
                if track_changes is not None:
                    report.issues.append("文档启用了修订追踪")
                    report.recommendations.append("修订追踪下编辑会被记录,确认是否需要")
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)

        except ExpertError:
            raise
        except Exception as e:
            report.editable = False
            report.issues.append(f"读取失败: {e}")

        return report

    def _check_xlsx(self, path: str) -> EditabilityReport:
        """检查 xlsx 可编辑性。

        检查项:
          - 工作簿未加密
          - 工作表未保护
          - 单元格可编辑
        """
        report = EditabilityReport(file_type="xlsx")
        try:
            openpyxl = self._require_lib("openpyxl")
            wb = openpyxl.load_workbook(path, read_only=False)

            sheet_count = len(wb.sheetnames)
            report.total_objects = sheet_count
            report.editable_objects = sheet_count

            # 检查工作表保护
            for ws in wb.worksheets:
                if ws.protection and ws.protection.sheet:
                    report.locked_objects += 1
                    report.issues.append(f"工作表 '{ws.title}' 已保护")

            if report.locked_objects > 0:
                report.recommendations.append("如需编辑,请取消工作表保护")
                report.editable = False

            # 检查工作簿保护
            if wb.security and wb.security.lockStructure:
                report.issues.append("工作簿结构已锁定")
                report.recommendations.append("如需编辑,请取消工作簿保护")
                report.editable = False

            wb.close()
        except ExpertError:
            raise
        except Exception as e:
            report.editable = False
            report.issues.append(f"读取失败: {e}")

        return report

    def _check_pptx(self, path: str) -> EditabilityReport:
        """检查 pptx 可编辑性。

        检查项:
          - 幻灯片可编辑
          - 文本框存在(非纯图片)
        """
        report = EditabilityReport(file_type="pptx")
        try:
            pptx = self._require_lib("pptx")
            prs = pptx.Presentation(path)

            slide_count = len(prs.slides)
            report.total_objects = slide_count

            text_slides = 0
            for slide in prs.slides:
                has_text = False
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        if shape.text_frame.text.strip():
                            has_text = True
                            break
                if has_text:
                    text_slides += 1

            report.editable_objects = text_slides

            if text_slides == 0 and slide_count > 0:
                report.image_only_objects = slide_count
                report.issues.append(f"全部 {slide_count} 张幻灯片均无文本(纯图片)")
                report.recommendations.append("建议添加文本框以保证可编辑性")
                report.editable = False

        except ExpertError:
            raise
        except Exception as e:
            report.editable = False
            report.issues.append(f"读取失败: {e}")

        return report

    def _check_pdf(self, path: str) -> EditabilityReport:
        """检查 pdf 可编辑性。

        PDF 本质上不可编辑,标记为只读并建议转 docx。
        """
        report = EditabilityReport(
            file_type="pdf",
            editable=False,
            total_objects=1,
            editable_objects=0,
        )
        report.issues.append("PDF 格式不可直接编辑")
        report.recommendations.append("如需编辑,建议转换为 docx/xlsx(用 ConverterExpert.convert)")
        return report
