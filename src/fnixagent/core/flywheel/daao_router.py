"""DAAO — Difficulty-Aware Agentic Orchestration 真路由决策器（Spec 7+）。

借鉴:
  - arxiv 2509.11079 DAAO: VAE 量化 query 难度 → 动态决定 workflow depth
  - AutoAgents-ai/DAAO: 多智能体架构搜索（可学习调度大脑）
  - AMORE: Adaptive Multi-agent Orchestration with Reflective Execution
  - OpenAI Swarm handoff: 模式切换的轻量化实现

核心: 根据 (user_input, workspace_kind, work_mode, hera_hit_rate, recent_failure_rate)
估算难度, 输出 (reasoning_mode, max_steps, max_reflect_rounds, route_reason)。

不依赖额外 LLM 调用 — 纯启发式 + 规则，零延迟。

设计取舍 (对标 Aider "简单性 > 复杂性"):
  原设计含 tool_subset 字段试图筛选工具子集, 但 8 处分支全部赋空 list,
  且 work_pipeline 仅透传给前端 UI 展示, 不实际过滤工具集。
  对标 Cursor/Claude Code/Aider 均不做工具子集筛选——LLM 自己会选对工具,
  强行过滤反而可能让 LLM 拿不到需要的工具。已诚实移除该字段, 消除误导。

四维闭环核心（Spec 7+）:
  - hera_hit_rate ≥ 0.5  → 信任已有技能 → 减少 max_reflect_rounds
  - hera_hit_rate < 0.2  → 陌生任务 → 增加 max_reflect_rounds
  - recent_failure_rate ≥ 0.5 → 该类任务易失败 → 切换到 plan_execute
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RouteDecision:
    """DAAO 路由决策结果。"""

    reasoning_mode: str  # "react" / "plan_execute" / "self_reflect"
    max_steps: int
    max_reflect_rounds: int
    route_reason: str = ""
    difficulty_score: float = 0.0  # 0.0-1.0
    hera_hit_rate: float = 0.0  # 0.0-1.0
    recent_failure_rate: float = 0.0
    confidence: float = 1.0


# ── 难度信号关键词 ────────────────────────────────────────────────────

_COMPLEXITY_KEYWORDS = {
    "high": [
        "重构",
        "refactor",
        "完整实现",
        "从零",
        "from scratch",
        "全套",
        "多文件",
        "multi-file",
        "微服务",
        "microservice",
        "系统设计",
        "迁移",
        "migrate",
        "测试套件",
        "test suite",
        "全部",
        "all",
        "端到端",
        "end-to-end",
        "完整流水线",
        "full pipeline",
    ],
    "medium": [
        "实现",
        "implement",
        "添加",
        "add",
        "修改",
        "modify",
        "优化",
        "optimize",
        "设计",
        "design",
        "建站",
        "website",
        "原型",
        "prototype",
        "demo",
        "生成",
        "generate",
        "编写",
        "write",
    ],
}


def estimate_difficulty(
    user_input: str,
    workspace_kind: str,
    work_mode: str,
) -> float:
    """估算任务难度 [0.0, 1.0]。

    启发式规则:
      - 基础难度按 work_mode: ask=0.1, plan=0.5, craft=0.3
      - 长输入 +0.1~0.2（每 200 字符 +0.05，上限 +0.2）
      - 高复杂度关键词 +0.2
      - 中复杂度关键词 +0.1
      - 编码任务 +0.1
      - 调研任务 -0.1（调研类靠检索而非推理）
    """
    text = (user_input or "").lower()
    base = 0.1 if work_mode == "ask" else (0.5 if work_mode == "plan" else 0.3)

    # 长度信号
    length_bonus = min(0.2, len(text) / 200 * 0.05)

    # 关键词信号
    keyword_bonus = 0.0
    for kw in _COMPLEXITY_KEYWORDS["high"]:
        if kw in text:
            keyword_bonus = max(keyword_bonus, 0.2)
            break
    if keyword_bonus == 0.0:
        for kw in _COMPLEXITY_KEYWORDS["medium"]:
            if kw in text:
                keyword_bonus = max(keyword_bonus, 0.1)
                break

    # workspace_kind 信号
    kind_bonus = 0.1 if workspace_kind == "code" else 0.0
    if workspace_kind == "research":
        kind_bonus = -0.1

    return max(0.0, min(1.0, base + length_bonus + keyword_bonus + kind_bonus))


# ── 路由策略 ────────────────────────────────────────────────────────────


def route(
    *,
    user_input: str,
    workspace_kind: str,
    work_mode: str,
    tool_count: int = 8,
    hera_hit_rate: float = 0.0,
    recent_failure_rate: float = 0.0,
) -> RouteDecision:
    """DAAO 真路由 — 根据难度+历史命中率自适应选择执行策略。

    反馈回路（Spec 7+ 四维闭环核心）:
      - hera_hit_rate ≥ 0.5  → 信任已有技能 → 减少 max_reflect_rounds
      - hera_hit_rate < 0.2  → 陌生任务 → 增加 max_reflect_rounds
      - recent_failure_rate ≥ 0.5 → 该类任务易失败 → 切换到 plan_execute
    """
    difficulty = estimate_difficulty(user_input, workspace_kind, work_mode)
    mode = (work_mode or "craft").lower()

    # ── 基础路由（按 work_mode + workspace_kind）─────────────────────
    if mode == "ask":
        reasoning_mode = "react"
        max_steps = 5
        max_reflect_rounds = 0
        reason = "Ask 模式：少步 ReAct，专注问答，不写文件"
    elif mode == "plan":
        reasoning_mode = "plan_execute"
        max_steps = 25
        max_reflect_rounds = 2
        reason = "Plan 模式：Plan&Execute，先规划再执行"
    elif workspace_kind == "code":
        reasoning_mode = "react"
        max_steps = 16
        max_reflect_rounds = 2
        reason = f"Craft 编码任务：ReAct + {max_steps} 步上限，优先 write_file 落盘"
    elif workspace_kind == "research":
        reasoning_mode = "react"
        max_steps = 12
        max_reflect_rounds = 1
        reason = "调研任务：ReAct + 多步检索，引用可追溯"
    else:
        # 通用 craft — 按难度分级
        if difficulty >= 0.7:
            reasoning_mode = "plan_execute"
            max_steps = 25
            max_reflect_rounds = 2
            reason = f"高难度任务(diff={difficulty:.2f})：Plan&Execute + {max_steps} 步"
        elif difficulty >= 0.4:
            reasoning_mode = "react"
            max_steps = 18
            max_reflect_rounds = 2
            reason = f"中难度任务(diff={difficulty:.2f})：ReAct + {max_steps} 步"
        else:
            reasoning_mode = "react"
            max_steps = 12
            max_reflect_rounds = 1
            reason = f"轻量任务(diff={difficulty:.2f})：ReAct + {max_steps} 步"

    # ── 反馈回路调整（Spec 7+ 四维闭环）─────────────────────────────
    # 1. HERA 高命中率 → 已有可靠技能 → 减少反思次数
    if hera_hit_rate >= 0.5 and max_reflect_rounds > 0:
        old = max_reflect_rounds
        max_reflect_rounds = max(0, max_reflect_rounds - 1)
        reason += f"；HERA 命中率高({hera_hit_rate:.0%}) → 反思轮数 {old}→{max_reflect_rounds}"

    # 2. HERA 低命中率 + 高难度 → 陌生复杂任务 → 增加反思次数
    if hera_hit_rate < 0.2 and difficulty >= 0.5 and max_reflect_rounds < 3:
        old = max_reflect_rounds
        max_reflect_rounds = min(3, max_reflect_rounds + 1)
        reason += f"；HERA 命中率低({hera_hit_rate:.0%}) → 反思轮数 {old}→{max_reflect_rounds}"

    # 3. 最近失败率高 → 该类任务易失败 → 切换到 plan_execute
    if recent_failure_rate >= 0.5 and reasoning_mode != "plan_execute":
        old_mode = reasoning_mode
        reasoning_mode = "plan_execute"
        max_steps = max(max_steps, 20)
        reason += f"；最近失败率高({recent_failure_rate:.0%}) → 模式 {old_mode}→plan_execute"

    return RouteDecision(
        reasoning_mode=reasoning_mode,
        max_steps=max_steps,
        max_reflect_rounds=max_reflect_rounds,
        route_reason=reason,
        difficulty_score=difficulty,
        hera_hit_rate=hera_hit_rate,
        recent_failure_rate=recent_failure_rate,
        confidence=1.0 if hera_hit_rate > 0 else 0.7,
    )


def compute_hera_hit_rate(
    *,
    retrieved_count: int,
    requested_top_k: int = 3,
) -> float:
    """计算 HERA 命中率 = 实际召回数 / 请求 top_k。

    用于 DAAO 反馈回路: 高命中率意味着 HERA 已有该类任务的可靠技能,
    可以减少 VMAO 反思次数; 低命中率意味着陌生任务, 需要更多反思储备。
    """
    if requested_top_k <= 0:
        return 0.0
    return min(1.0, retrieved_count / requested_top_k)


def compute_recent_failure_rate(
    *,
    workspace_kind: str,
    library: Any = None,
) -> float:
    """从 HERA SkillLibrary 计算最近失败率。

    最近 20 个同 workspace_kind 的技能中, success=False 的占比。
    用于 DAAO 反馈回路: 高失败率 → 该类任务容易失败 → 切换到 plan_execute 模式。

    修复正反馈回路: 排除 source="vmao_reflection" 的条目。
    VMAO 反思是正常调试过程 (工具失败≥2 次触发), 任务最终可能成功。
    若把反思中间失败计入 failure_rate, 会形成正反馈回路:
    反思→failure_skill→failure_rate↑→DAAO 切保守模式→更多步数→
    更多失败机会→更多反思→failure_rate 进一步↑。
    只统计 source="task" 的真实任务级失败。
    """
    if library is None:
        return 0.0
    try:
        recent = [
            s
            for s in library.skills[-50:]
            if s.workspace_kind == workspace_kind
            and getattr(s, "source", "task") == "task"  # 排除 vmao_reflection
        ][-20:]
        if not recent:
            return 0.0
        failed = sum(1 for s in recent if not s.success)
        return failed / len(recent)
    except Exception:
        return 0.0


__all__ = [
    "RouteDecision",
    "compute_hera_hit_rate",
    "compute_recent_failure_rate",
    "estimate_difficulty",
    "route",
]
