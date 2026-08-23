"""FnixForge — 把第三方 Agent 放进熔炉：Benchmark 测评 → 诊断 → 自动修复 → 复测闭环。

定位（区别于既有 FCS 自测体系）:
  - FCS (`core/code/benchmark`): 检验 FnixAgent 自身的写码能力。
  - Forge (`core/forge`): 以用户目录中的 *外部 Agent 项目* 为被测对象（SUT, system under test），
    通过专业 benchmark 驱动它、暴露能力缺陷，再用 FnixAgent 自身的写码与诊断能力
    修复其代码，反复迭代直到达到生产级通过率。

模块:
  spec      — ForgeTask 任务 schema（JSON 可序列化）
  adapters  — 被测 Agent 驱动适配器（cli / http / subprocess-fn）
  probe     — 自动探测目标项目的调用方式，生成适配器配置建议
  checks    — 确定性校验函数（文件 / 正则 / JSON / 命令 / stdout / 安全边界）
  runner    — 单题沙箱执行 + 轨迹采集
  scorer    — 任务级与套件级评分、能力矩阵
  diagnose  — 失败聚类 + 根因定位上下文构建（供修复用）
  fixer     — git 守卫下用 FnixAgent 代码能力修复目标项目，回归即回滚
  loop      — test → diagnose → fix → re-test 编排器（NDJSON 事件流）
  report    — JSON + HTML 能力矩阵报告
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.forge.adapters import AdapterConfig, CallableAdapter, CliAdapter, HttpAdapter, TargetResponse, make_adapter
from fnixagent.core.forge.loop import ForgeLoop, ForgeLoopResult, ndjson_sink
from fnixagent.core.forge.probe import ProbeResult, probe_target, propose_adapter_config
from fnixagent.core.forge.report import write_html_report, write_json_report
from fnixagent.core.forge.runner import ForgeRunner, list_suites, locate_suite
from fnixagent.core.forge.scorer import TaskScore, aggregate, production_readiness
from fnixagent.core.forge.spec import CAPABILITIES, ForgeCheck, ForgeTask, load_task, load_suite, validate_task

__all__ = [
    "AdapterConfig",
    "CAPABILITIES",
    "CallableAdapter",
    "CliAdapter",
    "ForgeCheck",
    "ForgeLoop",
    "ForgeLoopResult",
    "ForgeRunner",
    "ForgeTask",
    "HttpAdapter",
    "ProbeResult",
    "TargetResponse",
    "TaskScore",
    "aggregate",
    "list_suites",
    "load_suite",
    "load_task",
    "locate_suite",
    "make_adapter",
    "ndjson_sink",
    "probe_target",
    "production_readiness",
    "propose_adapter_config",
    "validate_task",
    "write_html_report",
    "write_json_report",
]
