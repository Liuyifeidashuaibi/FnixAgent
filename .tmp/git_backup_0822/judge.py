"""BenchForge — 任务判定器。

两级判定：
  1. 启发式判定（零成本、确定性强）：崩溃 / 空输出 / 全是报错 → 直接分类
  2. LLM 判定（语义层面）：把原始 prompt + 轨迹摘要 + 最终产物交给评审模型，
     判定成功或给出失败类型（六类之一）

后台评测默认启发式全量跑，LLM 判定对启发式难判的样本做复核。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fnixagent.bench.schema import BenchTask, FailureType, TaskRun, TaskStatus

_logger = logging.getLogger(__name__)


@dataclass
class Verdict:
    status: TaskStatus
    failure_type: str = ""     # FailureType.value
    evidence: str = ""
    method: str = "heuristic"


# 模型端基础设施错误（配额耗尽 / 鉴权失败 / 限流）——不能计入 Agent 能力失败，归为 other
# B7: 补充 HTTP 429 限流 —— qwen3.7-max 在 batch-v4 中因限流 4 条任务被误判为
# incomplete_output 能力失败，实际上应归 infra_skip 待重跑。
_INFRA_PAT = re.compile(
    r"(insufficient_quota)|(Free quota exhausted)|(invalid_api_key)"
    r"|(HTTP (401|403|404))"
    r"|(HTTP 429)|(429)|(rate limit)|(Requests rate limit exceeded)"
    r"|(too many requests)|(Too Many Requests)|(throttl)", re.I,
)

_CRASH_MARKERS = (
    "Traceback (most recent call last)", "asyncio.exceptions", "TimeoutError",
    "CancelledError", "RuntimeError", "KeyError", "AttributeError",
    "任务超时", "agent returned failure",
)

_TOOL_ERROR_PAT = re.compile(
    r"(tool.*(error|fail|exception))|(mcp.*(error|fail))|(No such file or directory)"
    r"|(Permission denied)|(command not found)", re.I,
)

_PATH_PAT = re.compile(
    r"(No such file or directory)|(not a directory)|(path.*(invalid|not found|missing))"
    r"|(FileNotFoundError)|(cannot find the path)", re.I,
)

_CONTEXT_PAT = re.compile(
    r"(我不记得|之前的(对话|内容|结果).*(丢|没|忘))|(上下文.*(丢|截断|overflow))"
    r"|(context.*(lost|truncated|overflow))|(重复(劳动|执行|生成))", re.I,
)


class Judge:
    """任务判定器。"""

    def __init__(
        self,
        llm_call: Callable[..., Any] | None = None,
        use_llm_for_ambiguous: bool = True,
        sample_llm_review: bool = False,
    ) -> None:
        """
        Args:
            llm_call:               评审模型调用函数 (async, OpenAI 兼容签名)
            use_llm_for_ambiguous:  启发式无法确定时升级到 LLM 判定
            sample_llm_review:      是否对启发式判成功的样本也做 LLM 复核（抽样审查）
        """
        self._llm = llm_call
        self._use_llm_ambiguous = use_llm_for_ambiguous
        self._sample_review = sample_llm_review

    # ------------------------------------------------------------------
    # LLM 判定
    # ------------------------------------------------------------------

    async def _llm_judge(self, task: BenchTask, run: TaskRun) -> Verdict:
        prompt = f"""你是 Agent 能力评测的评审专家。请判定以下任务执行结果。

【原始任务（原样）】
{task.prompt[:3000]}

【Agent 执行轨迹摘要】
- 总步数: {len(run.steps)}
- 工具调用: {len(run.tool_calls)} 次（失败 {sum(1 for c in run.tool_calls if not c.get('success'))} 次）
- 产出文件: {run.files_written[:20] or '无'}
- 运行错误: {(run.error or '无')[:400]}

【Agent 最终输出（截断）】
{(run.final_response or '(空)')[:2000]}

