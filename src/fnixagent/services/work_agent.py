"""Work 模式 Agent 装配 — 办公工作台主路径。

对齐工程实践：任务拆解 → 调 Office/业务工具 → 可交付产物。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fnixagent.core.agent.loop import AgenticLoop
from fnixagent.core.llm.adapter import LLMAdapter
from fnixagent.core.tools.protocol import ToolMetadata
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.tools.workspace import register_workspace_tools
from fnixagent.core.types import ToolPermission

logger = logging.getLogger(__name__)
_logger = logger


WORK_SYSTEM_PROMPT = """你是 FnixAgent 办公工作台助手（对齐行业最佳实践 + Work 内的 Code 能力）。
你拥有自进化内核：KTG 知识拓扑检索 + STP 技能突触调度 + MFP 四阶飞轮。
你帮助用户完成学习、教育、办公与编码任务：周报、文档、Excel、PPT、PDF、网站/HTML、脚本、资料检索等。

模式说明（对齐行业最佳实践）：
- 你当前是 **Work（Chat）模式**：通用工作台，**也可以写代码、做网站**（与 Code 同等落盘标准）。
- **Code** 是专精编码模式：绑定项目文件夹、先预览 diff 再 Accept；Work 则直接 write_file 落盘到工作区。

规则:
1. 先理解任务目标与验收标准，再调用工具执行
2. **写盘契约**：交付文件写到工作区的「自然路径」——若任务指向仓库中已存在的文件(或要求修改现有代码)，直接在原路径编辑；新建文件时用任务隐含的相对路径(相对工作区根，如 `index.html`、`src/components/header/header.component.ts`)。如需在产物预览面板展示，可把同一文件再写入 `.fnix/artifacts/<项目名>/<相对路径>` 作为镜像(二者至少其一，且不要只写 .fnix 而遗漏原路径)。
3. 写代码文件时，`content` 必须是完整可运行源码，禁止只写「创建xxx文件」这类说明文字
4. 用户要求创建网站 / HTML / CSS / JS / 编码任务时，**必须**通过 tools API 调用 `write_file`（file_path + content）写入完整源码到任务要求的自然相对路径；写完后列出真实路径
5. **严禁**用 `<write_file>` / `<path>` / `<content>` XML 假装调用工具（不会落盘）
6. 纯前端/静态站不要跑 pytest；没有测试用例时不要强行 test
7. 需要信息时先读文件 / 检索，再生成
8. 若系统提示中给出「KTG 推理路径」，优先沿该路径选择对应技能
9. 若加载了「项目技能」，优先匹配技能描述
10. 回复简洁，说明产物路径与下一步可验收点
11. **对齐现有项目结构**：写盘前先 `ls` / `glob` 工作区，了解既有目录约定。若任务描述的相对路径（如 `components/...`、`src/...`、`app/...`）与脚手架已有目录不一致，优先把文件放到「约定目录」下（例如源码都在 `src/` 下就写到 `src/components/...`），不要凭空在工作区根新建同名目录；若任务指向的「组件/模块」在脚手架中已存在，直接编辑原文件而非新建同名文件。
12. **内置浏览器优先**：搜索网页 / 浏览网页 / 读取页面内容 / 操作页面元素时，用两个正交原语——`browser_view`（只读看页面，what=refs|text|all）与 `browser_act`（写操作页面，action=goto|click|type|scroll|back|forward|refresh|wait|viewport）。调 `browser_act(action="goto", url=...)` 可直接传网址或搜索关键词，搜索与浏览都在应用内置浏览器中完成并展示给用户；典型节奏是 `browser_view` 看一眼 → `browser_act` 操作 → 再 `browser_view` 确认。**严禁**用 run_command 的 start/explorer 或 desktop_launch 打开 Edge/Chrome 等系统浏览器打扰用户。需要操控电脑原生应用（打开软件、点击桌面程序、输入登录等）时才用 `desktop_*` 工具。

你当前的工作目录是: {workspace_root}
"""


def format_code_task_prompt() -> str:
    """Work 模式下检测到编码/建站任务时追加的提示（工作模式编码任务检测）。"""
    return """

## 编码/应用生成任务（Work 内可做，对齐工程实践 Work App generation + Craft 模式）
你现在处于 **Work 模式的 Craft 执行态**：必须动手写文件，不能只聊天。
1. 立刻用 **tools API** 调用 `write_file`（每个文件一次），参数名是 `file_path` 与 `content`
2. 静态网站最少三个文件（写到工作区自然路径，不要只塞进 .fnix/artifacts）：
   - `index.html` (或任务要求的文件名)
   - `style.css`
   - `script.js`
