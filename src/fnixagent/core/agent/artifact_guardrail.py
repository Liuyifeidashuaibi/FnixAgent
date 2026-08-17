"""Artifact Guardrail — 借鉴 OpenAI Agents SDK guardrail + Reflexion Actor-Evaluator.

设计目的: 解决 "LLM 工具调用成功但产物不合规" 的盲点
  - craft 模式未落盘 → 强制重跑
  - .py 文件 AST 语法错误 → Reflexion 修复循环
  - .html 文件结构不完整 → Reflexion 修复循环
  - HTML 任务未分离 CSS/JS → 提示重写

借鉴:
  - OpenAI Agents SDK guardrail: 输入/输出 guardrail 强制校验
  - noahshinn/reflexion: Actor + Evaluator + Self-Reflection 修复循环
  - LangGraph: 状态机式修复流程 (validate → repair → re-validate)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """单个产物的校验结果."""

    path: str
    ok: bool
    issues: list[str] = field(default_factory=list)
    severity: str = "info"  # info | warning | error


@dataclass
class GuardrailReport:
    """一次 craft 任务的完整 guardrail 报告."""

    passed: bool
    missing_artifacts: list[str] = field(default_factory=list)
    validation_results: list[ValidationResult] = field(default_factory=list)
    repair_attempts: int = 0
    final_artifacts: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""

    @property
    def all_issues(self) -> list[str]:
        out = list(self.missing_artifacts)
        for v in self.validation_results:
            out.extend(v.issues)
        return out


def validate_python_file(path: Path) -> ValidationResult:
    """Python 文件 AST 语法校验."""
    if not path.is_file():
        return ValidationResult(path=str(path), ok=False, issues=["文件不存在"], severity="error")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return ValidationResult(
            path=str(path), ok=False, issues=[f"读取失败: {e}"], severity="error"
        )

    try:
        ast.parse(content)
    except SyntaxError as e:
        return ValidationResult(
            path=str(path),
            ok=False,
            issues=[f"Python 语法错误 (line {e.lineno}): {e.msg}"],
            severity="error",
        )

    issues: list[str] = []
    # 检查是否定义了至少一个函数/类
    try:
        tree = ast.parse(content)
        has_def = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            for node in ast.walk(tree)
        )
        if not has_def:
            issues.append("未定义任何函数或类")
    except Exception:
        pass

    return ValidationResult(
        path=str(path),
        ok=len(issues) == 0,
        issues=issues,
        severity="warning" if issues else "info",
    )


def validate_html_file(path: Path, *, require_separate_css_js: bool = False) -> ValidationResult:
    """HTML 文件结构校验."""
    if not path.is_file():
        return ValidationResult(path=str(path), ok=False, issues=["文件不存在"], severity="error")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return ValidationResult(
            path=str(path), ok=False, issues=[f"读取失败: {e}"], severity="error"
        )

    issues: list[str] = []
    lowered = content.lower()

    # 基本结构检查
    has_doctype = "<!doctype html" in lowered
    has_html_tag = "<html" in lowered
    has_body = "<body" in lowered

    if not has_doctype and not has_html_tag:
        issues.append("缺少 <!DOCTYPE html> 或 <html> 标签")
    if not has_body and "<body" not in lowered:
        issues.append("缺少 <body> 标签")

    # 如果要求分离 CSS/JS, 检查是否内嵌过多
    if require_separate_css_js:
        # 内嵌 <style> 块超过 200 字符 → 建议分离
        style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", content, re.DOTALL | re.IGNORECASE)
        if style_blocks:
            total_css = sum(len(b) for b in style_blocks)
            if total_css > 200:
                issues.append(f"内嵌 CSS {total_css} 字符, 建议分离为 .css 文件")
        # 内嵌 <script> 块超过 200 字符 → 建议分离
        script_blocks = re.findall(
            r"<script[^>]*>(.*?)</script>", content, re.DOTALL | re.IGNORECASE
        )
        if script_blocks:
            total_js = sum(len(b) for b in script_blocks)
            if total_js > 200:
                issues.append(f"内嵌 JS {total_js} 字符, 建议分离为 .js 文件")

    return ValidationResult(
        path=str(path),
        ok=len(issues) == 0,
        issues=issues,
        severity="warning" if issues else "info",
    )


def validate_markdown_file(
    path: Path,
    *,
    min_length: int = 0,
    expect_mermaid: bool = False,
    expect_table: bool = False,
    expect_code: bool = False,
) -> ValidationResult:
    """Markdown 文件内容校验."""
    if not path.is_file():
        return ValidationResult(path=str(path), ok=False, issues=["文件不存在"], severity="error")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return ValidationResult(
            path=str(path), ok=False, issues=[f"读取失败: {e}"], severity="error"
        )

    issues: list[str] = []
    if min_length > 0 and len(content) < min_length:
        issues.append(f"内容过短: {len(content)} < {min_length}")
    if expect_mermaid and "```mermaid" not in content:
        issues.append("缺少 Mermaid 代码块")
    if expect_table and ("|" not in content or "---" not in content):
        issues.append("缺少 Markdown 表格")
    if expect_code and "```" not in content:
        issues.append("缺少代码块")

    return ValidationResult(
        path=str(path),
        ok=len(issues) == 0,
        issues=issues,
        severity="warning" if issues else "info",
    )


def validate_artifact(
    path: str, workspace: str, *, workspace_kind: str = "general"
) -> ValidationResult:
    """根据扩展名自动选择校验器."""
    full_path = Path(workspace) / path
    if not full_path.is_file():
        full_path = Path(workspace) / ".fnix" / "artifacts" / path
    if not full_path.is_file():
        # 尝试直接路径
        full_path = Path(path)

    ext = Path(path).suffix.lower()
    require_separate = workspace_kind == "code" and ext == ".html"

    if ext == ".py":
        return validate_python_file(full_path)
    elif ext in (".html", ".htm"):
        return validate_html_file(full_path, require_separate_css_js=require_separate)
    elif ext == ".md":
        return validate_markdown_file(full_path)
    elif ext in (".css", ".js", ".json", ".csv", ".txt"):
        if not full_path.is_file():
            return ValidationResult(path=path, ok=False, issues=["文件不存在"], severity="error")
        return ValidationResult(path=path, ok=True)
    else:
        return ValidationResult(path=path, ok=True)


def enforce_craft_deliverables(
    *,
    exec_mode: str,
    workspace_kind: str,
    artifacts: list[dict[str, str]],
    tool_calls: list[dict[str, Any]],
    workspace: str,
) -> GuardrailReport:
    """OpenAI Agents SDK 风格 output guardrail: craft 模式必须有合规产物.

    返回:
      passed=True: 至少有一个合规产物
      passed=False: 无产物 或 产物校验失败 (需要 Reflexion 修复)
    """
    report = GuardrailReport(passed=True)

    # ask/plan 模式不强制产物
    if exec_mode != "craft":
        report.summary = f"{exec_mode} 模式, 不强制产物"
        return report

    wrote_code = any(str(t.get("name") or "") in ("write_file", "edit_file") for t in tool_calls)

    # craft 模式但无产物
    if not artifacts:
        if workspace_kind == "code":
            report.passed = False
            report.missing_artifacts.append("craft 编码任务未调用 write_file 落盘")
        elif workspace_kind in ("document", "research"):
            report.passed = False
            report.missing_artifacts.append(f"craft {workspace_kind} 任务未落盘 Markdown/文档")
        else:
            # general 模式宽松一些: 有工具调用即算
            if not wrote_code:
                report.passed = False
                report.missing_artifacts.append("craft 任务未调用任何写盘工具")
        report.summary = "; ".join(report.missing_artifacts) or "通过"
        return report

    # 有产物, 校验每个产物
    for art in artifacts:
        path = str(art.get("path") or "")
        if not path:
            continue
        v = validate_artifact(path, workspace, workspace_kind=workspace_kind)
        report.validation_results.append(v)
        if not v.ok and v.severity == "error":
            report.passed = False

    # code 类任务: 检查是否有 HTML + CSS + JS 三件套 (如果是建站任务)
    if workspace_kind == "code":
        paths_lower = [str(a.get("path") or "").lower() for a in artifacts]
        has_html = any(p.endswith(".html") or p.endswith(".htm") for p in paths_lower)
        if has_html:
            has_css = any(p.endswith(".css") for p in paths_lower)
            has_js = any(p.endswith(".js") for p in paths_lower)
            # 只对显式要求多文件的提示 (不强制, 因为单 HTML 也可用)
            if not has_css and not has_js:
                # 检查 HTML 内是否内嵌了 CSS/JS, 如果是单 HTML 应用且内嵌合理, 不算失败
                for art in artifacts:
                    p = str(art.get("path") or "")
                    if p.lower().endswith((".html", ".htm")):
                        full = Path(workspace) / p
                        if not full.is_file():
                            full = Path(workspace) / ".fnix" / "artifacts" / p
                        if full.is_file():
                            content = full.read_text(encoding="utf-8", errors="ignore")
                            # 内嵌超过 500 字符的 CSS/JS 才提示分离
                            style_blocks = re.findall(
                                r"<style[^>]*>(.*?)</style>", content, re.DOTALL | re.IGNORECASE
                            )
                            script_blocks = re.findall(
                                r"<script[^>]*>(.*?)</script>", content, re.DOTALL | re.IGNORECASE
                            )
                            total_inline = sum(len(b) for b in style_blocks + script_blocks)
                            if total_inline > 500:
                                report.validation_results.append(
                                    ValidationResult(
                                        path=p,
                                        ok=True,  # 不算失败, 只是 warning
                                        issues=[
                                            f"内嵌 CSS+JS {total_inline} 字符, 建议分离为 .css/.js 文件以提升可维护性"
                                        ],
                                        severity="warning",
                                    )
                                )

    errs = [v for v in report.validation_results if not v.ok and v.severity == "error"]
    if errs:
        report.passed = False
        report.summary = f"{len(errs)} 个产物有 error 级问题"
    else:
        warnings = [v for v in report.validation_results if v.issues and v.severity == "warning"]
        if warnings:
            report.summary = f"通过 (含 {len(warnings)} 个 warning)"
        else:
            report.summary = "通过"

    return report


def build_reflexion_repair_prompt(
    *,
    user_input: str,
    workspace_kind: str,
    report: GuardrailReport,
    artifacts: list[dict[str, str]],
) -> str:
    """构造 Reflexion 风格的修复提示.

    借鉴 noahshinn/reflexion: Actor 失败 → Evaluator 反馈 → Actor 看到反馈重试.
    把 guardrail 检测到的所有问题作为"反思反馈"传给 LLM, 让它修复.
    """
    issues_text = "\n".join(f"- {issue}" for issue in report.all_issues[:10])

    if workspace_kind == "code":
        artifact_hint = (
            "请重新调用 write_file 落盘完整产物. "
            "如果是建站任务, 必须分离为 index.html + style.css + script.js 三文件. "
            "如果是单 HTML 应用 (如 Todo), 可以单文件但 CSS/JS 内嵌合理."
        )
    elif workspace_kind in ("document", "research"):
        artifact_hint = "请重新调用 write_file 落盘完整 Markdown 文档到 .fnix/artifacts/ 下."
    else:
        artifact_hint = "请重新调用 write_file 落盘产物到 .fnix/artifacts/ 下."

    return (
        f"【Reflexion 修复 · 第 2 次尝试】\n"
        f"原任务: {user_input[:300]}\n\n"
        f"上一次尝试的产物有以下问题:\n{issues_text}\n\n"
        f"{artifact_hint}\n"
        f"禁止只回复文字说明, 必须调用 write_file 工具写入完整产物.\n"
        f"如果上一次产物路径不对, 这次必须用正确路径: .fnix/artifacts/<项目名>/<文件名>"
    )


def should_route_short_explanation_to_ask(
    *,
    user_input: str,
    work_mode: str,
) -> bool:
    """DAAO 短任务路由: 短输入 + 解释类 → 应该用 ask 而非 craft.

    解决测试中发现的问题: B1/C2/E3 等短任务被 LLM 直接文字回答, 未触发 write_file.
    如果用户用 craft 模式但输入是解释类, 应该提示用户切到 ask, 或者 DAAO 自动降级.
    """
    text = (user_input or "").strip()
    if len(text) > 80:
        return False
    if work_mode == "ask":
        return False  # 已经是 ask
    explain_hints = (
        "解释",
        "是什么",
        "什么是",
        "介绍",
        "含义",
        "区别",
        "为什么",
        "如何理解",
        "原理",
        "说说",
        "谈谈",
        "简述",
        "概述",
    )
    return any(h in text for h in explain_hints)


# ============================================================================
# H1 史诗级优化: Input/Tool Guardrail 三层架构
# 借鉴 OpenAI Agents SDK v0.18 的 input_guardrail + tool_input_guardrail
# 设计文档: https://openai.github.io/openai-agents-python/guardrails/
#
# 三层 guardrail:
#   1. Input Guardrail  — 用户输入阶段: 检测提示注入 / API Key 泄露 / 越权
#   2. Tool Guardrail   — 工具执行前: 检测路径穿越 / 趯界 / 内容泄露
#   3. Output Guardrail — 产物校验 (已实现的 enforce_craft_deliverables)
#
# 短路机制 (借鉴 SDK 的 tripwire_triggered):
#   guardrail 触发 → 抛出 TripwireTriggered 异常 → Runner 立即终止
#   而不是返回 passed=False 让后续步骤继续跑
# ============================================================================


@dataclass
class GuardrailFunctionOutput:
    """Guardrail 函数输出 (借鉴 OpenAI Agents SDK GuardrailFunctionOutput).

    tripwire_triggered=True 时, Runner 应立即终止当前流程.
    """

    tripwire_triggered: bool = False
    output_info: Any = None
    reject_reason: str = ""

    @property
    def allow(self) -> bool:
        """是否允许继续 (与 tripwire_triggered 相反)."""
        return not self.tripwire_triggered

    def reject(self, reason: str) -> GuardrailFunctionOutput:
        """标记为拒绝."""
        self.tripwire_triggered = True
        self.reject_reason = reason
        return self


class InputGuardrailTripwireTriggered(Exception):
    """Input guardrail 触发短路 (借鉴 OpenAI Agents SDK InputGuardrailTripwireTriggered)."""

    def __init__(self, guardrail_name: str, output: GuardrailFunctionOutput):
        self.guardrail_name = guardrail_name
        self.output = output
        super().__init__(f"Input guardrail '{guardrail_name}' triggered: {output.reject_reason}")


class ToolGuardrailTripwireTriggered(Exception):
    """Tool guardrail 触发短路 (借鉴 OpenAI Agents SDK ToolGuardrailTripwireTriggered)."""

    def __init__(self, guardrail_name: str, output: GuardrailFunctionOutput):
        self.guardrail_name = guardrail_name
        self.output = output
        super().__init__(f"Tool guardrail '{guardrail_name}' triggered: {output.reject_reason}")


class OutputGuardrailTripwireTriggered(Exception):
    """Output guardrail 触发短路."""

    def __init__(self, guardrail_name: str, output: GuardrailFunctionOutput):
        self.guardrail_name = guardrail_name
        self.output = output
        super().__init__(f"Output guardrail '{guardrail_name}' triggered: {output.reject_reason}")


# ── 内置 Input Guardrails ────────────────────────────────────────────────

# 提示注入模式 (参考 OWASP LLM Top 10 LLM01)
_PROMPT_INJECTION_PATTERNS = [
    (r"ignore\s+(previous|all|above|prior)\s+instructions?", "忽略前述指令"),
    (r"disregard\s+(previous|all|above|prior)", "无视前述指令"),
    (r"forget\s+(everything|all|previous|prior)", "遗忘前述上下文"),
    (
        r"you\s+are\s+(now|actually|really)\s+(a|an)?\s*(developer|admin|root|system)",
        "角色劫持为特权身份",
    ),
    (r"system\s*[:：]\s*", "伪造 system 消息"),
    (r"<\|im_start\|>\s*system", "伪造 ChatML system 标记"),
    (r"new\s+instructions?\s*[:：]", "伪造新指令覆盖"),
    (r"jailbreak", "显式越狱关键词"),
    (r"DAN\s*mode", "DAN 越狱模式"),
]

# API Key / Token 模式 (参考 truffleHog + gitleaks)
_SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{40,}", "OpenAI API Key"),
    (r"sk-ant-[a-zA-Z0-9\-_]{40,}", "Anthropic API Key"),
    (r"GLM-[a-zA-Z0-9]{32,}", "GLM API Key"),
    (r"dashscope-sk-[a-zA-Z0-9]{32,}", "DashScope API Key"),
    (r"xai-[a-zA-Z0-9]{40,}", "xAI API Key"),
    (r"gh[pousr]_[A-Za-z0-9]{36}", "GitHub Token"),
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key ID"),
    (r"AIza[A-Za-z0-9_\-]{35}", "Google API Key"),
    (r"sk-or-v1-[a-zA-Z0-9]{40,}", "OpenRouter API Key"),
]


def block_prompt_injection(text: str) -> GuardrailFunctionOutput:
    """Input Guardrail: 检测提示注入攻击.

    借鉴 OpenAI Agents SDK 示例 block_secrets + OWASP LLM01.
    """
    if not text:
        return GuardrailFunctionOutput(output_info="空输入")
    for pat, desc in _PROMPT_INJECTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return GuardrailFunctionOutput(
                tripwire_triggered=True,
                reject_reason=f"提示注入检测: {desc} (匹配 /{pat}/)",
                output_info={"pattern": pat, "desc": desc},
            )
    return GuardrailFunctionOutput(output_info="通过")


def block_secrets_in_input(text: str) -> GuardrailFunctionOutput:
    """Input Guardrail: 检测用户输入中的 API Key 泄露.

    用户不应该在 prompt 里贴 API Key, 这是安全隐患.
    """
    if not text:
        return GuardrailFunctionOutput(output_info="空输入")
    for pat, name in _SECRET_PATTERNS:
        m = re.search(pat, text)
        if m:
            # 脱敏: 只显示前 8 + 后 4 字符
            matched = m.group(0)
            masked = matched[:8] + "..." + matched[-4:] if len(matched) > 12 else "***"
            return GuardrailFunctionOutput(
                tripwire_triggered=True,
                reject_reason=f"输入中检测到 {name}: {masked}",
                output_info={"pattern": pat, "name": name},
            )
    return GuardrailFunctionOutput(output_info="通过")


def block_oversized_input(text: str, *, max_chars: int = 32000) -> GuardrailFunctionOutput:
    """Input Guardrail: 检测过长输入 (防止 token 耗尽攻击).

    32K 字符约等于 8K tokens, 足够大多数办公场景.
    """
    if len(text) > max_chars:
        return GuardrailFunctionOutput(
            tripwire_triggered=True,
            reject_reason=f"输入过长: {len(text)} > {max_chars} 字符",
            output_info={"length": len(text), "max": max_chars},
        )
    return GuardrailFunctionOutput(output_info=f"长度 {len(text)}")


# ── 内置 Tool Guardrails ─────────────────────────────────────────────────


def block_path_traversal(
    tool_name: str, args: dict[str, Any], workspace: str
) -> GuardrailFunctionOutput:
    """Tool Guardrail: 检测 write_file/edit_file 路径穿越.

    防止 LLM 生成 ../../../etc/passwd 这种路径逃逸 workspace.
    """
    if tool_name not in ("write_file", "edit_file", "create_file", "patch_file"):
        return GuardrailFunctionOutput(output_info="非写盘工具, 跳过")

    path = str(
        args.get("path")
        or args.get("file_path")
        or args.get("rel_path")
        or args.get("filename")
        or ""
    )
    if not path:
        return GuardrailFunctionOutput(output_info="无路径参数")

    # 1. 检测 ../ 穿越
    parts = re.split(r"[\\/]", path)
    if ".." in parts:
        return GuardrailFunctionOutput(
            tripwire_triggered=True,
            reject_reason=f"路径穿越检测: {path} 包含 '..'",
            output_info={"path": path, "violation": "traversal"},
        )

    # 2. 检测绝对路径越界 (Windows 盘符 / Unix 根路径)
    is_absolute = path.startswith("/") or bool(re.match(r"^[A-Za-z]:[\\/]", path))
    if is_absolute:
        try:
            ws_abs = Path(workspace).resolve()
            p_abs = Path(path).resolve()
            # 必须在 workspace 内 (或 .fnix/artifacts 内)
            ws_str = str(ws_abs)
            p_str = str(p_abs)
            if not (p_str == ws_str or p_str.startswith(ws_str + os.sep)):
                return GuardrailFunctionOutput(
                    tripwire_triggered=True,
                    reject_reason=f"路径越界: {path} 不在 workspace {workspace} 内",
                    output_info={"path": path, "violation": "escape", "workspace": workspace},
                )
        except Exception as e:
            # resolve 失败, 保守拒绝
            return GuardrailFunctionOutput(
                tripwire_triggered=True,
                reject_reason=f"路径解析失败: {e}",
                output_info={"path": path, "violation": "resolve_error"},
            )

    # 3. 检测 Windows 保留设备名 (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    base = Path(path).name.upper().split(".")[0]
    reserved = (
        {"CON", "PRN", "AUX", "NUL"}
        | {f"COM{i}" for i in range(1, 10)}
        | {f"LPT{i}" for i in range(1, 10)}
    )
    if base in reserved:
        return GuardrailFunctionOutput(
            tripwire_triggered=True,
            reject_reason=f"Windows 保留设备名: {base}",
            output_info={"path": path, "violation": "reserved"},
        )

    return GuardrailFunctionOutput(output_info=f"通过: {path}")


def block_secrets_in_content(tool_name: str, args: dict[str, Any]) -> GuardrailFunctionOutput:
    """Tool Guardrail: 检测 write_file 内容中的 API Key 泄露.

    防止 LLM 把 .env 里的 API Key 写到产物文件 (如 README).
    """
    if tool_name not in ("write_file", "edit_file", "create_file"):
        return GuardrailFunctionOutput(output_info="非写盘工具, 跳过")

    content = str(args.get("content") or args.get("new_string") or args.get("text") or "")
    if not content:
        return GuardrailFunctionOutput(output_info="无内容")

    for pat, name in _SECRET_PATTERNS:
        m = re.search(pat, content)
        if m:
            matched = m.group(0)
            masked = matched[:8] + "..." + matched[-4:] if len(matched) > 12 else "***"
            return GuardrailFunctionOutput(
                tripwire_triggered=True,
                reject_reason=f"产物内容检测到 {name}: {masked}",
                output_info={"pattern": pat, "name": name},
            )
    return GuardrailFunctionOutput(output_info="通过")


def block_destructive_operations(
    tool_name: str, args: dict[str, Any], workspace: str
) -> GuardrailFunctionOutput:
    """Tool Guardrail: 检测破坏性操作 (rm -rf, format, del /f 等).

    防止 LLM 在 shell 命令中执行破坏性操作.
    """
    if tool_name not in ("shell", "bash", "exec", "run_command", "execute"):
        return GuardrailFunctionOutput(output_info="非 shell 工具, 跳过")

    cmd = str(args.get("command") or args.get("cmd") or "")
    if not cmd:
        return GuardrailFunctionOutput(output_info="无命令")

    destructive_patterns = [
        (r"\brm\s+-rf?\s+/", "rm -rf /"),
        (r"\brm\s+-rf?\s+\*", "rm -rf *"),
        (r"\bformat\s+[A-Z]:", "format 盘符"),
        (r"\bdel\s+/[fsq]\s+[A-Z]:\\", "Windows del 强制删除"),
        (r"\bmkfs\.", "mkfs 格式化"),
        (r"\bdd\s+if=.*of=/dev/", "dd 写设备"),
        (r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:", "fork bomb"),
        (r"\bshutdown\b", "shutdown 关机"),
        (r"\btaskkill\s+/[fF]", "taskkill 强杀"),
    ]
    for pat, desc in destructive_patterns:
        if re.search(pat, cmd, re.IGNORECASE):
            return GuardrailFunctionOutput(
                tripwire_triggered=True,
                reject_reason=f"破坏性命令检测: {desc}",
                output_info={"pattern": pat, "cmd": cmd[:100]},
            )
    return GuardrailFunctionOutput(output_info="通过")


# ── 高层 API: 批量运行 guardrails ────────────────────────────────────────


def run_input_guardrails(text: str) -> tuple[bool, list[str]]:
    """运行所有 input guardrails.

    Returns:
        (passed, reasons): passed=True 表示全部通过, reasons 是失败原因列表
    """
    reasons: list[str] = []
    for name, fn in [
        ("block_prompt_injection", lambda: block_prompt_injection(text)),
        ("block_secrets_in_input", lambda: block_secrets_in_input(text)),
        ("block_oversized_input", lambda: block_oversized_input(text)),
    ]:
        try:
            out = fn()
            if out.tripwire_triggered:
                reasons.append(f"[{name}] {out.reject_reason}")
        except Exception as e:
            # guardrail 自身异常不阻断, 但记录
            reasons.append(f"[{name}] guardrail 异常: {e}")
    return (len(reasons) == 0, reasons)


def run_tool_guardrails(
    tool_name: str, args: dict[str, Any], workspace: str
) -> tuple[bool, list[str]]:
    """运行所有 tool guardrails (在工具执行前调用).

    Returns:
        (passed, reasons): passed=True 表示允许执行, reasons 是拒绝原因列表
    """
    reasons: list[str] = []
    for name, fn in [
        ("block_path_traversal", lambda: block_path_traversal(tool_name, args, workspace)),
        ("block_secrets_in_content", lambda: block_secrets_in_content(tool_name, args)),
        (
            "block_destructive_operations",
            lambda: block_destructive_operations(tool_name, args, workspace),
        ),
    ]:
        try:
            out = fn()
            if out.tripwire_triggered:
                reasons.append(f"[{name}] {out.reject_reason}")
        except Exception as e:
            reasons.append(f"[{name}] guardrail 异常: {e}")
    return (len(reasons) == 0, reasons)


def check_tool_call_safety(tool_name: str, args: dict[str, Any], workspace: str) -> GuardrailReport:
    """工具调用安全检查 (返回完整 GuardrailReport 供前端展示).

    这是 Tool Guardrail 的高级 API, 返回 GuardrailReport 而不是 tuple,
    方便接入 work_pipeline 的事件流.
    """
    report = GuardrailReport(passed=True)
    passed, reasons = run_tool_guardrails(tool_name, args, workspace)
    if not passed:
        report.passed = False
        report.missing_artifacts.append(f"工具 {tool_name} 被安全策略拒绝")
        report.validation_results.append(
            ValidationResult(
                path=str(args.get("path") or args.get("file_path") or ""),
                ok=False,
                issues=reasons,
                severity="error",
            )
        )
        report.summary = f"工具调用被拒绝: {len(reasons)} 个安全问题"
    else:
        report.summary = "工具调用安全检查通过"
    return report
