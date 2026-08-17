"""题库/试卷处理场景(Phase 7.1)。

fnixagent 的首个落地场景,集成任务引擎全部模块,端到端处理题库 docx:
  解析题目 → 检测乱码 → 恢复答案 → 风险评估 → 填入括号
  → 删题号/答案行 → 统一格式 → 验证 → 导出pending清单

典型用户场景:
  用户上传"课堂练习题汇总.docx",答案字段为 NAME...CONTENT 乱码(选项
  字母+内容拼接,丢失正确答案标记),需要:
    1. 恢复正确答案(题库→LLM→人工兜底)
    2. 答案填入题干括号
    3. 删除题号(如"11. ")保留原题题号
    4. 删除答案行(非问答题)
    5. 统一字体/字号/粗细
    6. 验证无乱码残留/答案已填/格式统一
    7. 未确认答案导出 pending.xlsx

底层依赖:
  - python-docx(解析题目)
  - RunEditor(原地编辑)
  - FormatNormalizer(格式统一)
  - GarbageDetector + AnswerResolver(答案恢复)
  - TaskValidator(验证)
  - PendingExporter(pending 清单)
  - HumanConfirmer(高风险确认)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fnixagent.office.base import BaseExpert, ExpertResult
from fnixagent.office.format_spec import FormatNormalizer
from fnixagent.office.run_editor import EditOp, RunEditor
from fnixagent.tasks.confirmer import HumanConfirmer, RiskLevel
from fnixagent.tasks.dsl import TaskResult
from fnixagent.tasks.pending_export import PendingExporter
from fnixagent.tasks.resolver import AnswerResolver, GarbageDetector
from fnixagent.tasks.validator import TaskValidator

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class QuestionInfo:
    """单道题目结构。

    Attributes:
        num: 题号(如 "11")
        qtype: 题型("单选题"/"多选题"/"填空题"/"问答题"/"其他题")
        stem: 题干文本
        options: 选项列表
        answer_raw: 原始答案(可能乱码)
        answer_resolved: 恢复的答案字母(如 "B"),未恢复为 None
        has_paren: 题干是否有空白括号
        needs_manual: 是否需人工确认
        paragraph_idx: 题干段落索引(用于定位)
        confidence: 答案置信度(0-1)
        answer_source: 答案来源("question_bank"/"llm"/"manual"/"none")
    """

    num: str = ""
    qtype: str = ""
    stem: str = ""
    options: list[str] = field(default_factory=list)
    answer_raw: str = ""
    answer_resolved: str | None = None
    has_paren: bool = False
    needs_manual: bool = False
    paragraph_idx: int = 0
    confidence: float = 0.0
    answer_source: str = "none"

@dataclass
class ProcessOptions:
    """题库处理选项。

    Attributes:
        fill_answer: 填答案入括号
        delete_number: 删除题号(如 "11. ")
        delete_answer_line: 删除答案行(非问答题)
        normalize_format: 统一格式
        delete_options_for_judge: 判断题(其他题)删选项
        output_suffix: 输出文件后缀
        export_pending: 导出pending清单
        llm_router: LLM路由器(可选)
        require_confirmation: 高风险操作是否需人工确认
    """

    fill_answer: bool = True
    delete_number: bool = True
    delete_answer_line: bool = True
    normalize_format: bool = True
    delete_options_for_judge: bool = True
    output_suffix: str = "_最终版"
    export_pending: bool = True
    llm_router: Any | None = None
    require_confirmation: bool = True

# ---------------------------------------------------------------------------
# 题目正则
# ---------------------------------------------------------------------------

# 题干: "11. 【单选题】 题干内容..."
_QSTEM_RE = re.compile(r"^(\d+)\.\s*【(单选题|多选题|填空题|问答题|其他题)】(.*)")
# 选项: "A. xxx"
_OPTION_RE = re.compile(r"^[A-Z]\.\s")
# 答案行: "【答案】xxx"
_ANSWER_LINE_RE = re.compile(r"【答案】(.*)")
# 空白括号(全角/半角)
_BLANK_PAREN_RE = re.compile(r"[（(]\s*[）)]")

# ---------------------------------------------------------------------------
# 题库处理场景
# ---------------------------------------------------------------------------

class QuestionBankScenario(BaseExpert):
    """题库/试卷处理场景(Phase 7.1)。

    端到端处理题库 docx,集成任务引擎全部模块。

    流程:
      1. 解析题目(状态机)
      2. 检测乱码(GarbageDetector)
      3. 恢复答案(AnswerResolver: 题库→LLM→人工)
      4. 风险评估(HumanConfirmer)
      5. 构造 EditOp 列表
      6. RunEditor 执行编辑
      7. FormatNormalizer 统一格式
      8. TaskValidator 验证
      9. PendingExporter 导出待确认清单

    能力边界:
      - 仅处理 .docx
      - 答案恢复依赖题库/LLM,均不可用时降级到人工
      - 高风险操作可配置是否需确认
    """

    @property
    def name(self) -> str:
        return "question_bank"

    def __init__(self, llm_router: Any | None = None) -> None:
        """初始化各模块实例。

        Args:
            llm_router: LLM 路由器(可选,传给 AnswerResolver)
        """
        self._editor = RunEditor()
        self._normalizer = FormatNormalizer()
        self._detector = GarbageDetector()
        self._resolver = AnswerResolver(llm_router=llm_router)
        self._validator = TaskValidator()
        self._pending = PendingExporter()
        self._confirmer = HumanConfirmer()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def process(
        self,
        file_path: str,
        options: ProcessOptions | None = None,
        output_path: str | None = None,
    ) -> ExpertResult:
        """端到端处理单个题库文件。

        Args:
            file_path: 输入 docx 路径
            options: 处理选项;None 用默认
            output_path: 输出路径;None 则原文件名+后缀

        Returns:
            ExpertResult(output=processed_path, metadata={
                "task_result": TaskResult,
                "validation": ValidationReport,
                "pending_path": Optional[str],
                "questions": list[QuestionInfo],
            })
        """
        start_ts = time.time()
        opts = options or ProcessOptions()
        task_id = str(uuid.uuid4())[:8]

        # 1. 路径校验
        err = self._validate_path(file_path, must_exist=True, allowed_exts=("docx",))
        if err:
            return self._failure(err)

        # 2. 输出路径
        if output_path is None:
            base, ext = os.path.splitext(file_path)
            output_path = f"{base}{opts.output_suffix}{ext}"

        # 3. 解析题目
        try:
            questions = self.parse_questions(file_path)
        except Exception as e:
            return self._failure(f"解析题目失败: {e}")

        if not questions:
            return self._failure("未解析到任何题目,请检查文件格式")

        # 4. 检测乱码 + 恢复答案
        questions, pending_items = self.resolve_answers(questions, task_id)

        # 5. 风险评估
        ops = self.build_edit_ops(questions, opts)
        risk = self._assess_risk(ops, file_path, output_path)

        if opts.require_confirmation and self._confirmer.should_confirm(risk):
            # 高风险:不直接执行,返回需确认
            conf_req = self._confirmer.request_confirmation(
                task_id=task_id,
                action_desc=f"题库处理: {len(ops)} 个编辑操作",
                affected_files=[file_path, output_path],
                risk_level=risk,
                estimated_impact=f"修改 {len(questions)} 道题",
            )
            return self._failure(
                f"操作风险等级 {risk.value},需人工确认(request_id={conf_req.request_id})",
                task_id=task_id,
                risk_level=risk.value,
                confirmation_request=conf_req,
            )

        # 6. 执行编辑
        try:
            edit_result = self._editor.edit_word(file_path, ops, output_path=output_path)
            if not edit_result.success:
                return self._failure(
                    f"编辑失败: {edit_result.error}",
                    task_id=task_id,
                    questions=questions,
                )
        except Exception as e:
            return self._failure(f"编辑异常: {e}", task_id=task_id)

        # 7. 统一格式
        if opts.normalize_format:
            try:
                self._normalizer.normalize_word(output_path, output_path=output_path)
            except Exception:
                # 格式统一失败不中断,记录 warning
                pass

        # 8. 验证
        try:
            validation = self._validator.validate_question_bank(file_path, output_path)
        except Exception:
            validation = None

        # 9. 导出 pending 清单
        pending_path = None
        if opts.export_pending and pending_items:
            try:
                base, _ = os.path.splitext(output_path)
                pending_path = f"{base}_pending.xlsx"
                self._pending.add_items(pending_items)
                self._pending.export_excel(pending_path, task_id=task_id)
            except Exception:
                pending_path = None

        # 10. 构造 TaskResult
        duration_ms = (time.time() - start_ts) * 1000
        task_result = TaskResult(
            task_id=task_id,
            success=True,
            output_files=[output_path] + ([pending_path] if pending_path else []),
            pending_items=pending_items,
            stats={
                "question_count": len(questions),
                "resolved_count": sum(1 for q in questions if q.answer_resolved),
                "needs_manual_count": sum(1 for q in questions if q.needs_manual),
                "edit_ops": len(ops),
                "risk_level": risk.value,
            },
            duration_ms=duration_ms,
        )

        return self._success(
            output=output_path,
            task_result=task_result,
            validation=validation,
            pending_path=pending_path,
            questions=questions,
        )

    # ------------------------------------------------------------------
    # 题目解析(状态机)
    # ------------------------------------------------------------------

    def parse_questions(self, file_path: str) -> list[QuestionInfo]:
        """状态机解析题目。

        遍历 doc.paragraphs,遇 `^N. 【题型】` 开新题,收集选项,
        遇【答案】闭题。

        Args:
            file_path: docx 路径

        Returns:
            题目列表

        Raises:
            ExpertError: python-docx 不可用
        """
        docx = self._require_lib("docx")
        doc = docx.Document(file_path)

        questions: list[QuestionInfo] = []
        current: QuestionInfo | None = None

        for idx, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if not text:
                continue

            # 题干
            m = _QSTEM_RE.match(text)
            if m:
                # 闭合上一题
                if current is not None:
                    questions.append(current)
                num, qtype, stem = m.group(1), m.group(2), m.group(3).strip()
                current = QuestionInfo(
                    num=num,
                    qtype=qtype,
                    stem=stem,
                    paragraph_idx=idx,
                    has_paren=bool(_BLANK_PAREN_RE.search(stem)),
                )
                continue

            if current is None:
                continue

            # 选项
            if _OPTION_RE.match(text):
                current.options.append(text)
                continue

            # 答案行
            am = _ANSWER_LINE_RE.search(text)
            if am:
                current.answer_raw = am.group(1).strip()
                questions.append(current)
                current = None
                continue

        # 闭合最后一题(无答案行)
        if current is not None:
            questions.append(current)

        return questions

    # ------------------------------------------------------------------
    # 答案恢复
    # ------------------------------------------------------------------

    def resolve_answers(
        self, questions: list[QuestionInfo], task_id: str
    ) -> tuple[list[QuestionInfo], list[dict]]:
        """批量恢复答案。

        对每道题:
          1. GarbageDetector 检测是否乱码
          2. 正常答案直接用
          3. 乱码且不可恢复 → AnswerResolver 多级策略
          4. needs_manual 的加入 pending

        Args:
            questions: 题目列表
            task_id: 任务ID

        Returns:
            (更新后的 questions, pending_items)
        """
        pending_items: list[dict] = []

        for q in questions:
            # 问答题/填空题:答案直接保留,不恢复
            if q.qtype in ("问答题", "填空题"):
                q.answer_resolved = q.answer_raw if q.answer_raw else None
                q.answer_source = "raw"
                q.confidence = 1.0 if q.answer_raw else 0.0
                continue

            # 无答案:跳过
            if not q.answer_raw:
                q.needs_manual = True
                continue

            # 检测乱码
            report = self._detector.detect(q.answer_raw)

            if not report.is_garbled:
                # 正常答案:提取字母
                letter = self._extract_answer_letter(q.answer_raw)
                if letter:
                    q.answer_resolved = letter
                    q.answer_source = "raw"
                    q.confidence = 1.0
                else:
                    # 无法提取字母,可能是文本答案
                    q.answer_resolved = q.answer_raw
                    q.answer_source = "raw"
                    q.confidence = 0.8
                continue

            # 乱码且不可恢复:多级策略
            if not report.recoverable:
                resolved = self._resolver.resolve(
                    question_num=q.num,
                    stem=q.stem,
                    options=q.options,
                    garbled_answer=q.answer_raw,
                )
                q.answer_resolved = resolved.answer
                q.confidence = resolved.confidence
                q.answer_source = resolved.source
                q.needs_manual = resolved.needs_manual

                if q.needs_manual:
                    pending_items.append(
                        {
                            "task_id": task_id,
                            "question_num": q.num,
                            "stem": q.stem[:100],
                            "options": q.options,
                            "garbled_answer": q.answer_raw,
                            "suggested_answer": resolved.answer,
                            "confidence": resolved.confidence,
                            "reason": f"答案来源: {resolved.source}",
                        }
                    )

        return questions, pending_items

    # ------------------------------------------------------------------
    # 构造编辑操作
    # ------------------------------------------------------------------

    def build_edit_ops(self, questions: list[QuestionInfo], opts: ProcessOptions) -> list[EditOp]:
        """根据题目和选项构造编辑操作列表。

        Args:
            questions: 题目列表
            opts: 处理选项

        Returns:
            EditOp 列表
        """
        ops: list[EditOp] = []
        # 用集合去重,避免对同一目标重复添加相同操作
        seen_delete_targets: set[str] = set()

        for q in questions:
            # 1. 填答案入括号(仅选择题且有括号且有答案)
            if opts.fill_answer and q.has_paren and q.answer_resolved:
                if q.qtype in ("单选题", "多选题", "其他题"):
                    # target 用题干前20字定位
                    target = q.stem[:20] if q.stem else f"题{q.num}"
                    ops.append(
                        EditOp(
                            op_type="fill_blank",
                            target=target,
                            value=q.answer_resolved,
                        )
                    )

            # 2. 删除题号(如 "11. ")
            if opts.delete_number:
                num_target = f"{q.num}. "
                if num_target not in seen_delete_targets:
                    seen_delete_targets.add(num_target)
                    ops.append(
                        EditOp(
                            op_type="delete",
                            target=num_target,
                        )
                    )

            # 3. 删除答案行(非问答题)
            # 用"【答案】"前缀匹配:run 可能被分割,精确匹配会失败;
            # 同一文件多个答案行,delete 操作会删除所有包含"【答案】"的段落,
            # 所以只添加一次操作即可
            if opts.delete_answer_line and q.qtype != "问答题":
                if q.answer_raw and "【答案】" not in seen_delete_targets:
                    seen_delete_targets.add("【答案】")
                    ops.append(
                        EditOp(
                            op_type="delete",
                            target="【答案】",
                        )
                    )

            # 4. 判断题(其他题)删选项
            if opts.delete_options_for_judge and q.qtype == "其他题":
                for opt in q.options:
                    if opt not in seen_delete_targets:
                        seen_delete_targets.add(opt)
                        ops.append(
                            EditOp(
                                op_type="delete",
                                target=opt,
                            )
                        )

        return ops

    # ------------------------------------------------------------------
    # 题库与 LLM 管理
    # ------------------------------------------------------------------

    def register_bank(self, entries: list[dict]) -> ExpertResult:
        """注册题库(透传给 AnswerResolver)。

        Args:
            entries: 题库条目列表,每条含 year/stem/answer

        Returns:
            ExpertResult
        """
        return self._resolver.register_question_bank(entries)

    def set_llm_router(self, router: Any) -> None:
        """设置 LLM 路由器。

        Args:
            router: LLM 路由器实例
        """
        self._resolver.set_llm_router(router)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _assess_risk(self, ops: list[EditOp], input_path: str, output_path: str) -> RiskLevel:
        """评估操作风险等级。

        Args:
            ops: 编辑操作列表
            input_path: 输入路径
            output_path: 输出路径

        Returns:
            RiskLevel
        """
        # 覆盖原文件 → HIGH
        if os.path.realpath(input_path) == os.path.realpath(output_path):
            return RiskLevel.HIGH

        # 大量删除操作 → MEDIUM
        delete_count = sum(1 for op in ops if op.op_type == "delete")
        if delete_count > 50:
            return RiskLevel.HIGH
        if delete_count > 10:
            return RiskLevel.MEDIUM

        # 默认 LOW(写副本)
        return RiskLevel.LOW

    @staticmethod
    def _extract_answer_letter(text: str) -> str | None:
        """从答案文本提取字母(如 "（B）" → "B")。

        Args:
            text: 答案文本

        Returns:
            答案字母;无法提取返回 None
        """
        if not text:
            return None
        # 匹配括号内的字母
        m = re.search(r"[（(]\s*([A-Z]+)\s*[）)]", text)
        if m:
            return m.group(1)
        # 匹配单个大写字母
        m = re.search(r"\b([A-Z])\b", text)
        if m:
            return m.group(1)
        return None
