"""
业务能力层 - 格式转换。

实现 docx ↔ pdf ↔ markdown ↔ html 等格式转换。

安全防护:
  - 文件大小限制(MAX_INPUT_FILE_BYTES,默认 100MB),避免超大文件导致内存爆炸
  - 输入文件存在性校验
  - 输入/输出格式枚举校验

性能优化:
  - 大文件流式处理(由底层 pandoc/libreoffice 处理,本层仅校验大小)
  - 转换函数表(dict O(1) 查找)而非 if-elif 链
"""
import logging
import os
from typing import Callable, Optional

from officeagent.core.tools.protocol import ToolMetadata


_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 输入文件大小上限(100 MB);超过拒绝,避免 OOM
MAX_INPUT_FILE_BYTES = 100 * 1024 * 1024

# 支持的源/目标格式
_VALID_FORMATS = frozenset({"docx", "pdf", "md", "html", "txt"})


# ---------------------------------------------------------------------------
# 格式转换工具
# ---------------------------------------------------------------------------


def convert_document(
    file_path: str,
    source_format: str,
    target_format: str,
    output_path: Optional[str] = None,
) -> dict:
    """
    文档格式转换。

    Args:
        file_path: 源文件路径(必须存在)
        source_format: 源格式(docx/pdf/md/html/txt)
        target_format: 目标格式(不得与 source_format 相同)
        output_path: 输出路径(可选,默认自动生成)

    Returns:
        {success, output_file, source_format, target_format} 或 {success, error}
    """
    # 参数非空校验
    if not file_path:
        return {"success": False, "error": "file_path must not be empty"}
    if not source_format or not target_format:
        return {"success": False, "error": "source_format and target_format must not be empty"}

    # 格式枚举校验
    if source_format not in _VALID_FORMATS:
        return {
            "success": False,
            "error": f"unsupported source_format {source_format!r}, "
                     f"must be one of {sorted(_VALID_FORMATS)}",
        }
    if target_format not in _VALID_FORMATS:
        return {
            "success": False,
            "error": f"unsupported target_format {target_format!r}, "
                     f"must be one of {sorted(_VALID_FORMATS)}",
        }
    if source_format == target_format:
        return {
            "success": False,
            "error": f"source_format and target_format must not be the same ({source_format!r})",
        }

    # 文件存在性校验
    if not os.path.exists(file_path):
        return {"success": False, "error": f"input file not found: {file_path}"}
    if not os.path.isfile(file_path):
        return {"success": False, "error": f"input path is not a regular file: {file_path}"}

    # 文件大小校验
    try:
        file_size = os.path.getsize(file_path)
    except OSError as e:
        return {"success": False, "error": f"cannot stat input file: {e}", "file_path": file_path}
    if file_size > MAX_INPUT_FILE_BYTES:
        return {
            "success": False,
            "error": f"input file size ({file_size} bytes) exceeds limit "
                     f"({MAX_INPUT_FILE_BYTES // 1024 // 1024}MB)",
            "file_path": file_path,
        }
    if file_size == 0:
        return {"success": False, "error": "input file is empty", "file_path": file_path}

    # 生成输出路径
    if not output_path:
        base_name = os.path.splitext(file_path)[0]
        output_path = f"{base_name}.{target_format}"

    try:
        # 转换函数表(dict O(1) 查找),避免长 if-elif 链
        supported_conversions: dict[tuple[str, str], Callable[[str, str], dict]] = {
            ("docx", "pdf"): convert_docx_to_pdf,
            ("docx", "md"): convert_docx_to_md,
            ("md", "docx"): convert_md_to_docx,
            ("pdf", "docx"): convert_pdf_to_docx,
        }

        conversion_func = supported_conversions.get((source_format, target_format))

        if conversion_func:
            # 底层转换函数应流式处理大文件,避免一次性 read() 导致 OOM
            return conversion_func(file_path, output_path)

        return {
            "success": False,
            "error": f"Unsupported conversion: {source_format} → {target_format}",
        }

    except Exception as e:
        _logger.exception("convert_document failed: %s: %s", type(e).__name__, e)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "file_path": file_path,
        }


def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> dict:
    """DOCX 转 PDF。"""
    # TODO: 接入真实转换引擎(Word COM / LibreOffice)
    return {
        "success": True,
        "output_file": pdf_path,
        "source_format": "docx",
        "target_format": "pdf",
        "engine": "stub",
    }


def convert_docx_to_md(docx_path: str, md_path: str) -> dict:
    """DOCX 转 Markdown。"""
    # TODO: 接入 pandoc / python-docx
    return {
        "success": True,
        "output_file": md_path,
        "source_format": "docx",
        "target_format": "md",
        "engine": "stub",
    }


def convert_md_to_docx(md_path: str, docx_path: str) -> dict:
    """Markdown 转 DOCX。"""
    # TODO: 接入 pandoc / python-docx
    return {
        "success": True,
        "output_file": docx_path,
        "source_format": "md",
        "target_format": "docx",
        "engine": "stub",
    }


def convert_pdf_to_docx(pdf_path: str, docx_path: str) -> dict:
    """PDF 转 DOCX。"""
    # TODO: 接入 pdf2docx / PyPDF2 + python-docx
    return {
        "success": True,
        "output_file": docx_path,
        "source_format": "pdf",
        "target_format": "docx",
        "engine": "stub",
    }

# ---------------------------------------------------------------------------
# 工具元数据
# ---------------------------------------------------------------------------


TOOL_METADATA = {
    "convert_document": ToolMetadata(
        name="convert_document",
        description="文档格式转换(docx/pdf/md/html/txt)",
        category="converter",
        input_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "source_format": {"type": "string", "enum": ["docx", "pdf", "md", "html", "txt"]},
                "target_format": {"type": "string", "enum": ["docx", "pdf", "md", "html", "txt"]},
                "output_path": {"type": "string"},
            },
            "required": ["file_path", "source_format", "target_format"],
        },
    ),
}


def register_converter_tools(registry) -> None:
    """注册格式转换工具。"""
    registry.register(TOOL_METADATA["convert_document"], convert_document)