3. HTML 必须引用 style.css / script.js；JS 含真实交互逻辑
4. **禁止**只输出「创建项目基础结构」「接下来我会…」而不调用工具
5. **禁止**输出 `<write_file>...</write_file>` XML；必须走 function calling
6. 写完后列出产物路径与打开方式（如双击 index.html）
7. 与 Code 同属 Chat 交付：小项目写到工作区根或任务要求的相对路径；如需预览可镜像到 `.fnix/artifacts/<项目名>/`；已 Open project 时直接改仓库文件（preview → Accept）
"""


def wrap_code_user_input(user_input: str) -> str:
    """把编码类用户输入改写成强制落盘指令（减少 LLM 只聊天不写文件）。"""
    text = (user_input or "").strip()
    return (
        f"{text}\n\n"
        "【强制执行 · Work Craft】这是可交付编码/建站任务。"
        "请立即用 tools API 调用 write_file（file_path + content）写入完整源码；"
        "禁止输出 <write_file> XML；不要只回复计划或说明文字。"
        "写到任务要求的相对路径(如 index.html、src/components/...)，必要时可镜像到 "
        "`.fnix/artifacts/<项目名>/` 供预览，但不要只写 .fnix 而遗漏原路径。"
    )


# 工作台式执行模式：Ask（只问）/ Plan（先想）/ Craft（做一做）
WorkExecMode = str  # "ask" | "plan" | "craft"

_MUTATING_TOOL_NAMES = frozenset(
    {
        "write_file",
        "edit_file",
        "delete_file",
        "create_docx",
        "edit_docx",
        "format_docx",
        "create_xlsx",
        "create_pptx",
        "create_pdf",
        "create_chart",
        "convert_document",
    }
)

# Craft 建站/编码时收窄工具面，避免模型忽略 write_file
# show_widget 保留：编码任务中仍可内联展示架构图/对比矩阵（dynamic-ui）
_CRAFT_CODE_TOOL_ALLOW = frozenset(
    {
        "write_file",
        "edit_file",
        "read_file",
        "ls",
        "glob",
        "grep",
        "delete_file",
        "run_command",
        "web_search",
        "web_fetch",
        "show_widget",
        # 内置浏览器（Phase 5 收敛为两个正交原语）：建站/编码任务可打开参考网站或实时预览页面
        #   browser_view = 只读（看页面，what=refs|text|all）
        #   browser_act  = 写操作（action=goto|click|type|scroll|back|forward|refresh|wait|viewport）
        "browser_view",
        "browser_act",
    }
)

_CODE_TASK_HINTS = (
    "代码",
    "编程",
    "html",
    "css",
    "javascript",
    "typescript",
    "前端",
    "网站",
    "网页",
    "mbti",
    "小程序",
    "脚本",
    "组件",
    "落地页",
    "index.html",
    "vue",
    "react",
    "写一个",
    "做一个",
    "创建网站",
    "生成页面",
    "静态站",
    "webpage",
    "website",
)


def looks_like_code_craft_task(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    return any(h in text for h in _CODE_TASK_HINTS)


def normalize_work_mode(mode: str | None) -> str:
    m = (mode or "craft").strip().lower()
    if m in ("ask", "plan", "craft"):
        return m
    return "craft"


def format_ask_prompt() -> str:
    return """

## 执行模式：Ask（问一问 · 对齐工程实践 Ask）
- 只回答问题、解释、给建议，**禁止**创建/修改/删除任何文件
- 不可调用 write_file / edit_file / 办公生成类写盘工具
- 若用户需要落盘交付，请提示切换到 **Craft（做一做）**
"""


def format_plan_prompt() -> str:
    return """