请严格按以下 JSON 输出（不要输出其他内容）:
{{
  "success": true/false,
  "failure_type": "planning_error|mcp_call_error|path_error|context_loss|requirement_misunderstanding|crash|incomplete_output|other",
  "evidence": "判定依据，一两句话"
}}
failure_type 仅在 success=false 时填写。判定标准：输出结果是否真正满足任务需求。"""
        try:
            resp = await self._llm([{"role": "user", "content": prompt}], tools=None)
            content = ""
            if isinstance(resp, dict):
                choices = resp.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content", "") or ""
            elif hasattr(resp, "content"):
                content = resp.content or ""
            payload = _extract_json(content)
            success = bool(payload.get("success"))
            if success:
                return Verdict(TaskStatus.SUCCESS,
                               evidence=str(payload.get("evidence", ""))[:300],
                               method="llm")
            ft = str(payload.get("failure_type") or "other")
            valid = {f.value for f in FailureType}
            if ft not in valid:
                ft = FailureType.OTHER.value
            return Verdict(TaskStatus.FAILURE, ft,
                           evidence=str(payload.get("evidence", ""))[:300], method="llm")
        except Exception as exc:
            _logger.warning("LLM 判定失败，退回启发式成功: %s", exc)
            return Verdict(TaskStatus.SUCCESS, method="heuristic",
                           evidence=f"LLM 判定不可用（{exc}），按启发式成功保守处理")

    # ------------------------------------------------------------------

    async def judge(self, task: BenchTask, run: TaskRun) -> Verdict:
        """对单条任务运行做判定。"""
        # 这里是同步 helper 调用，用函数级规避循环引用
        verdict = self._heuristic_inner(task, run)
        if verdict is not None:
            # 抽样复核：启发式说成功的，也可送 LLM 复核（可选）
            if self._sample_review and verdict.status == TaskStatus.SUCCESS and self._llm:
                return await self._llm_judge(task, run)
            return verdict
        if self._llm and self._use_llm_ambiguous:
            return await self._llm_judge(task, run)
        return Verdict(TaskStatus.SUCCESS, method="heuristic",
                       evidence="启发式无法确定且无 LLM 评审，保守成功")

    def _heuristic_inner(self, task: BenchTask, run: TaskRun) -> Verdict | None:
        err = run.error or ""

        # 基础设施错误最优先识别：模型配额/鉴权失败属于环境问题，不是 Agent 能力缺陷。
        # 注意：不能依赖 run.status == FAILURE —— agent 返回失败时 status 仍是 PENDING，
        # 之前因此漏判，上千条配额耗尽被误归类为 incomplete_output。
        if err and _INFRA_PAT.search(err):
            return Verdict(
                TaskStatus.INFRA_SKIP, "",
                evidence=f"基础设施错误(LLM 配额/鉴权)，待配额恢复后重跑: {err[:200]}",
                method="heuristic",
            )
        # 工具调用错误里也可能携带配额信息（中途配额耗尽）
        if run.tool_calls:
            joined = " ".join(str(c.get("output_preview", "")) for c in run.tool_calls[-3:])
            if _INFRA_PAT.search(joined):
                return Verdict(
                    TaskStatus.INFRA_SKIP, "",
                    evidence=f"工具输出含配额/鉴权错误: {joined[:200]}",
                    method="heuristic",
                )

        if run.status == TaskStatus.FAILURE and (
            any(m in err for m in _CRASH_MARKERS) or err
        ):
            return Verdict(TaskStatus.FAILURE, FailureType.CRASH.value,
                           evidence=(err[:300] or "agent 返回失败"), method="heuristic")

        # golden-match 仅用于 GAIA 式短答案（单行 ≤160 字符）；
        # SWE-bench 补丁、测试列表等长期望改用启发式/LLM 判定，避免全局误判。
        if task.expected and isinstance(task.expected, str) and task.expected.strip():
            gold_raw = task.expected.strip()
            if len(gold_raw) <= 160 and "\n" not in gold_raw:
                gold = gold_raw.lower()
                got = (run.final_response or "").strip().lower()
                if gold and gold in got:
                    return Verdict(TaskStatus.SUCCESS, method="golden-match",
                                   evidence=f"命中标准答案: {task.expected[:80]}")
                return Verdict(
                    TaskStatus.FAILURE, FailureType.REQUIREMENT_MISUNDERSTANDING.value,
                    evidence=f"期望[{task.expected[:80]}] 实际[{got[:160]}]",
                    method="golden-match",
                )

        if not (run.final_response or "").strip() and not run.files_written:
            return Verdict(TaskStatus.FAILURE, FailureType.INCOMPLETE_OUTPUT.value,
                           evidence="无最终回复且未产出任何文件", method="heuristic")

        calls = run.tool_calls
        if calls:
            failed = [c for c in calls if not c.get("success")]
            fail_ratio = len(failed) / len(calls)
            joined_err = " ".join(str(c.get("output_preview", "")) for c in failed[:5])
            if fail_ratio >= 0.5 and len(calls) >= 2:
                if _PATH_PAT.search(joined_err):
                    return Verdict(TaskStatus.FAILURE, FailureType.PATH_ERROR.value,
                                   evidence=f"工具失败率{fail_ratio:.0%}，路径错误特征",
                                   method="heuristic")
                return Verdict(TaskStatus.FAILURE, FailureType.MCP_CALL_ERROR.value,
                               evidence=f"工具失败率{fail_ratio:.0%}", method="heuristic")
            if failed and not run.files_written and _PATH_PAT.search(joined_err):
                return Verdict(TaskStatus.FAILURE, FailureType.PATH_ERROR.value,
                               evidence="路径类工具错误且无产物", method="heuristic")

        if _CONTEXT_PAT.search(run.final_response or ""):
            return Verdict(TaskStatus.FAILURE, FailureType.CONTEXT_LOSS.value,
                           evidence="最终回复出现上下文丢失特征表述", method="heuristic")

        if run.steps and len(run.steps) >= 25 and not run.files_written:
            last_actions = [s.get("action", "") for s in run.steps[-5:]]
            if len(set(last_actions)) <= 2:
                return Verdict(TaskStatus.FAILURE, FailureType.PLANNING_ERROR.value,
                               evidence="步数耗尽且陷入重复动作循环", method="heuristic")

        # 需要 LLM 进一步判定的模糊样本
        if run.files_written or len(run.final_response) > 100:
            return None if self._llm else Verdict(TaskStatus.SUCCESS, method="heuristic")
        return None


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 回复中提取 JSON 对象（容忍 markdown 围栏）。"""
    text = re.sub(r"```(?:json)?\s*|\s*```", "", text or "")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
