"""任务路由器(Phase 5.2)。

根据自然语言任务描述识别任务类型与用户意图,生成执行步骤计划。
是 Agent 调度层的"大脑":接收 TaskRequest → classify → route → list[TaskStep]。

职责:
  - match_intent:     关键词匹配意图
  - infer_task_type:  从意图 + 文件类型推断任务类型
  - classify:         识别 task_type / intents / requires_confirmation 并回填 request
  - route:            按 task_type 生成 list[TaskStep] 执行计划
  - is_high_risk:     判断是否高风险(批量删除/覆盖原文件/加密 等),需人工确认

设计:
  - 继承 BaseExpert,复用 name 抽象属性(返回 "task_router")
  - 意图识别基于关键词规则(可后续扩展为 LLM 识别)
  - 路由按 task_type 派发到步骤模板,步骤间通过 depends_on 表达串行依赖
  - 纯规划,不含实际执行逻辑(执行由后续 Executor 负责)

能力边界:
  - 意图识别仅基于关键词,不支持复杂语义理解
  - 路由步骤为模板化生成,不感知文件实际内容
  - 高风险判断基于启发式规则(批量/覆盖/删除/加密)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
from typing import Any

from fnixagent.office.base import BaseExpert
from fnixagent.tasks.dsl import (
    Intent,
    TaskRequest,
    TaskStep,
    TaskType,
)

# 表格类文件扩展名(用于 TABLE_EXTRACT 推断)
_TABLE_EXTS = {"xlsx", "xls", "csv", "xlsm"}


class TaskRouter(BaseExpert):
    """任务路由器:意图识别 + 任务类型推断 + 步骤计划生成。

    用法:
        router = TaskRouter()
        req = TaskRequest(description="把答案填入括号并统一格式", file_paths=["a.docx"])
        req = router.classify(req)      # 回填 task_type / intents / requires_confirmation
        steps = router.route(req)       # 生成执行步骤链
    """

    @property
    def name(self) -> str:
        return "task_router"

    def __init__(self) -> None:
        # 关键词 → Intent 映射表(dict 保持插入顺序,匹配时按声明顺序遍历)
        # 单个意图命中任一关键词即成立;同一描述可命中多个意图
        self._intent_rules: dict[Intent, list[str]] = {
            Intent.FILL_ANSWER: ["填答案", "答案填入", "填入括号", "括号", "填空"],
            Intent.FIX_GARBLED: ["乱码", "修复", "恢复", "decode"],
            Intent.UNIFY_FORMAT: ["格式统一", "统一格式", "字体", "字号", "加粗", "行距"],
            Intent.DELETE_NUMBER: [
                "删题号",
                "删除题号",
                "删除序号",
                "去掉编号",
                "去题号",
                "删除编号",
            ],
            Intent.EXTRACT_CONTENT: ["提取", "抽取"],
            Intent.CONVERT_FORMAT: ["转换", "转成", "to pdf", "转pdf", "导出"],
            Intent.MERGE_FILES: ["合并"],
            Intent.SPLIT_FILE: ["拆分", "分割"],
        }
        # 高风险关键词(出现即触发人工确认)
        self._risk_keywords: list[str] = ["加密", "清空", "覆盖原文件", "脱敏", "删除全部"]

    # ------------------------------------------------------------------
    # 意图识别
    # ------------------------------------------------------------------

    def match_intent(self, text: str) -> list[Intent]:
        """关键词匹配意图。

        Args:
            text: 自然语言描述

        Returns:
            匹配到的意图列表(去重保序,空列表表示无匹配)
        """
        if not text:
            return []
        lower = text.lower()
        matched: list[Intent] = []
        for intent, keywords in self._intent_rules.items():
            for kw in keywords:
                if kw.lower() in lower:
                    if intent not in matched:
                        matched.append(intent)
                    break  # 单个意图命中一个关键词即可,避免重复
        return matched

    # ------------------------------------------------------------------
    # 任务类型推断
    # ------------------------------------------------------------------

    def infer_task_type(self, intents: list[Intent], file_paths: list[str]) -> TaskType:
        """从意图 + 文件类型推断任务类型。

        优先级(从高到低):
          1. 填答案/删题号         → QUESTION_BANK(强信号)
          2. 合并/拆分             → BATCH_PROCESS
          3. 转换格式              → DOCUMENT_CONVERT
          4. 提取内容 + 表格文件   → TABLE_EXTRACT(否则 DOCUMENT_EDIT)
          5. 统一格式              → FORMAT_NORMALIZE
          6. 修复乱码              → DOCUMENT_EDIT
          7. 多文件无明确意图      → BATCH_PROCESS
          8. 单文件无明确意图      → DOCUMENT_EDIT
          9. 兜底                  → UNKNOWN
        """
        intent_set = set(intents)

        # 1. 题库处理(填答案/删题号是强信号)
        if intent_set & {Intent.FILL_ANSWER, Intent.DELETE_NUMBER}:
            return TaskType.QUESTION_BANK

        # 2. 合并/拆分 → 批量处理
        if intent_set & {Intent.MERGE_FILES, Intent.SPLIT_FILE}:
            return TaskType.BATCH_PROCESS

        # 3. 格式转换
        if Intent.CONVERT_FORMAT in intent_set:
            return TaskType.DOCUMENT_CONVERT

        # 4. 提取内容:表格文件 → TABLE_EXTRACT,否则按文档编辑处理
        if Intent.EXTRACT_CONTENT in intent_set:
            if file_paths and self._has_table_file(file_paths):
                return TaskType.TABLE_EXTRACT
            return TaskType.DOCUMENT_EDIT

        # 5. 统一格式
        if Intent.UNIFY_FORMAT in intent_set:
            return TaskType.FORMAT_NORMALIZE

        # 6. 修复乱码 → 文档编辑
        if Intent.FIX_GARBLED in intent_set:
            return TaskType.DOCUMENT_EDIT

        # 7/8. 无明确意图:按文件数量判断
        if len(file_paths) > 1:
            return TaskType.BATCH_PROCESS
        if len(file_paths) == 1:
            return TaskType.DOCUMENT_EDIT

        # 9. 兜底
        return TaskType.UNKNOWN

    @staticmethod
    def _has_table_file(file_paths: list[str]) -> bool:
        """判断文件列表中是否含表格类文件(xlsx/csv 等)。"""
        for p in file_paths:
            ext = os.path.splitext(p)[1].lstrip(".").lower()
            if ext in _TABLE_EXTS:
                return True
        return False

    # ------------------------------------------------------------------
    # 分类(意图识别 + 类型推断 + 高风险标记)
    # ------------------------------------------------------------------

    def classify(self, request: TaskRequest) -> TaskRequest:
        """识别任务类型和意图,原地回填 request 并返回。

        会填充以下字段:
          - request.intents               ← match_intent(description)
          - request.task_type             ← infer_task_type(intents, file_paths)
          - request.requires_confirmation ← is_high_risk(request) 为 True 时置 True

        Args:
            request: 任务请求(description 已填)

        Returns:
            回填后的 request(同一对象,便于链式调用)
        """
        # 意图识别
        request.intents = self.match_intent(request.description)
        # 任务类型推断
        request.task_type = self.infer_task_type(request.intents, request.file_paths)
        # 高风险标记(基于已识别的 intents / task_type 判断)
        if self.is_high_risk(request):
            request.requires_confirmation = True
        return request

    # ------------------------------------------------------------------
    # 高风险判断
    # ------------------------------------------------------------------

    def is_high_risk(self, request: TaskRequest) -> bool:
        """判断是否高风险任务(需人工确认)。

        判定规则(满足任一即高风险):
          1. 批量删除题号(DELETE_NUMBER + 文件数 > 3)
          2. 输出路径覆盖原文件(output_path 与某 file_path 相同)
          3. 描述含高风险关键词(加密/清空/覆盖原文件/脱敏/删除全部)
          4. 紧急优先级(priority>=2)+ 破坏性意图(删题号/修复乱码)
          5. 批量处理且文件数 > 10

        Returns:
            True 表示高风险,应触发人工确认
        """
        intent_set = set(request.intents)
        desc = request.description or ""

        # 1. 批量删除题号
        if Intent.DELETE_NUMBER in intent_set and len(request.file_paths) > 3:
            return True

        # 2. 输出路径覆盖原文件
        if request.output_path and request.file_paths:
            out_real = os.path.realpath(request.output_path)
            for fp in request.file_paths:
                if os.path.realpath(fp) == out_real:
                    return True

        # 3. 高风险关键词
        lower_desc = desc.lower()
        for kw in self._risk_keywords:
            if kw in lower_desc:
                return True

        # 4. 紧急优先级 + 破坏性意图
        if request.priority >= 2 and (intent_set & {Intent.DELETE_NUMBER, Intent.FIX_GARBLED}):
            return True

        # 5. 批量处理且文件数过多
        if request.task_type == TaskType.BATCH_PROCESS and len(request.file_paths) > 10:
            return True

        return False

    # ------------------------------------------------------------------
    # 路由(生成执行步骤)
    # ------------------------------------------------------------------

    def route(self, request: TaskRequest) -> list[TaskStep]:
        """根据任务类型生成执行步骤计划。

        Args:
            request: 已 classify 的任务请求(至少 task_type 已填充)

        Returns:
            TaskStep 列表(按依赖顺序排列,每步依赖前一步)
        """
        # 公共参数:所有步骤可访问的文件/输出/任务信息
        common: dict[str, Any] = {
            "task_id": request.task_id,
            "file_paths": list(request.file_paths),
            "output_path": request.output_path,
            "params": dict(request.params),
            "intents": [i.value for i in request.intents],
        }

        task_type = request.task_type
        if task_type == TaskType.QUESTION_BANK:
            return self._route_question_bank(request, common)
        if task_type == TaskType.FORMAT_NORMALIZE:
            return self._route_format_normalize(common)
        if task_type == TaskType.DOCUMENT_EDIT:
            return self._route_document_edit(common)
        if task_type == TaskType.TABLE_EXTRACT:
            return self._route_table_extract(common)
        if task_type == TaskType.DOCUMENT_CONVERT:
            return self._route_document_convert(common)
        if task_type == TaskType.BATCH_PROCESS:
            return self._route_batch_process(request, common)
        if task_type == TaskType.DOCUMENT_REVIEW:
            return self._route_document_review(common)
        if task_type == TaskType.DATA_ANALYSIS:
            return self._route_data_analysis(common)
        if task_type == TaskType.REPORT_GENERATE:
            return self._route_report_generate(common)

        # UNKNOWN:最小步骤(解析 + 校验)
        return self._build_steps(
            common,
            [
                ("parse", "解析文档", "parser"),
                ("validate", "校验结果", "validator"),
            ],
        )

    # ------------------------------------------------------------------
    # 各任务类型的步骤模板
    # ------------------------------------------------------------------

    def _route_question_bank(self, request: TaskRequest, common: dict[str, Any]) -> list[TaskStep]:
        """题库处理:解析 → 检测乱码 → 解析答案 → 填答案 → [删题号] → [统一格式] → 校验。

        delete_number / normalize_format 根据意图条件包含,避免无意义步骤。
        """
        intent_set = set(request.intents)
        spec: list[tuple[str, str, str]] = [
            ("parse", "解析文档", "parser"),
            ("detect_garbled", "检测乱码", "garbled_detector"),
            ("resolve_answer", "解析答案", "answer_resolver"),
            ("fill_answer", "填入答案", "answer_filler"),
        ]
        if Intent.DELETE_NUMBER in intent_set:
            spec.append(("delete_number", "删除题号", "number_deleter"))
        if Intent.UNIFY_FORMAT in intent_set:
            spec.append(("normalize_format", "统一格式", "format_normalizer"))
        spec.append(("validate", "校验结果", "validator"))
        return self._build_steps(common, spec)

    def _route_format_normalize(self, common: dict[str, Any]) -> list[TaskStep]:
        """格式统一:解析 → 统一格式 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析文档", "parser"),
                ("normalize_format", "统一格式", "format_normalizer"),
                ("validate", "校验结果", "validator"),
            ],
        )

    def _route_document_edit(self, common: dict[str, Any]) -> list[TaskStep]:
        """文档编辑:解析 → 编辑 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析文档", "parser"),
                ("edit", "编辑文档", "run_editor"),
                ("validate", "校验结果", "validator"),
            ],
        )

    def _route_table_extract(self, common: dict[str, Any]) -> list[TaskStep]:
        """表格抽取:解析 → 抽取表格 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析文档", "parser"),
                ("extract_table", "抽取表格", "table_extractor"),
                ("validate", "校验结果", "validator"),
            ],
        )

    def _route_document_convert(self, common: dict[str, Any]) -> list[TaskStep]:
        """格式转换:解析 → 转换 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析文档", "parser"),
                ("convert", "格式转换", "converter"),
                ("validate", "校验结果", "validator"),
            ],
        )

    def _route_batch_process(self, request: TaskRequest, common: dict[str, Any]) -> list[TaskStep]:
        """批量处理:按意图选择 合并/拆分/逐文件处理,均以解析开头、校验结尾。

        以单步聚合形式表达(实际执行器内部循环),保持步骤计划简洁。
        """
        if Intent.MERGE_FILES in request.intents:
            spec: list[tuple[str, str, str]] = [
                ("parse_all", "解析全部文件", "parser"),
                ("merge", "合并文件", "file_merger"),
                ("validate", "校验结果", "validator"),
            ]
        elif Intent.SPLIT_FILE in request.intents:
            spec = [
                ("parse", "解析文档", "parser"),
                ("split", "拆分文件", "file_splitter"),
                ("validate", "校验结果", "validator"),
            ]
        else:
            spec = [
                ("parse_all", "解析全部文件", "parser"),
                ("process_each", "逐文件处理", "batch_processor"),
                ("validate", "校验结果", "validator"),
            ]
        return self._build_steps(common, spec)

    def _route_document_review(self, common: dict[str, Any]) -> list[TaskStep]:
        """文档审查:解析 → 审查 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析文档", "parser"),
                ("review", "文档审查", "document_reviewer"),
                ("validate", "校验结果", "validator"),
            ],
        )

    def _route_data_analysis(self, common: dict[str, Any]) -> list[TaskStep]:
        """数据分析:解析 → 分析 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析数据", "parser"),
                ("analyze", "数据分析", "data_analyzer"),
                ("validate", "校验结果", "validator"),
            ],
        )

    def _route_report_generate(self, common: dict[str, Any]) -> list[TaskStep]:
        """报告生成:解析 → 分析 → 生成报告 → 校验。"""
        return self._build_steps(
            common,
            [
                ("parse", "解析数据", "parser"),
                ("analyze", "数据分析", "data_analyzer"),
                ("generate_report", "生成报告", "report_generator"),
                ("validate", "校验结果", "validator"),
            ],
        )

    # ------------------------------------------------------------------
    # 步骤构建工具
    # ------------------------------------------------------------------

    @staticmethod
    def _build_steps(
        common: dict[str, Any],
        spec: list[tuple[str, str, str]],
    ) -> list[TaskStep]:
        """按 (key, name, handler) 列表构建串行步骤链。

        每步依赖前一步(首步无依赖),step_id 形如 "s1"/"s2"。
        common 参数合并进每个步骤的 params,key 字段标识步骤语义。
        """
        steps: list[TaskStep] = []
        prev_id: str | None = None
        for idx, (key, name, handler) in enumerate(spec, start=1):
            step_id = f"s{idx}"
            depends = [prev_id] if prev_id else []
            steps.append(
                TaskStep(
                    step_id=step_id,
                    name=name,
                    handler=handler,
                    params={**common, "key": key},
                    depends_on=depends,
                )
            )
            prev_id = step_id
        return steps
