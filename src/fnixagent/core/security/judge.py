"""
LLM 裁判注入检测器 (LLM Judge) - P1 安全模块。

与 injection.py 互补:
  - injection.py  检测**输入侧**的 Prompt 注入(用户 → LLM)
  - judge.py      审查**输出侧**的 LLM 生成内容(LLM → 工具/用户)

职责:
  1. 二次审查 LLM 输出文本,检测 prompt injection 残留模式
     (ignore previous / system: / <new_instructions> / forget previous 等)
  2. 检测工具调用参数异常(LLM 试图调用未授权工具 / 参数越界)
  3. 检测数据外泄企图(LLM 试图把敏感数据写入文件 / HTTP 外发)
  4. 可疑输出降级到人工确认(recommendation="confirm")
  5. sanitize:用 [REDACTED] 替换敏感模式,产出可放行版本

设计原则:
  - 多层检测:正则模式匹配 + 启发式(大段重复 / 异常字符密度)
  - 严格模式:任何威胁 → safe=False
  - 非严格模式:仅 high severity 威胁 → safe=False,中低危 → confirm
  - 所有异常不外泄,捕获后返回 safe=False + detail
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 模块级预编译正则(性能优化:避免每次 judge() 重复编译)
# ---------------------------------------------------------------------------

# 注入威胁模式(prompt injection 残留 / 角色劫持 / 指令覆盖)
# 任务规范要求覆盖:ignore previous / system: / <new_instructions> /
#                 ignore all / forget previous / you are now / new role
INJECTION_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(previous|prior|above|all)\s+instructions",
    r"forget\s+(previous|prior|all)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"new\s+role\s*:",
    r"<\s*new_instructions?\s*>",
    r"system\s*:",
    r"disregard\s+(previous|all)",
    r"override\s+(system|instructions)",
)

# 数据外泄模式(HTTP URL / curl / wget / requests.* / upload / send to)
DATA_EXFIL_PATTERNS: tuple[str, ...] = (
    r"https?://[^\s\"]+",
    r"curl\s+",
    r"wget\s+",
    r"requests\.(get|post|put)",
    r"upload\s+to\s+",
    r"send\s+to\s+",
)

# 文件写入外泄模式(把敏感数据落盘)
FILE_WRITE_PATTERNS: tuple[str, ...] = (
    r"open\s*\([^)]*['\"][wa]",
    r"\.write\s*\(",
    r"with\s+open\s*\(",
    r"shutil\.(copy|move)",
    r"os\.(remove|unlink)",
)

# 编译为正则对象
_COMPILED_INJECTION: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS
)
_COMPILED_EXFIL: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in DATA_EXFIL_PATTERNS
)
_COMPILED_FILE_WRITE: tuple[re.Pattern, ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in FILE_WRITE_PATTERNS
)

# 启发式阈值
_REPEAT_THRESHOLD = 20  # 连续重复字符超过此长度视为可疑
_NONPRINT_RATIO = 0.30  # 非可打印字符占比阈值

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class JudgeVerdict:
    """裁判结论。

    Attributes:
        safe: 是否安全(可放行)
        confidence: 置信度 [0.0, 1.0],越高越确信判定
        threats: 检测到的威胁列表(每项为简短描述)
        recommendation: 处置建议 "allow" / "deny" / "confirm" / "sanitize"
        sanitized_output: sanitize 后的输出(仅 sanitize 模式产出)
        detail: 详细说明(命中模式 / 异常原因)
    """

    safe: bool
    confidence: float
    threats: list[str] = field(default_factory=list)
    recommendation: str = "allow"
    sanitized_output: str | None = None
    detail: str = ""


@dataclass
class JudgeConfig:
    """裁判配置。

    Attributes:
        enabled: 是否启用裁判(关闭时一律放行)
        strict_mode: 严格模式 — 任何威胁都 deny
        use_llm_judge: 是否用 LLM 二次审查(需注入 LLM 客户端,本模块默认 False)
        patterns_custom: 自定义正则列表(在 add_pattern 中动态追加)
    """

    enabled: bool = True
    strict_mode: bool = False
    use_llm_judge: bool = False
    patterns_custom: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 威胁严重度分级
# ---------------------------------------------------------------------------
# high:    直接 deny(注入劫持 / 数据外泄)
# medium:  非严格模式降级到 confirm(文件写入 / 启发式可疑)
# low:     仅记录,safe 不变
_SEVERITY_HIGH = "high"
_SEVERITY_MEDIUM = "medium"
_SEVERITY_LOW = "low"


class LLMJudge:
    """LLM 输出裁判。

    对所有 LLM 生成内容做二次审查:
      - judge(output, context):           审查文本输出
      - judge_tool_call(tool, params, allowed): 审查工具调用
      - sanitize(output):                 移除/转义威胁模式
      - add_pattern(pattern, category):   动态追加自定义检测模式
    """

    def __init__(self, config: JudgeConfig | None = None):
        self.config = config or JudgeConfig()
        # 自定义模式:按 category 分组存储 (category, compiled)
        self._custom_patterns: list[tuple[str, re.Pattern]] = []
        for pat in self.config.patterns_custom:
            try:
                self._custom_patterns.append(("custom", re.compile(pat, re.IGNORECASE)))
            except re.error:
                # 非法正则忽略,不阻断初始化
                pass

    # -- 核心入口:审查文本输出 -------------------------------------------

    def judge(self, output: str, context: dict | None = None) -> JudgeVerdict:
        """审查 LLM 输出文本。

        多层检测:
          1. 正则模式匹配(注入 / 外泄 / 文件写入 / 自定义)
          2. 启发式:大段重复字符 / 非可打印字符密度
          3. confidence = min(1.0, 0.4 * matches + 0.2 * heuristic_flag)

        Args:
            output: LLM 生成的文本
            context: 可选上下文(task_type / user_id 等,用于审计)

        Returns:
            JudgeVerdict:含 safe / confidence / threats / recommendation
        """
        # 关闭或空输入直接放行
        if not self.config.enabled:
            return JudgeVerdict(safe=True, confidence=1.0, recommendation="allow")
        if not output or not isinstance(output, str):
            return JudgeVerdict(safe=True, confidence=1.0, recommendation="allow")

        try:
            threats: list[str] = []
            severities: list[str] = []
            detail_parts: list[str] = []

            # 1. 注入模式匹配(高危)
            for p in _COMPILED_INJECTION:
                m = p.search(output)
                if m:
                    threats.append(f"injection: {m.group(0)}")
                    severities.append(_SEVERITY_HIGH)
                    detail_parts.append(f"injection pattern {p.pattern}")

            # 2. 数据外泄(高危)
            for p in _COMPILED_EXFIL:
                m = p.search(output)
                if m:
                    threats.append(f"data_exfil: {m.group(0)}")
                    severities.append(_SEVERITY_HIGH)
                    detail_parts.append(f"exfil pattern {p.pattern}")

            # 3. 文件写入(中危)
            for p in _COMPILED_FILE_WRITE:
                m = p.search(output)
                if m:
                    threats.append(f"file_write: {m.group(0)}")
                    severities.append(_SEVERITY_MEDIUM)
                    detail_parts.append(f"file_write pattern {p.pattern}")

            # 4. 自定义模式
            for category, p in self._custom_patterns:
                m = p.search(output)
                if m:
                    threats.append(f"{category}: {m.group(0)}")
                    severities.append(_SEVERITY_MEDIUM)
                    detail_parts.append(f"{category} pattern {p.pattern}")

            # 5. 启发式:大段重复 / 异常字符密度
            heuristic_hit = self._heuristic_check(output)
            if heuristic_hit:
                threats.append(heuristic_hit)
                severities.append(_SEVERITY_MEDIUM)
                detail_parts.append(heuristic_hit)

            # 综合评分
            high_count = severities.count(_SEVERITY_HIGH)
            medium_count = severities.count(_SEVERITY_MEDIUM)
            confidence = min(
                1.0, 0.4 * (high_count + medium_count) + 0.2 * (1 if heuristic_hit else 0)
            )

            # 判定 safe
            has_high = high_count > 0
            has_medium = medium_count > 0
            if self.config.strict_mode:
                safe = len(threats) == 0
            else:
                # 非严格模式:仅 high 威胁 unsafe,medium 降级到 confirm
                safe = not has_high

            # 处置建议
            if safe and not threats:
                recommendation = "allow"
            elif safe and has_medium and not has_high:
                # 非严格模式下仅有中危 → 建议确认
                recommendation = "confirm"
            elif not safe:
                # 严格模式或高危 → 拒绝(可改 sanitize 后放行)
                recommendation = "sanitize" if self._can_sanitize(threats) else "deny"
            else:
                recommendation = "allow"

            return JudgeVerdict(
                safe=safe,
                confidence=confidence,
                threats=threats,
                recommendation=recommendation,
                detail="; ".join(detail_parts) if detail_parts else "",
            )
        except Exception as e:
            # 任何异常不外泄,降级到安全默认(deny + 人工确认)
            return JudgeVerdict(
                safe=False,
                confidence=0.0,
                threats=[f"judge_error: {type(e).__name__}"],
                recommendation="confirm",
                detail=f"裁判异常: {e}",
            )

    # -- 工具调用审查 -----------------------------------------------------

    def judge_tool_call(
        self,
        tool_name: str,
        params: dict,
        allowed_tools: list[str],
    ) -> JudgeVerdict:
        """审查 LLM 发起的工具调用。

        检测维度:
          1. 工具是否在 allowed_tools 白名单内(fnmatch 通配)
          2. 参数是否包含可疑外发(含 URL / 文件路径 / base64 大块)
          3. 参数是否包含注入残留

        Args:
            tool_name: 待调用工具名
            params: 调用参数字典
            allowed_tools: 允许的工具列表(支持通配符)

        Returns:
            JudgeVerdict:tool 不在白名单 → deny + confirm
        """
        if not self.config.enabled:
            return JudgeVerdict(safe=True, confidence=1.0, recommendation="allow")

        try:
            import fnmatch

            threats: list[str] = []
            detail_parts: list[str] = []

            # 1. 白名单检查
            authorized = any(fnmatch.fnmatch(tool_name, pat) for pat in allowed_tools)
            if not authorized:
                threats.append(f"unauthorized_tool: {tool_name}")
                detail_parts.append(f"工具 {tool_name} 不在白名单 {allowed_tools}")
                # 未授权工具直接 deny
                return JudgeVerdict(
                    safe=False,
                    confidence=0.95,
                    threats=threats,
                    recommendation="deny",
                    detail="; ".join(detail_parts),
                )

            # 2. 参数内容审查(转字符串后跑注入/外泄模式)
            params_str = str(params)
            sub_verdict = self.judge(params_str)
            if sub_verdict.threats:
                threats.extend(sub_verdict.threats)
                detail_parts.append(f"参数可疑: {sub_verdict.detail}")

            # 参数含 base64 大块(疑似编码外发)
            if re.search(r"[A-Za-z0-9+/]{80,}={0,2}", params_str):
                threats.append("params_large_b64: 疑似 base64 编码外发")
                detail_parts.append("参数含 80+ 字符 base64 串")

            has_high = any("injection" in t or "exfil" in t or "unauthorized" in t for t in threats)
            if self.config.strict_mode:
                safe = len(threats) == 0
            else:
                safe = not has_high

            recommendation = "allow" if safe and not threats else ("confirm" if safe else "deny")

            return JudgeVerdict(
                safe=safe,
                confidence=min(1.0, 0.5 * len(threats) + 0.2),
                threats=threats,
                recommendation=recommendation,
                detail="; ".join(detail_parts),
            )
        except Exception as e:
            return JudgeVerdict(
                safe=False,
                confidence=0.0,
                threats=[f"tool_judge_error: {type(e).__name__}"],
                recommendation="confirm",
                detail=f"工具调用审查异常: {e}",
            )

    # -- sanitize ---------------------------------------------------------

    def sanitize(self, output: str) -> str:
        """移除/转义威胁模式,产出可放行版本。

        用 [REDACTED] 替换:
          - 注入模式整段匹配
          - HTTP URL
          - curl/wget/requests 命令
          - 文件写入调用
          - base64 大块

        Args:
            output: 原始 LLM 输出

        Returns:
            处理后的字符串(原始输入异常时原样返回)
        """
        if not output or not isinstance(output, str):
            return output
        try:
            sanitized = output
            for p in _COMPILED_INJECTION + _COMPILED_EXFIL + _COMPILED_FILE_WRITE:
                sanitized = p.sub("[REDACTED]", sanitized)
            # 自定义模式
            for _, p in self._custom_patterns:
                sanitized = p.sub("[REDACTED]", sanitized)
            # base64 大块
            sanitized = re.sub(r"[A-Za-z0-9+/]{80,}={0,2}", "[REDACTED]", sanitized)
            return sanitized
        except Exception:
            # 异常时原样返回(不阻断主流程)
            return output

    # -- 动态扩展模式 -----------------------------------------------------

    def add_pattern(self, pattern: str, category: str = "custom") -> None:
        """追加自定义检测模式。

        Args:
            pattern: 正则字符串
            category: 分类标签(用于威胁列表显示)
        """
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._custom_patterns.append((category, compiled))
        except re.error:
            # 非法正则忽略
            pass

    # -- 内部辅助 ---------------------------------------------------------

    def _heuristic_check(self, output: str) -> str:
        """启发式检测:大段重复字符 / 异常字符密度。

        Returns:
            命中时返回描述字符串,未命中返回空串
        """
        # 大段连续重复字符(如 "aaaaaaaaaa..." 20+ 字符)
        m = re.search(r"(.)\1{" + str(_REPEAT_THRESHOLD) + r",}", output)
        if m:
            return f"heuristic_repeat: 连续重复字符 {len(m.group(0))} 个"

        # 非可打印字符占比过高(疑似编码混淆)
        if len(output) > 0:
            non_printable = sum(1 for c in output if not c.isprintable() and c not in "\n\r\t")
            ratio = non_printable / len(output)
            if ratio > _NONPRINT_RATIO:
                return f"heuristic_nonprint: 非可打印字符占比 {ratio:.0%}"
        return ""

    def _can_sanitize(self, threats: list[str]) -> bool:
        """判断当前威胁是否可被 sanitize 处理(否则只能 deny)。

        注入劫持类无法 sanitize(语义已被破坏),数据外泄/文件写入可 sanitize。
        """
        for t in threats:
            if t.startswith("injection") or t.startswith("heuristic"):
                return False
        return True
