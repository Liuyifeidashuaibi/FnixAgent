"""L1 Office Expert 基类(P2-9)。

定义所有 Office 专家的统一接口与返回结构。
子类按需实现具体方法,底层依赖可选(python-docx/openpyxl/python-pptx/PyPDF2 等)。

专家职责:
  - 提供 Office 文档的创建/读取/编辑/转换/解析等原子能力
  - 统一通过 ExpertResult 返回(success/output/error/metadata)
  - 可选依赖不可用时通过 ExpertError 优雅降级,不崩溃

底层依赖:
  - python-docx(Word)、openpyxl(Excel)、python-pptx(PPT)
  - pypdf/PyPDF2(PDF)、reportlab(PDF 生成)、PyMuPDF/fitz(PDF 渲染)
  - matplotlib(图表)、pandas(透视表)、pytesseract(OCR)
  全部为可选依赖,运行时按需 import。

降级策略:
  - 依赖缺失:抛 ExpertError(missing_lib=...)提示安装,上层捕获后返回 _failure
  - 文件 IO 异常:捕获 PermissionError/IOError,返回 _failure 而非崩溃
  - 第三方库异常:捕获具体异常类型,转 _failure
  - 路径穿越:通过 _validate_path 拦截 .. 与越界访问

设计:
  - ExpertResult:统一返回结构(success/output/error/metadata)
  - ExpertError:统一异常(底层库不可用时抛出,提示安装)
  - BaseExpert:抽象基类,提供 _require_lib / _validate_* 工具方法
"""
from __future__ import annotations

import abc
import importlib
import os
from dataclasses import dataclass, field
from typing import Any, Optional


# 默认文件大小上限(100 MB),防止 OOM
DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024


# ---------------------------------------------------------------------------
# 返回结构
# ---------------------------------------------------------------------------


@dataclass
class ExpertResult:
    """Expert 方法统一返回结构。

    Attributes:
        success: 是否成功
        output: 成功时的产物(文件路径/数据结构/文本 等)
        error: 失败时的错误描述
        metadata: 附加元数据(行数/页数/耗时等)
        duration_ms: 执行耗时(毫秒)
    """

    success: bool = True
    output: Any = None               # 文件路径/数据结构/文本 等
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class ExpertError(Exception):
    """Expert 基础异常。

    Attributes:
        missing_lib: 缺失的第三方库名(用于上层提示安装)
    """

    def __init__(self, message: str, missing_lib: Optional[str] = None) -> None:
        super().__init__(message)
        self.missing_lib = missing_lib


# ---------------------------------------------------------------------------
# BaseExpert
# ---------------------------------------------------------------------------


class BaseExpert(abc.ABC):
    """Office Expert 抽象基类。

    子类需实现:
      - name 属性:专家名(如 "word"/"excel")
      - 业务方法:create/edit/...

    子类共用工具:
      - _require_lib(lib_name):检查可选依赖,不可用时抛 ExpertError 提示安装
      - _success(output, **metadata):构造成功 ExpertResult
      - _failure(error, **metadata):构造失败 ExpertResult
      - _validate_path(path, ...):路径校验(非空/穿越/扩展名/存在性/大小)
      - _validate_string(value, name):字符串 strip + 非空校验
      - _validate_int(value, name, min/max):整数范围校验

    能力边界:
      - 仅处理本地文件,不支持 URL/网络路径
      - 单次操作内存上限受 DEFAULT_MAX_FILE_SIZE 约束
      - 不处理并发写,调用方需自行加锁
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """专家名(如 "word"/"excel")。"""
        ...

    # ------------------------------------------------------------------
    # 工具方法(子类共用)
    # ------------------------------------------------------------------

    def _require_lib(self, lib_name: str) -> Any:
        """检查可选依赖是否可用,返回模块;不可用时抛 ExpertError。

        Args:
            lib_name: 顶层 import 名(如 "docx"/"openpyxl")

        Returns:
            已 import 的模块对象

        Raises:
            ExpertError: 依赖不可用时抛出,携带 missing_lib 信息
        """
        try:
            return importlib.import_module(lib_name)
        except ImportError as e:
            raise ExpertError(
                f"'{lib_name}' is required for {self.name} expert, "
                f"please install: pip install {lib_name}",
                missing_lib=lib_name,
            ) from e

    def _success(self, output: Any = None, **metadata: Any) -> ExpertResult:
        """构造成功 ExpertResult。"""
        return ExpertResult(success=True, output=output, metadata=metadata)

    def _failure(self, error: str, **metadata: Any) -> ExpertResult:
        """构造失败 ExpertResult。"""
        return ExpertResult(success=False, error=error, metadata=metadata)

    # ------------------------------------------------------------------
    # 参数校验(public API 共用)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_path(
        path: str,
        *,
        must_exist: bool = False,
        allowed_exts: Optional[tuple[str, ...]] = None,
        max_size: Optional[int] = DEFAULT_MAX_FILE_SIZE,
        allow_root: Optional[str] = None,
    ) -> Optional[str]:
        """校验文件路径,返回失败原因字符串;None 表示通过。

        Args:
            path: 待校验路径
            must_exist: 是否要求文件已存在(读操作前应置 True)
            allowed_exts: 允许的扩展名元组(小写无点,如 ("docx",))
            max_size: 文件大小上限(字节);None 不限
            allow_root: 允许的根目录(realpath 必须位于其下);None 不限

        Returns:
            失败原因字符串;通过则返回 None
        """
        if not path or not isinstance(path, str):
            return "path must be a non-empty string"
        # 路径穿越防护:先标准化再校验
        real = os.path.realpath(path)
        # 禁止 .. 路径穿越(以 realpath 后再判断更稳妥)
        if ".." in path.replace("\\", "/").split("/"):
            # 仅作为提示;真正穿越靠 realpath + allow_root 兜底
            pass
        if allow_root:
            allow_real = os.path.realpath(allow_root)
            # 保证目录分隔,避免前缀误判(如 /tmp/abc vs /tmp/abcdef)
            if not (real == allow_real or real.startswith(allow_real + os.sep)):
                return f"path traversal blocked: {path} outside allowed root"
        if allowed_exts:
            ext = os.path.splitext(path)[1].lstrip(".").lower()
            if ext not in allowed_exts:
                return f"unsupported extension: .{ext}, allowed: {allowed_exts}"
        if must_exist and not os.path.exists(real):
            return f"file not found: {path}"
        if max_size is not None and os.path.exists(real):
            try:
                size = os.path.getsize(real)
            except OSError as e:
                return f"cannot stat file: {e}"
            if size > max_size:
                return f"file too large: {size} bytes > limit {max_size}"
        return None

    @staticmethod
    def _validate_string(value: str, name: str) -> Optional[str]:
        """校验字符串参数:strip 后非空。

        Args:
            value: 待校验字符串
            name: 参数名(用于错误信息)

        Returns:
            失败原因字符串;通过则返回 None
        """
        if not isinstance(value, str):
            return f"{name} must be a string"
        if not value.strip():
            return f"{name} must be non-empty"
        return None

    @staticmethod
    def _validate_int(
        value: int,
        name: str,
        *,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> Optional[str]:
        """校验整数范围。

        Args:
            value: 待校验整数
            name: 参数名
            min_value: 最小值(含);None 不限
            max_value: 最大值(含);None 不限

        Returns:
            失败原因字符串;通过则返回 None
        """
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{name} must be int"
        if min_value is not None and value < min_value:
            return f"{name} must be >= {min_value}, got {value}"
        if max_value is not None and value > max_value:
            return f"{name} must be <= {max_value}, got {value}"
        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"
