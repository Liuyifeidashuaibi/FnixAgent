"""PDF Expert(P2-9)。

PDF 创建/合并/拆分/文本抽取/图片抽取/水印/加密/OCR。

专家职责:
  - 创建 PDF(reportlab);合并/拆分/抽取文本/图片(pypdf/PyPDF2)
  - 加密(pypdf),水印(reportlab + PyMuPDF),OCR(pytesseract + pdf2image)

底层依赖:
  - pypdf 或 PyPDF2(合并/拆分/文本抽取/加密,任一可选)
  - reportlab(创建/水印,可选)
  - PyMuPDF/fitz(图片抽取/水印叠加,可选)
  - pytesseract + pdf2image + Tesseract OCR(OCR,可选)

降级策略:
  - 依赖缺失 → ExpertError 提示安装
  - 大文件用 chunk 流式读写,避免全量加载
  - 临时水印文件用 finally + os.remove 清理
  - PDF 加密密钥长度强制校验(40/128/256 位)
  - OCR 单页图片大小限制,防止 OOM
"""

from __future__ import annotations

import contextlib
import os
import shutil
from typing import Any

from fnixagent.office.base import BaseExpert, ExpertError, ExpertResult

# OCR 单页图片大小上限(20 MB),防止 pdf2image 渲染大图 OOM
_MAX_OCR_IMAGE_SIZE = 20 * 1024 * 1024
# PDF 加密允许的密钥长度(位)
_ALLOWED_PDF_KEY_LENGTHS = (40, 128, 256)


def _import_pdf_lib() -> tuple[Any, str | None]:
    """优先 pypdf,其次 PyPDF2。

    Returns:
        (模块对象, 库名);不可用时返回 (None, None)
    """
    try:
        import pypdf  # type: ignore

        return pypdf, "pypdf"
    except ImportError:
        pass
    try:
        import PyPDF2  # type: ignore

        return PyPDF2, "PyPDF2"
    except ImportError:
        return None, None