## 执行模式：Plan（想一想 · 对齐工程实践 Plan）
- 先输出清晰可执行计划（步骤、产物路径、风险），**本回合不写盘**
- 可读文件做调研；禁止 write_file / 生成文档写盘
- 计划确认后用户会切到 **Craft** 再执行
"""


def strip_mutating_tools(registry: ToolRegistry) -> None:
    """Ask/Plan 模式下移除写盘工具。"""
    for name in list(_MUTATING_TOOL_NAMES):
        try:
            registry.unregister(name)
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)


class _StpAwareRegistry:
    """在 ToolRegistry 之上叠加 STP 优先级排序 + 成功/失败反馈。"""

    # STP 统一 top_k (修复两套独立选择 top_k 不一致的问题)
    # 与 work_pipeline.step5b_stp_select 的 top_k=5 保持一致
    STP_TOP_K = 5

    def __init__(
        self,
        registry: ToolRegistry,
        scheduler: Any = None,
        feedback: Any = None,
        path: Any = None,
    ):
        self._registry = registry
        self._scheduler = scheduler
        self._feedback = feedback
        self._path = path

    def execute(self, tool_name: str, args: dict) -> Any:
        try:
            result = self._registry.execute(tool_name, args)
            ok = True
            if isinstance(result, dict) and result.get("success") is False:
                ok = False
            if self._feedback:
                if ok:
                    self._feedback.on_skill_success(tool_name, path=self._path)
                else:
                    self._feedback.on_skill_failure(tool_name, path=self._path)
            return result
        except Exception:
            if self._feedback:
                try:
                    self._feedback.on_skill_failure(tool_name, path=self._path)
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)
            raise

    def get_tool_definitions(self) -> list[dict]:
        if self._scheduler is not None:
            try:
                selected = self._scheduler.select_skills(path=self._path, top_k=self.STP_TOP_K)
                names = {t.name for t in selected}
                all_defs = self._registry.get_tool_definitions()
                prioritized = [d for d in all_defs if d.get("function", {}).get("name") in names]
                rest = [d for d in all_defs if d.get("function", {}).get("name") not in names]
                return prioritized + rest
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        return self._registry.get_tool_definitions()

    def get_tools_description(self) -> str:
        if self._scheduler is not None:
            try:
                selected = self._scheduler.select_skills(path=self._path, top_k=self.STP_TOP_K)
                if selected:
                    lines = [f"- {t.name}: {t.description}" for t in selected]
                    return "\n".join(lines)
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        return self._registry.get_tools_description()


def _format_ktg_context(paths: list) -> str:
    if not paths:
        return ""
    lines = ["\n\n## KTG 推理路径（必须优先参考）"]
    for i, path in enumerate(paths[:3], 1):
        nodes = getattr(path, "nodes", None) or []
        names = []
        for n in nodes:
            if isinstance(n, str):
                names.append(n)
            else:
                names.append(getattr(n, "name", None) or str(n))
        weight = getattr(path, "total_weight", 0)
        lines.append(f"{i}. 权重={weight:.3f} · {' → '.join(names)}")
    return "\n".join(lines)


def run_mfp_after_task(
    components: Any,
    user_input: str,
    success: bool,
    tool_calls: list[dict],
    duration_ms: float = 0.0,
    concept_path: list[str] | None = None,
    workspace: str = "",
    critic_skipped: bool = False,
) -> dict:
    """任务结束后跑 MFP ②③④（① 由 Work AgenticLoop 承担）。

    critic_skipped: Spec 7 fail-soft-with-signal 闭环, 让 MFP 第 3 阶
        (元反思) 可统计 critic.skip_rate 健康度指标。
    """
    import time
    import uuid

    from fnixagent.core.types import ReasoningMode, TraceRecord

    out: dict = {"solidified": None, "reflected": None, "climbed": False}
    if components is None:
        return out

    trace = TraceRecord(
        trace_id=str(uuid.uuid4()),
        task_id=str(uuid.uuid4()),
        goal=user_input,
        mode=ReasoningMode.REACT,
        concept_path=concept_path or [],
        tool_calls=tool_calls,
        success=success,
        duration_ms=duration_ms,
        created_at=time.time(),
        critic_skipped=critic_skipped,
    )
    try:
        components.trace_store.append(trace)
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)
    try:
        out["solidified"] = components.flywheel_solidification.process(trace)
    except Exception as e:
        out["solidified"] = {"error": str(e)}
    try:
        if components.flywheel_reflection.should_trigger():
            out["reflected"] = components.flywheel_reflection.run()
    except Exception as e:
        out["reflected"] = {"error": str(e)}
    try:
        if components.flywheel_climbing.should_trigger():
            components.flywheel_climbing.run()
            out["climbed"] = True
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)

    # 注: Intelligence 七层闭环由上层 work_pipeline.py 主路径统一触发,
    # 避免双重调用导致 L5 记忆重复写入 / L7 重复审判 / L6 重复技能创建。
    # run_mfp_after_task 仅专注 MFP 飞轮 (②固化/③反思/④爬坡)。
    return out


_PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1/",
    "glm": "https://open.bigmodel.cn/api/paas/v4/",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1/",
    "deepseek": "https://api.deepseek.com/v1/",
}


def _dict_kwargs(fn: Callable[..., Any]) -> Callable[[dict], Any]:
    """把 AgenticLoop 传入的 args dict 拆成关键字参数。"""
    sig = inspect.signature(fn)
    params = set(sig.parameters.keys())

    def runner(args: dict) -> Any:
        if not isinstance(args, dict):
            return fn(args)
        kwargs = {k: v for k, v in args.items() if k in params}
        return fn(**kwargs)

    return runner


def adapter_from_llm_override(llm: dict | None = None) -> LLMAdapter:
    """从请求级 llm 覆盖或环境变量构建适配器。"""
    from fnixagent.services.llm_policy import normalize_llm_model

    llm = llm or {}
    api_key = (llm.get("api_key") or llm.get("apiKey") or "").strip()
    provider = (llm.get("provider") or "").strip().lower()
    model = normalize_llm_model((llm.get("model") or "").strip(), provider)
    base_url = (llm.get("base_url") or llm.get("baseUrl") or "").strip()

    # 请求级 LLM 请求超时（秒）；仅在合法正值时透传，否则由适配器决定默认值
    req_timeout = llm.get("timeout")
    try:
        req_timeout = float(req_timeout) if req_timeout else None
        if req_timeout is not None and req_timeout <= 0:
            req_timeout = None
    except (TypeError, ValueError):
        req_timeout = None

    if api_key:
        if not base_url and provider in _PROVIDER_BASE_URLS:
            base_url = _PROVIDER_BASE_URLS[provider]
        if not base_url and provider in ("qwen", "dashscope"):
            base_url = _PROVIDER_BASE_URLS["qwen"]
        return LLMAdapter(
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            provider_name=provider or "custom",
            timeout=req_timeout,
        )

    # 无客户端 Key：回退服务端环境（含 DASHSCOPE_API_KEY）
    env_model = normalize_llm_model(
        model or os.getenv("LLM_MODEL") or os.getenv("QWEN_MODEL") or "",
        provider or os.getenv("LLM_PROVIDER") or "",
    )
    env_provider = provider or os.getenv("LLM_PROVIDER") or ""
    return LLMAdapter(model_name=env_model, provider_name=env_provider, timeout=req_timeout)


def register_office_work_tools(
    registry: ToolRegistry,
    workspace_root: str,
    *,
    craft_artifacts: bool = False,
) -> None:
    """注册办公场景常用工具（Word/Excel/PPT/PDF + business）。"""
    from fnixagent.harness.paths import coerce_craft_artifact_path

    root = Path(workspace_root).resolve()

    def _resolve(path: str) -> str:
        raw = (path or "").strip()
        if craft_artifacts:
            # Prefer workspace-relative then coerce into artifacts.
            try:
                abs_candidate = Path(raw)
                if abs_candidate.is_absolute():
                    try:
                        raw = str(abs_candidate.resolve().relative_to(root)).replace("\\", "/")
                    except ValueError:
                        raw = abs_candidate.name
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
            raw = coerce_craft_artifact_path(raw or "output.bin")
        p = Path(raw)
        if not p.is_absolute():
            p = root / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    try:
        from fnixagent.business.word.editor import (
            TOOL_METADATA as WORD_META,
        )
        from fnixagent.business.word.editor import (
            create_docx,
            edit_docx,
            format_docx,
        )

        def _create_docx(args: dict) -> Any:
            # P1 统一: 同时接受 file_path 和 output_path
            out = _resolve(args.get("output_path") or args.get("file_path") or "output.docx")
            return create_docx(
                content=args.get("content", ""),
                title=args.get("title"),
                template=args.get("template"),
                output_path=out,
            )

        registry.register(WORD_META["create_docx"], _create_docx)

        # P1 修复: edit_docx/format_docx 也走 _resolve, 保证 Craft 模式路径一致性
        def _edit_docx(args: dict) -> Any:
            args = dict(args)
            if args.get("file_path"):
                args["file_path"] = _resolve(args["file_path"])
            return edit_docx(**args)

        def _format_docx(args: dict) -> Any:
            args = dict(args)
            if args.get("file_path"):
                args["file_path"] = _resolve(args["file_path"])
            return format_docx(**args)

        registry.register(WORD_META["edit_docx"], _edit_docx)
        registry.register(WORD_META["format_docx"], _format_docx)
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)

    try:
        # P0 修复: 删除 stub format_converter, 改用真实 ConverterExpert
        # 原 business/converter/format_converter.py 的 convert_docx_to_pdf 等全是 stub
        # (返回 {"success": true, "engine": "stub"} 但不写任何文件 — 严重失信)
        from fnixagent.office.converter import ConverterExpert

        converter = ConverterExpert()

        def convert_document(args: dict) -> dict:
            file_path = args.get("file_path") or ""
            target_format = (args.get("target_format") or "").lower().lstrip(".")
            output_path = args.get("output_path") or ""
            # 输出路径走 _resolve (Craft 模式落 .fnix/artifacts/)
            if output_path:
                output_path = _resolve(output_path)
            if not file_path or not target_format:
                return {"success": False, "error": "file_path 和 target_format 必填"}
            result = converter.convert(
                source_path=file_path,
                output_path=output_path,
                target_format=target_format,
            )
            return {
                "success": result.success,
                "file_path": result.output if result.success else None,
                "error": None if result.success else (result.error or "convert failed"),
            }

        registry.register(
            ToolMetadata(
                name="convert_document",
                description="文档格式转换 (docx/pdf/md/html/xlsx/csv/json 互转, 部分格式需 LibreOffice)",
                category="office",
                permission_level=ToolPermission.MIDDLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "源文件路径"},
                        "target_format": {
                            "type": "string",
                            "description": "目标格式: pdf/docx/md/html/xlsx/csv/json/txt",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径 (可选, 不填则同名换扩展名)",
                        },
                    },
                    "required": ["file_path", "target_format"],
                },
            ),
            convert_document,
        )
    except Exception as exc:
        logger.warning("office convert_document tool not registered: %s", exc)

    # P0 修复: 注册 read_pdf / read_xlsx / read_docx 工具
    # 原本只有 create_pdf/create_xlsx/create_docx, 无法读取已有文档 — "总结这份 PDF" 无法跑通
    try:
        from fnixagent.office.pdf import PDFExpert

        pdf = PDFExpert()

        def read_pdf(args: dict) -> dict:
            result = pdf.extract_text(
                path=args.get("file_path") or "",
                page_range=tuple(args["page_range"]) if args.get("page_range") else None,
            )
            if not result.success:
                return {"success": False, "error": result.error or "read_pdf failed"}
            output = result.output or {}
            full_text = output.get("full_text", "")
            # 截断防止超长文本塞爆 LLM 上下文 (保留前 8000 字符)
            if len(full_text) > 8000:
                full_text = (
                    full_text[:8000]
                    + f"\n\n... [已截断, 共 {len(output.get('full_text', ''))} 字符]"
                )
            return {
                "success": True,
                "page_count": len(output.get("pages", [])),
                "text": full_text,
            }

        registry.register(
            ToolMetadata(
                name="read_pdf",
                description="读取 PDF 文件并提取文本内容 (用于总结/分析已有 PDF)",
                category="office",
                permission_level=ToolPermission.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "PDF 文件路径"},
                        "page_range": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "页码范围 [start, end] (1-based, 可选)",
                        },
                    },
                    "required": ["file_path"],
                },
            ),
            read_pdf,
        )
    except Exception as exc:
        logger.warning("office read_pdf tool not registered: %s", exc)

    try:
        from fnixagent.office.excel import ExcelExpert

        excel_reader = ExcelExpert()

        def read_xlsx(args: dict) -> dict:
            result = excel_reader.read(
                path=args.get("file_path") or "",
                sheet_name=args.get("sheet_name"),
                max_rows=args.get("max_rows"),
                with_header=args.get("with_header", True),
            )
            if not result.success:
                return {"success": False, "error": result.error or "read_xlsx failed"}
            output = result.output or {}
            return {
                "success": True,
                "headers": output.get("headers", []),
                "rows": output.get("rows", []),
                "sheet_names": output.get("sheet_names", []),
            }

        registry.register(
            ToolMetadata(
                name="read_xlsx",
                description="读取 Excel 文件内容为二维表格 (用于分析已有 Excel/CSV 数据)",
                category="office",
                permission_level=ToolPermission.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": ".xlsx 文件路径"},
                        "sheet_name": {
                            "type": "string",
                            "description": "sheet 名 (可选, 默认第一个)",
                        },
                        "max_rows": {"type": "integer", "description": "最大返回行数 (可选)"},
                        "with_header": {
                            "type": "boolean",
                            "description": "首行是否为表头 (默认 true)",
                        },
                    },
                    "required": ["file_path"],
                },
            ),
            read_xlsx,
        )
    except Exception as exc:
        logger.warning("office read_xlsx tool not registered: %s", exc)

    try:
        from fnixagent.business.word.editor import read_docx as _read_docx_impl

        def read_docx(args: dict) -> dict:
            return _read_docx_impl(file_path=args.get("file_path") or "")

        registry.register(
            ToolMetadata(
                name="read_docx",
                description="读取 Word 文档文本内容 (用于总结/分析已有 docx)",
                category="office",
                permission_level=ToolPermission.LOW,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": ".docx 文件路径"},
                    },
                    "required": ["file_path"],
                },
            ),
            read_docx,
        )
    except Exception as exc:
        logger.warning("office read_docx tool not registered: %s", exc)

    try:
        from fnixagent.business.search import register_search_tools

        register_search_tools(registry)
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)

    try:
        from fnixagent.office.excel import ExcelExpert

        excel = ExcelExpert()

        def create_xlsx(args: dict) -> dict:
            # P1 统一: 同时接受 file_path 和 output_path (LLM 调用时命名不一致)
            out = _resolve(args.get("output_path") or args.get("file_path") or "output.xlsx")
            result = excel.create(
                output_path=out,
                sheet_name=args.get("sheet_name") or "Sheet1",
                data=args.get("data"),
                sheets=args.get("sheets"),
            )
            return {
                "success": result.success,
                "file_path": result.output if result.success else None,
                "error": None if result.success else (result.error or "create_xlsx failed"),
            }

        registry.register(
            ToolMetadata(
                name="create_xlsx",
                description="创建 Excel 工作簿(.xlsx)，可写入二维 data 或多 sheet",
                category="office",
                permission_level=ToolPermission.MIDDLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "输出路径 (与 output_path 等价)",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径 (与 file_path 等价)",
                        },
                        "sheet_name": {"type": "string"},
                        "data": {"type": "array"},
                        "sheets": {"type": "array"},
                    },
                },
            ),
            create_xlsx,
        )
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)

    try:
        from fnixagent.office.powerpoint import PPTExpert

        ppt = PPTExpert()

        def create_pptx(args: dict) -> dict:
            # P1 统一: 同时接受 file_path 和 output_path
            out = _resolve(args.get("output_path") or args.get("file_path") or "output.pptx")
            result = ppt.create(
                output_path=out,
                title=args.get("title") or "",
                subtitle=args.get("subtitle") or "",
                slides=args.get("slides"),
            )
            return {
                "success": result.success,
                "file_path": result.output if result.success else None,
                "error": None if result.success else (result.error or "create_pptx failed"),
            }

        registry.register(
            ToolMetadata(
                name="create_pptx",
                description="创建 PowerPoint 演示文稿(.pptx)",
                category="office",
                permission_level=ToolPermission.MIDDLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "输出路径 (与 output_path 等价)",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径 (与 file_path 等价)",
                        },
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "slides": {"type": "array"},
                    },
                },
            ),
            create_pptx,
        )
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)

    try:
        from fnixagent.office.pdf import PDFExpert

        pdf = PDFExpert()

        def create_pdf(args: dict) -> dict:
            # P1 统一: 同时接受 file_path 和 output_path
            out = _resolve(args.get("output_path") or args.get("file_path") or "output.pdf")
            result = pdf.create(
                output_path=out,
                text=args.get("text") or "",
                title=args.get("title") or "",
                author=args.get("author") or "",
                pages=args.get("pages"),
            )
            return {
                "success": result.success,
                "file_path": result.output if result.success else None,
                "error": None if result.success else (result.error or "create_pdf failed"),
            }

        registry.register(
            ToolMetadata(
                name="create_pdf",
                description="创建简单 PDF 文档",
                category="office",
                permission_level=ToolPermission.MIDDLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "输出路径 (与 output_path 等价)",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径 (与 file_path 等价)",
                        },
                        "text": {"type": "string"},
                        "title": {"type": "string"},
                        "author": {"type": "string"},
                        "pages": {"type": "array"},
                    },
                },
            ),
            create_pdf,
        )
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)

    # 图表生成（README 业务能力）
    try:
        from fnixagent.office.chart import ChartExpert

        chart = ChartExpert()

        def create_chart(args: dict) -> dict:
            # P1 统一: 同时接受 file_path 和 output_path
            out = _resolve(args.get("output_path") or args.get("file_path") or "chart.png")
            # P1 兼容: 支持 data 结构 或 x_labels+series 简写
            if args.get("data"):
                data = args["data"]
            elif args.get("x_labels") or args.get("series"):
                # 简写模式: x_labels + series → ChartExpert 的 data 格式
                categories = args.get("x_labels") or []
                series_data = args.get("series") or []
                series_dict = {}
                for s in series_data:
                    if isinstance(s, dict):
                        series_dict[s.get("name", "series")] = s.get("data", [])
                data = {"categories": categories, "series": series_dict}
            else:
                data = {"categories": ["A", "B"], "series": {"s1": [1, 2]}}
            result = chart.create_chart(
                chart_type=args.get("chart_type") or "bar",
                data=data,
                output_path=out,
                title=args.get("title") or "",
            )
            return {
                "success": result.success,
                "file_path": result.output if result.success else None,
                "error": None if result.success else (result.error or "create_chart failed"),
            }

        registry.register(
            ToolMetadata(
                name="create_chart",
                description="生成图表(柱/折线/饼/散点等)并保存为图片。支持两种数据格式: 1) data={categories,series} 2) x_labels+series=[{name,data}]",
                category="office",
                permission_level=ToolPermission.MIDDLE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "输出路径 (与 output_path 等价)",
                        },
                        "output_path": {
                            "type": "string",
                            "description": "输出路径 (与 file_path 等价)",
                        },
                        "chart_type": {
                            "type": "string",
                            "description": "bar/line/pie/scatter/area/radar/heatmap/histogram",
                        },
                        "data": {
                            "type": "object",
                            "description": "{categories:[...], series:{name:[values]}}",
                        },
                        "x_labels": {
                            "type": "array",
                            "description": "x 轴标签 (简写模式, 与 series 配合)",
                        },
                        "series": {
                            "type": "array",
                            "description": "[{name, data}] (简写模式, 与 x_labels 配合)",
                        },
                        "title": {"type": "string"},
                    },
                },
            ),
            create_chart,
        )
    except Exception as exc:
        logger.warning("office create_chart tool not registered: %s", exc)


def _build_router_fallback_llm_call(temperature: float, max_tokens: int):
    """构建基于全局调度器 LLMRouter 的 llm_call 回退。

    当请求级 LLM 未配置 (无 API Key) 时, 回退到调度器的 LLMRouter,
    使 MockLLMProvider 等已注册 provider 仍可工作。

    Returns:
        async llm_call(messages, tools=None) 或 None (调度器/路由器不可用时)。
    """
    try:
        from fnixagent.services import get_scheduler

        _sched = get_scheduler()
        if _sched is None:
            return None
        _router = getattr(_sched._ctx, "llm_router", None)
        if _router is None:
            return None
    except Exception:
        return None

    from fnixagent.core.llm.base import LLMRequest
    from fnixagent.core.types import Message, MessageRole

    async def _llm_call(messages, tools=None):
        msg_objects = [
            Message(
                role=MessageRole(m.get("role", "user")),
                content=str(m.get("content", "")),
                name=m.get("name"),
            )
            for m in messages
        ]
        request = LLMRequest(
            model="",
            messages=msg_objects,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools or [],
        )
        # LLMRouter.chat 是同步方法 (内部可能用 httpx 同步客户端), offload 避免阻塞 event loop
        response = await asyncio.to_thread(_router.chat, request)
        result: dict[str, Any] = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": response.content,
                        "reasoning_content": getattr(response, "reasoning_content", "") or "",
                    }
                }
            ],
            "usage": {
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "cached_tokens": getattr(response.usage, "cached_tokens", 0) or 0,
            },
        }
        if response.tool_calls:
            import json as _json

            normalized_calls = []
            for i, tc in enumerate(response.tool_calls):
                args = tc.get("arguments", {})
                if not isinstance(args, str):
                    args = _json.dumps(args or {}, ensure_ascii=False)
                normalized_calls.append(
                    {
                        "id": tc.get("id", f"call_{i}"),
                        "type": "function",
                        "function": {"name": tc.get("name", ""), "arguments": args},
                    }
                )
            result["choices"][0]["message"]["tool_calls"] = normalized_calls
        return result

    return _llm_call


def build_work_agent_loop(
    workspace_root: str | None = None,
    llm: dict | None = None,
    max_steps: int = 30,
    graph_components: Any = None,
    user_input: str = "",
    prompt_extra: str = "",
    work_mode: str = "craft",
    max_reflect_rounds: int = 2,
) -> AgenticLoop | None:
    """构建 Work 模式 AgenticLoop；接入 KTG/STP（有 GraphComponents 时）。

    Args:
        max_reflect_rounds: Spec 7+ DAAO 真路由决策传入的 VMAO 反思轮数上限
            (HERA 高命中率 → 减少; HERA 低命中率+高难度 → 增加)
    """
    try:
        root = workspace_root or os.getenv("FNIXAGENT_WORKSPACE") or os.getcwd()
        mode = normalize_work_mode(work_mode)
        craft_artifacts = mode == "craft"
        registry = ToolRegistry()
        register_workspace_tools(registry, root, craft_artifacts=craft_artifacts)
        register_office_work_tools(registry, root, craft_artifacts=craft_artifacts)
        # 内置浏览器（Playwright 截图流）：未安装 playwright 时内部静默跳过
        try:
            from fnixagent.core.tools.browser import register_browser_tools

            register_browser_tools(registry)
        except Exception as exc:
            logger.warning("browser tools register skipped: %s", exc)
        # 桌面驱动（cua-driver）：未安装时内部静默跳过
        try:
            from fnixagent.core.tools.desktop import register_desktop_tools

            register_desktop_tools(registry)
        except Exception as exc:
            logger.warning("desktop tools register skipped: %s", exc)
        # MCP：空 mcp.json 或连接失败时跳过，不阻断 Work（必须可观测）
        try:
            from fnixagent.harness.config import attach_mcp_tools_to_registry

            attach_mcp_tools_to_registry(registry)
        except Exception as exc:
            logger.warning("MCP tools attach skipped: %s", exc)

        ktg_paths: list = []
        concept_ids: list[str] = []
        tool_executor: Any = registry
        system_prompt = WORK_SYSTEM_PROMPT

        if graph_components is not None:
            # 合并图上已注册工具（避免丢 STP 绑定的 business 工具）
            try:
                for name, tool in list(graph_components.tool_registry._tools.items()):
                    if name not in registry._tools:
                        registry.register(tool.metadata, tool.func)
            except Exception as exc:
                logger.warning("KTG/STP tool merge skipped: %s", exc)

            try:
                ktg_paths = graph_components.search_engine.search(user_input or "办公任务")
                for p in ktg_paths:
                    for n in getattr(p, "nodes", []) or []:
                        if isinstance(n, str):
                            if n.startswith("L2:"):
                                concept_ids.append(n)
                        else:
                            nid = getattr(n, "node_id", None)
                            if nid and str(nid).startswith("L2:"):
                                concept_ids.append(str(nid))
            except Exception as exc:
                logger.warning("KTG search skipped: %s", exc)
                ktg_paths = []

            best_path = ktg_paths[0] if ktg_paths else None
            tool_executor = _StpAwareRegistry(
                registry,
                scheduler=getattr(graph_components, "scheduler", None),
                feedback=getattr(graph_components, "feedback_handler", None),
                path=best_path,
            )
            system_prompt = WORK_SYSTEM_PROMPT + _format_ktg_context(ktg_paths)

        # Ask/Plan：移除写盘工具（对齐工程实践 权限边界）
        if mode in ("ask", "plan"):
            strip_mutating_tools(registry)

        code_craft = mode == "craft" and looks_like_code_craft_task(user_input)
        if code_craft:
            for name in list(getattr(registry, "_tools", {}) or {}):
                if name not in _CRAFT_CODE_TOOL_ALLOW:
                    try:
                        registry.unregister(name)
                    except Exception:
                        _logger.debug('Unhandled exception', exc_info=True)

        if prompt_extra:
            system_prompt = system_prompt + prompt_extra

        adapter = adapter_from_llm_override(llm)
        temperature = 0.7
        if llm and llm.get("temperature") is not None:
            try:
                temperature = float(llm["temperature"])
            except (TypeError, ValueError):
                pass
        # Website/source dumps need headroom for multi-file tool arguments.
        max_tokens = 16384 if code_craft else 4096

        if adapter.is_configured:

            async def llm_call(messages, tools=None):
                return await adapter.chat(
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            async def llm_stream_call(messages, tools=None, on_chunk=None):
                # 真·token 级流式：正文逐 chunk 上屏，工具调用从流尾解析，
                # 返回结构与 llm_call 完全一致（Trae/Cursor 同架构）。
                return await adapter.chat_stream(
                    messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    on_chunk=on_chunk,
                )
        else:
            # 未配置请求级 LLM 时, 回退到全局调度器的 LLMRouter (含 MockLLMProvider)。
            # 这样在无 API Key 的离线/测试环境下, 仍能用 MockLLM 完成完整流程验证。
            _router_llm_call = _build_router_fallback_llm_call(temperature, max_tokens)
            if _router_llm_call is not None:
                llm_call = _router_llm_call
            else:
                # P1: 调度器也无可用 LLM 时抛明确异常, 让 AgenticLoop 走 error 分支告知用户
                _not_configured_msg = (
                    "[LLM 未配置] 请在 Desktop 设置中填写 API Key, "
                    "或在服务端 .env 设置 OPENAI_API_KEY / GLM_API_KEY / QWEN_API_KEY / DEEPSEEK_API_KEY"
                )

                async def llm_call(messages, tools=None):
                    raise RuntimeError(_not_configured_msg)

        _llm_stream = llm_stream_call if adapter.is_configured else None

        # 子代理: 派生隔离子循环执行探索性子任务(只读工具集), 保护主上下文预算
        try:
            from fnixagent.core.agent.subagent import register_subagent_tool

            register_subagent_tool(
                registry,
                root,
                make_llm=lambda: (
                    llm_call,
                    llm_stream_call if adapter.is_configured else None,
                ),
            )
        except Exception as exc:
            logger.warning("subagent tool register skipped: %s", exc)

        # AgentTeams: 多角色并行协作(fan_out/任务清单/信箱), 仅主循环可调度
        try:
            from fnixagent.core.teams.runner import register_team_tools

            register_team_tools(
                registry,
                root,
                make_llm=lambda: (
                    llm_call,
                    llm_stream_call if adapter.is_configured else None,
                ),
            )
        except Exception as exc:
            logger.warning("team tools register skipped: %s", exc)

        loop = AgenticLoop(
            llm_call=llm_call,
            llm_stream_call=_llm_stream,
            tool_executor=tool_executor,
            workspace_root=root,
            max_steps=max_steps,
            enable_evolution=graph_components is not None,
            evolution_interval=1,  # Work 每次任务后都走 MFP 钩子
            system_prompt=system_prompt,
            force_tool_delivery=code_craft,
            max_reflect_rounds=max_reflect_rounds,
        )
        # 挂上 GraphComponents，供 MFP 钩子使用
        loop._graph_components = graph_components
        loop._ktg_concept_path = concept_ids
        loop._work_user_input = user_input
        return loop
    except Exception:
        return None


__all__ = [
    "WORK_SYSTEM_PROMPT",
    "adapter_from_llm_override",
    "build_work_agent_loop",
    "format_ask_prompt",
    "format_code_task_prompt",
    "format_plan_prompt",
    "looks_like_code_craft_task",
    "normalize_work_mode",
    "register_office_work_tools",
    "run_mfp_after_task",
    "strip_mutating_tools",
    "wrap_code_user_input",
]
