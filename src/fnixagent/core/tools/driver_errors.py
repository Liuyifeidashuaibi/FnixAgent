"""驱动故障分类（GUI_DRIVER_ROADMAP.md Phase 3 的地基，Phase 2 先接入字段）。

依据 arXiv 2606.01416《Self-Healing Agentic Orchestrators》：
在 9000 次注入故障的执行中，静态工作流 70.1%、纯重试 94.5%、全量重规划 93.8%，
而**先分类再定向恢复**达到 98.8%，并把静默失败从 13.2-17.6% 压到 0%。

结论是：**分类本身就有价值**，不是"多试几次"能替代的。所以每一个动作的失败
都必须带上可分类的标签，而不是抛一个笼统异常。

七类：
  F1 超时          —— 动作/工具超时
  F2 参数错误      —— 参数缺失、类型错、模式不匹配
  F3 输出格式错误  —— 返回值无法解析
  F4 工具选择错误  —— 目标不可操作/不存在，该换工具或换目标
  F5 上下文过期    —— ref 失效、页面已重渲染，需重新快照
  F6 证据矛盾      —— 多个信号互相冲突，需重规划
  F7 控制循环      —— 原地打转，需终止并上报
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

F1_TIMEOUT = "F1"
F2_ARGUMENT = "F2"
# F3 来自论文那七类，编排层是通用的，但**浏览器路径当前不产生**：classify 的
# 关键词规则里没有任何一条指向 F3（输出格式错发生在模型解析工具结果那一层，
# 不在这条链路上）。保留分类与阶梯是为了编排层不被绑死在浏览器上——但别把
# 它算进"F1-F8 都有定向恢复"的成绩里，那一级是空的。
F3_OUTPUT = "F3"
F4_TOOL_CHOICE = "F4"
F5_STALE_CONTEXT = "F5"
F6_CONTRADICTION = "F6"
F7_CONTROL_LOOP = "F7"
# F8 是被脏页面基线逼出来的，不在论文那七类里。
#
# 原本"被遮挡 / 不可见 / 不稳定"和"目标选错"一起归在 F4，恢复动作就一律是
# "换目标"。实测（dirty_baseline 的 d05）后果是：指令加购 A，A 的按钮被固定
# 顶栏压住点不动，自愈换成了另一个同名的"加入购物车"，于是加购了 B——驱动层
# 一句错都没报，任务被判成功。**够不着 ≠ 选错了**：换目标是在替用户改意图。
F8_UNREACHABLE = "F8"

LABELS = {
    F1_TIMEOUT: "超时",
    F2_ARGUMENT: "参数错误",
    F3_OUTPUT: "输出格式错误",
    F4_TOOL_CHOICE: "工具选择错误",
    F5_STALE_CONTEXT: "上下文过期",
    F6_CONTRADICTION: "证据矛盾",
    F7_CONTROL_LOOP: "控制循环",
    F8_UNREACHABLE: "目标不可达",
}

# 各类对应的建议恢复动作（Phase 3 编排层消费）
RECOVERY_HINT = {
    F1_TIMEOUT: "指数退避重试",
    F2_ARGUMENT: "本地修正参数后重试（不消耗模型）",
    F3_OUTPUT: "带 schema 重问",
    F4_TOOL_CHOICE: "更换工具或目标（如 click_text → click ref）",
    F5_STALE_CONTEXT: "重新获取快照后再决策",
    F6_CONTRADICTION: "重新规划",
    F7_CONTROL_LOOP: "终止并上报用户",
    F8_UNREACHABLE: "先解除遮挡（滚动到视口居中）再重试同一个目标，不换目标",
}

# 关键词 → 故障类。**顺序敏感**，必须把更具体的放前面。
#
# 一个必须踩过的坑：Playwright 找不到元素时抛的是
# `Timeout 8000ms exceeded. waiting for get_by_text(...)`，
# 字面上是 timeout，实质是"目标不对"——若按超时分类，编排层会傻等重试，
# 而正确动作是换目标或换工具（F4）。所以 F4 的匹配必须排在 F1 之前。
_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    # F5：上下文过期（ref 失效、节点已脱离文档）
    (("stale", "detached", "context was destroyed", "已失效"), F5_STALE_CONTEXT),
    # F8：目标存在但**够不着**。与 F4 的区别：F4 是"这个目标不对"，F8 是
    # "这个目标对，但现在点不到"。两者恢复动作完全相反，必须分开。
    # F8 排在 F4 前面——"not visible"/"not stable" 这类措辞两边都可能命中，
    # 但它们是可达性问题，先按 F8 判定。
    (
        (
            "intercepts pointer events", "not stable", "not visible",
            "outside of the viewport", "element is not enabled",
            "被遮挡", "不可达",
        ),
        F8_UNREACHABLE,
    ),
    # F4：目标不对（找不到 / 匹配歧义）
    (
        (
            "no element found", "could not find", "strict mode violation",
            "unable to find", "not found", "waiting for", "locator", "get_by",
            "未找到", "不存在", "没有找到",
        ),
        F4_TOOL_CHOICE,
    ),
    # F1：超时与网络
    (("timeout", "timed out", "net::err_", "navigation failed"), F1_TIMEOUT),
    # F2：参数/模式
    (("must be", "cannot be empty", "invalid", "expected", "unknown"), F2_ARGUMENT),
)


def classify(exc: BaseException | None, hint: str = "") -> str:
    """把异常归到 F1-F8。无法判定返回空串。

    `hint` 用于补充异常消息之外的上下文（例如调用方已知这是参数问题）。
    """
    if exc is None:
        return ""
    # ref 失效是明确可判定的一类，优先于文本匹配
    if type(exc).__name__ == "RefStaleError":
        return F5_STALE_CONTEXT
    if isinstance(exc, ValueError):
        # 我们自己抛的参数校验都是 ValueError
        if not _looks_like_element_problem(str(exc)):
            return F2_ARGUMENT
    text = f"{exc} {hint}".lower()
    for keys, code in _RULES:
        if any(k in text for k in keys):
            return code
    return ""


def _looks_like_element_problem(msg: str) -> bool:
    m = msg.lower()
    return any(k in m for k in ("no element", "not found", "could not find", "未找到"))


def describe(code: str) -> str:
    """给日志/前端用的可读描述。"""
    if not code:
        return ""
    return f"{code} {LABELS.get(code, '')} → {RECOVERY_HINT.get(code, '')}"