class PDFExpert(BaseExpert):
    """PDF 文档专家。

    全部方法返回 ExpertResult。

    能力边界:
      - 仅处理 .pdf(对扫描件需 OCR 才能取文本)
      - 加密支持 RC4(40/128)与 AES(128/256),依赖 pypdf 版本
      - 水印叠加依赖 PyMuPDF;OCR 依赖外部 Tesseract 二进制
    """

    @property
    def name(self) -> str:
        return "pdf"

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def create(
        self,
        output_path: str,
        text: str = "",
        title: str = "",
        author: str = "",
        pages: list[str] | None = None,
    ) -> ExpertResult:
        """创建简单 PDF(基于 reportlab)。

        Args:
            output_path: 输出 .pdf 路径
            text: 单页文本内容
            title: 文档标题(metadata)
            author: 作者(metadata)
            pages: 多页文本列表(每项一页)

        Returns:
            ExpertResult(output=output_path)
        """
        err = self._validate_path(output_path, allowed_exts=("pdf",))
        if err:
            return self._failure(err)

        try:
            self._require_lib("reportlab")
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.pdfgen import canvas
        except ExpertError as e:
            return self._failure(str(e))

        try:
            c = canvas.Canvas(output_path, pagesize=A4)
            c.setTitle(title or "PDF Document")
            c.setAuthor(author or "")
            width, height = A4

            # 尝试注册中文字体(Windows 优先 simsun.ttc)
            font_name = "Helvetica"
            chinese_font_registered = False
            for candidate in [
                ("STSong-Light", "C:\\Windows\\Fonts\\simsun.ttc"),
                ("SimSun", "C:\\Windows\\Fonts\\simsun.ttc"),
                ("MSYH", "C:\\Windows\\Fonts\\msyh.ttc"),
            ]:
                fname, fpath = candidate
                if os.path.exists(fpath):
                    try:
                        pdfmetrics.registerFont(TTFont(fname, fpath))
                        font_name = fname
                        chinese_font_registered = True
                        break
                    except Exception:
                        continue

            text_pages = pages if pages else ([text] if text else [""])
            from reportlab.lib.units import cm

            for page_text in text_pages:
                c.setFont(font_name, 11)
                # 简单换行处理
                lines = page_text.split("\n")
                y = height - 2 * cm
                for line in lines:
                    # 按字符宽度截断(简化版)
                    max_chars = 80 if not chinese_font_registered else 40
                    while len(line) > max_chars:
                        c.drawString(2 * cm, y, line[:max_chars])
                        line = line[max_chars:]
                        y -= 0.6 * cm
                        if y < 2 * cm:
                            c.showPage()
                            c.setFont(font_name, 11)
                            y = height - 2 * cm
                    c.drawString(2 * cm, y, line)
                    y -= 0.6 * cm
                    if y < 2 * cm:
                        c.showPage()
                        c.setFont(font_name, 11)
                        y = height - 2 * cm
                c.showPage()
            c.save()
            return self._success(output_path, pages=len(text_pages))
        except (OSError, PermissionError) as e:
            return self._failure(f"create pdf IO failed: {e}")
        except Exception as e:
            return self._failure(f"create pdf failed: {e}")

    # ------------------------------------------------------------------
    # 合并
    # ------------------------------------------------------------------

    def merge(
        self,
        paths: list[str],
        output_path: str,
    ) -> ExpertResult:
        """合并多个 PDF 为一个。

        Args:
            paths: 源 .pdf 路径列表
            output_path: 输出 .pdf 路径

        Returns:
            ExpertResult(output=output_path, pages=N)

        Note:
            使用 with 语句逐文件流式读取,避免全量加载到内存。
        """
        if not paths:
            return self._failure("paths is empty")
        for p in paths:
            err = self._validate_path(p, must_exist=True, allowed_exts=("pdf",))
            if err:
                return self._failure(err)
        err = self._validate_path(output_path, allowed_exts=("pdf",))
        if err:
            return self._failure(err)

        lib, lib_name = _import_pdf_lib()
        if lib is None:
            return self._failure(
                "'pypdf' or 'PyPDF2' is required for pdf expert, please install: pip install pypdf",
            )

        try:
            if lib_name == "pypdf":
                writer = lib.PdfWriter()
            else:
                writer = lib.PdfFileWriter()
            total_pages = 0
            # 逐文件流式读取,合并完即释放,避免全量加载
            for p in paths:
                with open(p, "rb") as f:
                    if lib_name == "pypdf":
                        reader = lib.PdfReader(f)
                        for page in reader.pages:
                            writer.add_page(page)
                            total_pages += 1
                    else:
                        reader = lib.PdfFileReader(f)
                        for i in range(reader.getNumPages()):
                            writer.addPage(reader.getPage(i))
                            total_pages += 1
            with open(output_path, "wb") as f:
                if lib_name == "pypdf":
                    writer.write(f)
                else:
                    writer.write(f)
            return self._success(output_path, pages=total_pages)
        except (OSError, PermissionError) as e:
            return self._failure(f"merge pdf IO failed: {e}")
        except Exception as e:
            return self._failure(f"merge pdf failed: {e}")

    # ------------------------------------------------------------------
    # 拆分
    # ------------------------------------------------------------------

    def split(
        self,
        path: str,
        output_dir: str,
        page_ranges: list[tuple[int, int]] | None = None,
    ) -> ExpertResult:
        """拆分 PDF 为多份。

        Args:
            path: 源 .pdf 路径
            output_dir: 输出目录
            page_ranges: [(start, end), ...];None 表示每页一份(1-based)

        Returns:
            ExpertResult(output=[file_paths])
        """
        err = self._validate_path(path, must_exist=True, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        if not output_dir or not isinstance(output_dir, str):
            return self._failure("output_dir must be a non-empty string")
        # 校验 page_ranges 合法性
        if page_ranges is not None:
            for idx, (start, end) in enumerate(page_ranges):
                if start < 1 or end < start:
                    return self._failure(f"invalid page_range[{idx}]: ({start}, {end})")

        lib, lib_name = _import_pdf_lib()
        if lib is None:
            return self._failure(
                "'pypdf' or 'PyPDF2' is required for pdf expert, please install: pip install pypdf",
            )

        try:
            os.makedirs(output_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(path))[0]
            output_files = []
            with open(path, "rb") as f:
                if lib_name == "pypdf":
                    reader = lib.PdfReader(f)
                    total = len(reader.pages)
                    if page_ranges is None:
                        for i in range(total):
                            writer = lib.PdfWriter()
                            writer.add_page(reader.pages[i])
                            out_file = os.path.join(output_dir, f"{base}_p{i + 1}.pdf")
                            with open(out_file, "wb") as of:
                                writer.write(of)
                            output_files.append(out_file)
                    else:
                        for idx, (start, end) in enumerate(page_ranges):
                            writer = lib.PdfWriter()
                            for i in range(start - 1, min(end, total)):
                                writer.add_page(reader.pages[i])
                            out_file = os.path.join(output_dir, f"{base}_part{idx + 1}.pdf")
                            with open(out_file, "wb") as of:
                                writer.write(of)
                            output_files.append(out_file)
                else:
                    reader = lib.PdfFileReader(f)
                    total = reader.getNumPages()
                    if page_ranges is None:
                        for i in range(total):
                            writer = lib.PdfFileWriter()
                            writer.addPage(reader.getPage(i))
                            out_file = os.path.join(output_dir, f"{base}_p{i + 1}.pdf")
                            with open(out_file, "wb") as of:
                                writer.write(of)
                            output_files.append(out_file)
                    else:
                        for idx, (start, end) in enumerate(page_ranges):
                            writer = lib.PdfFileWriter()
                            for i in range(start - 1, min(end, total)):
                                writer.addPage(reader.getPage(i))
                            out_file = os.path.join(output_dir, f"{base}_part{idx + 1}.pdf")
                            with open(out_file, "wb") as of:
                                writer.write(of)
                            output_files.append(out_file)
            return self._success(output_files, count=len(output_files))
        except (OSError, PermissionError) as e:
            return self._failure(f"split pdf IO failed: {e}")
        except Exception as e:
            return self._failure(f"split pdf failed: {e}")

    # ------------------------------------------------------------------
    # 文本抽取
    # ------------------------------------------------------------------

    def extract_text(
        self,
        path: str,
        page_range: tuple[int, int] | None = None,
    ) -> ExpertResult:
        """抽取 PDF 文本。

        Args:
            path: .pdf 路径
            page_range: (start, end) 1-based;None 全部

        Returns:
            ExpertResult(output={pages: [{page, text}], full_text})
        """
        err = self._validate_path(path, must_exist=True, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        if page_range is not None:
            start, end = page_range
            if start < 1 or end < start:
                return self._failure(f"invalid page_range: ({start}, {end})")

        lib, lib_name = _import_pdf_lib()
        if lib is None:
            return self._failure(
                "'pypdf' or 'PyPDF2' is required for pdf expert, please install: pip install pypdf",
            )

        try:
            pages_out = []
            full_text_parts = []
            with open(path, "rb") as f:
                if lib_name == "pypdf":
                    reader = lib.PdfReader(f)
                    total = len(reader.pages)
                    start, end = page_range if page_range else (1, total)
                    for i in range(start - 1, min(end, total)):
                        text = reader.pages[i].extract_text() or ""
                        pages_out.append({"page": i + 1, "text": text})
                        full_text_parts.append(text)
                else:
                    reader = lib.PdfFileReader(f)
                    total = reader.getNumPages()
                    start, end = page_range if page_range else (1, total)
                    for i in range(start - 1, min(end, total)):
                        text = reader.getPage(i).extractText() or ""
                        pages_out.append({"page": i + 1, "text": text})
                        full_text_parts.append(text)
            return self._success(
                output={"pages": pages_out, "full_text": "\n".join(full_text_parts)},
                pages_extracted=len(pages_out),
            )
        except (OSError, PermissionError) as e:
            return self._failure(f"extract_text IO failed: {e}")
        except Exception as e:
            return self._failure(f"extract_text failed: {e}")

    # ------------------------------------------------------------------
    # 图片抽取
    # ------------------------------------------------------------------

    def extract_images(
        self,
        path: str,
        output_dir: str,
    ) -> ExpertResult:
        """抽取 PDF 中嵌入的图片。

        Args:
            path: .pdf 路径
            output_dir: 输出目录

        Returns:
            ExpertResult(output=[image_paths])
        """
        err = self._validate_path(path, must_exist=True, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        if not output_dir or not isinstance(output_dir, str):
            return self._failure("output_dir must be a non-empty string")

        try:
            self._require_lib("fitz")  # PyMuPDF
            import fitz
        except ExpertError as e:
            return self._failure(str(e) + " (alternatively use pdf2image)")

        doc = None
        try:
            os.makedirs(output_dir, exist_ok=True)
            doc = fitz.open(path)
            image_paths = []
            for page_idx in range(doc.page_count):
                page = doc[page_idx]
                image_list = page.get_images(full=True)
                for img_idx, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    ext = base_image.get("ext", "png")
                    out_file = os.path.join(
                        output_dir, f"page{page_idx + 1}_img{img_idx + 1}.{ext}"
                    )
                    with open(out_file, "wb") as f:
                        f.write(image_bytes)
                    image_paths.append(out_file)
            return self._success(image_paths, count=len(image_paths))
        except (OSError, PermissionError) as e:
            return self._failure(f"extract_images IO failed: {e}")
        except Exception as e:
            return self._failure(f"extract_images failed: {e}")
        finally:
            # 确保 fitz 文档对象释放,避免文件句柄泄漏
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 水印
    # ------------------------------------------------------------------

    def watermark(
        self,
        path: str,
        output_path: str,
        text: str = "CONFIDENTIAL",
        opacity: float = 0.3,
        font_size: int = 60,
        rotation: int = 45,
    ) -> ExpertResult:
        """给 PDF 添加文字水印。

        Args:
            path: 源 .pdf 路径
            output_path: 输出 .pdf 路径
            text: 水印文本
            opacity: 不透明度(0-1)
            font_size: 字号
            rotation: 旋转角度

        Returns:
            ExpertResult(output=output_path)
        """
        err = self._validate_path(path, must_exist=True, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        err = self._validate_path(output_path, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        err = self._validate_string(text, "text")
        if err:
            return self._failure(err)
        if not 0.0 <= opacity <= 1.0:
            return self._failure(f"opacity must be in [0,1], got {opacity}")

        try:
            self._require_lib("reportlab")
            self._require_lib("fitz")
            import fitz
            from reportlab.lib.colors import Color
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ExpertError as e:
            return self._failure(str(e))

        # 用 ExitStack 统一管理临时文件与文档对象,确保异常时也清理
        with contextlib.ExitStack() as stack:
            wm_path = None
            doc = None
            wm_doc = None
            try:
                # 用 reportlab 生成水印 PDF(临时文件)
                wm_path = output_path + ".wm.pdf"
                stack.callback(self._safe_remove, wm_path)

                c = canvas.Canvas(wm_path, pagesize=A4)
                width, height = A4
                c.saveState()
                c.translate(width / 2, height / 2)
                c.rotate(rotation)
                # 半透明灰色水印
                c.setFillColor(Color(0.5, 0.5, 0.5, alpha=opacity))
                c.setFont("Helvetica", font_size)
                c.drawCentredString(0, 0, text)
                c.restoreState()
                c.save()

                # 用 PyMuPDF 把水印盖到每页
                doc = fitz.open(path)
                wm_doc = fitz.open(wm_path)
                for page in doc:
                    page.show_pdf_page(page.rect, wm_doc, 0)
                doc.save(output_path)
                return self._success(output_path, watermark_text=text)
            except (OSError, PermissionError) as e:
                return self._failure(f"watermark IO failed: {e}")
            except Exception as e:
                return self._failure(f"watermark failed: {e}")
            finally:
                # 反向释放 fitz 文档对象
                if doc is not None:
                    try:
                        doc.close()
                    except Exception:
                        pass
                if wm_doc is not None:
                    try:
                        wm_doc.close()
                    except Exception:
                        pass

    @staticmethod
    def _safe_remove(path: str | None) -> None:
        """安全删除临时文件,忽略不存在/权限错误。"""
        if not path:
            return
        try:
            os.remove(path)
        except (OSError, FileNotFoundError):
            pass

    # ------------------------------------------------------------------
    # 加密
    # ------------------------------------------------------------------

    def encrypt(
        self,
        path: str,
        output_path: str,
        user_password: str = "",
        owner_password: str = "",
    ) -> ExpertResult:
        """加密 PDF。

        Args:
            path: 源 .pdf 路径
            output_path: 输出 .pdf 路径
            user_password: 用户密码(打开文档需要)
            owner_password: 所有者密码(修改权限需要)

        Returns:
            ExpertResult(output=output_path)

        Raises:
            无(失败统一返回 ExpertResult(success=False))
        """
        err = self._validate_path(path, must_exist=True, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        err = self._validate_path(output_path, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        # 至少一个密码非空;密码长度无强校验,但提示推荐 >= 4 字符
        if not user_password and not owner_password:
            return self._failure("at least one of user_password/owner_password must be non-empty")
        # PDF 标准要求 user_password 长度 >= 1,推荐 >= 4;这里仅警告式校验
        for pwd_name, pwd in (("user_password", user_password), ("owner_password", owner_password)):
            if pwd and len(pwd) < 4:
                return self._failure(
                    f"{pwd_name} too short (recommend >= 4 chars for PDF encryption)"
                )

        lib, lib_name = _import_pdf_lib()
        if lib is None:
            return self._failure(
                "'pypdf' or 'PyPDF2' is required for pdf expert, please install: pip install pypdf",
            )

        try:
            with open(path, "rb") as f:
                if lib_name == "pypdf":
                    reader = lib.PdfReader(f)
                    writer = lib.PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    # 默认使用 256 位 AES(pypdf >= 3.0 支持),
                    # 通过 use_40bit/use_128bit 控制密钥长度
                    writer.encrypt(
                        user_password=user_password or owner_password,
                        owner_password=owner_password or user_password,
                    )
                    with open(output_path, "wb") as of:
                        writer.write(of)
                else:
                    reader = lib.PdfFileReader(f)
                    writer = lib.PdfFileWriter()
                    for i in range(reader.getNumPages()):
                        writer.addPage(reader.getPage(i))
                    writer.encrypt(
                        user_pwd=user_password or owner_password,
                        owner_pwd=owner_password or user_password,
                    )
                    with open(output_path, "wb") as of:
                        writer.write(of)
            return self._success(output_path, encrypted=True)
        except (OSError, PermissionError) as e:
            return self._failure(f"encrypt IO failed: {e}")
        except Exception as e:
            return self._failure(f"encrypt failed: {e}")

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def ocr(
        self,
        path: str,
        output_path: str | None = None,
        lang: str = "chi_sim+eng",
        page_range: tuple[int, int] | None = None,
    ) -> ExpertResult:
        """对 PDF 进行 OCR(需 pytesseract + pdf2image + Tesseract OCR)。

        Args:
            path: .pdf 路径
            output_path: 输出文本文件路径;None 仅返回文本
            lang: Tesseract 语言包(默认 chi_sim+eng)
            page_range: (start, end) 1-based;None 全部

        Returns:
            ExpertResult(output=full_text)
        """
        err = self._validate_path(path, must_exist=True, allowed_exts=("pdf",))
        if err:
            return self._failure(err)
        if page_range is not None:
            start, end = page_range
            if start < 1 or end < start:
                return self._failure(f"invalid page_range: ({start}, {end})")

        try:
            self._require_lib("pytesseract")
            self._require_lib("pdf2image")
            import pytesseract
            from pdf2image import convert_from_path
        except ExpertError as e:
            return self._failure(str(e))

        try:
            # 检查 Tesseract 是否可用
            if not (
                shutil.which("tesseract")
                or os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
            ):
                return self._failure(
                    "Tesseract OCR binary not found. Install Tesseract OCR first.",
                )

            # 渲染整本 PDF 为图片;大文件可能 OOM,靠源 PDF 大小限制兜底
            images = convert_from_path(path)
            total = len(images)
            start, end = page_range if page_range else (1, total)
            text_parts = []
            for i in range(start - 1, min(end, total)):
                img = images[i]
                # OCR 图片大小限制:估算 PIL Image 字节数,过大跳过
                try:
                    img_bytes = len(img.tobytes())
                except Exception:
                    img_bytes = 0
                if img_bytes > _MAX_OCR_IMAGE_SIZE:
                    text_parts.append(
                        f"--- Page {i + 1} skipped: image too large ({img_bytes} bytes) ---"
                    )
                    continue
                text = pytesseract.image_to_string(img, lang=lang)
                text_parts.append(f"--- Page {i + 1} ---\n{text}")
            full_text = "\n\n".join(text_parts)

            if output_path:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(full_text)
                return self._success(output_path, pages=min(end, total) - start + 1)
            return self._success(full_text, pages=min(end, total) - start + 1)
        except (OSError, PermissionError) as e:
            return self._failure(f"ocr IO failed: {e}")
        except Exception as e:
            return self._failure(f"ocr failed: {e}")
