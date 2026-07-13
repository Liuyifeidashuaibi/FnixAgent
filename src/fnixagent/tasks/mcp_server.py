"""MCP 协议暴露文档操作(Phase 8.1)。

把 fnixagent 的文档处理能力(WordExpert/ExcelExpert/PPTExpert/PDFExpert/
ParserExpert/FormatNormalizer/RunEditor/ConverterExpert/TaskRouter/
QuestionBankScenario)通过 MCP(Model Context Protocol)暴露给外部 Agent 调用。

职责:
  - register_default_tools:注册默认工具集(9 个核心工具)
  - register_tool:注册自定义工具
  - list_tools:列出工具(可按分类过滤)
  - get_tool_schema:获取工具参数 schema
  - invoke:调用工具(派发到对应 Expert 方法)
  - invoke_by_name:便捷调用
  - to_mcp_manifest:生成 MCP 协议清单(tools 列表 + schema)

设计:
  - 继承 BaseExpert,统一 ExpertResult 返回
  - Expert 实例延迟初始化(首次调用时创建),避免 __init__ 触发依赖加载
  - 实例缓存(同一 Expert 只创建一次)
  - 高风险(destructive=True)操作记录审计日志(print)
  - 借鉴 Office-Word-MCP-Server 的 readOnlyHint/destructiveHint 注解
  - 所有异常不外泄,统一转 _failure
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional

from fnixagent.office.base import BaseExpert, ExpertResult


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ToolAnnotations:
    """MCP 工具注解(符合 MCP 规范)。

    借鉴 Office-Word-MCP-Server 的 readOnlyHint/destructiveHint,
    并扩展 idempotentHint(幂等性提示)。

    Attributes:
        read_only_hint:   是否只读(不修改文件/状态)
        destructive_hint: 是否破坏性(可能覆盖/删除原文件)
        idempotent_hint:  是否幂等(重复调用结果一致)
    """

    read_only_hint: bool = True
    destructive_hint: bool = False
    idempotent_hint: bool = False


@dataclass
class ToolDef:
    """工具定义。

    Attributes:
        name: 工具名(如 "word.read")
        description: 中文描述
        handler: 处理器路径(如 "office.parser.parse_elements")
        params_schema: 参数 JSON Schema
        annotations: 工具注解(符合 MCP 规范)
        category: 分类(如 "office"/"tasks")

    向后兼容:
        read_only / destructive 作为 annotations 的别名(property)
    """

    name: str
    description: str
    handler: str
    params_schema: dict = field(default_factory=dict)
    annotations: ToolAnnotations = field(default_factory=ToolAnnotations)
    category: str = "office"

    # -- 向后兼容属性(映射到 annotations) --------------------------------

    @property
    def read_only(self) -> bool:
        """是否只读(等价于 annotations.read_only_hint)。"""
        return self.annotations.read_only_hint

    @property
    def destructive(self) -> bool:
        """是否破坏性(等价于 annotations.destructive_hint)。"""
        return self.annotations.destructive_hint


@dataclass
class ToolInvocation:
    """工具调用。

    Attributes:
        tool_name: 工具名
        params: 参数 dict
        caller: 调用方标识(默认 "external")
        request_id: 请求ID(用于 tracing/审计)
    """

    tool_name: str
    params: dict = field(default_factory=dict)
    caller: str = "external"
    request_id: str = ""


# ---------------------------------------------------------------------------
# OfficeMCPServer
# ---------------------------------------------------------------------------


class OfficeMCPServer(BaseExpert):
    """MCP 文档操作服务器:把 fnixagent 能力暴露给外部 Agent。

    用法:
        server = OfficeMCPServer()
        tools = server.list_tools()                 # 列出全部工具
        manifest = server.to_mcp_manifest()         # 生成 MCP 清单
        result = server.invoke_by_name(
            "tasks.router.classify",
            description="把答案填入括号",
            file_paths=["a.docx"],
        )
    """

    @property
    def name(self) -> str:
        return "office_mcp_server"

    def __init__(self) -> None:
        """初始化工具注册表与 Expert 实例缓存(延迟创建)。"""
        self._tools: dict[str, ToolDef] = {}
        self._instances: dict[str, Any] = {}
        self.register_default_tools()

    # ------------------------------------------------------------------
    # 工具注册
    # ------------------------------------------------------------------

    def register_default_tools(self) -> None:
        """注册默认工具集(9 个核心工具)。"""
        defaults = [
            ToolDef(
                name="office.parse",
                description="解析文档,返回统一 Element 列表(段落/表格/标题等)",
                handler="office.parser.parse_elements",
                params_schema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "待解析文件路径(docx/xlsx/pdf/pptx/html/csv/json/txt)",
                        },
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
                category="office",
            ),
            ToolDef(
                name="office.format.normalize",
                description="统一文档格式(Word/Excel/PPT 字体/字号/标题样式)",
                handler="office.format_spec.normalize",
                params_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "输入文档路径"},
                        "output_path": {
                            "type": "string",
                            "description": "输出路径;省略则覆盖原文件",
                        },
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
                category="office",
            ),
            ToolDef(
                name="office.word.edit",
                description="Word run 级编辑(替换/插入/删除/填空)",
                handler="office.run_editor.edit_word",
                params_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "输入 .docx 路径"},
                        "ops": {
                            "type": "array",
                            "description": "编辑操作列表,每项为 "
                            "{op_type, target, value, position, preserve_format}",
                            "items": {"type": "object"},
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径;省略则覆盖原文件",
                        },
                    },
                    "required": ["path", "ops"],
                },
                annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
                category="office",
            ),
            ToolDef(
                name="office.excel.read",
                description="读取 Excel 内容为二维列表(含 sheet 名/headers)",
                handler="office.excel.read",
                params_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": ".xlsx 文件路径"},
                        "sheet_name": {
                            "type": "string",
                            "description": "指定 sheet;省略取第一个",
                        },
                        "max_rows": {
                            "type": "integer",
                            "description": "限制最大行数",
                        },
                        "with_header": {
                            "type": "boolean",
                            "description": "是否将首行作为 headers",
                            "default": True,
                        },
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
                category="office",
            ),
            ToolDef(
                name="office.powerpoint.read",
                description="读取 PPT 内容(每页标题/文本/图片/表格/备注)",
                handler="office.powerpoint.read",
                params_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": ".pptx 文件路径"},
                        "slide_range": {
                            "type": "array",
                            "description": "[start, end] 1-based 闭区间",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
                category="office",
            ),
            ToolDef(
                name="office.pdf.extract_text",
                description="提取 PDF 文本(按页/全文)",
                handler="office.pdf.extract_text",
                params_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": ".pdf 文件路径"},
                        "page_range": {
                            "type": "array",
                            "description": "[start, end] 1-based",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
                category="office",
            ),
            ToolDef(
                name="office.convert",
                description="格式转换(Word↔PDF/Excel↔CSV/PPT↔图片 等)",
                handler="office.converter.convert",
                params_schema={
                    "type": "object",
                    "properties": {
                        "source_path": {
                            "type": "string",
                            "description": "源文件路径",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出文件路径",
                        },
                        "target_format": {
                            "type": "string",
                            "description": "目标格式(如 pdf);省略从 output_path 推断",
                        },
                    },
                    "required": ["source_path", "output_path"],
                },
                annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
                category="office",
            ),
            ToolDef(
                name="tasks.question_bank.process",
                description="题库端到端处理(解析题目→恢复答案→填括号→删题号→统一格式→验证)",
                handler="tasks.scenarios.question_bank.process",
                params_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "输入题库 .docx 路径",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径;省略则原文件名+后缀",
                        },
                    },
                    "required": ["file_path"],
                },
                annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True),
                category="tasks",
            ),
            ToolDef(
                name="tasks.router.classify",
                description="任务分类(意图识别+类型推断+高风险标记)",
                handler="tasks.router.classify",
                params_schema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "自然语言任务描述",
                        },
                        "file_paths": {
                            "type": "array",
                            "description": "输入文件路径列表",
                            "items": {"type": "string"},
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径(可选)",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "优先级(0普通/1高/2紧急)",
                            "default": 0,
                        },
                    },
                    "required": ["description"],
                },
                annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False),
                category="tasks",
            ),
            ToolDef(
                name="office.image.extract_storyboard",
                description="从合成分镜图中均匀切割网格单元(如 24 格分镜头),"
                "每单元输出独立 PNG(无损、尺寸统一)。"
                "auto_crop_text=True 时智能检测并裁剪每格底部文字描述带。",
                handler="office.image.extract_grid_cells",
                params_schema={
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "输入图像路径(png/jpg/bmp/tiff/webp)",
                        },
                        "rows": {
                            "type": "integer",
                            "description": "网格行数;省略自动推断",
                        },
                        "cols": {
                            "type": "integer",
                            "description": "网格列数;省略自动推断",
                        },
                        "expected_count": {
                            "type": "integer",
                            "description": "期望单元数(默认 24),用于自动推断 rows×cols",
                            "default": 24,
                        },
                        "output_dir": {
                            "type": "string",
                            "description": "输出目录;省略在源图同目录建 <stem>_cells/",
                        },
                        "filename_prefix": {
                            "type": "string",
                            "description": "输出文件名前缀(默认 shot_)",
                            "default": "shot_",
                        },
                        "auto_crop_text": {
                            "type": "boolean",
                            "description": "是否自动检测并裁剪每格底部文字描述带。"
                            "True 时逐格分析行方差剖面,智能定位文字边界;"
                            "无文字带的格子保留整格。",
                            "default": False,
                        },
                        "crop_text_ratio": {
                            "type": "number",
                            "description": "底部文字带裁剪比例(0.0~0.5),仅 auto_crop_text=False 时生效。"
                            "0.0=不裁(纯切割);0.15=裁掉底部 15%(典型文字带)。",
                            "default": 0.0,
                        },
                    },
                    "required": ["image_path"],
                },
                annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False),
                category="office",
            ),
            ]
        for tool in defaults:
            self._tools[tool.name] = tool

    def register_tool(self, tool: ToolDef) -> ExpertResult:
        """注册自定义工具。

        Args:
            tool: 工具定义(名称不能与已有工具重复)

        Returns:
            ExpertResult(success=True, output=tool.name) 或 _failure
        """
        try:
            if not tool.name or not isinstance(tool.name, str):
                return self._failure("tool.name must be a non-empty string")
            if not tool.handler or not isinstance(tool.handler, str):
                return self._failure("tool.handler must be a non-empty string")
            if tool.name in self._tools:
                return self._failure(f"tool '{tool.name}' already registered")
            self._tools[tool.name] = tool
            return self._success(tool.name, tool_count=len(self._tools))
        except Exception as e:
            return self._failure(f"register_tool error: {e}")

    # ------------------------------------------------------------------
    # 工具查询
    # ------------------------------------------------------------------

    def list_tools(self, category: Optional[str] = None) -> list[ToolDef]:
        """列出工具(可按分类过滤)。

        Args:
            category: 分类过滤(如 "office"/"tasks");None 返回全部

        Returns:
            工具定义列表(按注册顺序)
        """
        if category is None:
            return list(self._tools.values())
        return [t for t in self._tools.values() if t.category == category]

    def get_tool_schema(self, name: str) -> Optional[dict]:
        """获取工具参数 schema。

        Args:
            name: 工具名

        Returns:
            参数 JSON Schema;工具不存在返回 None
        """
        tool = self._tools.get(name)
        if tool is None:
            return None
        return tool.params_schema

    # ------------------------------------------------------------------
    # 工具调用
    # ------------------------------------------------------------------

    def invoke(self, invocation: ToolInvocation) -> ExpertResult:
        """调用工具。

        根据 tool_name 派发到对应 Expert 处理器;
        高风险(destructive=True)操作记录审计日志。

        Args:
            invocation: 工具调用请求

        Returns:
            ExpertResult(success/output/error/metadata)
        """
        tool = self._tools.get(invocation.tool_name)
        if tool is None:
            return self._failure(f"unknown tool: {invocation.tool_name}")

        # 高风险操作审计日志(实际可接 audit.logger)
        if tool.destructive:
            print(
                f"[AUDIT] destructive tool '{invocation.tool_name}' invoked "
                f"by caller='{invocation.caller}', "
                f"request_id='{invocation.request_id}'"
            )

        # 参数校验:必填参数缺失返回 _failure
        if not isinstance(invocation.params, dict):
            return self._failure("params must be a dict")
        err = self._validate_required(tool, invocation.params)
        if err:
            return self._failure(err)

        return self._dispatch(invocation.tool_name, invocation.params)

    def invoke_by_name(self, tool_name: str, **params: Any) -> ExpertResult:
        """便捷调用:工具名 + 关键字参数。

        Args:
            tool_name: 工具名
            **params: 工具参数

        Returns:
            ExpertResult
        """
        return self.invoke(
            ToolInvocation(tool_name=tool_name, params=dict(params))
        )

    # ------------------------------------------------------------------
    # MCP 清单
    # ------------------------------------------------------------------

    def to_mcp_manifest(self) -> dict:
        """生成 MCP 协议清单(tools 列表 + schema)。

        兼容 Anthropic MCP tools/list 响应格式,
        额外携带 readOnlyHint/destructiveHint/idempotentHint 注解。

        Returns:
            {
                "server_name": "office_mcp_server",
                "version": "1.0.0",
                "tools": [
                    {
                        "name", "description", "inputSchema",
                        "annotations": {
                            "readOnlyHint", "destructiveHint", "idempotentHint"
                        },
                        "category",
                    },
                    ...
                ],
            }
        """
        tools = []
        for t in self.list_tools():
            tools.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.params_schema,
                    "annotations": {
                        "readOnlyHint": t.annotations.read_only_hint,
                        "destructiveHint": t.annotations.destructive_hint,
                        "idempotentHint": t.annotations.idempotent_hint,
                    },
                    "category": t.category,
                }
            )
        return {
            "server_name": self.name,
            "version": "1.0.0",
            "tools": tools,
        }

    # ------------------------------------------------------------------
    # 内部:Expert 实例延迟初始化
    # ------------------------------------------------------------------

    def _get_instance(self, key: str) -> Any:
        """按 key 延迟创建并缓存 Expert 实例。

        首次调用时创建,后续直接返回缓存。

        Args:
            key: Expert 标识(如 "parser"/"excel"/"task_router")

        Returns:
            Expert 实例

        Raises:
            KeyError: 未知 key
        """
        if key in self._instances:
            return self._instances[key]
        if key == "parser":
            from fnixagent.office.parser import ParserExpert

            inst: Any = ParserExpert()
        elif key == "format_normalizer":
            from fnixagent.office.format_spec import FormatNormalizer

            inst = FormatNormalizer()
        elif key == "run_editor":
            from fnixagent.office.run_editor import RunEditor

            inst = RunEditor()
        elif key == "excel":
            from fnixagent.office.excel import ExcelExpert

            inst = ExcelExpert()
        elif key == "ppt":
            from fnixagent.office.powerpoint import PPTExpert

            inst = PPTExpert()
        elif key == "pdf":
            from fnixagent.office.pdf import PDFExpert

            inst = PDFExpert()
        elif key == "image":
            from fnixagent.office.image import ImageExpert

            inst = ImageExpert()
        elif key == "converter":
            from fnixagent.office.converter import ConverterExpert

            inst = ConverterExpert()
        elif key == "question_bank":
            from fnixagent.tasks.scenarios.question_bank import (
                QuestionBankScenario,
            )

            inst = QuestionBankScenario()
        elif key == "task_router":
            from fnixagent.tasks.router import TaskRouter

            inst = TaskRouter()
        else:
            raise KeyError(f"unknown expert key: {key}")
        self._instances[key] = inst
        return inst

    # ------------------------------------------------------------------
    # 内部:参数校验
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_required(tool: ToolDef, params: dict) -> Optional[str]:
        """校验必填参数是否齐全。

        Args:
            tool: 工具定义
            params: 实际参数

        Returns:
            失败原因字符串;通过返回 None
        """
        schema = tool.params_schema or {}
        required = schema.get("required", [])
        if not required:
            return None
        for name in required:
            if name not in params:
                return f"missing required parameter: {name}"
            val = params[name]
            # 空字符串/空列表视同缺失
            if isinstance(val, (str, list)) and not val:
                return f"required parameter '{name}' must be non-empty"
        return None

    # ------------------------------------------------------------------
    # 内部:工具派发
    # ------------------------------------------------------------------

    def _dispatch(self, tool_name: str, params: dict) -> ExpertResult:
        """根据 tool_name 派发到对应 Expert 处理器。

        所有异常捕获后转 _failure,不外泄。
        """
        try:
            if tool_name == "office.parse":
                inst = self._get_instance("parser")
                return inst.parse_elements(path=params["path"])

            elif tool_name == "office.format.normalize":
                inst = self._get_instance("format_normalizer")
                return inst.normalize(
                    path=params["path"],
                    output_path=params.get("output_path"),
                )

            elif tool_name == "office.word.edit":
                inst = self._get_instance("run_editor")
                ops, err = self._build_edit_ops(params["ops"])
                if err is not None:
                    return self._failure(err)
                return inst.edit_word(
                    path=params["path"],
                    ops=ops,
                    output_path=params.get("output_path"),
                )

            elif tool_name == "office.excel.read":
                inst = self._get_instance("excel")
                return inst.read(
                    path=params["path"],
                    sheet_name=params.get("sheet_name"),
                    max_rows=params.get("max_rows"),
                    with_header=params.get("with_header", True),
                )

            elif tool_name == "office.powerpoint.read":
                inst = self._get_instance("ppt")
                slide_range = params.get("slide_range")
                if slide_range is not None:
                    slide_range = tuple(slide_range)
                return inst.read(path=params["path"], slide_range=slide_range)

            elif tool_name == "office.pdf.extract_text":
                inst = self._get_instance("pdf")
                page_range = params.get("page_range")
                if page_range is not None:
                    page_range = tuple(page_range)
                return inst.extract_text(
                    path=params["path"], page_range=page_range
                )

            elif tool_name == "office.convert":
                inst = self._get_instance("converter")
                return inst.convert(
                    source_path=params["source_path"],
                    output_path=params["output_path"],
                    target_format=params.get("target_format"),
                )

            elif tool_name == "office.image.extract_storyboard":
                inst = self._get_instance("image")
                return inst.extract_grid_cells(
                    image_path=params["image_path"],
                    rows=params.get("rows"),
                    cols=params.get("cols"),
                    expected_count=params.get("expected_count", 24),
                    output_dir=params.get("output_dir"),
                    filename_prefix=params.get("filename_prefix", "shot_"),
                    auto_crop_text=params.get("auto_crop_text", False),
                    crop_text_ratio=params.get("crop_text_ratio", 0.0),
                )

            elif tool_name == "tasks.question_bank.process":
                inst = self._get_instance("question_bank")
                return inst.process(
                    file_path=params["file_path"],
                    output_path=params.get("output_path"),
                )

            elif tool_name == "tasks.router.classify":
                from fnixagent.tasks.dsl import TaskRequest

                inst = self._get_instance("task_router")
                req = TaskRequest(
                    description=params.get("description", ""),
                    file_paths=list(params.get("file_paths", [])),
                    output_path=params.get("output_path"),
                    priority=params.get("priority", 0),
                )
                result_req = inst.classify(req)
                # classify 返回 TaskRequest(原地回填),非 ExpertResult,需包装
                return self._success(
                    output={
                        "task_type": result_req.task_type.value,
                        "intents": [i.value for i in result_req.intents],
                        "requires_confirmation": result_req.requires_confirmation,
                        "task_id": result_req.task_id,
                    },
                    tool=tool_name,
                )

            else:
                return self._failure(f"tool '{tool_name}' has no dispatcher")

        except Exception as e:
            return self._failure(f"dispatch error: {e}", tool=tool_name)

    # ------------------------------------------------------------------
    # 内部:EditOp 构造(office.word.edit 用)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_edit_ops(ops_raw: Any) -> tuple[list, Optional[str]]:
        """把 dict 列表转为 EditOp 列表。

        Args:
            ops_raw: 原始 ops(list[dict] 或 list[EditOp])

        Returns:
            (ops, error):成功时 error=None;失败时 ops=[], error=原因
        """
        from fnixagent.office.run_editor import EditOp

        if not isinstance(ops_raw, list) or not ops_raw:
            return [], "ops must be a non-empty list"
        known = {f.name for f in dataclasses.fields(EditOp)}
        ops: list = []
        for i, op in enumerate(ops_raw):
            if isinstance(op, EditOp):
                ops.append(op)
            elif isinstance(op, dict):
                filtered = {k: v for k, v in op.items() if k in known}
                try:
                    ops.append(EditOp(**filtered))
                except TypeError as e:
                    return [], f"invalid op[{i}]: {e}"
            else:
                return (
                    [],
                    f"invalid op[{i}]: must be dict, got {type(op).__name__}",
                )
        return ops, None
